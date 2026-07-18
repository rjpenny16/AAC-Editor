"""Local web UI backend, served only on 127.0.0.1.

Page-set content, button labels, and local AI requests stay on the machine.
The sole optional network feature is Wikipedia grounding: it is off by
default and sends only the current page title after the user explicitly opts
in for that suggestion request.

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
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

from flask import Flask, jsonify, request, send_file, send_from_directory

from .. import __version__, builder, grid3, live, schema, validate
from ..errors import PagesetError
from ..pageset import Pageset, is_sqlite_file
from . import grounding, localai, ollama, prompts

APP_ID = "aac-editor"
DEFAULT_PORT = 8765
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # page sets with media can be large
SESSION_MAX_AGE = 24 * 60 * 60  # leftover session dirs older than this are removed
MAX_ACTIVE_SESSIONS = 4
MAX_SESSION_STORAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ITEMS = 200
MAX_TITLE_CHARS = 60
MAX_PAGE_NAME_CHARS = 120
MAX_LABEL_CHARS = 60
MAX_MESSAGE_CHARS = 200

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

API_TOKEN = secrets.token_urlsafe(32)
# ponytail: TD Snap exposes one UI; one lock prevents concurrent automation.
_LIVE_LOCK = threading.Lock()

_SESSION_ROOT = os.path.join(tempfile.gettempdir(), "tdsnap-editor")
_sessions = {}
_sessions_lock = threading.Lock()

# Set by the host process so endpoints can stop the server or raise the
# native window.
_runtime = {"native": False, "focus": None, "shutdown": None}


def set_native(native: bool) -> None:
    """Tell the frontend whether it is running in the native window."""
    _runtime["native"] = native


def set_focus_handler(handler) -> None:
    """Called by POST /api/focus to bring the native window to the front."""
    _runtime["focus"] = handler


def _json_payload() -> dict:
    payload = request.get_json(force=True, silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise PagesetError("The request body must be a JSON object.")
    return payload


def _bounded_text(value, name: str, limit: int, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise PagesetError(f"'{name}' must be text.")
    value = value.strip()
    if required and not value:
        raise PagesetError(f"'{name}' is required.")
    if len(value) > limit:
        raise PagesetError(f"'{name}' must be {limit} characters or fewer.")
    return value


def _bounded_int(value, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PagesetError(f"'{name}' must be a whole number.")
    if not minimum <= value <= maximum:
        raise PagesetError(f"'{name}' must be between {minimum} and {maximum}.")
    return value


def _validated_items(value) -> list:
    if not isinstance(value, list):
        raise PagesetError("'items' must be a list of words.")
    if len(value) > MAX_ITEMS:
        raise PagesetError(f"No more than {MAX_ITEMS} buttons can be added at once.")
    for item in value:
        if isinstance(item, str):
            _bounded_text(item, "label", MAX_LABEL_CHARS, required=True)
            continue
        if not isinstance(item, dict):
            raise PagesetError("Each item must be text or a button object.")
        _bounded_text(item.get("label"), "label", MAX_LABEL_CHARS, required=True)
        _bounded_text(item.get("message"), "message", MAX_MESSAGE_CHARS)
        slot = item.get("slot")
        if slot is not None and (isinstance(slot, bool) or not isinstance(slot, int)
                                 or slot < 0):
            raise PagesetError("Each button slot must be a non-negative integer.")
    return value


def _validated_existing(value) -> list:
    if not isinstance(value, list):
        raise PagesetError("'existing' must be a list of button labels.")
    if len(value) > 100:
        raise PagesetError("No more than 100 existing button labels are allowed.")
    return [
        _bounded_text(label, "existing label", 80, required=True)
        for label in value
    ]


def _session_storage_bytes(exclude: str = "") -> int:
    total = 0
    try:
        entries = os.scandir(_SESSION_ROOT)
    except OSError:
        return 0
    with entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False) or entry.path == exclude:
                continue
            for root, _, files in os.walk(entry.path):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except OSError:
                        pass
    return total


def release_session(session_id: str) -> None:
    with _sessions_lock:
        session = _sessions.pop(session_id, None)
    if session is not None:
        shutil.rmtree(session["dir"], ignore_errors=True)


def cleanup_sessions() -> None:
    """Remove every sensitive temporary copy owned by this process."""
    with _sessions_lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for session in sessions:
        shutil.rmtree(session["dir"], ignore_errors=True)


def _session_dir(session_id: str) -> str:
    with _sessions_lock:
        session = _sessions.get(session_id)
    if session is None:
        raise PagesetError("Unknown or expired session; re-upload the file.")
    if time.time() - session.get("last_access", 0) > SESSION_MAX_AGE:
        release_session(session_id)
        raise PagesetError("Unknown or expired session; re-upload the file.")
    session["last_access"] = time.time()
    try:
        os.utime(session["dir"], None)
    except OSError:
        pass
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
        layouts = conn.execute(
            "SELECT pl.*, (SELECT COUNT(*) FROM ElementPlacement ep "
            "WHERE ep.PageLayoutId = pl.Id) AS PlacementCount "
            "FROM PageLayout pl WHERE pl.PageId = ?",
            (page_id,),
        ).fetchall()
        if not layouts:
            return 0
        configured = conn.execute(
            "SELECT GridDimension FROM PageSetProperties LIMIT 1"
        ).fetchone()
        preferred = (
            schema.parse_grid(configured[0])
            if configured and configured[0]
            else None
        )
        matching = [
            layout for layout in layouts
            if preferred and schema.parse_grid(layout["PageLayoutSetting"]) == preferred
        ]
        layout = matching[0] if matching else max(
            layouts, key=lambda candidate: candidate["PlacementCount"]
        )
        cols, rows = schema.parse_grid(layout["PageLayoutSetting"])
        used = set()
        for placement in conn.execute(
            "SELECT GridPosition, GridSpan FROM ElementPlacement "
            "WHERE PageLayoutId = ? AND Visible = 1",
            (layout["Id"],),
        ):
            col, grid_row = schema.parse_grid_position(placement["GridPosition"])
            col_span, row_span = schema.parse_grid_span(placement["GridSpan"])
            used.update(
                (x, y)
                for x in range(col, min(cols, col + col_span))
                for y in range(grid_row, min(rows, grid_row + row_span))
            )
        return cols * rows - len(used)
    finally:
        conn.close()


def _new_session_dir() -> tuple[str, str]:
    os.makedirs(_SESSION_ROOT, exist_ok=True)
    cleanup_stale_sessions()
    with _sessions_lock:
        if len(_sessions) >= MAX_ACTIVE_SESSIONS:
            raise PagesetError(
                "Too many page sets are open. Close one or restart AAC Editor."
            )
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
        expected_bytes = os.path.getsize(original) * 2
        if (_session_storage_bytes(exclude=session_dir) + expected_bytes
                > MAX_SESSION_STORAGE_BYTES):
            raise PagesetError(
                "Opening this page set would exceed the temporary storage limit."
            )
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

    with _sessions_lock:
        _sessions[session_id] = {
            "dir": session_dir,
            "filename": filename,
            "baseline_warnings": baseline["warnings"],
            "edits": 0,
            "last_access": time.time(),
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
    try:
        shutil.copyfile(path, os.path.join(session_dir, "original"))
        return _register_session(session_id, session_dir, os.path.basename(path))
    except Exception:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise


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
    directory = os.path.dirname(os.path.abspath(dest_path)) or os.curdir
    handle, temporary = tempfile.mkstemp(prefix=".aac-editor-", dir=directory)
    os.close(handle)
    try:
        shutil.copyfile(current, temporary)
        os.replace(temporary, dest_path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


@app.errorhandler(PagesetError)
def _pageset_error(exc):
    return jsonify({"ok": False, "error": str(exc)}), 400


@app.after_request
def _security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


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
    protected = request.method == "POST" or request.path.startswith("/api/ai/")
    if request.method == "OPTIONS" or not protected or request.path in {
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
        {"ok": True, "token": API_TOKEN, "native": _runtime["native"],
         "elevated": grid3.is_elevated(), "version": __version__}
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
    page = request.args.get("page")
    if page is not None:
        page = _bounded_text(page, "page", MAX_PAGE_NAME_CHARS, required=True)
    with _LIVE_LOCK:
        return jsonify({"ok": True, **live.inspect_page(page)})


@app.post("/api/tdsnap/edit-plan")
def live_execute_plan():
    if request.headers.get("X-TDSnap-Editor") != "1":
        raise PagesetError("Direct TD Snap edits must start in this app.")
    payload = _json_payload()
    if payload.get("operation") != "add_to_existing_page":
        raise PagesetError("This edit operation is not supported yet.")
    items = _validated_items(payload.get("items", []))
    page = _bounded_text(
        payload.get("page"), "page", MAX_PAGE_NAME_CHARS, required=True
    )
    fingerprint = _bounded_text(payload.get("fingerprint"), "fingerprint", 256)
    with _LIVE_LOCK:
        report = live.add_to_existing_page(page, items, fingerprint or None)
    return jsonify({"ok": True, **report})


@app.post("/api/tdsnap/page")
def live_add_page():
    # Custom header forces a cross-origin preflight, preventing arbitrary web
    # pages from driving this localhost-only mutation endpoint.
    if request.headers.get("X-TDSnap-Editor") != "1":
        raise PagesetError("Direct TD Snap edits must start in this app.")
    payload = _json_payload()
    items = _validated_items(payload.get("items", []))
    title = _bounded_text(
        payload.get("title"), "title", MAX_TITLE_CHARS, required=True
    )
    parent = _bounded_text(
        payload.get("parent", live.DEFAULT_PARENT),
        "parent", MAX_PAGE_NAME_CHARS, required=True,
    )
    with _LIVE_LOCK:
        report = live.add_topic_page(title, items, parent)
    report["warnings"] = [warning for warning in report["warnings"] if warning]
    return jsonify({"ok": True, **report})


@app.get("/api/grid3/status")
def grid3_status():
    with _LIVE_LOCK:
        result = grid3.status(include_layout=request.args.get("layout") == "1")
    return jsonify({"ok": True, **result})


@app.get("/api/grid3/page-layout")
def grid3_page_layout():
    with _LIVE_LOCK:
        result = grid3.inspect_page()
    return jsonify({"ok": True, **result})


@app.post("/api/grid3/probe")
def grid3_probe():
    if request.headers.get("X-AAC-Editor") != "grid3":
        raise PagesetError("The Grid 3 compatibility check must start in this app.")
    with _LIVE_LOCK:
        result = grid3.probe_accessibility()
    return jsonify({"ok": True, **result})


@app.post("/api/grid3/edit-plan")
def grid3_execute_plan():
    # The token middleware authenticates this elevated mutation. This custom
    # header additionally forces a browser cross-origin preflight.
    if request.headers.get("X-AAC-Editor") != "grid3":
        raise PagesetError("Direct Grid 3 edits must start in this app.")
    payload = _json_payload()
    if payload.get("operation") != "add_to_existing_page":
        raise PagesetError("This Grid 3 edit operation is not supported yet.")
    items = _validated_items(payload.get("items", []))
    fingerprint = _bounded_text(payload.get("fingerprint"), "fingerprint", 256)
    with _LIVE_LOCK:
        report = grid3.add_to_existing_page(items, fingerprint or None)
    return jsonify({"ok": True, **report})


@app.post("/api/pageset")
def upload_pageset():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise PagesetError("No file was uploaded.")

    filename = os.path.basename(upload.filename.replace("\\", "/"))
    filename = _bounded_text(filename, "filename", 255, required=True)
    session_id, session_dir = _new_session_dir()
    try:
        upload.save(os.path.join(session_dir, "original"))
        return jsonify(_register_session(session_id, session_dir, filename))
    except Exception:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise


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
    payload = _json_payload()
    title = _bounded_text(
        payload.get("title"), "title", MAX_TITLE_CHARS, required=True
    )
    items = _validated_items(payload.get("items", []))
    parent_page_id = payload.get("parent_page_id")
    if parent_page_id is None:
        raise PagesetError("'parent_page_id' is required.")
    parent_page_id = _bounded_int(parent_page_id, "parent_page_id", 1, 2**63 - 1)

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
        roundtrip = validate.check_roundtrip(before, after)
        problems = (
            roundtrip
            + validate.validate_new_page(ps.conn, report)
            + result["problems"]
            + validate.new_warnings(baseline, result)
        )
        checks = {
            "sqlite_integrity": "pass",
            "linkage_chains": "pass" if not problems else "fail",
            "roundtrip_diff": "pass" if not roundtrip else "fail",
        }
        if problems:
            return jsonify(
                {"ok": False, "error": "Validation failed; nothing was saved.",
                 "problems": problems, "checks": checks}
            ), 422
        ps.save_as(current, allow_source_overwrite=True)
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


@app.post("/api/pageset/<session_id>/close")
def close_pageset(session_id):
    release_session(session_id)
    return jsonify({"ok": True})


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
    try:
        host = ollama.normalize_host(request.args.get("host", ollama.DEFAULT_HOST))
    except ValueError as exc:
        raise PagesetError(str(exc)) from exc
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
    payload = _json_payload()
    existing = _validated_existing(payload.get("existing", []))
    category = _bounded_text(
        payload.get("category"), "category", MAX_PAGE_NAME_CHARS, required=True
    )
    count = _bounded_int(payload.get("count", 10), "count", 1, 60)
    kind = payload.get("kind", "words")
    if kind not in {"words", "phrases"}:
        raise PagesetError("'kind' must be 'words' or 'phrases'.")
    function = payload.get("function")
    if function is not None and function not in prompts.PHRASE_FUNCTIONS:
        raise PagesetError("'function' is not a supported phrase type.")
    grounding_requested = payload.get("grounding", False)
    if not isinstance(grounding_requested, bool):
        raise PagesetError("'grounding' must be true or false.")
    args = {
        "category": category,
        "count": count,
        "kind": kind,
        "function": function,
        "existing": existing,
    }
    try:
        host = ollama.normalize_host(payload.get("host", ollama.DEFAULT_HOST))
    except ValueError as exc:
        raise PagesetError(str(exc)) from exc
    model = _bounded_text(
        payload.get("model", ollama.DEFAULT_MODEL), "model", 120, required=True
    )
    ollama_state = ollama.status(host)
    # An Ollama server with no models can't generate anything; fall through
    # to the built-in engine instead of failing with "model not found".
    if ollama_state["reachable"] and ollama_state["models"]:
        engine, generate = "ollama", lambda: ollama.generate_words(
            host=host, model=model, **args
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
    args["reference"] = (
        grounding.reference_text(category, requested=True)
        if grounding_requested else ""
    )
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
                with _sessions_lock:
                    expired = [
                        session_id for session_id, session in _sessions.items()
                        if session.get("dir") == path
                    ]
                    for session_id in expired:
                        _sessions.pop(session_id, None)
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


def _open_browser(url: str) -> bool:
    """Open a system browser without PyInstaller's private DLL search path."""
    import webbrowser

    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return webbrowser.open(url)
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    kernel32.SetDllDirectoryW.restype = wintypes.BOOL
    kernel32.SetDllDirectoryW(None)
    try:
        return webbrowser.open(url)
    finally:
        kernel32.SetDllDirectoryW(getattr(sys, "_MEIPASS", None))


def run(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
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
            _open_browser(url)
            print(f"Already running at {url} — opened it in your browser.")
        else:
            print(f"Already running at {url}.")
        return

    port = pick_port(port)
    server = make_server(port)
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(1.0, lambda: _open_browser(url)).start()
    print(f"AAC Editor running at {url} (press Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_sessions()
        server.server_close()
    print("AAC Editor stopped.")


if __name__ == "__main__":  # pragma: no cover
    run()
