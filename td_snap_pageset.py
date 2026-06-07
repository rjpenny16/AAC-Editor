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

import os
import shutil
import sqlite3
import sys
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


def find_page_id_by_name(conn: sqlite3.Connection, name: str) -> int:
    """Return the Id of the page whose Title/Name matches *name* (case-insensitive).

    Raises :class:`PagesetError` if no page matches or if the name is ambiguous
    (more than one page shares it). Used by the CLI so users can pick a parent
    page by its human-readable name instead of a numeric Id.
    """
    matches = [
        page_id for page_id, display in list_pages(conn)
        if display.casefold() == name.casefold()
    ]
    if not matches:
        raise PagesetError(f"No page named {name!r} found.")
    if len(matches) > 1:
        raise PagesetError(
            f"Page name {name!r} is ambiguous ({len(matches)} pages share it); "
            "use the numeric page Id instead."
        )
    return matches[0]


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


def _default_output_path(source: str) -> str:
    """Return the sibling ``<name>.edited<ext>`` path for *source*."""
    base, ext = os.path.splitext(source)
    return f"{base}.edited{ext}"


def _cmd_list(args) -> int:
    """``list`` subcommand: print every page's Id and name."""
    conn = open_pageset(args.pageset)
    try:
        pages = list_pages(conn)
    finally:
        conn.close()
    if not pages:
        print("(no pages found)")
        return 0
    width = max(len(str(page_id)) for page_id, _ in pages)
    for page_id, name in pages:
        print(f"{page_id:>{width}}  {name}")
    return 0


def _cmd_add(args) -> int:
    """``add`` subcommand: add a category page and write an edited copy.

    Mirrors what the GUI does, but without Tkinter or Ollama: the items come
    straight from the command line, so the tool is scriptable and headless.
    """
    items = [item.strip() for item in args.items.split(",") if item.strip()]
    if not items:
        raise PagesetError("No items given. Pass a comma-separated --items list.")

    conn = open_pageset(args.pageset)
    try:
        if args.parent_id is not None:
            parent_id = args.parent_id
        elif args.parent_name is not None:
            parent_id = find_page_id_by_name(conn, args.parent_name)
        else:
            parent_id = None

        page_id = add_category_page(
            conn, args.title, items, parent_id, cols=args.cols
        )
        dest = args.output or _default_output_path(args.pageset)
        save_as(conn, dest)
    finally:
        conn.close()

    print(f"Added page '{args.title}' (Id {page_id}) with {len(items)} buttons.")
    if args.parent_id is not None or args.parent_name is not None:
        print(f"Linked from parent page Id {parent_id}.")
    print(f"Wrote edited page set to: {dest}")
    print("Re-import this file into TD Snap to see your new page.")
    return 0


def main(argv: List[str] = None) -> int:
    """Command-line entry point for editing a page set without the GUI."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="td_snap_pageset",
        description="Edit a TD Snap page set (.spb/.sps) from the command line. "
        "The original export is never modified; an edited copy is written.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list the pages in a page set")
    p_list.add_argument("pageset", help="path to the exported .spb/.sps file")
    p_list.set_defaults(func=_cmd_list)

    p_add = sub.add_parser("add", help="add a category page of word buttons")
    p_add.add_argument("pageset", help="path to the exported .spb/.sps file")
    p_add.add_argument("--title", required=True, help="title of the new page")
    p_add.add_argument(
        "--items", required=True,
        help="comma-separated button labels, e.g. \"Water,Juice,Soda\"",
    )
    group = p_add.add_mutually_exclusive_group()
    group.add_argument(
        "--parent-id", type=int, default=None,
        help="Id of the existing page to link from (see the 'list' command)",
    )
    group.add_argument(
        "--parent-name", default=None,
        help="name of the existing page to link from (case-insensitive)",
    )
    p_add.add_argument(
        "--cols", type=int, default=4, help="grid width of the new page (default 4)"
    )
    p_add.add_argument(
        "-o", "--output", default=None,
        help="where to write the edited file (default: <name>.edited<ext>)",
    )
    p_add.set_defaults(func=_cmd_add)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PagesetError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
