"""Local web UI backend. Serves 127.0.0.1 only — nothing leaves the machine.

Session model: each opened page set gets a directory under the system temp
dir holding ``original`` (an untouched copy) and ``current`` (the state
after zero or more edits). Every edit opens a scratch working copy of
``current``, builds and validates the page there, and only replaces
``current`` when every check passes — so a failed edit can't leave the
session corrupted, and the download endpoint always serves the last good
state.

Lifecycle: the server runs on a controllable werkzeug server so it can be
stopped cleanly — by the Quit button in browser mode (``POST /api/quit``),
or by closing the window in native mode (see ``desktop.py``). Launching a
second copy reuses the running instance instead of failing with "address
already in use": ``instance_running`` recognises us via ``GET /api/health``,
and ``POST /api/focus`` asks a native window to come to the front.

Security: every POST (except ``/api/focus``, which only raises the window)
must carry the ``X-TDSnap-Token`` header. The token is only readable
same-origin via ``GET /api/config``, so a malicious web page in the user's
browser can't drive the API with cross-site requests to 127.0.0.1.
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
import urllib.request

from flask import Flask, jsonify, request, send_file, send_from_directory

from .. import __version__, builder, validate
from ..errors import PagesetError
from ..pageset import Pageset, is_sqlite_file
from . import localai, ollama

APP_ID = "tdsnap-page-builder"
DEFAULT_PORT = 8765
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # page sets with media can be large
SESSION_MAX_AGE = 24 * 60 * 60  # leftover session dirs older than this are removed

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

API_TOKEN = secrets.token_urlsafe(32)

_SESSION_ROOT = os.path.join(tempfile.gettempdir(), "tdsnap-editor")
_sessions = {}

# Set by the host process (browser or native window) so endpoints can stop
# the server or raise the window. See run() and desktop.py.
_runtime = {"native": False, "focus": None, "shutdown": None}


def set_native(native: bool) -> None:
    """Tell the frontend it runs inside a native window (see /api/config)."""
    _runtime["native"] = native


def set_focus_handler(handler) -> None:
    """Called by POST /api/focus to bring the native window to the front."""
    _runtime["focus"] = handler


def _session_dir(session_id: str) -> str:
    session = _sessions.get(session_id)
    if session is None:
        raise PagesetError("Unknown or expired session; re-open the file.")
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


def _register_session(session_id: str, session_dir: str, filename: str) -> dict:
    """Validate ``session_dir/original`` and activate the session.

    Shared by the browser upload endpoint and the native open-file dialog;
    the payload is what the frontend needs to enter the build step.
    """
    original = os.path.join(session_dir, "original")
    if not is_sqlite_file(original):
        shutil.rmtree(session_dir, ignore_errors=True)
        raise PagesetError(
            f"{filename!r} is not a TD Snap page set (.sps/.spb export)."
        )

    # Validate structure by opening it the same way an edit would.
    probe = Pageset(original, working_copy=os.path.join(session_dir, "probe"))
    try:
        schema_version = probe.schema_version
        cols, rows = probe.grid_dimension()
        baseline = validate.validate_pageset(probe.conn)
    finally:
        probe.close()
    os.replace(os.path.join(session_dir, "probe"), os.path.join(session_dir, "current"))

    _sessions[session_id] = {
        "dir": session_dir,
        "filename": filename,
        "baseline_warnings": baseline["warnings"],
        "edits": 0,
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


def _new_session_dir() -> "tuple[str, str]":
    session_id = secrets.token_urlsafe(16)
    session_dir = os.path.join(_SESSION_ROOT, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_id, session_dir


def open_path(path: str) -> dict:
    """Open the page set at *path* (native file dialog flow).

    The file is copied into a fresh session; the original is never touched.
    """
    if not os.path.isfile(path):
        raise PagesetError(f"{path!r} does not exist or is not a file.")
    session_id, session_dir = _new_session_dir()
    shutil.copyfile(path, os.path.join(session_dir, "original"))
    return _register_session(session_id, session_dir, os.path.basename(path))


def edited_filename(session_id: str) -> str:
    """Suggested name for the edited copy, e.g. ``My Set.edited.sps``."""
    session = _sessions.get(session_id)
    if session is None:
        raise PagesetError("Unknown or expired session; re-open the file.")
    base, ext = os.path.splitext(session["filename"])
    return f"{base}.edited{ext or '.sps'}"


def save_current_as(session_id: str, dest_path: str) -> None:
    """Write the session's last good state to *dest_path* (native save flow)."""
    current = _current_path(session_id)
    if not os.path.exists(current):
        raise PagesetError("Nothing to save yet; re-open the file.")
    shutil.copyfile(current, dest_path)


