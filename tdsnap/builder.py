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
from typing import Optional, Union

from . import schema, templates
from .colors import BORDER_THICKNESS, argb_from_hex, is_allowed_border_color
from .errors import PagesetError
from .pageset import Pageset
from .ticks import net_ticks_now

Item = Union[str, dict[str, object]]
MAX_TITLE_LENGTH = 60
MAX_LABEL_LENGTH = 60
MAX_MESSAGE_LENGTH = 200


def _normalize_title(title: str) -> str:
    if not isinstance(title, str):
        raise PagesetError("The new page title must be text.")
    title = title.strip()
    if not title:
        raise PagesetError("The new page needs a title.")
    if len(title) > MAX_TITLE_LENGTH:
        raise PagesetError(
            f"The new page title is too long (maximum {MAX_TITLE_LENGTH} characters)."
        )
    return title


def _normalize_items(items: list[Item]) -> list[dict[str, object]]:
    """Accept plain labels or richer button dictionaries.

    ``message`` (optional) is the full sentence to speak while ``label`` stays
    short on the button — how real TD Snap quick-fire phrase buttons work.
    ``border_color`` (optional) is '#RRGGBB' or a signed ARGB int, and must
    match one of ``colors.FUNCTION_BORDER_COLORS`` — the five-color topic-page
    convention is clinical, not a UI preference, so nothing else is accepted.
    ``slot`` is an optional zero-based grid index chosen in the visual
    preview. ``symbol`` controls whether live editing should make a
    best-effort symbol search, and ``symbol_query`` says what to search for
    when the label itself is a poor query — a button labelled "more please"
    finds nothing, while "more" finds the symbol the label is standing in for.
    Neither reaches the exported-file path, which writes no symbols at all.
    """
    if not isinstance(items, list):
        raise PagesetError("Words must be provided as a list.")
    normalized = []
    labels = set()
    for item in items:
        if isinstance(item, str):
            item = {"label": item}
        elif not isinstance(item, dict):
            raise PagesetError("Each word must be text or a {label, ...} object.")
        raw_label = item.get("label", "")
        if raw_label is None:
            raw_label = ""
        if not isinstance(raw_label, str):
            raise PagesetError("Each button label must be text.")
        label = raw_label.strip()
        if not label:
            continue
        if len(label) > MAX_LABEL_LENGTH:
            raise PagesetError(
                f"Button label {label!r} is too long "
                f"(maximum {MAX_LABEL_LENGTH} characters)."
            )
        folded = label.casefold()
        if folded in labels:
            raise PagesetError(f"The reviewed vocabulary contains duplicate labels: {label!r}.")
        labels.add(folded)
        raw_message = item.get("message")
        if raw_message is not None and not isinstance(raw_message, str):
            raise PagesetError(f"The spoken message for {label!r} must be text.")
        message = (raw_message or "").strip() or None
        if message and len(message) > MAX_MESSAGE_LENGTH:
            raise PagesetError(
                f"The spoken message for {label!r} is too long "
                f"(maximum {MAX_MESSAGE_LENGTH} characters)."
            )
        if message == label:
            message = None  # speaking the label is the default; don't duplicate
        border = item.get("border_color")
        if isinstance(border, str) and border.strip():
            border = argb_from_hex(border)
        elif border is None or border == "":
            border = None
        elif (
            isinstance(border, bool)
            or not isinstance(border, int)
            or not -(1 << 31) <= border < (1 << 31)
        ):
            raise PagesetError(
                f"The border color for {label!r} must be #RRGGBB or a signed 32-bit integer."
            )
        # The five function colors are a clinical convention (see colors.py),
        # not a UI preference — never write whatever color a request sends.
        if border is not None and not is_allowed_border_color(border):
            raise PagesetError(
                f"The border color for {label!r} is not one of the supported "
                "communicative-function colors."
            )
        slot = item.get("slot")
        if slot is not None and (
            isinstance(slot, bool) or not isinstance(slot, int) or slot < 0
        ):
            raise PagesetError(f"The grid slot for {label!r} must be a non-negative integer.")
        symbol = item.get("symbol", True)
        if not isinstance(symbol, bool):
            raise PagesetError(f"The symbol setting for {label!r} must be true or false.")
        query = item.get("symbol_query")
        if query is not None and not isinstance(query, str):
            raise PagesetError(f"The symbol search words for {label!r} must be text.")
        query = (query or "").strip() or None
        if query and len(query) > MAX_LABEL_LENGTH:
            raise PagesetError(
                f"The symbol search words for {label!r} are too long "
                f"(maximum {MAX_LABEL_LENGTH} characters)."
            )
        normalized.append({"label": label, "message": message,
                           "border_color": border, "slot": slot,
                           "symbol": symbol, "symbol_query": query})
    return normalized


