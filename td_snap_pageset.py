"""Direct editor for TD Snap / Snap Core First page sets.

A TD Snap page set (``.spb`` / ``.sps``) is a SQLite database. Instead of driving
the live application with simulated mouse clicks, this module edits the database
directly: it adds a new page full of word buttons and wires a navigation button on
an existing page to open it. The user then re-imports the edited file into TD Snap.

Relevant schema (confirmed against the open-source ``obf-node`` Snap converter):

    Page(Id PK, UniqueId TEXT UNIQUE, Title, Name, BackgroundColor)
    Button(Id PK, Label, Message, NavigatePageId, ElementReferenceId,
           LibrarySymbolId, PageSetImageId, ...)
    ElementReference(Id PK, PageId, ForegroundColor, BackgroundColor)
    ElementPlacement(Id PK, ElementReferenceId, GridPosition "col,row", GridSpan "1,1")

A *cell* on a page is the trio Button + ElementReference (which ties the button to a
PageId) + ElementPlacement (its grid position). A button navigates to another page
by setting ``Button.NavigatePageId`` to that page's ``Id``.

This v1 creates text-only buttons (``Label`` + ``Message``); symbols/images are
deferred until the real-export verification (see ``inspect_pageset.py``) pins down
how ``LibrarySymbolId`` / ``PageSetData`` are linked.
"""

import shutil
import sqlite3
import uuid
from typing import List, Tuple

# Tables this module reads from / writes to. ``open_pageset`` checks they exist so
# we fail loudly on an unexpected file rather than corrupting it.
REQUIRED_TABLES = (
    "Page",
    "Button",
    "ElementReference",
    "ElementPlacement",
)

SQLITE_MAGIC = b"SQLite format 3\x00"


class PagesetError(Exception):
    """Raised when a file is not a usable TD Snap page set."""


def is_sqlite_file(path: str) -> bool:
    """Return True if *path* begins with the SQLite file magic header."""
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def open_pageset(path: str, working_copy: str = None) -> sqlite3.Connection:
    """Open a page set for editing.

    Operates on a *copy* so the user's original export is never mutated. Pass
    ``working_copy`` to control where the editable copy lives; otherwise a sibling
    ``<name>.editing<ext>`` file is created. Raises :class:`PagesetError` if the
    file is not SQLite or is missing the expected tables.
    """
    if not is_sqlite_file(path):
        raise PagesetError(
            f"{path!r} is not a SQLite database. TD Snap page sets are expected to "
            "be SQLite files; verify the export with inspect_pageset.py."
        )

    if working_copy is None:
        if "." in path.rsplit("/", 1)[-1]:
            base, ext = path.rsplit(".", 1)
            working_copy = f"{base}.editing.{ext}"
        else:
            working_copy = f"{path}.editing"

    shutil.copyfile(path, working_copy)
    conn = sqlite3.connect(working_copy)
    conn.row_factory = sqlite3.Row

    existing = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        conn.close()
        raise PagesetError(
            "File does not look like a TD Snap page set; missing tables: "
            + ", ".join(missing)
        )

    return conn


def list_pages(conn: sqlite3.Connection) -> List[Tuple[int, str]]:
    """Return ``(Id, display_name)`` for every page, ordered by name.

    Used to let the user pick which existing page should host the navigation
    button that opens the newly created category page.
    """
    rows = conn.execute(
        "SELECT Id, COALESCE(NULLIF(Title, ''), NULLIF(Name, ''), 'Page ' || Id) "
        "AS DisplayName FROM Page ORDER BY DisplayName COLLATE NOCASE"
    ).fetchall()
    return [(row["Id"], row["DisplayName"]) for row in rows]


def _next_id(conn: sqlite3.Connection, table: str) -> int:
    """Return ``MAX(Id) + 1`` for *table* (1 when the table is empty)."""
    row = conn.execute(f"SELECT MAX(Id) AS m FROM {table}").fetchone()
    return (row["m"] or 0) + 1


