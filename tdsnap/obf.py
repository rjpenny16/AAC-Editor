"""Open Board Format (.obf / .obz): boards in, boards out.

OBF is the AAC interchange format CoughDrop and several other tools speak. A
single board is a JSON file; a board set is a zip (``.obz``) with a
``manifest.json`` naming the root board and every board, image and sound
inside it.

Reading turns a board into the shape the rest of this app already handles —
a page with a grid, speaking items placed in slots, and the buttons that open
other boards listed separately — so an imported board goes through the same
review, placement and confirmation as anything typed in. Writing turns a page
set's pages into one board each, with ``load_board`` links between them.

Symbols are neither read nor written: OBF images point at files or URLs, TD
Snap's symbols are licensed content that cannot leave the page set, and this
app writes no images anywhere. Labels, spoken text, layout, function colours
and links travel; pictures do not, and the README says so.
"""

from __future__ import annotations

import io
import json
import posixpath
import re
import sqlite3
import zipfile
from typing import Any

from . import colors, schema, templates
from .errors import PagesetError

FORMAT = "open-board-0.1"
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_BOARD_BYTES = 8 * 1024 * 1024
_MAX_BOARDS = 2000  # a full TD Snap page set runs to several hundred pages
_MAX_BUTTONS = 400
_RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


# ---------------------------------------------------------------------------
# reading


def read(data: bytes, filename: str = "") -> dict:
    """Parse an ``.obf`` or ``.obz`` into pages.

    Returns ``{"root": <page index or None>, "pages": [page, ...],
    "warnings": [str, ...]}``. A page is ``{"title", "grid": {"cols", "rows"},
    "items": [{"label", "message", "slot", "function"}], "links": [{"slot",
    "label", "board"}], "skipped": int}``; ``board`` is the index in ``pages``
    of the board a link opens, or ``None`` when it points outside the file.
    """
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise PagesetError("The board file is empty.")
    if len(data) > _MAX_ARCHIVE_BYTES:
        raise PagesetError("The board file is larger than AAC Editor will open (64 MB).")
    if data[:2] == b"PK":
        return _read_obz(bytes(data))
    board = _load_json(bytes(data), filename or "board")
    page, warnings = _page_from_board(board, {}, [])
    return {"root": 0, "pages": [page], "warnings": warnings}


def _load_json(raw: bytes, name: str) -> dict:
    if len(raw) > _MAX_BOARD_BYTES:
        raise PagesetError(f"{name!r} is larger than a board should be.")
    try:
        parsed = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PagesetError(f"{name!r} is not an Open Board Format JSON file.") from exc
    if not isinstance(parsed, dict):
        raise PagesetError(f"{name!r} is not an Open Board Format board.")
    return parsed


def _read_obz(data: bytes) -> dict:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise PagesetError("The .obz file is not a readable archive.") from exc
    with archive:
        names = set(archive.namelist())
        if "manifest.json" not in names:
            raise PagesetError("The .obz file has no manifest.json, so its boards cannot be found.")
        manifest = _load_json(archive.read("manifest.json"), "manifest.json")
        paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
        board_paths = paths.get("boards") if isinstance(paths.get("boards"), dict) else {}
        ordered = []
        root_path = _clean_path(manifest.get("root"))
        if root_path:
            ordered.append(root_path)
        for path in board_paths.values():
            cleaned = _clean_path(path)
            if cleaned and cleaned not in ordered:
                ordered.append(cleaned)
        # Boards the manifest forgot still count if they are plainly boards.
        for name in sorted(names):
            if name.endswith(".obf") and name not in ordered:
                ordered.append(name)
        ordered = [path for path in ordered if path in names]
        if not ordered:
            raise PagesetError("The .obz file contains no boards.")
        if len(ordered) > _MAX_BOARDS:
            raise PagesetError(f"The .obz file holds more than {_MAX_BOARDS} boards.")
        boards = []
        for path in ordered:
            board = _load_json(archive.read(path), path)
            boards.append((path, board))
    # Links name a board by id or by path; both resolve to a page index.
    index_by_id: dict[str, int] = {}
    index_by_path: dict[str, int] = {}
    for index, (path, board) in enumerate(boards):
        index_by_path[path] = index
        board_id = str(board.get("id") or "").strip()
        if board_id:
            index_by_id.setdefault(board_id, index)
    warnings: list[str] = []
    pages = []
    for _path, board in boards:
        page, page_warnings = _page_from_board(board, index_by_id, list(index_by_path.items()))
        pages.append(page)
        warnings.extend(page_warnings)
    root = index_by_path.get(root_path, 0) if root_path else 0
    return {"root": root, "pages": pages, "warnings": warnings}


def _clean_path(value: Any) -> str:
    path = str(value or "").replace("\\", "/").lstrip("/")
    if not path or ".." in path.split("/"):
        return ""
    return posixpath.normpath(path)


