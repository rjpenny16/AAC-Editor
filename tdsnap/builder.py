"""Create a category page of speaking buttons, linked from an existing page.

This is the write path that used to crash TD Snap. It now mirrors, row for
row, what TD Snap itself writes (verified against a real Motor Plan 40 export,
schema 4.13): cloned Page/Button/ElementReference rows, a PageLayout for the
new page, an ElementPlacement per cell tied to that layout, one
CommandSequence per button, a ButtonPageLink for navigation, a SyncData ledger
row for the new page, and timestamp bumps on everything it modified.

Known limitation: the SyncHash algorithm is proprietary. New pages get a
random 64-bit hash used consistently in Page and SyncData; rows we merely
touch keep their hash and only get a new Timestamp. If a device ever rejects
an edited file, these hash fields are the first suspects — ``tdsnap verify``
prints them for debugging.
"""

import random
import sqlite3
import uuid
from typing import Dict, List, Optional, Tuple, Union

from . import templates
from .colors import BORDER_THICKNESS, argb_from_hex
from .errors import PagesetError
from .pageset import Pageset
from .ticks import net_ticks_now

Item = Union[str, Dict[str, object]]


def _normalize_items(items: List[Item]) -> List[Dict[str, object]]:
    """Accept plain labels or ``{label, message, border_color}`` dicts.

    ``message`` (optional) is the full sentence to speak while ``label`` stays
    short on the button — how real TD Snap quick-fire phrase buttons work.
    ``border_color`` (optional) is '#RRGGBB' or a signed ARGB int, the
    color-coding convention used on topic pages.
    """
    normalized = []
    for item in items:
        if isinstance(item, str):
            item = {"label": item}
        elif not isinstance(item, dict):
            raise PagesetError("Each word must be text or a {label, ...} object.")
        label = str(item.get("label", "") or "").strip()
        if not label:
            continue
        message = str(item.get("message", "") or "").strip() or None
        if message == label:
            message = None  # speaking the label is the default; don't duplicate
        border = item.get("border_color")
        if isinstance(border, str) and border.strip():
            border = argb_from_hex(border)
        elif not isinstance(border, int):
            border = None
        normalized.append({"label": label, "message": message,
                           "border_color": border})
    return normalized


def _random_sync_hash() -> int:
    """A random signed 64-bit value, the shape real SyncHash values have."""
    return random.getrandbits(64) - (1 << 63)


def _parent_layout(
    conn: sqlite3.Connection, parent_page_id: int, grid: Tuple[int, int]
) -> sqlite3.Row:
    """Return the PageLayout of *parent_page_id* to place the nav button in.

    Pages can carry several layouts (one per grid size the user has viewed);
    prefer the one matching the page set's grid, then the most-populated one.
    """
    layouts = conn.execute(
        "SELECT * FROM PageLayout WHERE PageId = ?", (parent_page_id,)
    ).fetchall()
    if not layouts:
        raise PagesetError(
            f"Parent page Id {parent_page_id} has no PageLayout; cannot place "
            "a navigation button on it."
        )
    grid_prefix = f"{grid[0]},{grid[1]},"
    matching = [
        l for l in layouts
        if (l["PageLayoutSetting"] or "").startswith(grid_prefix)
    ]
    if matching:
        return matching[0]

    def placement_count(layout: sqlite3.Row) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM ElementPlacement WHERE PageLayoutId = ?",
            (layout["Id"],),
        ).fetchone()[0]

    return max(layouts, key=placement_count)


