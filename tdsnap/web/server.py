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

import contextlib
import hashlib
import io
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
from typing import Optional

from flask import Flask, jsonify, request, send_file, send_from_directory

from .. import __version__, builder, grid3, live, obf, pageset, schema, validate
from ..errors import PagesetError
from ..pageset import Pageset, is_sqlite_file
from . import diagnostics, engines, grounding, localai, ollama, prompts, settings

APP_ID = "aac-editor"
DEFAULT_PORT = 8765
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # page sets with media can be large
SESSION_MAX_AGE = 24 * 60 * 60  # leftover session dirs older than this are removed
MAX_ACTIVE_SESSIONS = 4
# How slow a first suggestion round may be and still earn a second one. The
# browser gives a generation 150 seconds; two rounds have to fit inside that.
RETRY_BUDGET_SECONDS = 45
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


def _validated_changes(value) -> list:
    """Bound ``[{slot, label?, message?}]`` before it reaches the write path.

    ``label``/``message`` absent means "leave that as it is"; an empty message
    means "go back to speaking the label", so ``None`` and ``""`` are kept
    distinct here rather than collapsed the way ``_validated_items`` does.
    """
    if not isinstance(value, list):
        raise PagesetError("'changes' must be a list of button changes.")
    if len(value) > MAX_ITEMS:
        raise PagesetError(f"No more than {MAX_ITEMS} buttons can be changed at once.")
    changes = []
    for change in value:
        if not isinstance(change, dict):
            raise PagesetError("Each change must be a {slot, label, message} object.")
        slot = change.get("slot")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise PagesetError("Each changed button slot must be a non-negative integer.")
        entry = {"slot": slot}
        if change.get("label") is not None:
            entry["label"] = _bounded_text(
                change.get("label"), "label", MAX_LABEL_CHARS, required=True
            )
        if change.get("message") is not None:
            entry["message"] = _bounded_text(
                change.get("message"), "message", MAX_MESSAGE_CHARS
            )
        changes.append(entry)
    return changes


def _validated_removals(value) -> list:
    if not isinstance(value, list):
        raise PagesetError("'removals' must be a list of button slots.")
    if len(value) > MAX_ITEMS:
        raise PagesetError(f"No more than {MAX_ITEMS} buttons can be removed at once.")
    for slot in value:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise PagesetError("Each removed button slot must be a non-negative integer.")
    return value


def _validated_moves(value) -> list:
    """Bound ``[{slot, to}]`` before it reaches the write path."""
    if not isinstance(value, list):
        raise PagesetError("'moves' must be a list of button moves.")
    if len(value) > MAX_ITEMS:
        raise PagesetError(f"No more than {MAX_ITEMS} buttons can be moved at once.")
    moves = []
    for move in value:
        if not isinstance(move, dict):
            raise PagesetError("Each move must be a {slot, to} object.")
        for key in ("slot", "to"):
            slot = move.get(key)
            if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
                raise PagesetError(
                    "Each moved button needs a non-negative 'slot' and 'to' cell."
                )
        moves.append({"slot": move["slot"], "to": move["to"]})
    return moves


def _validated_existing(value) -> list:
    if not isinstance(value, list):
        raise PagesetError("'existing' must be a list of button labels.")
    if len(value) > 100:
        raise PagesetError("No more than 100 existing button labels are allowed.")
    return [
        _bounded_text(label, "existing label", 80, required=True)
        for label in value
    ]