def _page_from_board(board: dict, index_by_id: dict, path_index: list) -> tuple[dict, list[str]]:
    title = str(board.get("name") or board.get("id") or "Imported board").strip() or "Imported board"
    grid = board.get("grid") if isinstance(board.get("grid"), dict) else {}
    raw_buttons = board.get("buttons") if isinstance(board.get("buttons"), list) else []
    if len(raw_buttons) > _MAX_BUTTONS:
        raise PagesetError(f"Board {title!r} holds more than {_MAX_BUTTONS} buttons.")
    order = grid.get("order") if isinstance(grid.get("order"), list) else []
    rows = _dimension(grid.get("rows"), len(order))
    cols = _dimension(grid.get("columns"), max((len(row) for row in order if isinstance(row, list)), default=0))
    slots: dict[str, int] = {}
    for row_index, row in enumerate(order[:rows]):
        if not isinstance(row, list):
            continue
        for col_index, cell in enumerate(row[:cols]):
            if cell is not None and str(cell) not in slots:
                slots[str(cell)] = row_index * cols + col_index
    items, links, warnings = [], [], []
    skipped = 0
    seen = set()
    for raw in raw_buttons:
        if not isinstance(raw, dict) or raw.get("hidden"):
            skipped += 1
            continue
        label = str(raw.get("label") or "").strip()
        button_id = str(raw.get("id") if raw.get("id") is not None else "").strip()
        slot = slots.get(button_id)
        if not label or label.casefold() in seen:
            skipped += 1
            continue
        target = raw.get("load_board") if isinstance(raw.get("load_board"), dict) else None
        if target is not None:
            board_index = index_by_id.get(str(target.get("id") or "").strip())
            if board_index is None:
                cleaned = _clean_path(target.get("path"))
                board_index = next((index for path, index in path_index if path == cleaned), None)
            links.append({"slot": slot, "label": label, "board": board_index})
            seen.add(label.casefold())
            continue
        action = str(raw.get("action") or "").strip()
        if action or (isinstance(raw.get("actions"), list) and raw.get("actions")):
            # "+x" and ":action" buttons drive a keyboard or the app, not speech.
            skipped += 1
            continue
        message = str(raw.get("vocalization") or "").strip()
        items.append({
            "label": label,
            "message": message if message and message.casefold() != label.casefold() else None,
            "slot": slot,
            "function": colors.function_for_hex(_hex_color(raw.get("border_color"))),
        })
        seen.add(label.casefold())
    if skipped:
        warnings.append(
            f"{skipped} button{'' if skipped == 1 else 's'} on “{title}” "
            "could not be imported (hidden, unlabelled, repeated, or a keyboard action)."
        )
    if cols * rows == 0:
        warnings.append(f"“{title}” has no grid; its buttons will be placed in order.")
    return {
        "title": title,
        "grid": {"cols": cols, "rows": rows},
        "items": items,
        "links": links,
        "skipped": skipped,
    }, warnings


def _dimension(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return number if number > 0 else max(0, fallback)


def _hex_color(value: Any) -> str | None:
    """A CSS colour as '#RRGGBB', or None for anything else (including alpha)."""
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.upper()
    match = _RGB.match(text)
    if match:
        red, green, blue = (min(255, int(part)) for part in match.groups())
        return f"#{red:02X}{green:02X}{blue:02X}"
    return None


# ---------------------------------------------------------------------------
# writing


def write(pages: list[dict], *, name: str = "AAC Editor export", locale: str = "en") -> bytes:
    """Build an ``.obz`` from pages in the shape ``read`` returns.

    Each page becomes one board; ``links`` become ``load_board`` buttons
    pointing at the board for the page they name. The first page is the root.
    """
    if not pages:
        raise PagesetError("There are no pages to export.")
    if len(pages) > _MAX_BOARDS:
        raise PagesetError(f"More than {_MAX_BOARDS} pages cannot be exported at once.")
    ids = [str(page.get("id") or index + 1) for index, page in enumerate(pages)]
    paths = [f"boards/{_slug(page.get('title'), index)}.obf" for index, page in enumerate(pages)]
    manifest = {
        "format": FORMAT,
        "root": paths[0],
        "paths": {"boards": dict(zip(ids, paths)), "images": {}, "sounds": {}},
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _dumps(manifest))
        for index, page in enumerate(pages):
            archive.writestr(paths[index], _dumps(_board(page, ids, paths, index, locale, name)))
    return buffer.getvalue()


def _board(page: dict, ids: list[str], paths: list[str], index: int, locale: str, set_name: str) -> dict:
    grid = page.get("grid") or {}
    cols, rows = int(grid.get("cols") or 0), int(grid.get("rows") or 0)
    buttons = []
    placed: dict[int, str] = {}
    next_id = 1

    def add(entry: dict, slot) -> None:
        nonlocal next_id
        entry["id"] = str(next_id)
        next_id += 1
        buttons.append(entry)
        if isinstance(slot, int) and 0 <= slot < cols * rows and slot not in placed:
            placed[slot] = entry["id"]

    for item in page.get("items") or []:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        entry: dict[str, Any] = {"label": label}
        message = str(item.get("message") or "").strip()
        if message and message.casefold() != label.casefold():
            entry["vocalization"] = message
        border = colors.FUNCTION_BORDER_COLORS.get(str(item.get("function") or ""))
        if border:
            entry["border_color"] = border
        add(entry, item.get("slot"))
    for link in page.get("links") or []:
        label = str(link.get("label") or "").strip()
        target = link.get("board")
        if not label or not isinstance(target, int) or not 0 <= target < len(ids):
            continue
        add({
            "label": label,
            "load_board": {"id": ids[target], "path": paths[target]},
        }, link.get("slot"))
    # Buttons without a reviewed slot take the first free cells, in order.
    free = [slot for slot in range(cols * rows) if slot not in placed]
    for entry in buttons:
        if entry["id"] not in placed.values() and free:
            placed[free.pop(0)] = entry["id"]
    order = [
        [placed.get(row * cols + col) for col in range(cols)] for row in range(rows)
    ] if cols and rows else []
    return {
        "format": FORMAT,
        "id": ids[index],
        "locale": locale,
        "name": str(page.get("title") or f"Page {index + 1}"),
        "description_html": f"Exported from {set_name} by AAC Editor without symbols.",
        "buttons": buttons,
        "grid": {"rows": rows, "columns": cols, "order": order},
        "images": [],
        "sounds": [],
    }


def _slug(title: Any, index: int) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(title or "")).strip("-").lower()[:40]
    return f"{index + 1:03d}-{text or 'board'}"