def _free_slot(
    conn: sqlite3.Connection, layout: sqlite3.Row
) -> Tuple[int, int]:
    """First empty ``(col, row)`` cell in *layout*, row-major order."""
    from . import schema

    cols, rows = schema.parse_grid(layout["PageLayoutSetting"])
    used = set()
    for row in conn.execute(
        "SELECT GridPosition FROM ElementPlacement WHERE PageLayoutId = ?",
        (layout["Id"],),
    ):
        pos = row["GridPosition"]
        if pos and "," in pos:
            try:
                c, r = (int(n) for n in pos.split(",", 1))
                used.add((c, r))
            except ValueError:
                continue
    for index in range(cols * rows):
        slot = (index % cols, index // cols)
        if slot not in used:
            return slot
    raise PagesetError(
        "The parent page's grid is full; free a cell or pick another page for "
        "the navigation button."
    )


def _insert_cell(
    conn: sqlite3.Connection,
    chain: Dict[str, sqlite3.Row],
    *,
    page_id: int,
    layout_id: int,
    slot: Tuple[int, int],
    label: str,
    command_flags: int,
    serialized_commands: str,
    message: Optional[str] = None,
    border_color: Optional[int] = None,
) -> Tuple[int, int]:
    """Clone one full cell (reference, button, commands, placement).

    Returns ``(button_id, reference_id)``. ``message`` makes it a phrase
    button (label shown, message spoken); ``border_color`` adds the 3px
    colored border used for function coding on topic pages.
    """
    ref_id = templates.clone_row(
        conn,
        "ElementReference",
        chain["reference"],
        {"PageId": page_id, "ElementType": 0},
    )

    button_overrides = {
        "Label": label,
        "Message": message,
        "UniqueId": str(uuid.uuid4()),
        "CommandFlags": command_flags,
        "ElementReferenceId": ref_id,
        "ContentTag": None,
        "BorderColor": border_color,
        "BorderThickness": BORDER_THICKNESS if border_color is not None else 0.0,
    }
    # Fields that exist in schema 4.13 but may not in older files: reset any
    # media/symbol linkage so the clone can't point at the template's assets.
    button_overrides.update(
        templates.filtered_overrides(
            conn,
            "Button",
            {
                "LibrarySymbolId": 0,
                "PageSetImageId": 0,
                "MessageRecordingId": 0,
                "SymbolColorDataId": 0,
                "SerializedContentTypeHandler": None,
                "SerializedMessageSoundMetadata": None,
                "UseMessageRecording": None,
            },
        )
    )
    button_id = templates.clone_row(conn, "Button", chain["button"], button_overrides)

    conn.execute(
        "INSERT INTO CommandSequence (SerializedCommands, ButtonId) VALUES (?, ?)",
        (serialized_commands, button_id),
    )
    conn.execute(
        "INSERT INTO ElementPlacement "
        "(GridPosition, GridSpan, Visible, ElementReferenceId, PageLayoutId) "
        "VALUES (?, '1,1', 1, ?, ?)",
        (f"{slot[0]},{slot[1]}", ref_id, layout_id),
    )
    return button_id, ref_id


def add_category_page(
    pageset: Pageset,
    title: str,
    items: List[Item],
    parent_page_id: Optional[int],
) -> Dict[str, object]:
    """Add a page of speaking buttons and (optionally) link it from a parent.

    Items may be plain labels or ``{label, message, border_color}`` dicts
    (see ``_normalize_items``). All writes happen in one transaction; any
    failure rolls the working copy back to its pre-call state. Returns a
    report dict used by validation and the UIs:
    ``{page_id, page_unique_id, button_ids, buttons, nav_button_id, grid}``.
    """
    conn = pageset.conn
    title = (title or "").strip()
    items = _normalize_items(items)
    if not title:
        raise PagesetError("The new page needs a title.")
    if not items:
        raise PagesetError("Cannot create a page with no words.")

    cols, rows = pageset.grid_dimension()
    if len(items) > cols * rows:
        raise PagesetError(
            f"{len(items)} words don't fit the page set's {cols}x{rows} grid "
            f"({cols * rows} cells). Split them across two pages."
        )

    parent_page = None
    if parent_page_id is not None:
        parent_page = conn.execute(
            "SELECT * FROM Page WHERE Id = ?", (parent_page_id,)
        ).fetchone()
        if parent_page is None:
            raise PagesetError(f"Parent page Id {parent_page_id} not found.")

    template_page = templates.find_template_page(conn)
    speak_chain = templates.find_speak_chain(conn)
    nav_chain = templates.find_nav_chain(conn) if parent_page is not None else None

    now = net_ticks_now()
    page_uuid = str(uuid.uuid4())
    sync_hash = _random_sync_hash()

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    try:
        page_overrides = {
            "UniqueId": page_uuid,
            "Title": title,
            "PageType": 1,
            "Timestamp": now,
            "SyncHash": sync_hash,
            "ContentTag": None,
        }
        page_overrides.update(
            templates.filtered_overrides(
                conn,
                "Page",
                {
                    "SerializedMetadata": None,
                    "LibrarySymbolId": 0,
                    "PageSetImageId": 0,
                    "GridDimension": None,
                    "SymbolColorDataId": 0,
                    "VocabPlannerForcedVisible": 0,
                    "SerializedSymbolPersonColors": None,
                },
            )
        )
        page_id = templates.clone_row(conn, "Page", template_page, page_overrides)

        layout_id = conn.execute(
            "INSERT INTO PageLayout (PageLayoutSetting, PageId) VALUES (?, ?)",
            (f"{cols},{rows},True,0", page_id),
        ).lastrowid

        button_ids = []
        button_specs = []
        for index, item in enumerate(items):
            slot = (index % cols, index // cols)
            button_id, _ = _insert_cell(
                conn,
                speak_chain,
                page_id=page_id,
                layout_id=layout_id,
                slot=slot,
                label=item["label"],
                command_flags=templates.COMMAND_FLAGS_SPEAK,
                serialized_commands=templates.SPEAK_COMMANDS,
                message=item["message"],
                border_color=item["border_color"],
            )
            button_ids.append(button_id)
            button_specs.append({"id": button_id, **item})

        conn.execute(
            "INSERT INTO SyncData (UniqueId, Type, Timestamp, SyncHash, Deleted, "
            "Description) VALUES (?, 1, ?, ?, 0, ?)",
            (page_uuid, now, sync_hash, title),
        )

        nav_button_id = None
        if parent_page is not None:
            layout = _parent_layout(conn, parent_page_id, (cols, rows))
            slot = _free_slot(conn, layout)
            nav_button_id, _ = _insert_cell(
                conn,
                nav_chain,
                page_id=parent_page_id,
                layout_id=layout["Id"],
                slot=slot,
                label=title,
                command_flags=templates.COMMAND_FLAGS_NAVIGATE,
                serialized_commands=templates.navigate_commands(page_uuid),
            )
            conn.execute(
                "INSERT INTO ButtonPageLink (ButtonId, PageUniqueId) VALUES (?, ?)",
                (nav_button_id, page_uuid),
            )
            conn.execute(
                "UPDATE Page SET Timestamp = ? WHERE Id = ?", (now, parent_page_id)
            )
            conn.execute(
                "UPDATE SyncData SET Timestamp = ? WHERE UniqueId = ?",
                (now, parent_page["UniqueId"]),
            )

        conn.execute("UPDATE Synchronization SET PageSetTimestamp = ?", (now,))
        conn.execute("UPDATE PageSetProperties SET Timestamp = ?", (now,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "page_id": page_id,
        "page_unique_id": page_uuid,
        "button_ids": button_ids,
        "buttons": button_specs,
        "nav_button_id": nav_button_id,
        "grid": (cols, rows),
    }