def _validated_labels(value, name: str, limit: int) -> list:
    """A bounded list of short label-shaped strings, for the AI steering lists.

    Rejected suggestions, kept ones, and style samples are all user text headed
    for a prompt, so each gets the same length and count bound rather than
    being trusted because it came from this app's own UI.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise PagesetError(f"'{name}' must be a list of button labels.")
    if len(value) > limit:
        raise PagesetError(f"No more than {limit} '{name}' labels are allowed.")
    labels = [_bounded_text(label, f"{name} label", 120) for label in value]
    return [label for label in labels if label]


# Communicative functions a draft or topic-page item may carry; mirrors
# FUNCTIONS in static/state.js. "" means "no function" (a plain word button).
_DRAFT_FUNCTIONS = {"", "question", "comment", "positive", "negative", "personal"}

# Known preference keys the frontend remembers, and how each is validated.
# Unknown keys are dropped rather than rejected, so an older server tolerates
# a newer frontend's preferences file without failing the whole save.
_PREFERENCE_SCHEMA = {
    "provider": {"choices": {"tdsnap", "grid3", "file"}, "max_len": 20},
    "ai_engine": {"choices": {"auto", "ollama", "local"}, "max_len": 20},
    "ollama_host": {"max_len": 200},
    "ollama_model": {"max_len": 120},
    "ai_grounding": {"bool": True},
    "ai_style": {"bool": True},
    "ai_model": {"max_len": 20},
}


def _validated_preferences(value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PagesetError("'preferences' must be an object.")
    result = {}
    for key, raw in value.items():
        spec = _PREFERENCE_SCHEMA.get(key)
        if spec is None:
            continue
        if spec.get("bool"):
            if isinstance(raw, bool):
                result[key] = raw
            continue
        if not isinstance(raw, str):
            continue
        text = raw.strip()[: spec.get("max_len", 200)]
        if "choices" in spec and text not in spec["choices"]:
            continue
        result[key] = text
    return result


def _validated_draft_items(value) -> list:
    if not isinstance(value, list):
        raise PagesetError("'draft.items' must be a list.")
    if len(value) > MAX_ITEMS:
        raise PagesetError(f"A draft can hold no more than {MAX_ITEMS} buttons.")
    items = []
    for item in value:
        if not isinstance(item, dict):
            raise PagesetError("Each draft item must be an object.")
        label = _bounded_text(item.get("label"), "draft item label", MAX_LABEL_CHARS, required=True)
        message = _bounded_text(item.get("message"), "draft item message", MAX_MESSAGE_CHARS)
        fn = item.get("fn") or ""
        if fn not in _DRAFT_FUNCTIONS:
            raise PagesetError("Each draft item's function is invalid.")
        slot = item.get("slot")
        if slot is not None and (
            isinstance(slot, bool) or not isinstance(slot, int) or slot < 0
        ):
            raise PagesetError("Each draft item's slot must be a non-negative integer.")
        query = _bounded_text(item.get("symbol_query"), "draft symbol query", MAX_LABEL_CHARS)
        items.append(
            {
                "label": label,
                "message": message or None,
                "fn": fn,
                "slot": slot,
                "symbol": bool(item.get("symbol", True)),
                "symbol_query": query or None,
            }
        )
    return items


# A saved template is the one thing in the settings file that is deliberate,
# reusable work rather than a convenience, so it is bounded on its own terms:
# enough for a real caseload, far short of anything that could bloat the file.
MAX_TEMPLATES = 50
MAX_TEMPLATE_NAME_CHARS = 60


def _validated_templates(value) -> Optional[list]:
    """Bound ``[{name, page_style, items}]``, or ``None`` to leave them alone.

    Absent means "unchanged": the draft autosave PUTs every few seconds and
    says nothing about templates, and it must not be able to wipe them. An
    explicit empty list is how they are cleared.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        raise PagesetError("'templates' must be a list of saved templates.")
    if len(value) > MAX_TEMPLATES:
        raise PagesetError(f"No more than {MAX_TEMPLATES} templates can be saved.")
    templates = []
    names = set()
    for template in value:
        if not isinstance(template, dict):
            raise PagesetError("Each template must be an object.")
        name = _bounded_text(
            template.get("name"), "template name", MAX_TEMPLATE_NAME_CHARS, required=True
        )
        folded = name.casefold()
        if folded in names:
            raise PagesetError(f"Two templates cannot both be called {name!r}.")
        names.add(folded)
        style = template.get("page_style")
        if style not in {"words", "topic"}:
            raise PagesetError("Each template's page style must be 'words' or 'topic'.")
        saved_at = template.get("saved_at")
        if saved_at is not None:
            saved_at = _bounded_int(saved_at, "template saved_at", 0, 2**63 - 1)
        items = _validated_draft_items(template.get("items", []))
        if not items:
            raise PagesetError(f"Template {name!r} has no buttons to save.")
        templates.append({
            "name": name,
            "page_style": style,
            "saved_at": saved_at,
            "items": items,
        })
    return templates