@app.errorhandler(PagesetError)
def _pageset_error(exc):
    return jsonify({"ok": False, "error": str(exc)}), 400


@app.before_request
def _require_api_token():
    """Reject state-changing requests that don't carry our per-run token.

    The token forces a CORS preflight (custom header) and is unknowable to
    other origins, so random web pages can't POST to this local server.
    /api/focus is exempt: it comes from a second app launch (a different
    process that can't know the token) and only raises the window.
    """
    if request.method != "POST" or request.path == "/api/focus":
        return None
    if request.headers.get("X-TDSnap-Token") != API_TOKEN:
        return jsonify(
            {"ok": False, "error": "Missing or invalid API token; reload the page."}
        ), 403
    return None


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    """Identifies this server to new launches (see instance_running)."""
    return jsonify({"ok": True, "app": APP_ID, "version": __version__})


@app.get("/api/config")
def config():
    """Frontend bootstrap: the API token and whether we're in a native window."""
    return jsonify(
        {
            "ok": True,
            "token": API_TOKEN,
            "native": _runtime["native"],
            "version": __version__,
        }
    )


@app.post("/api/quit")
def quit_app():
    """Stop the app (Quit button in browser mode)."""
    shutdown = _runtime.get("shutdown")
    if shutdown is None:
        raise PagesetError("The app wasn't started in a stoppable mode.")
    # Let the response flush before the serve loop stops.
    threading.Timer(0.3, shutdown).start()
    return jsonify({"ok": True})


@app.post("/api/focus")
def focus():
    """Bring the native window to the front (called by a second launch)."""
    handler = _runtime.get("focus")
    if handler is not None:
        handler()
    return jsonify({"ok": True, "focused": handler is not None})


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
    current = _current_path(session_id)
    scratch = os.path.join(_session_dir(session_id), "scratch")

    with Pageset(current, working_copy=scratch) as ps:
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
        raise PagesetError("Nothing to download; re-open the file.")
    return send_file(
        current,
        as_attachment=True,
        download_name=edited_filename(session_id),
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
    args = {
        "category": payload.get("category", ""),
        "count": payload.get("count", 10),
        "kind": payload.get("kind", "words"),
        "function": payload.get("function"),
    }
    host = payload.get("host", ollama.DEFAULT_HOST)
    if ollama.status(host)["reachable"]:
        words, error = ollama.generate_words(
            host=host, model=payload.get("model", ollama.DEFAULT_MODEL), **args
        )
        engine = "ollama"
    elif localai.engine_available() and localai.is_downloaded():
        words, error = localai.generate_words(**args)
        engine = "local"
    else:
        return jsonify(
            {"ok": False, "words": [],
             "error": "No AI engine is ready yet — download the built-in "
                      "model below, or start Ollama."}
        ), 400
    if error:
        return jsonify({"ok": False, "error": error, "words": [],
                        "engine": engine}), 502
    return jsonify({"ok": True, "words": words, "engine": engine})


# ---------- lifecycle helpers ----------


def instance_running(port: int) -> bool:
    """True when another copy of this app is already serving *port*."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=1
        ) as response:
            return json.load(response).get("app") == APP_ID
    except Exception:
        return False


def pick_port(preferred: int = DEFAULT_PORT) -> int:
    """*preferred* if it's free, otherwise an OS-assigned free port."""
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
    """Remove leftover session dirs from previous runs (they can be large)."""
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
    """A controllable single-app server; its .shutdown() stops the app."""
    from werkzeug.serving import make_server as _make_server

    os.makedirs(_SESSION_ROOT, exist_ok=True)
    cleanup_stale_sessions()
    server = _make_server("127.0.0.1", port, app, threaded=True)
    _runtime["shutdown"] = server.shutdown
    return server


def run(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Browser mode: serve until Ctrl+C or the Quit button.

    If a copy of the app is already running on *port*, reuse it (open a tab
    pointing at it, or raise its native window) instead of failing with
    "address already in use". If the port is busy with something else, fall
    back to a free one.
    """
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
    print(f"TD Snap Page Builder running at {url} (press Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("TD Snap Page Builder stopped.")