def _next_free_slot(conn: sqlite3.Connection, page_id: int, cols: int) -> Tuple[int, int]:
    """Return the next empty ``(col, row)`` grid slot on *page_id*.

    Scans existing placements on the page (joined via ElementReference) and returns
    the first free cell in row-major order across ``cols`` columns.
    """
    used = set()
    rows = conn.execute(
        "SELECT ep.GridPosition FROM ElementPlacement ep "
        "JOIN ElementReference er ON ep.ElementReferenceId = er.Id "
        "WHERE er.PageId = ?",
        (page_id,),
    ).fetchall()
    for row in rows:
        pos = row["GridPosition"]
        if pos and "," in pos:
            try:
                c, r = (int(n) for n in pos.split(",", 1))
                used.add((c, r))
            except ValueError:
                continue

    index = 0
    while True:
        col, r = index % cols, index // cols
        if (col, r) not in used:
            return col, r
        index += 1


def _add_cell(
    conn: sqlite3.Connection,
    page_id: int,
    col: int,
    row: int,
    *,
    label: str,
    message: str = None,
    navigate_page_id: int = None,
) -> int:
    """Insert one cell (Button + ElementReference + ElementPlacement) on a page.

    Returns the new Button Id. ``message`` is the spoken text; ``navigate_page_id``
    turns the cell into a link that opens another page.
    """
    ref_id = _next_id(conn, "ElementReference")
    conn.execute(
        "INSERT INTO ElementReference (Id, PageId) VALUES (?, ?)",
        (ref_id, page_id),
    )

    button_id = _next_id(conn, "Button")
    conn.execute(
        "INSERT INTO Button (Id, Label, Message, NavigatePageId, ElementReferenceId) "
        "VALUES (?, ?, ?, ?, ?)",
        (button_id, label, message, navigate_page_id, ref_id),
    )

    placement_id = _next_id(conn, "ElementPlacement")
    conn.execute(
        "INSERT INTO ElementPlacement (Id, ElementReferenceId, GridPosition, GridSpan) "
        "VALUES (?, ?, ?, ?)",
        (placement_id, ref_id, f"{col},{row}", "1,1"),
    )
    return button_id


def add_category_page(
    conn: sqlite3.Connection,
    title: str,
    items: List[str],
    parent_page_id: int,
    *,
    cols: int = 4,
) -> int:
    """Add a new page of word buttons and link to it from an existing page.

    Creates a new :class:`Page` titled *title*, lays out one text button per entry
    in *items* across *cols* columns, then adds a navigation button on
    *parent_page_id* that opens the new page. All inserts run in a single
    transaction. Returns the new page's ``Id``.
    """
    if not items:
        raise PagesetError("Cannot create a page with no items.")
    if parent_page_id is not None:
        exists = conn.execute(
            "SELECT 1 FROM Page WHERE Id = ?", (parent_page_id,)
        ).fetchone()
        if exists is None:
            raise PagesetError(f"Parent page Id {parent_page_id} not found.")

    try:
        page_id = _next_id(conn, "Page")
        conn.execute(
            "INSERT INTO Page (Id, UniqueId, Title, Name) VALUES (?, ?, ?, ?)",
            (page_id, str(uuid.uuid4()), title, title),
        )

        for index, item in enumerate(items):
            col, row = index % cols, index // cols
            _add_cell(conn, page_id, col, row, label=item, message=item)

        if parent_page_id is not None:
            col, row = _next_free_slot(conn, parent_page_id, cols)
            _add_cell(
                conn,
                parent_page_id,
                col,
                row,
                label=title,
                navigate_page_id=page_id,
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return page_id


def save_as(conn: sqlite3.Connection, dest_path: str) -> str:
    """Flush pending writes and copy the edited database to *dest_path*.

    Returns *dest_path*. The caller re-imports this file into TD Snap.
    """
    conn.commit()
    source = _connection_path(conn)
    if source and source != dest_path:
        shutil.copyfile(source, dest_path)
    return dest_path


def _connection_path(conn: sqlite3.Connection) -> str:
    """Return the on-disk filename backing *conn* (empty for in-memory DBs)."""
    for _, name, filename in conn.execute("PRAGMA database_list"):
        if name == "main":
            return filename or ""
    return ""