def _validated_draft(value) -> Optional[dict]:
    """Bound and shape a draft, or drop it entirely if there's nothing in it.

    A draft with no items isn't worth resuming, so it collapses to ``None``
    rather than being stored and offered back to the user as empty.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PagesetError("'draft' must be an object or null.")
    items = _validated_draft_items(value.get("items", []))
    if not items:
        return None
    provider = value.get("provider")
    if provider not in {"tdsnap", "grid3", "file", None}:
        raise PagesetError("'draft.provider' is invalid.")
    operation = value.get("operation")
    if operation not in {"existing", "new", None}:
        raise PagesetError("'draft.operation' is invalid.")
    page_style = value.get("page_style")
    if page_style not in {"words", "topic", None}:
        raise PagesetError("'draft.page_style' is invalid.")
    active_fn = value.get("active_fn") or ""
    if active_fn not in _DRAFT_FUNCTIONS:
        raise PagesetError("'draft.active_fn' is invalid.")
    return {
        "provider": provider,
        "operation": operation,
        "page_style": page_style,
        "active_fn": active_fn,
        "target_page": _bounded_text(
            value.get("target_page"), "draft.target_page", MAX_PAGE_NAME_CHARS
        ),
        "title": _bounded_text(value.get("title"), "draft.title", MAX_TITLE_CHARS),
        "items": items,
        "saved_at": time.time(),
    }


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
                    with contextlib.suppress(OSError):
                        total += os.path.getsize(os.path.join(root, name))
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


def _write_session_meta(session_dir: str, filename: str, baseline_warnings: list, edits: int) -> None:
    """Persist the bit of session state that isn't already in the sqlite copy.

    ``original``/``current`` on disk survive a server restart on their own;
    only the filename, baseline warnings, and edit count need a home. Written
    best-effort — a failure here degrades a restart back to today's "re-upload
    the file" rather than breaking the edit that triggered it.
    """
    payload = {"filename": filename, "baseline_warnings": baseline_warnings, "edits": edits}
    try:
        handle, temp_path = tempfile.mkstemp(prefix=".meta-", dir=session_dir)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
                json.dump(payload, temp_file)
            os.replace(temp_path, os.path.join(session_dir, "meta.json"))
        finally:
            with contextlib.suppress(OSError):
                os.remove(temp_path)
    except OSError:
        pass


def _rehydrate_session(session_id: str):
    """Reconstruct an in-memory session record from its on-disk directory.

    ``_sessions`` lives in process memory, so a Flask restart — a crash, a
    port conflict, or a launcher killing a stale instance — used to turn
    every open file-mode session into "Unknown or expired session" even
    though the edited copy was sitting right there on disk. Returns ``None``
    (and lets the caller raise the usual error) when the directory, the
    edited copy, or its metadata is missing.
    """
    session_dir = os.path.join(_SESSION_ROOT, session_id)
    current = os.path.join(session_dir, "current")
    meta_path = os.path.join(session_dir, "meta.json")
    if not os.path.isfile(current) or not os.path.isfile(meta_path):
        return None
    try:
        with open(meta_path, encoding="utf-8") as handle:
            meta = json.load(handle)
        filename = meta["filename"]
        baseline_warnings = meta.get("baseline_warnings", [])
        edits = int(meta.get("edits", 0))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    session = {
        "dir": session_dir,
        "filename": filename,
        "baseline_warnings": baseline_warnings,
        "edits": edits,
        "last_access": time.time(),
        "lock": threading.Lock(),
    }
    with _sessions_lock:
        return _sessions.setdefault(session_id, session)


def _session_dir(session_id: str) -> str:
    with _sessions_lock:
        session = _sessions.get(session_id)
    if session is None:
        session = _rehydrate_session(session_id)
    if session is None:
        raise PagesetError("Unknown or expired session; re-upload the file.")
    if time.time() - session.get("last_access", 0) > SESSION_MAX_AGE:
        release_session(session_id)
        raise PagesetError("Unknown or expired session; re-upload the file.")
    session["last_access"] = time.time()
    with contextlib.suppress(OSError):
        os.utime(session["dir"], None)
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


def _page_state(path: str, page_id: int, include_buttons: bool = True) -> dict:
    """The grid, buttons, empty cells, and fingerprint of one page in a file session.

    This is the exported-file counterpart of ``live.inspect_page`` and answers
    the same questions the preview asks of TD Snap: how big is the grid, what is
    already on it, which cells are free, and has any of that changed since the
    review. The layout is chosen by ``builder.layout_for_page`` rather than a
    second copy of that rule, so the capacity the picker shows and the cells the
    writer fills can never disagree.

    Every existing button is reported locked. Changing and removing on the file
    path would need their own prior-content snapshot and rollback; until that
    exists, saying so plainly beats offering a control that does something else.

    *include_buttons* is off for the parent picker, which only needs a count and
    must keep working on a page set whose button tables this app cannot read.
    """
    with contextlib.closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        layout = builder.layout_for_page(conn, page_id, pageset.grid_dimension(conn))
        cols, rows = schema.parse_grid(layout["PageLayoutSetting"])
        state = {
            "grid": {"cols": cols, "rows": rows},
            "free_slots": builder.free_slots(conn, layout),
        }
        if not include_buttons:
            return state
        page = conn.execute(
            "SELECT Id, Title FROM Page WHERE Id = ? AND PageType = 1", (page_id,)
        ).fetchone()
        if page is None:
            raise PagesetError("That page is not in this page set.")
        buttons: list[dict] = []
        for row in conn.execute(
            "SELECT button.Label AS Label, button.Message AS Message, "
            "placement.GridPosition AS GridPosition "
            "FROM ElementPlacement placement "
            "JOIN ElementReference ref ON ref.Id = placement.ElementReferenceId "
            "JOIN Button button ON button.ElementReferenceId = ref.Id "
            "WHERE placement.PageLayoutId = ? AND placement.Visible = 1",
            (layout["Id"],),
        ):
            label = (row["Label"] or "").strip()
            if not label:
                continue
            col, grid_row = schema.parse_grid_position(row["GridPosition"])
            buttons.append({
                "slot": grid_row * cols + col,
                "label": label,
                "message": (row["Message"] or "").strip() or None,
                "function": None,
                "symbol": False,
                "editable": False,
                "locked_reason": "AAC Editor only adds buttons in exported files.",
            })
        buttons.sort(key=lambda button: button["slot"])
    payload = json.dumps(
        [[button["slot"], button["label"]] for button in buttons],
        ensure_ascii=False, separators=(",", ":"),
    )
    return {
        **state,
        "page": page["Title"] or f"Page {page_id}",
        "buttons": buttons,
        "content_readable": False,
        "fingerprint": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def _free_cells(path: str, page_id: int) -> int:
    """How many empty grid cells *page_id* has (for the parent picker)."""
    try:
        return len(_page_state(path, page_id, include_buttons=False)["free_slots"])
    except PagesetError:
        return 0


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
    _write_session_meta(session_dir, filename, baseline["warnings"], 0)
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
    _session_dir(session_id)  # raises, and rehydrates from disk, as needed
    base, ext = os.path.splitext(_sessions[session_id]["filename"])
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
        with contextlib.suppress(OSError):
            os.remove(temporary)


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
    protected = (
        request.method in ("POST", "PUT", "DELETE") or request.path.startswith("/api/ai/")
    )
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


@app.get("/api/diagnostics")
def diagnostics_report():
    """Environment facts for a bug report — never page-set content.

    Probing TD Snap and Grid 3 walks their accessibility trees, so this takes
    the same lock every other live call does.
    """
    with _LIVE_LOCK:
        data = diagnostics.report(_runtime["native"])
    return jsonify({"ok": True, "report": data, "text": diagnostics.as_text(data)})


@app.get("/api/settings")
def get_settings():
    """Remembered preferences and any recoverable draft — never page-set content."""
    data = settings.load()
    return jsonify({
        "ok": True,
        "preferences": data["preferences"],
        "draft": data["draft"],
        "templates": data["templates"],
    })


@app.put("/api/settings")
def put_settings():
    """Save preferences and/or a draft. Only reached when the user changes a
    preference or is composing something worth recovering — a fresh install
    never calls this, so it never creates the file."""
    payload = _json_payload()
    preferences = _validated_preferences(payload.get("preferences"))
    draft = _validated_draft(payload.get("draft"))
    templates = _validated_templates(payload.get("templates"))
    settings.save(preferences, draft, templates)
    return jsonify({"ok": True})


@app.delete("/api/settings")
def delete_settings():
    """Clear all saved data — the disclosure panel's "Clear all" control."""
    settings.clear()
    return jsonify({"ok": True})


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
    # "edit_page" carries additions, changes, moves, and removals together, so
    # one review and one rollback cover the whole edit. The older add-only name
    # stays accepted and behaves identically.
    if payload.get("operation") not in {"add_to_existing_page", "edit_page"}:
        raise PagesetError("This edit operation is not supported yet.")
    items = _validated_items(payload.get("items", []))
    changes = _validated_changes(payload.get("changes", []))
    removals = _validated_removals(payload.get("removals", []))
    moves = _validated_moves(payload.get("moves", []))
    page = _bounded_text(
        payload.get("page"), "page", MAX_PAGE_NAME_CHARS, required=True
    )
    fingerprint = _bounded_text(payload.get("fingerprint"), "fingerprint", 256)
    with _LIVE_LOCK:
        report = live.apply_page_edits(
            page, items, changes, removals, moves, fingerprint or None
        )
        report["undo"] = live.last_edit()
    return jsonify({"ok": True, **report})


