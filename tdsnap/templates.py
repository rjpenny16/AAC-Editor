"""Template selection and row cloning.

The safe way to insert rows into a schema we don't fully control is to copy a
row TD Snap itself wrote and override only the fields we understand. Column
lists come from ``PRAGMA table_info`` at call time, so cloning keeps working
when a TD Snap update adds columns — the new columns are simply copied from
the template.
"""

import json
import sqlite3
from typing import Any, Dict, Mapping, Optional

from . import schema
from .errors import PagesetError
from .pageset import PAGE_TYPE_VOCAB

# Command sequences and flags observed in a real page set (schema 4.13):
# every button has exactly one CommandSequence row. "$type":"3" speaks the
# button into the message bar (CommandFlags=8); "$type":"2" navigates to the
# page whose UniqueId is LinkedPageId (CommandFlags=9, plus a ButtonPageLink
# row carrying the same GUID).
SPEAK_COMMANDS = '{"$type":"1","$values":[{"$type":"3","MessageAction":0}]}'
COMMAND_FLAGS_SPEAK = 8
COMMAND_FLAGS_NAVIGATE = 9


def navigate_commands(page_unique_id: str) -> str:
    """Serialized command sequence for a button that opens *page_unique_id*."""
    return json.dumps(
        {"$type": "1", "$values": [{"$type": "2", "LinkedPageId": page_unique_id,
                                    "IsVisit": False}]},
        separators=(",", ":"),
    )


def clone_row(
    conn: sqlite3.Connection,
    table: str,
    template: Mapping[str, Any],
    overrides: Dict[str, Any],
) -> int:
    """Insert a copy of *template* into *table* and return the new row id.

    Every column except the primary key is copied from the template, then
    *overrides* are applied. The primary key is always assigned by SQLite so
    AUTOINCREMENT bookkeeping (``sqlite_sequence``) stays correct. Override
    keys that aren't columns of *table* raise, catching typos and schema
    mismatches instead of silently dropping data.
    """
    pk = schema.primary_key(conn, table)
    cols = [c for c in schema.columns(conn, table) if c != pk]

    unknown = set(overrides) - set(cols)
    if unknown:
        raise PagesetError(
            f"Cannot set columns that don't exist on {table}: {sorted(unknown)}"
        )

    values = {c: template[c] if c in template.keys() else None for c in cols}
    values.update(overrides)

    placeholders = ", ".join("?" for _ in cols)
    column_list = ", ".join(f'"{c}"' for c in cols)
    cursor = conn.execute(
        f'INSERT INTO "{table}" ({column_list}) VALUES ({placeholders})',
        [values[c] for c in cols],
    )
    return cursor.lastrowid


def filtered_overrides(
    conn: sqlite3.Connection, table: str, desired: Dict[str, Any]
) -> Dict[str, Any]:
    """Drop override keys that this file's schema doesn't have.

    Used for nice-to-have fields (e.g. ``SymbolColorDataId`` appeared in a
    later schema revision). Critical fields are passed straight to
    ``clone_row`` instead, so their absence fails loudly.
    """
    existing = set(schema.columns(conn, table))
    return {k: v for k, v in desired.items() if k in existing}


def find_template_page(conn: sqlite3.Connection) -> sqlite3.Row:
    """Return a vocabulary Page row to clone for new pages.

    Prefers a user-created page (``SerializedMetadata IS NULL``) because
    shipped pages carry signed content metadata we must not copy onto new
    pages anyway.
    """
    row = conn.execute(
        "SELECT * FROM Page WHERE PageType = ? "
        "ORDER BY (SerializedMetadata IS NULL) DESC, Id LIMIT 1",
        (PAGE_TYPE_VOCAB,),
    ).fetchone()
    if row is None:
        raise PagesetError(
            "No vocabulary page found to use as a template; this page set "
            "looks empty or unsupported."
        )
    return row


def _find_chain(
    conn: sqlite3.Connection, command_flags: int, needs_page_link: bool
) -> Dict[str, sqlite3.Row]:
    """Return a real ``{button, reference}`` pair with *command_flags*."""
    link_clause = (
        "AND EXISTS (SELECT 1 FROM ButtonPageLink l WHERE l.ButtonId = b.Id) "
        if needs_page_link
        else ""
    )
    row = conn.execute(
        "SELECT b.Id AS ButtonId, er.Id AS RefId FROM Button b "
        "JOIN ElementReference er ON b.ElementReferenceId = er.Id "
        "JOIN CommandSequence cs ON cs.ButtonId = b.Id "
        f"WHERE b.CommandFlags = ? AND b.Label IS NOT NULL {link_clause}"
        "ORDER BY b.Id LIMIT 1",
        (command_flags,),
    ).fetchone()
    if row is None:
        kind = "navigation" if needs_page_link else "speaking"
        raise PagesetError(
            f"No {kind} button found to use as a template; this page set "
            "looks unsupported."
        )
    button = conn.execute(
        "SELECT * FROM Button WHERE Id = ?", (row["ButtonId"],)
    ).fetchone()
    reference = conn.execute(
        "SELECT * FROM ElementReference WHERE Id = ?", (row["RefId"],)
    ).fetchone()
    return {"button": button, "reference": reference}


def find_speak_chain(conn: sqlite3.Connection) -> Dict[str, sqlite3.Row]:
    """A real speaking button + its ElementReference, to clone for word cells."""
    return _find_chain(conn, COMMAND_FLAGS_SPEAK, needs_page_link=False)


def find_nav_chain(conn: sqlite3.Connection) -> Dict[str, sqlite3.Row]:
    """A real page-link button + its ElementReference, to clone for nav cells."""
    return _find_chain(conn, COMMAND_FLAGS_NAVIGATE, needs_page_link=True)
