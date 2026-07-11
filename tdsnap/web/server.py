"""Local web UI backend. Serves 127.0.0.1 only — nothing leaves the machine.

Session model: each uploaded page set gets a directory under the system temp
dir holding ``original`` (the untouched upload) and ``current`` (the state
after zero or more edits). Every edit opens a scratch working copy of
``current``, builds and validates the page there, and only replaces
``current`` when every check passes — so a failed edit can't leave the
session corrupted, and the download endpoint always serves the last good
state.
"""

import os
import secrets
import sqlite3
import tempfile

from flask import Flask, jsonify, request, send_file, send_from_directory

from .. import builder, validate
from ..errors import PagesetError
from ..pageset import Pageset, is_sqlite_file
from . import ollama

MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # page sets with media can be large

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

_SESSION_ROOT = os.path.join(tempfile.gettempdir(), "tdsnap-editor")
_sessions = {}


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


@app.errorhandler(PagesetError)
def _pageset_error(exc):
    return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/pageset")
def upload_pageset():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise PagesetError("No file was uploaded.")

    session_id = secrets.token_urlsafe(16)
    session_dir = os.path.join(_SESSION_ROOT, session_id)
    os.makedirs(session_dir, exist_ok=True)
    original = os.path.join(session_dir, "original")
    upload.save(original)

    if not is_sqlite_file(original):
        os.remove(original)
        raise PagesetError(
            f"{upload.filename!r} is not a TD Snap page set (.sps/.spb export)."
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
        "filename": upload.filename,
        "baseline_warnings": baseline["warnings"],
        "edits": 0,
    }
    return jsonify(
        {
            "ok": True,
            "session_id": session_id,
            "filename": upload.filename,
            "schema_version": schema_version,
            "grid": {"cols": cols, "rows": rows},
            "pages": _list_pages(os.path.join(session_dir, "current")),
            "baseline_problems": baseline["problems"],
        }
    )


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
        raise PagesetError("Nothing to download; re-upload the file.")
    base, ext = os.path.splitext(session["filename"])
    return send_file(
        current,
        as_attachment=True,
        download_name=f"{base}.edited{ext or '.sps'}",
        mimetype="application/octet-stream",
    )


@app.get("/api/ollama/status")
def ollama_status():
    host = request.args.get("host", ollama.DEFAULT_HOST)
    return jsonify(ollama.status(host))


@app.post("/api/ollama/words")
def ollama_words():
    payload = request.get_json(force=True, silent=True) or {}
    words, error = ollama.generate_words(
        category=payload.get("category", ""),
        count=payload.get("count", 10),
        host=payload.get("host", ollama.DEFAULT_HOST),
        model=payload.get("model", ollama.DEFAULT_MODEL),
    )
    if error:
        return jsonify({"ok": False, "error": error, "words": []}), 502
    return jsonify({"ok": True, "words": words})


def run(port: int = 8765, open_browser: bool = True) -> None:
    os.makedirs(_SESSION_ROOT, exist_ok=True)
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(
            1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")
        ).start()
    app.run(host="127.0.0.1", port=port, debug=False)