@app.post("/api/tdsnap/batch")
def live_execute_batch():
    """Apply several reviewed page edits in one run, one page at a time.

    Each queued entry is validated exactly as a single-page edit is — the
    batch adds no new way to describe an edit, only a way to sequence several.
    """
    if request.headers.get("X-TDSnap-Editor") != "1":
        raise PagesetError("Direct TD Snap edits must start in this app.")
    payload = _json_payload()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise PagesetError("'entries' must be a list of queued page edits.")
    if len(entries) > live.MAX_BATCH_PAGES:
        raise PagesetError(
            f"No more than {live.MAX_BATCH_PAGES} pages can be applied in one go."
        )
    queued = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise PagesetError("Each queued page must be an object.")
        queued.append({
            "page": _bounded_text(
                entry.get("page"), "page", MAX_PAGE_NAME_CHARS, required=True
            ),
            "items": _validated_items(entry.get("items", [])),
            "changes": _validated_changes(entry.get("changes", [])),
            "removals": _validated_removals(entry.get("removals", [])),
            "moves": _validated_moves(entry.get("moves", [])),
            "fingerprint": _bounded_text(entry.get("fingerprint"), "fingerprint", 256)
            or None,
        })
    with _LIVE_LOCK:
        report = live.apply_batch(queued)
        report["undo"] = live.last_edit()
    return jsonify({"ok": True, **report})