def _dumps(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# a page set as pages


def pages_from_pageset(conn: sqlite3.Connection) -> list[dict]:
    """Every vocabulary page of a TD Snap page set, home page first.

    Speaking buttons become items with their label, spoken message and
    function colour; buttons that open another page become links; anything
    else (actions, keyboards, hidden buttons) is left out and counted.
    """
    conn.row_factory = sqlite3.Row
    home = None
    try:
        row = conn.execute("SELECT DefaultHomePageUniqueId FROM PageSetProperties LIMIT 1").fetchone()
        home = row[0] if row else None
    except sqlite3.Error:
        home = None
    page_rows = conn.execute(
        "SELECT Id, UniqueId, COALESCE(NULLIF(Title, ''), 'Page ' || Id) AS Title "
        "FROM Page WHERE PageType = 1 ORDER BY Title COLLATE NOCASE"
    ).fetchall()
    if not page_rows:
        raise PagesetError("This page set has no vocabulary pages to export.")
    page_rows.sort(key=lambda row: 0 if home and row["UniqueId"] == home else 1)
    index_by_uuid = {row["UniqueId"]: index for index, row in enumerate(page_rows)}
    default_cols, default_rows = schema.parse_grid(
        conn.execute("SELECT GridDimension FROM PageSetProperties LIMIT 1").fetchone()[0]
    )
    pages = []
    for row in page_rows:
        layout = conn.execute(
            "SELECT Id, PageLayoutSetting FROM PageLayout WHERE PageId = ? "
            "ORDER BY CASE WHEN PageLayoutSetting LIKE ? THEN 0 ELSE 1 END, Id",
            (row["Id"], f"{default_cols},{default_rows},%"),
        ).fetchone()
        cols, rows = (schema.parse_grid(layout["PageLayoutSetting"]) if layout
                      else (default_cols, default_rows))
        items, links, skipped = [], [], 0
        if layout:
            for cell in conn.execute(
                "SELECT button.Label AS Label, button.Message AS Message, "
                "button.BorderColor AS BorderColor, button.CommandFlags AS CommandFlags, "
                "placement.GridPosition AS GridPosition, "
                "(SELECT PageUniqueId FROM ButtonPageLink link WHERE link.ButtonId = button.Id "
                " LIMIT 1) AS LinkedPage "
                "FROM ElementPlacement placement "
                "JOIN ElementReference ref ON ref.Id = placement.ElementReferenceId "
                "JOIN Button button ON button.ElementReferenceId = ref.Id "
                "WHERE placement.PageLayoutId = ? AND placement.Visible = 1",
                (layout["Id"],),
            ):
                label = (cell["Label"] or "").strip()
                if not label:
                    skipped += 1
                    continue
                col, grid_row = schema.parse_grid_position(cell["GridPosition"])
                slot = grid_row * cols + col
                if cell["LinkedPage"]:
                    links.append({
                        "slot": slot, "label": label,
                        "board": index_by_uuid.get(cell["LinkedPage"]),
                    })
                    continue
                if cell["CommandFlags"] not in (None, templates.COMMAND_FLAGS_SPEAK):
                    skipped += 1  # an action or keyboard button
                    continue
                message = (cell["Message"] or "").strip()
                border = cell["BorderColor"]
                items.append({
                    "label": label,
                    "message": message if message and message.casefold() != label.casefold() else None,
                    "slot": slot,
                    "function": colors.function_for_hex(
                        colors.hex_from_argb(border) if border is not None else None
                    ),
                })
        pages.append({
            "id": row["UniqueId"], "title": row["Title"],
            "grid": {"cols": cols, "rows": rows},
            "items": sorted(items, key=lambda item: item["slot"]),
            "links": sorted(links, key=lambda link: link["slot"]),
            "skipped": skipped,
        })
    return pages

