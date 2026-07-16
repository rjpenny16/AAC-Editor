"""Local web UI backend. Serves 127.0.0.1 only — nothing leaves the machine.

Session model: each uploaded page set gets a directory under the system temp
dir holding ``original`` (the untouched upload) and ``current`` (the state
after zero or more edits). Every edit opens a scratch working copy of
``current``, builds and validates the page there, and only replaces
``current`` when every check passes — so a failed edit can't leave the
session corrupted, and the download endpoint always serves the last good
state.
"""

import json
import os
import secrets
import shutil
import socket
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import urllib.request

from flask import Flask, jsonify, request, send_file, send_from_directory

from .. import __version__, builder, live, validate
from ..errors import PagesetError
from ..pageset import Pageset, is_sqlite_file
from . import grounding, localai, ollama

APP_ID = "aac-editor"
DEFAULT_PORT = 8765
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # page sets with media can be large
SESSION_MAX_AGE = 24 * 60 * 60  # leftover session dirs older than this are removed

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

API_TOKEN = secrets.token_urlsafe(32)
# ponytail: TD Snap exposes one UI; one lock prevents concurrent automation.
_LIVE_LOCK = threading.Lock()

_SESSION_ROOT = os.path.join(tempfile.gettempdir(), "tdsnap-editor")
_sessions = {}

# Set by the host process so endpoints can stop the server or raise the
# native window.
_runtime = {"native": False, "focus": None, "shutdown": None}


def set_native(native: bool) -> None:
    """Tell the frontend whether it is running in the native window."""
    _runtime["native"] = native


def set_focus_handler(handler) -> None:
    """Called by POST /api/focus to bring the native window to the front."""
    _runtime["focus"] = handler


def _session_dir(session_id: str) -> str:
    session = _sessions.get(session_id)
    if session is None:
        raise PagesetError("Unknown or expired session; re-upload the file.")
    return session["dir"]


def _current_path(session_id: str) -> str:
    return os.path.join(_session_dir(session_id), "current")


def _list_pages(path: str):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [
            {"id": row["Id"], "title": row["DisplayName"]}
            for row in conn.execute(
                "SELECT Id, COALESCE(NULLIF(Title, ''), 'Page ' || Id) AS "
                "DisplayName FROM Page WHERE PageType = 1 "
                "ORDER BY DisplayName COLLATE NOCASE"
            )
        ]
    finally:
        conn.close()