@app.get("/api/tdsnap/vocabulary")
def live_vocabulary():
    """Every label in the open page set, for advisory duplicate checking.

    Read once per connection; the browser answers "where else does this word
    live?" from it. Advisory only — a page set this cannot read reports
    ``available: false`` and nothing downstream is blocked by it.
    """
    with _LIVE_LOCK:
        return jsonify({"ok": True, **live.vocabulary()})


@app.get("/api/tdsnap/last-edit")
def live_last_edit():
    """What "Undo my last change" would do, or ``null`` when there is nothing.

    The retained edit lives in the server process, so this survives a browser
    reload while — deliberately — not surviving a restart of the app itself.
    """
    with _LIVE_LOCK:
        return jsonify({"ok": True, "undo": live.last_edit()})


@app.delete("/api/tdsnap/last-edit")
def live_forget_last_edit():
    """Stop offering the undo — used when a session is torn down."""
    with _LIVE_LOCK:
        live.forget_last_edit()
    return jsonify({"ok": True})


@app.post("/api/tdsnap/undo")
def live_undo():
    # Same custom header as every other TD Snap mutation: it forces a
    # cross-origin preflight so no other page can drive this one.
    if request.headers.get("X-TDSnap-Editor") != "1":
        raise PagesetError("Direct TD Snap edits must start in this app.")
    with _LIVE_LOCK:
        report = live.undo_last_edit()
        report["undo"] = live.last_edit()
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
    """Grid 3's capability facts, plus what to say about them.

    ``guidance`` is the decision: one state, one sentence, the single next
    thing the user can do, and the standing limits of live Grid 3 editing.
    The browser renders that rather than assembling its own sentence out of
    five booleans — see grid3.explain.
    """
    with _LIVE_LOCK:
        result = grid3.status(include_layout=request.args.get("layout") == "1")
    return jsonify({"ok": True, **result, "guidance": grid3.explain(result)})


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
    operation = payload.get("operation")
    # The same three operations TD Snap accepts, carrying the same payloads.
    if operation not in {"add_to_existing_page", "edit_page", "create_page"}:
        raise PagesetError(
            "AAC Editor can add, change, move and remove speaking cells on the open "
            "Grid 3 grid, undo that, and create a linked grid. Nothing else is "
            "supported for Grid 3 yet."
        )
    items = _validated_items(payload.get("items", []))
    fingerprint = _bounded_text(payload.get("fingerprint"), "fingerprint", 256)
    if operation == "create_page":
        title = _bounded_text(payload.get("title"), "title", MAX_TITLE_CHARS, required=True)
        with _LIVE_LOCK:
            report = grid3.add_topic_page(title, items, fingerprint=fingerprint or None)
        return jsonify({"ok": True, **report})
    changes = _validated_changes(payload.get("changes", []))
    removals = _validated_removals(payload.get("removals", []))
    moves = _validated_moves(payload.get("moves", []))
    with _LIVE_LOCK:
        report = grid3.edit_page(items, changes, removals, moves, fingerprint or None)
        report["undo"] = grid3.last_edit()
    return jsonify({"ok": True, **report})


@app.post("/api/grid3/undo")
def grid3_undo():
    if request.headers.get("X-AAC-Editor") != "grid3":
        raise PagesetError("Direct Grid 3 edits must start in this app.")
    with _LIVE_LOCK:
        report = grid3.undo_last_edit()
        report["undo"] = grid3.last_edit()
    return jsonify({"ok": True, **report})


@app.delete("/api/grid3/last-edit")
def grid3_forget_last_edit():
    with _LIVE_LOCK:
        grid3.forget_last_edit()
    return jsonify({"ok": True})


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


