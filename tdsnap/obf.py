"""Open Board Format: read and write ``.obf``/``.obz``, and map them to a page set.

Open Board Format is the AAC interchange standard (https://www.openboardformat.org):
an ``.obf`` is one board as JSON, and an ``.obz`` is a zip of boards with a
``manifest.json`` naming the root. CoughDrop writes it, and several other
tools read or write it, so it is the one route by which a clinician's work in
TD Snap can leave TD Snap, and work from elsewhere can arrive.

Everything here is file in and file out. Nothing drives an app, nothing reaches
the network, and nothing writes to a page set: ``builder.add_linked_pages`` is
the write path, and it only ever receives what :func:`plan_import` produced and
the user reviewed.

**The canonical model.** Reading either direction produces the same plain,
JSON-ready shape, so the browser, the planner, the writer, and the tests all
speak one language::

    {"root": "<board id>",
     "boards": [{"id", "name", "locale", "rows", "columns",
                 "cells": [{"row", "col", "label", "message", "border", "link"}]}],
     "skipped": [{"board", "label", "reason"}],
     "notes": ["..."]}

``message`` is what the button says when it differs from its label (TD Snap's
Message, OBF's ``vocalization``); ``border`` is ``#RRGGBB`` or ``None``; and
``link`` is the id of another board *in the same set*, or ``None`` for a
button that speaks. Boards come root first, then in the order links reach
them, so the first board is always the one a user starts on.

**What does not come across, and why it is said rather than hidden.** Every
button that cannot be represented is listed in ``skipped`` with its board, its
label, and the reason, because an import that silently drops a third of a
board is worse than one that refuses. The standing exclusions:

* *Symbols.* TD Snap's symbols are licensed content; an export writes labels,
  messages, layout, and links and no images at all. Pictures in an imported
  board are not carried either: a live TD Snap edit searches TD Snap's own
  library for each new button, and the exported-file path writes no symbols.
* *Actions.* OBF's specialty actions (``:clear``, ``:home``, spelling ``+a``…)
  and TD Snap's non-speaking commands have no counterpart on the other side
  that this app can write safely.
* *Colours.* Only the five communicative-function border colours are written
  into a page set (see ``colors.py``); any other border is left off and
  counted, never approximated.

Reading is bounded throughout — entry counts, bytes per board, total bytes,
grid size — and never extracts to disk, so a hostile or accidental archive
costs a refusal rather than the machine.
"""

import contextlib
import io
import json
import math
import os
import posixpath
import re
import sqlite3
import tempfile
import zipfile
from collections import deque
from typing import Optional, Union

from . import builder, pageset, schema
from .colors import FUNCTION_BORDER_COLORS
from .errors import PagesetError

FORMAT = "open-board-0.1"

# Bounds on what a reader will look at. Generous for real board sets — the
# largest CoughDrop core sets are a few hundred boards of well under 100 KB
# each — and small enough that a zip bomb is refused rather than inflated.
MAX_BOARDS = 100
MAX_ZIP_ENTRIES = 20_000
MAX_BOARD_BYTES = 4 * 1024 * 1024
MAX_TOTAL_JSON_BYTES = 48 * 1024 * 1024
MAX_GRID_SIDE = 40
MAX_BUTTONS_PER_BOARD = MAX_GRID_SIDE * MAX_GRID_SIDE

MAX_LABEL_LENGTH = builder.MAX_LABEL_LENGTH
MAX_MESSAGE_LENGTH = builder.MAX_MESSAGE_LENGTH
MAX_TITLE_LENGTH = builder.MAX_TITLE_LENGTH

SYMBOLS_NOTE = (
    "Symbols are not included. TD Snap's symbols are licensed content, so an "
    "Open Board export carries labels, spoken messages, layout, and links only."
)

_CLINICAL_HEX = {value.upper() for value in FUNCTION_BORDER_COLORS.values()}

Source = Union[str, os.PathLike, io.IOBase]


# ---------------------------------------------------------------------------
# small helpers


def _text(value) -> str:
    """A label-like value as one line of trimmed text; anything else is empty."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _identifier(value) -> Optional[str]:
    """Board and button ids are strings in the spec and numbers in the wild."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        value = str(int(value)) if float(value).is_integer() else str(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _member_path(value) -> Optional[str]:
    """A zip member path, normalized the way manifests and ``load_board`` spell it."""
    if not isinstance(value, str) or not value.strip():
        return None
    path = posixpath.normpath(value.strip().replace("\\", "/")).lstrip("/")
    return None if path.startswith("..") or path == "." else path