def _free_cells(path: str, page_id: int) -> int:
    """How many empty grid cells *page_id* has (for the parent picker)."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT pl.Id AS LayoutId, pl.PageLayoutSetting AS s, "
            "(SELECT COUNT(*) FROM ElementPlacement ep "
            " WHERE ep.PageLayoutId = pl.Id) AS used "
            "FROM PageLayout pl WHERE pl.PageId = ? "
            "ORDER BY used DESC LIMIT 1",
            (page_id,),
        ).fetchone()
        if row is None or not row["s"]:
            return 0
        from ..schema import parse_grid

        cols, rows = parse_grid(row["s"])
        return max(0, cols * rows - row["used"])
    finally:
        conn.close()


def _new_session_dir() -> tuple[str, str]:
    session_id = secrets.token_urlsafe(16)
    session_dir = os.path.join(_SESSION_ROOT, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_id, session_dir


def _register_session(session_id: str, session_dir: str, filename: str) -> dict:
    """Validate the uploaded/opened file and activate the session.

    Any failure removes the session directory so rejected files don't pile up
    in the temp dir until the 24-hour cleanup.
    """
    original = os.path.join(session_dir, "original")
    try:
        if not is_sqlite_file(original):
            raise PagesetError(
                f"{filename!r} is not a TD Snap page set (.sps/.spb export)."
            )
        probe = Pageset(original, working_copy=os.path.join(session_dir, "probe"))
        try:
            schema_version = probe.schema_version
            cols, rows = probe.grid_dimension()
            baseline = validate.validate_pageset(probe.conn)
        finally:
            probe.close()
        os.replace(
            os.path.join(session_dir, "probe"), os.path.join(session_dir, "current")
        )
    except Exception:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise

    _sessions[session_id] = {
        "dir": session_dir,
        "filename": filename,
        "baseline_warnings": baseline["warnings"],
        "edits": 0,
        "lock": threading.Lock(),  # one edit at a time per session
    }
    return {
        "ok": True,
        "session_id": session_id,
        "filename": filename,
        "schema_version": schema_version,
        "grid": {"cols": cols, "rows": rows},
        "pages": _list_pages(os.path.join(session_dir, "current")),
        "baseline_problems": baseline["problems"],
    }


def open_path(path: str) -> dict:
    """Open a page-set file from disk into a fresh session."""
    if not os.path.isfile(path):
        raise PagesetError(f"{path!r} does not exist or is not a file.")
    session_id, session_dir = _new_session_dir()
    shutil.copyfile(path, os.path.join(session_dir, "original"))
    return _register_session(session_id, session_dir, os.path.basename(path))


def edited_filename(session_id: str) -> str:
    """Suggested name for the edited copy."""
    session = _sessions.get(session_id)
    if session is None:
        raise PagesetError("Unknown or expired session; re-upload the file.")
    base, ext = os.path.splitext(session["filename"])
    return f"{base}.edited{ext or '.sps'}"


def save_current_as(session_id: str, dest_path: str) -> None:
    """Write the current session copy to *dest_path*."""
    current = _current_path(session_id)
    if not os.path.exists(current):
        raise PagesetError("Nothing to save yet; re-upload the file.")
    shutil.copyfile(current, dest_path)


@app.errorhandler(PagesetError)
def _pageset_error(exc):
    return jsonify({"ok": False, "error": str(exc)}), 400


# Loopback names a request to this local server may legitimately carry. A
# request with any other Host reached us through DNS rebinding (a hostile
# domain resolving to 127.0.0.1), which would make the attacker's page
# same-origin with this server and able to read the API token.
_ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "::1"}


@app.before_request
def _require_loopback_host():
    try:
        hostname = urllib.parse.urlsplit(f"//{request.host}").hostname or ""
    except ValueError:
        hostname = ""
    if hostname.lower() not in _ALLOWED_HOSTNAMES:
        return jsonify(
            {"ok": False,
             "error": "This local app only answers to 127.0.0.1/localhost."}
        ), 403
    return None


@app.before_request
def _require_api_token():
    if request.method != "POST" or request.path in {
        "/api/focus", "/api/tdsnap/page", "/api/tdsnap/edit-plan"
    }:
        return None
    if request.headers.get("X-TDSnap-Token") != API_TOKEN:
        return jsonify(
            {"ok": False, "error": "Missing or invalid API token; reload the page."}
        ), 403
    return None


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "app": APP_ID, "version": __version__})


@app.get("/api/config")
def config():
    return jsonify(
        {"ok": True, "token": API_TOKEN, "native": _runtime["native"], "version": __version__}
    )


@app.post("/api/quit")
def quit_app():
    shutdown = _runtime.get("shutdown")
    if shutdown is None:
        raise PagesetError("The app wasn't started in a stoppable mode.")
    threading.Timer(0.3, shutdown).start()
    return jsonify({"ok": True})


@app.post("/api/focus")
def focus():
    handler = _runtime.get("focus")
    if handler is not None:
        handler()
    return jsonify({"ok": True, "focused": handler is not None})


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/tdsnap/status")
def live_status():
    with _LIVE_LOCK:
        status = live.status(False) if request.headers.get("X-TDSnap-Brief") == "1" else live.status()
    return jsonify({"ok": True, **status})


@app.post("/api/tdsnap/launch")
def live_launch():
    with _LIVE_LOCK:
        return jsonify({"ok": True, **live.launch()})


@app.get("/api/tdsnap/page-layout")
def live_page_layout():
    with _LIVE_LOCK:
        return jsonify({"ok": True, **live.inspect_page(request.args.get("page"))})


@app.post("/api/tdsnap/edit-plan")
def live_execute_plan():
    if request.headers.get("X-TDSnap-Editor") != "1":
        raise PagesetError("Direct TD Snap edits must start in this app.")
    payload = request.get_json(force=True, silent=True) or {}
    if payload.get("operation") != "add_to_existing_page":
        raise PagesetError("This edit operation is not supported yet.")
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise PagesetError("'items' must be a list of words.")
    with _LIVE_LOCK:
        report = live.add_to_existing_page(
            payload.get("page", ""), items, payload.get("fingerprint")
        )
    return jsonify({"ok": True, **report})


@app.post("/api/tdsnap/page")
def live_add_page():
    # Custom header forces a cross-origin preflight, preventing arbitrary web
    # pages from driving this localhost-only mutation endpoint.
    if request.headers.get("X-TDSnap-Editor") != "1":
        raise PagesetError("Direct TD Snap edits must start in this app.")
    payload = request.get_json(force=True, silent=True) or {}
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise PagesetError("'items' must be a list of words.")
    with _LIVE_LOCK:
        report = live.add_topic_page(
            payload.get("title", ""),
            items,
            payload.get("parent", live.DEFAULT_PARENT),
        )
    report["warnings"] = [warning for warning in report["warnings"] if warning]
    return jsonify({"ok": True, **report})


@app.post("/api/pageset")
def upload_pageset():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise PagesetError("No file was uploaded.")

    session_id, session_dir = _new_session_dir()
    upload.save(os.path.join(session_dir, "original"))
    return jsonify(_register_session(session_id, session_dir, upload.filename))


@app.get("/api/pageset/<session_id>/pages")
def pages(session_id):
    current = _current_path(session_id)
    return jsonify({"ok": True, "pages": _list_pages(current)})


@app.get("/api/pageset/<session_id>/page/<int:page_id>/capacity")
def capacity(session_id, page_id):
    current = _current_path(session_id)
    return jsonify({"ok": True, "free_cells": _free_cells(current, page_id)})


@app.post("/api/pageset/<session_id>/page")
def add_page(session_id):
    payload = request.get_json(force=True, silent=True) or {}
    title = payload.get("title", "")
    items = payload.get("items", [])
    parent_page_id = payload.get("parent_page_id")
    if not isinstance(items, list):
        raise PagesetError("'items' must be a list of words.")
    if parent_page_id is not None:
        parent_page_id = int(parent_page_id)

    session = _sessions.get(session_id)
    if session is None:
        raise PagesetError("Unknown or expired session; re-upload the file.")
    current = _current_path(session_id)
    scratch = os.path.join(session["dir"], "scratch")

    # One edit at a time per session: concurrent requests would share the
    # same scratch working copy and corrupt each other.
    with session["lock"], Pageset(current, working_copy=scratch, cleanup=True) as ps:
        baseline = validate.validate_pageset(ps.conn)
        before = validate.table_snapshot(ps.conn)
        report = builder.add_category_page(ps, title, items, parent_page_id)
        after = validate.table_snapshot(ps.conn)

        result = validate.validate_pageset(ps.conn)
        problems = (
            validate.check_roundtrip(before, after)
            + validate.validate_new_page(ps.conn, report)
            + result["problems"]
            + validate.new_warnings(baseline, result)
        )
        checks = {
            "sqlite_integrity": "pass",
            "linkage_chains": "pass" if not problems else "fail",
            "roundtrip_diff": "pass"
            if not validate.check_roundtrip(before, after)
            else "fail",
        }
        if problems:
            return jsonify(
                {"ok": False, "error": "Validation failed; nothing was saved.",
                 "problems": problems, "checks": checks}
            ), 422
        ps.save_as(current)
        session["edits"] += 1
    return jsonify(
        {
            "ok": True,
            "page_id": report["page_id"],
            "page_unique_id": report["page_unique_id"],
            "buttons": len(report["button_ids"]),
            "nav_button_id": report["nav_button_id"],
            "grid": {"cols": report["grid"][0], "rows": report["grid"][1]},
            "checks": checks,
            "edits": session["edits"],
        }
    )


@app.get("/api/pageset/<session_id>/download")
def download(session_id):
    session = _sessions.get(session_id)
    current = _current_path(session_id)
    if session is None or not os.path.exists(current):
        raise PagesetError("Nothing to download; re-upload the file.")
    base, ext = os.path.splitext(session["filename"])
    return send_file(
        current,
        as_attachment=True,
        download_name=f"{base}.edited{ext or '.sps'}",
        mimetype="application/octet-stream",
    )


@app.get("/api/ai/status")
def ai_status():
    """Which suggestion engines are usable right now."""
    host = request.args.get("host", ollama.DEFAULT_HOST)
    return jsonify(
        {
            "ollama": ollama.status(host),
            "local": {
                "engine_available": localai.engine_available(),
                "downloaded": localai.is_downloaded(),
                "download": localai.download_state(),
                "model": {
                    "name": localai.MODEL_NAME,
                    "license": localai.MODEL_LICENSE,
                    "size": localai.MODEL_SIZE_HINT,
                },
            },
        }
    )


@app.post("/api/ai/download")
def ai_download():
    """One-time download of the built-in model (user-initiated)."""
    if not localai.engine_available():
        return jsonify(
            {"ok": False,
             "error": "This install doesn't include the built-in AI engine; "
                      "use Ollama instead or install llama-cpp-python."}
        ), 400
    return jsonify({"ok": True, "download": localai.start_download()})


@app.get("/api/ai/download")
def ai_download_state():
    return jsonify({"ok": True, "download": localai.download_state()})


@app.post("/api/ai/words")
def ai_words():
    """Generate suggestions with whichever engine is ready.

    Preference order: a reachable Ollama server (user's choice of model),
    then the built-in downloaded model.
    """
    payload = request.get_json(force=True, silent=True) or {}
    existing = payload.get("existing", [])
    if not isinstance(existing, list):
        raise PagesetError("'existing' must be a list of button labels.")
    category = payload.get("category", "")
    args = {
        "category": category,
        "count": payload.get("count", 10),
        "kind": payload.get("kind", "words"),
        "function": payload.get("function"),
        "existing": [str(label).strip()[:80] for label in existing[:100]
                     if str(label).strip()],
    }
    host = payload.get("host", ollama.DEFAULT_HOST)
    ollama_state = ollama.status(host)
    # An Ollama server with no models can't generate anything; fall through
    # to the built-in engine instead of failing with "model not found".
    if ollama_state["reachable"] and ollama_state["models"]:
        engine, generate = "ollama", lambda: ollama.generate_words(
            host=host, model=payload.get("model", ollama.DEFAULT_MODEL), **args
        )
    elif localai.engine_available() and localai.is_downloaded():
        engine, generate = "local", lambda: localai.generate_words(**args)
    else:
        return jsonify(
            {"ok": False, "words": [],
             "error": "No AI engine is ready yet — download the built-in "
                      "model below, or start Ollama."}
        ), 400
    # Only look up reference facts once we know a model will actually run. Real
    # facts about the title stop a small model naming the wrong thing (e.g.
    # cartoon characters for "Roblox characters"). Best-effort: "" if offline.
    args["reference"] = grounding.reference_text(category)
    words, error = generate()
    if error:
        return jsonify({"ok": False, "error": error, "words": [],
                        "engine": engine}), 502
    return jsonify({"ok": True, "words": words, "engine": engine})


def instance_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=1
        ) as response:
            return json.load(response).get("app") == APP_ID
    except Exception:
        return False


def pick_port(preferred: int = DEFAULT_PORT) -> int:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
            return probe.getsockname()[1]
        except OSError:
            pass
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def cleanup_stale_sessions(max_age: int = SESSION_MAX_AGE) -> None:
    try:
        entries = os.listdir(_SESSION_ROOT)
    except OSError:
        return
    cutoff = time.time() - max_age
    for name in entries:
        path = os.path.join(_SESSION_ROOT, name)
        try:
            if os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


def make_server(port: int):
    from werkzeug.serving import make_server as _make_server

    os.makedirs(_SESSION_ROOT, exist_ok=True)
    cleanup_stale_sessions()
    server = _make_server("127.0.0.1", port, app, threaded=True)
    _runtime["shutdown"] = server.shutdown
    return server


def run(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    import webbrowser

    if instance_running(port):
        url = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(f"{url}/api/focus", method="POST"),
                timeout=2,
            ) as response:
                focused = json.load(response).get("focused", False)
        except Exception:
            focused = False
        if focused:
            print("Already running — brought its window to the front.")
        elif open_browser:
            webbrowser.open(url)
            print(f"Already running at {url} — opened it in your browser.")
        else:
            print(f"Already running at {url}.")
        return

    port = pick_port(port)
    server = make_server(port)
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"AAC Editor running at {url} (press Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("AAC Editor stopped.")


if __name__ == "__main__":  # pragma: no cover
    run()