@app.get("/api/pageset/<session_id>/vocabulary")
def pageset_vocabulary(session_id):
    """The exported-file counterpart of ``/api/tdsnap/vocabulary``."""
    current = _current_path(session_id)
    try:
        with contextlib.closing(
            sqlite3.connect(f"file:{current}?mode=ro", uri=True)
        ) as conn:
            conn.row_factory = sqlite3.Row
            labels = pageset.labels_by_page(conn)
            samples = pageset.label_samples(conn)
    except sqlite3.Error:
        return jsonify({"ok": True, "available": False, "labels": {}, "samples": []})
    return jsonify(
        {"ok": True, "available": True, "labels": labels, "samples": samples}
    )


@app.get("/api/pageset/<session_id>/page/<int:page_id>/layout")
def page_layout(session_id, page_id):
    """The exported-file counterpart of ``/api/tdsnap/page-layout``."""
    current = _current_path(session_id)
    return jsonify({"ok": True, **_page_state(current, page_id)})


@app.post("/api/pageset/<session_id>/page/<int:page_id>/buttons")
def add_buttons(session_id, page_id):
    """Add reviewed buttons to a page that already exists in an exported file.

    The same shape as ``add_page``: validate the whole file before and after,
    refuse to save anything that fails a check, and only then replace the
    session's ``current`` state.
    """
    payload = _json_payload()
    items = _validated_items(payload.get("items", []))
    fingerprint = _bounded_text(payload.get("fingerprint"), "fingerprint", 256)

    current = _current_path(session_id)  # raises, and rehydrates from disk, as needed
    if not fingerprint:
        raise PagesetError(
            "The review fingerprint is required. Reload the page and review again."
        )
    if _page_state(current, page_id)["fingerprint"] != fingerprint:
        raise PagesetError(
            "This page changed after the preview. Reload the page and review the "
            "edit again."
        )
    session = _sessions[session_id]
    scratch = os.path.join(session["dir"], "scratch")

    with session["lock"], Pageset(current, working_copy=scratch, cleanup=True) as ps:
        baseline = validate.validate_pageset(ps.conn)
        before = validate.table_snapshot(ps.conn)
        report = builder.add_buttons_to_page(ps, page_id, items)
        after = validate.table_snapshot(ps.conn)

        result = validate.validate_pageset(ps.conn)
        roundtrip = validate.check_roundtrip(before, after)
        problems = (
            roundtrip
            + validate.validate_added_buttons(ps.conn, report)
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
        _write_session_meta(
            session["dir"], session["filename"], session["baseline_warnings"], session["edits"]
        )
    checks["target_page"] = "pass"
    checks["positions"] = "pass"
    return jsonify(
        {
            "ok": True,
            "page_id": report["page_id"],
            "buttons": len(report["button_ids"]),
            "grid": {"cols": report["grid"][0], "rows": report["grid"][1]},
            "checks": checks,
            "edits": session["edits"],
        }
    )


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

    current = _current_path(session_id)  # raises, and rehydrates from disk, as needed
    session = _sessions[session_id]
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
        _write_session_meta(
            session["dir"], session["filename"], session["baseline_warnings"], session["edits"]
        )
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


# ---------------------------------------------------------------------------
# Open Board Format interchange (Phase 9)

MAX_BOARD_UPLOAD_BYTES = 64 * 1024 * 1024


def _obz_response(pages, name):
    if not name:
        raise PagesetError("There is nothing to export.")
    data = obf.write(pages, name=name)
    stem = "".join(char if char.isalnum() or char in " -_" else "_" for char in name).strip() or "pages"
    return send_file(
        io.BytesIO(data), as_attachment=True, download_name=f"{stem}.obz",
        mimetype="application/zip",
    )


@app.post("/api/obf/import")
def obf_import():
    """Read an .obf or .obz into pages the items step can take.

    Nothing is written anywhere: the boards come back as labels, spoken text,
    slots and function colours for the ordinary review flow. Buttons that open
    another board are listed separately, so the user can import that board as
    its own page and link it from this one.
    """
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise PagesetError("No board file was uploaded.")
    data = upload.read(MAX_BOARD_UPLOAD_BYTES + 1)
    if len(data) > MAX_BOARD_UPLOAD_BYTES:
        raise PagesetError("The board file is larger than AAC Editor will open (64 MB).")
    filename = os.path.basename(upload.filename.replace("\\", "/"))
    result = obf.read(data, filename)
    return jsonify({"ok": True, "filename": filename, **result})


@app.get("/api/pageset/<session_id>/obz")
def download_obz(session_id):
    """The whole exported-file session as an .obz: every page, linked, no symbols."""
    current = _current_path(session_id)
    session = _sessions[session_id]
    with contextlib.closing(sqlite3.connect(f"file:{current}?mode=ro", uri=True)) as conn:
        pages = obf.pages_from_pageset(conn)
    return _obz_response(pages, os.path.splitext(session["filename"])[0])


@app.get("/api/tdsnap/obz")
def live_obz():
    """The page set open in TD Snap as an .obz, read from its file, never edited."""
    page = _bounded_text(request.args.get("page"), "page", MAX_PAGE_NAME_CHARS)
    with _LIVE_LOCK:
        path = live._active_pageset_path(page or None)
    if not path:
        raise PagesetError(
            "AAC Editor could not tell which TD Snap page set is open. Connect to TD "
            "Snap first, with the page set you want to export showing."
        )
    with contextlib.closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)) as conn:
        pages = obf.pages_from_pageset(conn)
        try:
            row = conn.execute("SELECT FriendlyName FROM PageSetProperties LIMIT 1").fetchone()
            name = (row[0] or "").strip() if row else ""
        except sqlite3.Error:
            name = ""
    return _obz_response(pages, name or "TD Snap page set")