_RGB = re.compile(
    r"^rgba?\(\s*(\d{1,3}(?:\.\d+)?)\s*,\s*(\d{1,3}(?:\.\d+)?)\s*,\s*(\d{1,3}(?:\.\d+)?)"
    r"(?:\s*,\s*[\d.]+)?\s*\)$",
    re.IGNORECASE,
)


def parse_color(value) -> Optional[str]:
    """An OBF colour — ``rgb(…)``, ``rgba(…)``, ``#RGB``, or ``#RRGGBB`` — as ``#RRGGBB``.

    Anything else (a CSS colour name, a malformed string) is ``None``: a
    colour that has to be guessed at is not one worth writing.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    match = _RGB.match(text)
    if match:
        channels = [min(255, round(float(part))) for part in match.groups()]
        return "#{:02X}{:02X}{:02X}".format(*channels)
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.upper()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", text):
        return "#" + "".join(ch * 2 for ch in text[1:]).upper()
    return None


def css_color(hex_color: str) -> str:
    """``#RRGGBB`` as the ``rgb(r, g, b)`` form OBF files conventionally use."""
    value = int(hex_color.lstrip("#"), 16)
    return f"rgb({value >> 16 & 0xFF}, {value >> 8 & 0xFF}, {value & 0xFF})"


def is_clinical_color(hex_color: Optional[str]) -> bool:
    """True for the five communicative-function colours a page set may carry."""
    return bool(hex_color) and hex_color.upper() in _CLINICAL_HEX


def _skip(skipped: list, board: str, label: str, reason: str) -> None:
    skipped.append({"board": board, "label": label, "reason": reason})


# ---------------------------------------------------------------------------
# reading


def _load_json(data: bytes, what: str):
    if len(data) > MAX_BOARD_BYTES:
        raise PagesetError(f"{what} is larger than AAC Editor will read "
                           f"({MAX_BOARD_BYTES // (1024 * 1024)} MB).")
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PagesetError(f"{what} is not valid JSON: {exc}") from exc


def _raw_board(raw, what: str) -> dict:
    if not isinstance(raw, dict):
        raise PagesetError(f"{what} is not an Open Board board (expected a JSON object).")
    fmt = raw.get("format")
    if fmt is not None and (not isinstance(fmt, str) or not fmt.startswith("open-board-")):
        raise PagesetError(f"{what} is not in Open Board Format (format is {fmt!r}).")
    if not isinstance(raw.get("buttons", []), list):
        raise PagesetError(f"{what} has a 'buttons' value that is not a list.")
    return raw