def _random_sync_hash() -> int:
    """A random signed 64-bit value, the shape real SyncHash values have."""
    return random.getrandbits(64) - (1 << 63)


def layout_for_page(
    conn: sqlite3.Connection, page_id: int, grid: tuple[int, int]
) -> sqlite3.Row:
    """Return the PageLayout of *page_id* to place a new button in.

    Pages can carry several layouts (one per grid size the user has viewed);
    prefer the one matching the page set's grid, then the most-populated one.
    Public because the capacity the UI shows and the cells the writer fills
    have to be the same answer — two copies of this rule would drift.
    """
    layouts = conn.execute(
        "SELECT * FROM PageLayout WHERE PageId = ?", (page_id,)
    ).fetchall()
    if not layouts:
        raise PagesetError(
            f"Page Id {page_id} has no PageLayout, so AAC Editor cannot "
            "place a button on it."
        )
    grid_prefix = f"{grid[0]},{grid[1]},"
    matching = [
        layout_row
        for layout_row in layouts
        if (layout_row["PageLayoutSetting"] or "").startswith(grid_prefix)
    ]
    if matching:
        return matching[0]

    def placement_count(layout: sqlite3.Row) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM ElementPlacement WHERE PageLayoutId = ?",
            (layout["Id"],),
        ).fetchone()[0]

    return max(layouts, key=placement_count)


def _used_cells(conn: sqlite3.Connection, layout: sqlite3.Row) -> set[tuple[int, int]]:
    """Every ``(col, row)`` cell *layout* already has something visible in."""
    used = set()
    for row in conn.execute(
        "SELECT GridPosition, GridSpan FROM ElementPlacement "
        "WHERE PageLayoutId = ? AND Visible = 1",
        (layout["Id"],),
    ):
        col, grid_row = schema.parse_grid_position(row["GridPosition"])
        col_span, row_span = schema.parse_grid_span(row["GridSpan"])
        used.update(
            (x, y)
            for x in range(col, col + col_span)
            for y in range(grid_row, grid_row + row_span)
        )
    return used