@app.post("/api/pageset/<session_id>/close")
def close_pageset(session_id):
    release_session(session_id)
    return jsonify({"ok": True})


@app.get("/api/pageset/<session_id>/download")
def download(session_id):
    current = _current_path(session_id)  # raises, and rehydrates from disk, as needed
    if not os.path.exists(current):
        raise PagesetError("Nothing to download; re-upload the file.")
    session = _sessions[session_id]
    base, ext = os.path.splitext(session["filename"])
    return send_file(
        current,
        as_attachment=True,
        download_name=f"{base}.edited{ext or '.sps'}",
        mimetype="application/octet-stream",
    )


@app.get("/api/ai/status")
def ai_status():
    """Which suggestion engines are usable right now.

    ``local`` also describes every built-in model this build will download, so
    the panel can offer a bigger one on a machine measured to have the memory
    for it — and say plainly why it is not offering one otherwise.

    ``ai`` is the decision itself: one state, one sentence, and the single
    next thing the user can do. The browser renders that rather than working
    out for a second time which of two engines is usable — see engines.py.
    """
    try:
        host = ollama.normalize_host(request.args.get("host", ollama.DEFAULT_HOST))
    except ValueError as exc:
        raise PagesetError(str(exc)) from exc
    preferred = _bounded_text(request.args.get("model_key"), "model_key", 20) or None
    engine = _validated_engine(request.args.get("engine"))
    named = _bounded_text(request.args.get("model"), "model", 120)
    ollama_state = ollama.status(host)
    local_state = localai.status(preferred)
    return jsonify({
        "ok": True,
        "ollama": ollama_state,
        "local": local_state,
        "ai": engines.readiness(ollama_state, local_state, engine, named),
    })


@app.post("/api/ai/download")
def ai_download():
    """One-time download of a built-in model (user-initiated)."""
    if not localai.engine_available():
        return jsonify(
            {"ok": False,
             "error": "This install doesn't include the built-in AI engine; "
                      "use Ollama instead or install llama-cpp-python."}
        ), 400
    payload = _json_payload()
    key = _bounded_text(payload.get("model_key"), "model_key", 20) or None
    return jsonify({"ok": True, "download": localai.start_download(key)})


@app.get("/api/ai/download")
def ai_download_state():
    return jsonify({"ok": True, "download": localai.download_state()})


def _validated_engine(value) -> Optional[str]:
    """Which engine the user asked for, or None for "whichever is ready"."""
    if value in (None, "", engines.AUTO):
        return None
    if value not in engines.ENGINES:
        raise PagesetError("'engine' must be 'auto', 'ollama', or 'local'.")
    return value


def _labels_of(words) -> list:
    """The spoken text of each suggestion, whichever shape it came back in."""
    return [
        str(word.get("label", "") if isinstance(word, dict) else word)
        for word in words
    ]