def _grid_positions(raw: dict, buttons: dict, name: str, skipped: list):
    """``(rows, columns, [(row, col, button_id)])`` for one board.

    The grid's ``order`` is authoritative: a button the grid does not place is
    not on the board as anyone sees it. A board with no usable grid is laid
    out in the order its buttons are listed, which is what readers of the
    format do.
    """
    grid = raw.get("grid") if isinstance(raw.get("grid"), dict) else {}

    def dimension(key):
        value = grid.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        value = int(value)
        return value if value > 0 else None

    rows, columns = dimension("rows"), dimension("columns")
    order = grid.get("order")
    placed = []
    if isinstance(order, list) and order and all(isinstance(line, list) for line in order):
        rows = rows or len(order)
        columns = columns or max(len(line) for line in order)
        seen = set()
        for row_index, line in enumerate(order[:MAX_GRID_SIDE]):
            for col_index, entry in enumerate(line[:MAX_GRID_SIDE]):
                button_id = _identifier(entry)
                if button_id is None or button_id not in buttons or button_id in seen:
                    continue
                seen.add(button_id)
                placed.append((row_index, col_index, button_id))
        for button_id, button in buttons.items():
            if button_id not in seen and not button.get("hidden"):
                _skip(skipped, name, _text(button.get("label")),
                      "is not placed on the board's grid")
    else:
        ids = list(buttons)
        columns = columns or max(1, math.ceil(math.sqrt(len(ids) or 1)))
        columns = min(columns, MAX_GRID_SIDE)
        placed = [(index // columns, index % columns, button_id)
                  for index, button_id in enumerate(ids)]
        rows = max(rows or 0, math.ceil(len(ids) / columns) if ids else 1)
    rows = max(1, min(rows or 1, MAX_GRID_SIDE))
    columns = max(1, min(columns or 1, MAX_GRID_SIDE))
    placed = [(r, c, b) for r, c, b in placed if r < rows and c < columns]
    return rows, columns, placed


def _action_of(button: dict) -> Optional[str]:
    """The specialty action a button performs instead of speaking, if any."""
    actions = []
    if isinstance(button.get("action"), str) and button["action"].strip():
        actions.append(button["action"].strip())
    if isinstance(button.get("actions"), list):
        actions += [a.strip() for a in button["actions"] if isinstance(a, str) and a.strip()]
    for action in actions:
        if action == ":speak":
            continue
        return action
    return None


def _parse_board(raw: dict, fallback_id: str, skipped: list, counters: dict) -> dict:
    """One raw OBF board as the canonical board, with every drop recorded."""
    board_id = _identifier(raw.get("id")) or fallback_id
    name = _text(raw.get("name")) or f"Board {board_id}"
    buttons = {}
    for index, button in enumerate(raw.get("buttons", [])[:MAX_BUTTONS_PER_BOARD]):
        if not isinstance(button, dict):
            continue
        button_id = _identifier(button.get("id")) or f"#{index}"
        buttons.setdefault(button_id, button)
    if len(raw.get("buttons", [])) > MAX_BUTTONS_PER_BOARD:
        _skip(skipped, name, "", f"has more than {MAX_BUTTONS_PER_BOARD} buttons; "
              "the rest were not read")

    rows, columns, placed = _grid_positions(raw, buttons, name, skipped)
    cells = []
    labels = set()
    for row, col, button_id in placed:
        button = buttons[button_id]
        label = _text(button.get("label"))
        if button.get("hidden") is True:
            _skip(skipped, name, label, "is hidden on the original board")
            continue
        if not label:
            _skip(skipped, name, "", "has no label, only a picture")
            continue
        action = _action_of(button)
        if action is not None:
            _skip(skipped, name, label,
                  f"performs an action ({action}) rather than speaking or opening a board")
            continue
        load = button.get("load_board")
        link = None
        if isinstance(load, dict):
            link = {"id": _identifier(load.get("id")), "path": _member_path(load.get("path"))}
        elif _text(button.get("url")) or _text(button.get("video")):
            _skip(skipped, name, label, "opens a web link")
            continue
        if len(label) > MAX_LABEL_LENGTH:
            _skip(skipped, name, label[:MAX_LABEL_LENGTH] + "…",
                  f"has a label longer than {MAX_LABEL_LENGTH} characters")
            continue
        message = _text(button.get("vocalization")) or None
        if message == label:
            message = None
        if message and len(message) > MAX_MESSAGE_LENGTH:
            _skip(skipped, name, label,
                  f"speaks a message longer than {MAX_MESSAGE_LENGTH} characters")
            continue
        folded = label.casefold()
        if folded in labels:
            _skip(skipped, name, label, "appears more than once on this board")
            continue
        labels.add(folded)
        if button.get("image_id") is not None or isinstance(button.get("image"), dict):
            counters["pictures"] += 1
        cells.append({
            "row": row,
            "col": col,
            "label": label,
            "message": message,
            "border": parse_color(button.get("border_color")),
            "link": link,
        })
    locale = raw.get("locale") if isinstance(raw.get("locale"), str) else None
    return {"id": board_id, "name": name[:MAX_TITLE_LENGTH].strip() or name,
            "locale": locale, "rows": rows, "columns": columns, "cells": cells}


def _resolve_links(boards: list, by_path: dict, skipped: list) -> None:
    """Point every link at a board in this set by id, or drop it by name."""
    ids = {board["id"] for board in boards}
    for board in boards:
        kept = []
        for cell in board["cells"]:
            link = cell["link"]
            if link is None:
                kept.append(cell)
                continue
            target = link["id"] if link["id"] in ids else by_path.get(link["path"])
            if target is None:
                _skip(skipped, board["name"], cell["label"],
                      "opens a board that is not in this file")
                continue
            if target == board["id"]:
                _skip(skipped, board["name"], cell["label"], "opens the board it is on")
                continue
            kept.append({**cell, "link": target, "message": None})
        board["cells"] = kept


def _order_boards(boards: list, root: str) -> list:
    """Root first, then breadth-first along links, then anything unreachable."""
    by_id = {board["id"]: board for board in boards}
    ordered, seen = [], set()
    queue = deque([root] if root in by_id else [])
    while queue:
        board_id = queue.popleft()
        if board_id in seen:
            continue
        seen.add(board_id)
        ordered.append(by_id[board_id])
        queue.extend(cell["link"] for cell in by_id[board_id]["cells"] if cell["link"])
    ordered += [board for board in boards if board["id"] not in seen]
    return ordered


def _finish(boards: list, root: str, skipped: list, counters: dict) -> dict:
    if not boards:
        raise PagesetError("This file has no boards in it.")
    by_id = {}
    for board in boards:
        if board["id"] in by_id:
            _skip(skipped, board["name"], "",
                  "shares its id with another board in this file, so only the first was read")
            continue
        by_id[board["id"]] = board
    boards = list(by_id.values())
    if root not in by_id:
        root = boards[0]["id"]
    ordered = _order_boards(boards, root)
    notes = []
    if counters["pictures"]:
        notes.append(
            f"Pictures on {counters['pictures']} button"
            f"{'' if counters['pictures'] == 1 else 's'} are not brought across. "
            "TD Snap looks up its own symbols for buttons added while it is open; "
            "an exported file gets no symbols."
        )
    return {"format": FORMAT, "root": root, "boards": ordered,
            "skipped": skipped, "notes": notes}


def _read_single(data: bytes) -> dict:
    skipped: list = []
    counters = {"pictures": 0}
    raw = _raw_board(_load_json(data, "This board"), "This board")
    board = _parse_board(raw, "1", skipped, counters)
    _resolve_links([board], {}, skipped)
    return _finish([board], board["id"], skipped, counters)


def _read_zip(archive: zipfile.ZipFile) -> dict:
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise PagesetError(
            f"This .obz holds {len(infos)} files; AAC Editor reads at most {MAX_ZIP_ENTRIES}."
        )
    members = {}
    for info in infos:
        path = _member_path(info.filename)
        if path and not info.is_dir():
            members.setdefault(path, info)

    budget = {"left": MAX_TOTAL_JSON_BYTES}

    def read_member(path: str, what: str):
        info = members[path]
        if info.file_size > MAX_BOARD_BYTES:
            raise PagesetError(f"{what} is larger than AAC Editor will read.")
        with archive.open(info) as handle:
            data = handle.read(MAX_BOARD_BYTES + 1)
        budget["left"] -= len(data)
        if budget["left"] < 0:
            raise PagesetError("The boards in this .obz are larger in total than "
                               "AAC Editor will read.")
        return _load_json(data, what)

    if "manifest.json" not in members:
        raise PagesetError("This is a zip file but not an Open Board .obz: it has no "
                           "manifest.json.")
    manifest = read_member("manifest.json", "The .obz manifest")
    if not isinstance(manifest, dict):
        raise PagesetError("The .obz manifest is not a JSON object.")
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    listed = paths.get("boards") if isinstance(paths.get("boards"), dict) else {}
    board_paths: dict[str, str] = {}
    for key, value in listed.items():
        path = _member_path(value)
        if path:
            board_paths.setdefault(path, _identifier(key) or path)
    root_path = _member_path(manifest.get("root"))
    if root_path and root_path not in board_paths:
        board_paths = {root_path: root_path, **board_paths}
    if not board_paths:
        board_paths = {path: path for path in sorted(members) if path.endswith(".obf")}
    if len(board_paths) > MAX_BOARDS:
        raise PagesetError(
            f"This .obz has {len(board_paths)} boards; AAC Editor imports at most "
            f"{MAX_BOARDS} at a time."
        )

    skipped: list = []
    counters = {"pictures": 0}
    boards, by_path = [], {}
    root = None
    for path, fallback in board_paths.items():
        if path not in members:
            _skip(skipped, path, "", "is listed in the manifest but missing from the file")
            continue
        raw = _raw_board(read_member(path, f"Board {path!r}"), f"Board {path!r}")
        board = _parse_board(raw, fallback, skipped, counters)
        by_path[path] = board["id"]
        boards.append(board)
        if path == root_path:
            root = board["id"]
    _resolve_links(boards, by_path, skipped)
    return _finish(boards, root or (boards[0]["id"] if boards else ""), skipped, counters)


def read(source: Source) -> dict:
    """Read an ``.obf`` or ``.obz`` — a path or a binary file object — as a board set.

    The kind is decided by content, not by extension: a zip is an ``.obz``,
    anything else is tried as a single ``.obf``.
    """
    with contextlib.ExitStack() as stack:
        if isinstance(source, (str, os.PathLike)):
            handle = stack.enter_context(open(source, "rb"))
        else:
            handle = source
        start = handle.read(4)
        handle.seek(0)
        if start == b"PK\x03\x04":
            try:
                archive = stack.enter_context(zipfile.ZipFile(handle))
            except zipfile.BadZipFile as exc:
                raise PagesetError(f"This .obz could not be opened: {exc}") from exc
            try:
                return _read_zip(archive)
            except (zipfile.BadZipFile, OSError, EOFError) as exc:
                raise PagesetError(f"This .obz is damaged: {exc}") from exc
        data = handle.read(MAX_BOARD_BYTES + 1)
        return _read_single(data)


def read_bytes(data: bytes) -> dict:
    """:func:`read` for content already in memory."""
    return read(io.BytesIO(data))


# ---------------------------------------------------------------------------
# writing


def board_to_obf(board: dict, board_paths: dict[str, str]) -> dict:
    """One canonical board as an OBF document."""
    buttons, order = [], [[None] * board["columns"] for _ in range(board["rows"])]
    for index, cell in enumerate(
        sorted(board["cells"], key=lambda cell: (cell["row"], cell["col"]))
    ):
        button_id = str(index + 1)
        button = {"id": button_id, "label": cell["label"]}
        if cell.get("message"):
            button["vocalization"] = cell["message"]
        if cell.get("border"):
            button["border_color"] = css_color(cell["border"])
        if cell.get("link"):
            button["load_board"] = {"id": cell["link"], "path": board_paths[cell["link"]]}
        buttons.append(button)
        order[cell["row"]][cell["col"]] = button_id
    document = {
        "format": FORMAT,
        "id": board["id"],
        "name": board["name"],
        "buttons": buttons,
        "grid": {"rows": board["rows"], "columns": board["columns"], "order": order},
        "images": [],
        "sounds": [],
        "ext_aac_editor_symbols": "omitted",
    }
    if board.get("locale"):
        document["locale"] = board["locale"]
    return document


def to_obz_bytes(boardset: dict) -> bytes:
    """A board set as the bytes of an ``.obz``.

    Board files are numbered rather than named after their ids, because a
    TD Snap page id is a GUID and a board id from elsewhere can be anything;
    links carry both the id and the path, as the format recommends.
    """
    board_paths = {
        board["id"]: f"boards/{index + 1}.obf"
        for index, board in enumerate(boardset["boards"])
    }
    manifest = {
        "format": FORMAT,
        "root": board_paths[boardset["root"]],
        "paths": {"boards": board_paths, "images": {}, "sounds": {}},
        "ext_aac_editor_note": SYMBOLS_NOTE,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for board in boardset["boards"]:
            archive.writestr(
                board_paths[board["id"]],
                json.dumps(board_to_obf(board, board_paths), ensure_ascii=False, indent=1),
            )
    return buffer.getvalue()


def write_obz(boardset: dict, dest_path: str) -> str:
    """Write *boardset* to *dest_path* atomically (temp file, then replace)."""
    data = to_obz_bytes(boardset)
    directory = os.path.dirname(os.path.abspath(dest_path)) or os.curdir
    descriptor, temporary = tempfile.mkstemp(prefix=".aac-editor-", suffix=".obz",
                                             dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, dest_path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(temporary)
    return dest_path


# ---------------------------------------------------------------------------
# a TD Snap page set as a board set


def _command_parts(serialized) -> Optional[list[dict]]:
    """The commands of a TD Snap CommandSequence, or ``None`` when unreadable."""
    try:
        document = json.loads(serialized or "")
    except (TypeError, ValueError):
        return None
    values = document.get("$values") if isinstance(document, dict) else None
    if not isinstance(values, list) or not all(isinstance(v, dict) for v in values):
        return None
    return values


def export_pageset(conn: sqlite3.Connection) -> dict:
    """Every vocabulary page of a TD Snap page set, as a canonical board set.

    Read-only. A button is exported when it speaks, opens another vocabulary
    page in this page set, or both; everything else is named in ``skipped``
    with the reason, so a clinician can see what the export is missing before
    they rely on it somewhere else.
    """
    grid = pageset.grid_dimension(conn)
    pages = conn.execute(
        "SELECT Id, UniqueId, COALESCE(NULLIF(Title, ''), 'Page ' || Id) AS Title "
        "FROM Page WHERE PageType = ? ORDER BY Title COLLATE NOCASE, Id",
        (pageset.PAGE_TYPE_VOCAB,),
    ).fetchall()
    uuids = {row["UniqueId"] for row in pages if row["UniqueId"]}
    properties = conn.execute(
        "SELECT * FROM PageSetProperties LIMIT 1"
    ).fetchone()
    keys = properties.keys() if properties is not None else []
    home = properties["DefaultHomePageUniqueId"] if "DefaultHomePageUniqueId" in keys else None
    language = properties["Language"] if "Language" in keys else None
    locale = language.replace("_", "-") if isinstance(language, str) and language else None

    boards, skipped = [], []
    for page in pages:
        title = page["Title"]
        if not page["UniqueId"]:
            _skip(skipped, title, "", "has no page id, so nothing could link to it")
            continue
        try:
            layout = builder.layout_for_page(conn, page["Id"], grid)
        except PagesetError:
            # A page TD Snap has never laid out has no buttons yet; it is still
            # a page other pages link to, so it travels as an empty board.
            layout = None
        cols, rows = (schema.parse_grid(layout["PageLayoutSetting"]) if layout is not None
                      else grid)
        cells, taken = [], set()
        for row in [] if layout is None else conn.execute(
            "SELECT placement.GridPosition AS Position, placement.GridSpan AS Span, "
            "button.Label AS Label, button.Message AS Message, "
            "button.BorderColor AS BorderColor, button.BorderThickness AS Thickness, "
            "(SELECT cs.SerializedCommands FROM CommandSequence cs "
            " WHERE cs.ButtonId = button.Id ORDER BY cs.Id LIMIT 1) AS Commands, "
            "(SELECT link.PageUniqueId FROM ButtonPageLink link "
            " WHERE link.ButtonId = button.Id ORDER BY link.Id LIMIT 1) AS LinkedPage "
            "FROM ElementPlacement placement "
            "JOIN Button button ON button.ElementReferenceId = placement.ElementReferenceId "
            "WHERE placement.PageLayoutId = ? AND placement.Visible = 1 "
            "ORDER BY placement.Id",
            (layout["Id"],),
        ):
            label = _text(row["Label"])
            if not label:
                _skip(skipped, title, "", "has no label, only a picture")
                continue
            try:
                col, grid_row = schema.parse_grid_position(row["Position"])
            except PagesetError:
                _skip(skipped, title, label, "has a position AAC Editor cannot read")
                continue
            if not (0 <= col < cols and 0 <= grid_row < rows):
                _skip(skipped, title, label, "sits outside the page's grid")
                continue
            if (col, grid_row) in taken:
                _skip(skipped, title, label, "shares its cell with another button")
                continue
            parts = _command_parts(row["Commands"])
            if not parts:
                _skip(skipped, title, label, "has no command AAC Editor can read")
                continue
            kinds = {str(part.get("$type")) for part in parts}
            if not kinds <= {"2", "3"}:
                _skip(skipped, title, label,
                      "does something Open Board Format cannot describe (a TD Snap action)")
                continue
            link = None
            if "2" in kinds:
                target = next(
                    (part.get("LinkedPageId") for part in parts if str(part.get("$type")) == "2"),
                    None,
                ) or row["LinkedPage"]
                if target not in uuids or target == page["UniqueId"]:
                    _skip(skipped, title, label,
                          "opens a page that is not one of this page set's own pages")
                    continue
                link = target
            message = _text(row["Message"]) or None
            border = None
            if row["BorderColor"] is not None and row["Thickness"]:
                border = f"#{int(row['BorderColor']) & 0xFFFFFF:06X}"
            taken.add((col, grid_row))
            cells.append({
                "row": grid_row, "col": col, "label": label,
                "message": None if link or message == label else message,
                "border": border, "link": link,
            })
        boards.append({"id": page["UniqueId"], "name": title, "locale": locale,
                       "rows": rows, "columns": cols, "cells": cells})
    if not boards:
        raise PagesetError("This page set has no vocabulary pages to export.")
    exported = {board["id"] for board in boards}
    for board in boards:
        kept = []
        for cell in board["cells"]:
            if cell["link"] and cell["link"] not in exported:
                _skip(skipped, board["name"], cell["label"],
                      "opens a page that could not be exported")
                continue
            kept.append(cell)
        board["cells"] = kept
    root = home if home in exported else boards[0]["id"]
    return {"format": FORMAT, "root": root, "boards": _order_boards(boards, root),
            "skipped": skipped, "notes": [SYMBOLS_NOTE]}


def export_summary(boardset: dict) -> dict:
    """Counts and exclusions for the UI to show before anything is saved."""
    cells = [cell for board in boardset["boards"] for cell in board["cells"]]
    return {
        "boards": len(boardset["boards"]),
        "buttons": len(cells),
        "links": sum(1 for cell in cells if cell["link"]),
        "root": next(board["name"] for board in boardset["boards"]
                     if board["id"] == boardset["root"]),
        "skipped": boardset["skipped"],
        "notes": boardset["notes"],
    }


# ---------------------------------------------------------------------------
# planning an import into a page set


def _unique_title(name: str, taken: set) -> str:
    base = (name or "Board").strip()[:MAX_TITLE_LENGTH].strip() or "Board"
    title, number = base, 2
    while title.casefold() in taken:
        suffix = f" ({number})"
        title = base[:MAX_TITLE_LENGTH - len(suffix)].rstrip() + suffix
        number += 1
    taken.add(title.casefold())
    return title


def plan_import(boardset: dict, *, grid: tuple[int, int], existing_titles) -> dict:
    """Where every board and button will land in a page set, before anything is written.

    Each board becomes one new page, titled after the board (renamed, and said
    so, when a page of that name already exists). A board that fits the page
    set's grid keeps every button in its own row and column; a larger one is
    laid out in reading order, and what still does not fit is named in
    ``skipped`` rather than silently dropped. Deterministic: the same board
    set against the same page set always plans the same way, which is what
    lets the apply step prove nothing moved since the review.
    """
    cols, rows = grid
    capacity = cols * rows
    boards = boardset.get("boards") or []
    if not boards:
        raise PagesetError("There are no boards to import.")
    if len(boards) > MAX_BOARDS:
        raise PagesetError(f"AAC Editor imports at most {MAX_BOARDS} boards at a time.")
    taken = {title.casefold() for title in existing_titles}
    skipped = list(boardset.get("skipped") or [])
    notes = list(boardset.get("notes") or [])
    uncoloured = 0
    pages = []
    for board in boards:
        title = _unique_title(board["name"], taken)
        fits = board["rows"] <= rows and board["columns"] <= cols
        ordered = sorted(board["cells"], key=lambda cell: (cell["row"], cell["col"]))
        cells = []
        for index, cell in enumerate(ordered):
            if fits:
                slot = cell["row"] * cols + cell["col"]
            elif index < capacity:
                slot = index
            else:
                _skip(skipped, board["name"], cell["label"],
                      f"does not fit on a {cols} by {rows} page")
                continue
            border = cell.get("border")
            if border and not cell.get("link") and not is_clinical_color(border):
                uncoloured += 1
            cells.append({
                "slot": slot,
                "label": cell["label"],
                "message": None if cell.get("link") else cell.get("message"),
                "border_color": (border.upper() if not cell.get("link")
                                 and is_clinical_color(border) else None),
                "link": cell.get("link"),
            })
        pages.append({
            "board_id": board["id"],
            "title": title,
            "name": board["name"],
            "renamed": title != board["name"],
            "rearranged": not fits and bool(board["cells"]),
            "source_grid": {"rows": board["rows"], "cols": board["columns"]},
            "cells": cells,
        })
    known = {page["board_id"] for page in pages}
    for page in pages:
        for cell in page["cells"]:
            if cell["link"] not in (None, *known):
                raise PagesetError("A board links to a board that is not being imported.")
    if uncoloured:
        notes.append(
            f"{uncoloured} button border colour"
            f"{' is' if uncoloured == 1 else 's are'} not one of the five topic-page "
            f"function colours, so {'it is' if uncoloured == 1 else 'they are'} left off."
        )
    return {
        "grid": {"cols": cols, "rows": rows},
        "root": boardset["root"],
        "pages": pages,
        "skipped": skipped,
        "notes": notes,
        "counts": {
            "pages": len(pages),
            "buttons": sum(len(page["cells"]) for page in pages),
            "links": sum(1 for page in pages for cell in page["cells"] if cell["link"]),
        },
    }