def free_slots(conn: sqlite3.Connection, layout: sqlite3.Row) -> list[int]:
    """Empty zero-based slot numbers in *layout*, in reading order."""
    cols, rows = schema.parse_grid(layout["PageLayoutSetting"])
    used = _used_cells(conn, layout)
    return [
        index for index in range(cols * rows)
        if (index % cols, index // cols) not in used
    ]


def _free_slot(
    conn: sqlite3.Connection, layout: sqlite3.Row
) -> tuple[int, int]:
    """First empty ``(col, row)`` cell in *layout*, row-major order."""
    cols, _ = schema.parse_grid(layout["PageLayoutSetting"])
    free = free_slots(conn, layout)
    if not free:
        raise PagesetError(
            "The parent page's grid is full; free a cell or pick another page for "
            "the navigation button."
        )
    return (free[0] % cols, free[0] // cols)


def _insert_cell(
    conn: sqlite3.Connection,
    chain: dict[str, sqlite3.Row],
    *,
    page_id: int,
    layout_id: int,
    slot: tuple[int, int],
    label: str,
    command_flags: int,
    serialized_commands: str,
    message: Optional[str] = None,
    border_color: Optional[int] = None,
) -> tuple[int, int]:
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


def _create_page(
    conn: sqlite3.Connection,
    template_page: sqlite3.Row,
    title: str,
    grid: tuple[int, int],
    now: int,
) -> tuple[int, str, int]:
    """Clone a vocabulary Page with its own layout and SyncData ledger row.

    Returns ``(page_id, page_unique_id, layout_id)``. Shared by every path that
    creates a page, so a page made by an Open Board import is built exactly
    like one made by "Create a new page".
    """
    page_uuid = str(uuid.uuid4())
    sync_hash = _random_sync_hash()
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
        (f"{grid[0]},{grid[1]},True,0", page_id),
    ).lastrowid
    conn.execute(
        "INSERT INTO SyncData (UniqueId, Type, Timestamp, SyncHash, Deleted, "
        "Description) VALUES (?, 1, ?, ?, 0, ?)",
        (page_uuid, now, sync_hash, title),
    )
    return page_id, page_uuid, layout_id


def _link_from_parent(
    conn: sqlite3.Connection,
    nav_chain: dict[str, sqlite3.Row],
    parent_page: sqlite3.Row,
    grid: tuple[int, int],
    label: str,
    target_uuid: str,
    now: int,
) -> int:
    """Put a button opening *target_uuid* in the parent page's first empty cell."""
    layout = layout_for_page(conn, parent_page["Id"], grid)
    slot = _free_slot(conn, layout)
    nav_button_id, _ = _insert_cell(
        conn,
        nav_chain,
        page_id=parent_page["Id"],
        layout_id=layout["Id"],
        slot=slot,
        label=label,
        command_flags=templates.COMMAND_FLAGS_NAVIGATE,
        serialized_commands=templates.navigate_commands(target_uuid),
    )
    conn.execute(
        "INSERT INTO ButtonPageLink (ButtonId, PageUniqueId) VALUES (?, ?)",
        (nav_button_id, target_uuid),
    )
    conn.execute("UPDATE Page SET Timestamp = ? WHERE Id = ?", (now, parent_page["Id"]))
    conn.execute(
        "UPDATE SyncData SET Timestamp = ? WHERE UniqueId = ?",
        (now, parent_page["UniqueId"]),
    )
    return nav_button_id


def add_category_page(
    pageset: Pageset,
    title: str,
    items: list[Item],
    parent_page_id: Optional[int],
) -> dict[str, object]:
    """Add a page of speaking buttons and (optionally) link it from a parent.

    Items may be plain labels or ``{label, message, border_color}`` dicts
    (see ``_normalize_items``). All writes happen in one transaction; any
    failure rolls the working copy back to its pre-call state. Returns a
    report dict used by validation and the UIs:
    ``{page_id, page_unique_id, button_ids, buttons, nav_button_id, grid}``.
    """
    conn = pageset.conn
    title = _normalize_title(title)
    items = _normalize_items(items)
    if not items:
        raise PagesetError("Cannot create a page with no words.")

    cols, rows = pageset.grid_dimension()
    if len(items) > cols * rows:
        raise PagesetError(
            f"{len(items)} words don't fit the page set's {cols}x{rows} grid "
            f"({cols * rows} cells). Split them across two pages."
        )

    owns_transaction = not conn.in_transaction
    savepoint = f"tdsnap_add_{uuid.uuid4().hex}"
    if owns_transaction:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute(f"SAVEPOINT {savepoint}")
    try:
        parent_page = None
        if parent_page_id is not None:
            parent_page = conn.execute(
                "SELECT * FROM Page WHERE Id = ? AND PageType = 1", (parent_page_id,)
            ).fetchone()
            if parent_page is None:
                raise PagesetError(
                    f"Vocabulary parent page Id {parent_page_id} not found."
                )
        if conn.execute(
            "SELECT 1 FROM Page WHERE PageType = 1 AND Title = ? COLLATE NOCASE "
            "LIMIT 1",
            (title,),
        ).fetchone():
            raise PagesetError(f"A vocabulary page named {title!r} already exists.")

        template_page = templates.find_template_page(conn)
        speak_chain = templates.find_speak_chain(conn)
        nav_chain = templates.find_nav_chain(conn) if parent_page is not None else None
        now = net_ticks_now()
        page_id, page_uuid, layout_id = _create_page(conn, template_page, title, (cols, rows), now)

        button_ids = []
        button_specs = []
        used_slots = set()
        for index, item in enumerate(items):
            requested = item.get("slot")
            slot_index = requested if isinstance(requested, int) else index
            if slot_index >= cols * rows or slot_index in used_slots:
                slot_index = next(
                    candidate for candidate in range(cols * rows)
                    if candidate not in used_slots
                )
            used_slots.add(slot_index)
            slot = (slot_index % cols, slot_index // cols)
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

        nav_button_id = None
        if parent_page is not None:
            nav_button_id = _link_from_parent(
                conn, nav_chain, parent_page, (cols, rows), title, page_uuid, now
            )

        conn.execute("UPDATE Synchronization SET PageSetTimestamp = ?", (now,))
        conn.execute("UPDATE PageSetProperties SET Timestamp = ?", (now,))
        if owns_transaction:
            conn.commit()
        else:
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    except BaseException:
        if owns_transaction:
            conn.rollback()
        else:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise

    return {
        "page_id": page_id,
        "page_unique_id": page_uuid,
        "button_ids": button_ids,
        "buttons": button_specs,
        "nav_button_id": nav_button_id,
        "grid": (cols, rows),
    }


def add_buttons_to_page(
    pageset: Pageset, page_id: int, items: list[Item]
) -> dict[str, object]:
    """Add speaking buttons to the empty cells of a page that already exists.

    The exported-file path could only ever *create* a page, which meant the one
    thing most people want to do — put three more words on a page they already
    use — was possible on Windows with TD Snap running and nowhere else. This
    is that operation, and it deliberately mirrors ``add_category_page`` cell
    for cell: same speak chain, same clone, same placement rows, so a page this
    writes to is indistinguishable from a page TD Snap itself extended.

    Nothing already on the page is touched. Buttons land in the cells the
    review chose, and a request for a cell that is not empty is refused rather
    than quietly moved elsewhere — the preview said where these buttons were
    going, and silently disagreeing with it is how vocabulary ends up somewhere
    nobody expects.
    """
    conn = pageset.conn
    items = _normalize_items(items)
    if not items:
        raise PagesetError("Add at least one word or phrase.")

    owns_transaction = not conn.in_transaction
    savepoint = f"tdsnap_extend_{uuid.uuid4().hex}"
    if owns_transaction:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute(f"SAVEPOINT {savepoint}")
    try:
        page = conn.execute(
            "SELECT * FROM Page WHERE Id = ? AND PageType = 1", (page_id,)
        ).fetchone()
        if page is None:
            raise PagesetError(f"Vocabulary page Id {page_id} not found.")

        existing = {
            (row["Label"] or "").strip().casefold()
            for row in conn.execute(
                "SELECT button.Label AS Label FROM Button button "
                "JOIN ElementReference ref ON ref.Id = button.ElementReferenceId "
                "WHERE ref.PageId = ?",
                (page_id,),
            )
        }
        duplicates = [item["label"] for item in items if item["label"].casefold() in existing]
        if duplicates:
            raise PagesetError(
                "Already on this page: " + ", ".join(duplicates)
                + ". Remove or rename duplicates before submitting."
            )

        cols, rows = pageset.grid_dimension()
        layout = layout_for_page(conn, page_id, (cols, rows))
        cols, rows = schema.parse_grid(layout["PageLayoutSetting"])
        free = free_slots(conn, layout)
        if len(items) > len(free):
            raise PagesetError(
                f"{len(items)} button(s) don't fit: this page has "
                f"{len(free)} empty cell(s)."
            )

        unused = list(free)
        speak_chain = templates.find_speak_chain(conn)
        now = net_ticks_now()
        button_ids = []
        button_specs = []
        for item in items:
            requested = item.get("slot")
            if isinstance(requested, int):
                if requested not in unused:
                    raise PagesetError(
                        f"The cell chosen for {item['label']!r} is not empty on this "
                        "page. Reload the page and review the placement again."
                    )
                slot_index = requested
            else:
                slot_index = unused[0]
            unused.remove(slot_index)
            button_id, _ = _insert_cell(
                conn,
                speak_chain,
                page_id=page_id,
                layout_id=layout["Id"],
                slot=(slot_index % cols, slot_index // cols),
                label=item["label"],
                command_flags=templates.COMMAND_FLAGS_SPEAK,
                serialized_commands=templates.SPEAK_COMMANDS,
                message=item["message"],
                border_color=item["border_color"],
            )
            button_ids.append(button_id)
            button_specs.append({"id": button_id, **item, "slot": slot_index})

        conn.execute("UPDATE Page SET Timestamp = ? WHERE Id = ?", (now, page_id))
        conn.execute(
            "UPDATE SyncData SET Timestamp = ? WHERE UniqueId = ?",
            (now, page["UniqueId"]),
        )
        conn.execute("UPDATE Synchronization SET PageSetTimestamp = ?", (now,))
        conn.execute("UPDATE PageSetProperties SET Timestamp = ?", (now,))
        if owns_transaction:
            conn.commit()
        else:
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    except BaseException:
        if owns_transaction:
            conn.rollback()
        else:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise

    return {
        "page_id": page_id,
        "page_unique_id": page["UniqueId"],
        "layout_id": layout["Id"],
        "button_ids": button_ids,
        "buttons": button_specs,
        "grid": (cols, rows),
    }


MAX_IMPORT_PAGES = 100


def _planned_pages(plan: dict, capacity: int) -> list[dict]:
    """Check an import plan's shape and content before any row is written.

    The plan was produced by ``obf.plan_import`` and reviewed, but it reaches
    this function through a file on disk and a second request, so it is held to
    the same standard as anything else arriving at the write path: every label,
    message, colour, and cell goes through ``_normalize_items``, and every link
    must name a page in the same plan.
    """
    pages = plan.get("pages") if isinstance(plan, dict) else None
    if not isinstance(pages, list) or not pages:
        raise PagesetError("There are no boards to import.")
    if len(pages) > MAX_IMPORT_PAGES:
        raise PagesetError(f"AAC Editor imports at most {MAX_IMPORT_PAGES} pages at a time.")
    board_ids = [page.get("board_id") if isinstance(page, dict) else None for page in pages]
    if any(not isinstance(board_id, str) or not board_id for board_id in board_ids):
        raise PagesetError("Every imported board needs an id.")
    if len(set(board_ids)) != len(board_ids):
        raise PagesetError("Two imported boards share an id.")
    titles = set()
    checked = []
    for page in pages:
        title = _normalize_title(page.get("title"))
        if title.casefold() in titles:
            raise PagesetError(f"Two imported pages would both be called {title!r}.")
        titles.add(title.casefold())
        cells = page.get("cells")
        if not isinstance(cells, list):
            raise PagesetError(f"The buttons for {title!r} must be a list.")
        links = {}
        for cell in cells:
            if not isinstance(cell, dict):
                raise PagesetError(f"A button on {title!r} is not readable.")
            link = cell.get("link")
            if link is None:
                continue
            if link not in board_ids or link == page["board_id"]:
                raise PagesetError(
                    f"{cell.get('label')!r} on {title!r} links to a board that is not "
                    "being imported."
                )
            if cell.get("message") or cell.get("border_color"):
                raise PagesetError(
                    f"{cell.get('label')!r} on {title!r} opens a page, so it cannot also "
                    "speak a message or carry a function colour."
                )
            links[str(cell.get("label", "")).strip().casefold()] = link
        items = _normalize_items([
            {key: cell.get(key) for key in ("label", "message", "border_color", "slot")}
            for cell in cells
        ])
        for item in items:
            if item["slot"] is None or item["slot"] >= capacity:
                raise PagesetError(
                    f"{item['label']!r} on {title!r} has no cell on this page set's grid."
                )
        if len({item["slot"] for item in items}) != len(items):
            raise PagesetError(f"Two buttons on {title!r} were planned into the same cell.")
        for item in items:
            item["link"] = links.get(item["label"].casefold())
        checked.append({"board_id": page["board_id"], "title": title, "items": items})
    return checked


def add_linked_pages(
    pageset: Pageset, plan: dict, parent_page_id: int
) -> dict[str, object]:
    """Create one page per planned board, link them as the boards were, and
    link the first from *parent_page_id*.

    The Open Board import's write path. Every page is built by the same
    ``_create_page`` and ``_insert_cell`` as "Create a new page", every link
    button is cloned from a real TD Snap page-link button with its
    ButtonPageLink row, and the whole import is one transaction: if any page,
    button, or link cannot be written, nothing is. Returns a report for
    ``validate.validate_imported_pages``.
    """
    conn = pageset.conn
    cols, rows = pageset.grid_dimension()
    planned_grid = plan.get("grid") if isinstance(plan, dict) else None
    if planned_grid != {"cols": cols, "rows": rows}:
        raise PagesetError(
            "The import was planned for a different grid. Review the import again."
        )
    pages = _planned_pages(plan, cols * rows)

    owns_transaction = not conn.in_transaction
    savepoint = f"tdsnap_import_{uuid.uuid4().hex}"
    if owns_transaction:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute(f"SAVEPOINT {savepoint}")
    try:
        parent_page = conn.execute(
            "SELECT * FROM Page WHERE Id = ? AND PageType = 1", (parent_page_id,)
        ).fetchone()
        if parent_page is None:
            raise PagesetError(f"Vocabulary parent page Id {parent_page_id} not found.")
        for page in pages:
            if conn.execute(
                "SELECT 1 FROM Page WHERE PageType = 1 AND Title = ? COLLATE NOCASE LIMIT 1",
                (page["title"],),
            ).fetchone():
                raise PagesetError(f"A vocabulary page named {page['title']!r} already exists.")

        template_page = templates.find_template_page(conn)
        speak_chain = templates.find_speak_chain(conn)
        nav_chain = templates.find_nav_chain(conn)
        now = net_ticks_now()

        created = {}
        for page in pages:
            page_id, page_uuid, layout_id = _create_page(
                conn, template_page, page["title"], (cols, rows), now
            )
            created[page["board_id"]] = (page_id, page_uuid, layout_id)

        reports = []
        for page in pages:
            page_id, page_uuid, layout_id = created[page["board_id"]]
            button_ids, specs = [], []
            for item in page["items"]:
                slot = (item["slot"] % cols, item["slot"] // cols)
                target = created[item["link"]][1] if item["link"] else None
                button_id, _ = _insert_cell(
                    conn,
                    nav_chain if target else speak_chain,
                    page_id=page_id,
                    layout_id=layout_id,
                    slot=slot,
                    label=item["label"],
                    command_flags=(templates.COMMAND_FLAGS_NAVIGATE if target
                                   else templates.COMMAND_FLAGS_SPEAK),
                    serialized_commands=(templates.navigate_commands(target) if target
                                         else templates.SPEAK_COMMANDS),
                    message=item["message"],
                    border_color=item["border_color"],
                )
                if target:
                    conn.execute(
                        "INSERT INTO ButtonPageLink (ButtonId, PageUniqueId) VALUES (?, ?)",
                        (button_id, target),
                    )
                button_ids.append(button_id)
                specs.append({
                    "id": button_id, "label": item["label"], "message": item["message"],
                    "border_color": item["border_color"], "slot": item["slot"],
                    "link_unique_id": target,
                })
            reports.append({
                "board_id": page["board_id"], "title": page["title"],
                "page_id": page_id, "page_unique_id": page_uuid, "layout_id": layout_id,
                "button_ids": button_ids, "buttons": specs,
            })

        root = reports[0]
        nav_button_id = _link_from_parent(
            conn, nav_chain, parent_page, (cols, rows), root["title"],
            root["page_unique_id"], now,
        )
        conn.execute("UPDATE Synchronization SET PageSetTimestamp = ?", (now,))
        conn.execute("UPDATE PageSetProperties SET Timestamp = ?", (now,))
        if owns_transaction:
            conn.commit()
        else:
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    except BaseException:
        if owns_transaction:
            conn.rollback()
        else:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise

    return {
        "pages": reports,
        "parent_page_id": parent_page_id,
        "nav_button_id": nav_button_id,
        "grid": (cols, rows),
    }