@app.post("/api/ai/words")
def ai_words():
    """Generate suggestions with whichever engine is ready.

    Preference order: whichever engine the user chose, then a reachable Ollama
    server, then the built-in downloaded model (see engines.choose).
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
    # Steering: what the user rejected, what they kept and want more of, and
    # how their page set already words its buttons. All three only ever reach a
    # local model — see the grounding call below, which they never touch.
    avoid = _validated_labels(payload.get("avoid"), "avoid", 60)
    like = _validated_labels(payload.get("like"), "like", 20)
    style = _validated_labels(payload.get("style"), "style", 40)
    # Candidates already waiting in the tray. Not rejected and not on the page
    # — only used up, which is a third thing to tell a model (see prompts.py).
    already = _validated_labels(payload.get("already"), "already", 60)
    grounding_title = _bounded_text(
        payload.get("grounding_title"), "grounding_title", MAX_PAGE_NAME_CHARS
    )
    grounding_exclude = _validated_labels(
        payload.get("grounding_exclude"), "grounding_exclude", 20
    )
    args = {
        "category": category,
        "count": count,
        "kind": kind,
        "function": function,
        "existing": existing,
        "avoid": avoid,
        "like": like,
        "style": style,
        "already": already,
    }
    try:
        host = ollama.normalize_host(payload.get("host", ollama.DEFAULT_HOST))
    except ValueError as exc:
        raise PagesetError(str(exc)) from exc
    model = _bounded_text(
        payload.get("model", ollama.DEFAULT_MODEL), "model", 120, required=True
    )
    model_key = _bounded_text(payload.get("model_key"), "model_key", 20) or None
    preferred = _validated_engine(payload.get("engine"))
    ollama_state = ollama.status(host)
    local_state = localai.status(model_key)
    # An Ollama server with no models can't generate anything; engines.choose
    # falls through to the built-in engine instead of failing with "model not
    # found", and says so when it had to.
    engine, note = engines.choose(ollama_state, local_state, preferred)
    if engine is None:
        return jsonify(
            {"ok": False, "words": [],
             "error": engines.readiness(ollama_state, local_state)["summary"]}
        ), 400

    def generate(extra=None):
        call = {**args, **(extra or {})}
        if engine == engines.OLLAMA:
            return ollama.generate_words(host=host, model=model, **call)
        return localai.generate_words(model_key=model_key, **call)
    # Only look up reference facts once we know a model will actually run. Real
    # facts about the title stop a small model naming the wrong thing (e.g.
    # cartoon characters for "Roblox characters"). Best-effort: unused if
    # offline.
    #
    # The page title is the only thing that goes out, and this call is written
    # so that nothing else *can*: `category` is the page title, and the
    # remaining arguments are Wikipedia article titles this server named in an
    # earlier answer. The user's own words — `existing`, `avoid`, `like`,
    # `style` — are not in scope of this call by construction, and a test pins
    # that they never reach it.
    source = grounding.lookup(
        category,
        requested=grounding_requested,
        title=grounding_title or None,
        exclude=grounding_exclude,
    )
    args["reference"] = source["text"]
    # Ask for more than the user wants: cleaning drops repeats, the page title
    # echoed back, and anything already on the page, so a request for exactly
    # ten reliably delivers fewer than ten.
    args["count"] = prompts.overask(count)
    started = time.monotonic()
    words, error = generate()
    elapsed = time.monotonic() - started
    reported = {key: value for key, value in source.items() if key != "text"}
    if error:
        return jsonify({"ok": False, "error": error, "words": [],
                        "engine": engine, "grounding": reported}), 502

    def usable(candidates):
        """The last gate before a suggestion becomes a planned button.

        The engines clean their own replies, and this cleans again: it is the
        one place both of them pass through, so the promise that nothing
        already on the page — and nothing the user rejected — comes back as a
        suggestion holds whichever engine ran, and holds for the merged
        answer of two rounds as well as for one.
        """
        return prompts.clean_items(
            candidates, count, kind=kind, category=category,
            exclude=[*existing, *avoid, *already],
        )

    words = usable(words)
    # One retry, and only for the answer that is otherwise a dead end: fewer
    # than half of what was asked for. A second call costs the user real
    # seconds on a laptop model, which is worth spending to turn "Added 1"
    # into a usable set and not worth spending to turn 9 into 10 — and never
    # worth spending when the first call was slow enough that a second would
    # push the whole request past the browser's deadline. A thin answer is
    # still an answer; a request that times out is nothing at all.
    retried = False
    if len(words) < max(1, count // 2) and elapsed <= RETRY_BUDGET_SECONDS:
        retried = True
        more, retry_error = generate({"already": [*already, *_labels_of(words)]})
        if not retry_error:
            words = usable([*words, *more])
    return jsonify({
        "ok": True, "words": words, "engine": engine, "grounding": reported,
        # What the user asked for versus what survived, so the panel can say
        # "6 of the 10" rather than silently handing back fewer.
        "requested": count, "returned": len(words), "retried": retried,
        "note": note,
    })


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
            # fixed http://127.0.0.1:<port> instance check
            with urllib.request.urlopen(  # noqa: S310
                # fixed http://127.0.0.1:<port> instance check
                urllib.request.Request(f"{url}/api/focus", method="POST"),  # noqa: S310
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
