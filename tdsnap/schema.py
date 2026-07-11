"""Runtime schema discovery.

TD Snap's schema differs between app versions (``PageSetProperties.SchemaVersion``
was ``4.13`` in the file this package was verified against). Nothing here
hardcodes column lists: callers ask the live database what exists and adapt.
"""

import sqlite3
from typing import Dict, List, Tuple

from .errors import PagesetError

# Tables every edit in this package depends on. Failing loudly on a file that
# lacks one beats writing a page set TD Snap cannot open.
REQUIRED_TABLES = (
    "Page",
    "Button",
    "ElementReference",
    "ElementPlacement",
    "PageLayout",
    "CommandSequence",
    "ButtonPageLink",
    "SyncData",
    "PageSetProperties",
    "Synchronization",
)


def tables(conn: sqlite3.Connection) -> List[str]:
    """Return all table names in the database."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Return the column names of *table* in declaration order."""
    if not table.replace("_", "").isalnum():
        raise PagesetError(f"Suspicious table name: {table!r}")
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def primary_key(conn: sqlite3.Connection, table: str) -> str:
    """Return the name of *table*'s single-column primary key."""
    pks = [row[1] for row in conn.execute(f"PRAGMA table_info({table})") if row[5]]
    if len(pks) != 1:
        raise PagesetError(
            f"Table {table} has {len(pks)} primary-key columns; expected exactly 1."
        )
    return pks[0]


def require_tables(conn: sqlite3.Connection) -> None:
    """Raise PagesetError unless every table this package writes to exists."""
    existing = set(tables(conn))
    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        raise PagesetError(
            "File does not look like a supported TD Snap page set; missing tables: "
            + ", ".join(missing)
        )


def schema_version(conn: sqlite3.Connection) -> str:
    """Return PageSetProperties.SchemaVersion (empty string if unavailable)."""
    try:
        row = conn.execute(
            "SELECT SchemaVersion FROM PageSetProperties LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return ""
    return (row[0] if row and row[0] else "") or ""


def table_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    """Return ``{table: row count}`` for every table (used by ``inspect``)."""
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in tables(conn)
    }


def parse_grid(value: str) -> Tuple[int, int]:
    """Parse a ``"cols,rows"`` string (also the prefix of PageLayoutSetting)."""
    try:
        parts = value.split(",")
        cols, rows = int(parts[0]), int(parts[1])
    except (AttributeError, IndexError, ValueError):
        raise PagesetError(f"Unparseable grid dimension: {value!r}")
    if cols < 1 or rows < 1:
        raise PagesetError(f"Grid dimension out of range: {value!r}")
    return cols, rows
