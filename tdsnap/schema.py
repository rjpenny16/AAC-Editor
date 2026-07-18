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

SUPPORTED_SCHEMA_VERSIONS = frozenset({"4.13"})

# Columns the exported-file writer reads or writes directly. Optional media
# columns are still discovered at runtime in templates.filtered_overrides.
REQUIRED_COLUMNS = {
    "Page": {"Id", "UniqueId", "Title", "PageType", "Timestamp", "SyncHash",
             "ContentTag", "SerializedMetadata"},
    "Button": {"Id", "Label", "Message", "BorderColor", "BorderThickness",
               "UniqueId", "CommandFlags", "ElementReferenceId", "ContentTag"},
    "ElementReference": {"Id", "PageId", "ElementType"},
    "ElementPlacement": {"Id", "GridPosition", "GridSpan", "Visible",
                         "ElementReferenceId", "PageLayoutId"},
    "PageLayout": {"Id", "PageLayoutSetting", "PageId"},
    "CommandSequence": {"Id", "SerializedCommands", "ButtonId"},
    "ButtonPageLink": {"Id", "ButtonId", "PageUniqueId"},
    "SyncData": {"UniqueId", "Type", "Timestamp", "SyncHash", "Deleted",
                 "Description"},
    "PageSetProperties": {"Id", "SchemaVersion", "GridDimension", "Timestamp"},
    "Synchronization": {"Id", "PageSetTimestamp"},
}
REQUIRED_PRIMARY_KEYS = {
    table: ("UniqueId" if table == "SyncData" else "Id")
    for table in REQUIRED_COLUMNS
}


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


def require_supported_schema(conn: sqlite3.Connection) -> None:
    """Reject page sets the exported-file writer has not been tested against."""
    version = schema_version(conn)
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        raise PagesetError(
            f"TD Snap schema {version or 'unknown'} is not supported for editing; "
            f"supported version: {supported}."
        )
    missing = {}
    for table, required in REQUIRED_COLUMNS.items():
        absent = sorted(required - set(columns(conn, table)))
        if absent:
            missing[table] = absent
    if missing:
        details = "; ".join(
            f"{table}: {', '.join(names)}" for table, names in missing.items()
        )
        raise PagesetError(f"Page-set schema is missing required columns ({details}).")
    for table, expected in REQUIRED_PRIMARY_KEYS.items():
        actual = primary_key(conn, table)
        if actual != expected:
            raise PagesetError(
                f"Table {table} has primary key {actual!r}; expected {expected!r}."
            )
    for table in ("PageSetProperties", "Synchronization"):
        count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if count != 1:
            raise PagesetError(f"Table {table} has {count} rows; expected exactly 1.")


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


def parse_grid_position(value: str) -> Tuple[int, int]:
    """Parse a zero-based ``"col,row"`` placement coordinate."""
    try:
        parts = value.split(",")
        col, row = int(parts[0]), int(parts[1])
    except (AttributeError, IndexError, ValueError):
        raise PagesetError(f"Unparseable grid position: {value!r}")
    if len(parts) != 2 or col < 0 or row < 0:
        raise PagesetError(f"Grid position out of range: {value!r}")
    return col, row


def parse_grid_span(value: str) -> Tuple[int, int]:
    """Parse an exact, positive ``"column_span,row_span"`` value."""
    try:
        parts = value.split(",")
        col_span, row_span = int(parts[0]), int(parts[1])
    except (AttributeError, IndexError, ValueError):
        raise PagesetError(f"Unparseable grid span: {value!r}")
    if len(parts) != 2 or col_span < 1 or row_span < 1:
        raise PagesetError(f"Grid span out of range: {value!r}")
    return col_span, row_span
