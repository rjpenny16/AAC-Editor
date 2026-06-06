"""Inspect and diff TD Snap page set files (Phase 0 verification gate).

Our editor (``td_snap_pageset.py``) builds on the schema documented by the
open-source ``obf-node`` converter, but that source has gaps for *writing* files
TD Snap accepts on import (home-page marker, schema version, symbol linkage). Use
this tool on a REAL export to confirm those details before trusting the editor:

    # Confirm container + dump schema and sample rows
    python inspect_pageset.py mypageset.sps

    # Diff two exports (e.g. before vs. after manually adding a page in TD Snap)
    python inspect_pageset.py before.sps after.sps

The diff is how we discover which fields TD Snap actually requires: hand-edit a
page set inside TD Snap, export again, and see exactly what changed.
"""

import sqlite3
import sys
import zipfile

from td_snap_pageset import SQLITE_MAGIC, is_sqlite_file

SAMPLE_ROWS = 5


def detect_container(path: str) -> str:
    """Report the physical container of *path* (sqlite / zip / unknown)."""
    if is_sqlite_file(path):
        return "raw SQLite database"
    if zipfile.is_zipfile(path):
        return "ZIP archive (NOT a bare SQLite DB — editor assumptions need revisiting)"
    with open(path, "rb") as handle:
        head = handle.read(16)
    return f"unknown (first 16 bytes: {head!r}, expected {SQLITE_MAGIC!r})"


def _tables(conn: sqlite3.Connection) -> list:
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]


def dump(path: str) -> None:
    """Print container type, schema, row counts, and sample rows for *path*."""
    print(f"\n=== {path} ===")
    print(f"Container: {detect_container(path)}")
    if not is_sqlite_file(path):
        print("Cannot introspect tables: file is not a bare SQLite database.")
        return

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        for table in _tables(conn):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"\n-- {table}  ({count} rows)")
            schema = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if schema and schema[0]:
                print(schema[0])
            for row in conn.execute(f"SELECT * FROM {table} LIMIT {SAMPLE_ROWS}"):
                print("   ", dict(row))
    finally:
        conn.close()


def _table_signatures(path: str) -> dict:
    """Return ``{table: (schema_sql, row_count)}`` for diffing two files."""
    conn = sqlite3.connect(path)
    try:
        result = {}
        for table in _tables(conn):
            schema = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            result[table] = (schema[0] if schema else None, count)
        return result
    finally:
        conn.close()


def diff(before: str, after: str) -> None:
    """Print table-level differences (added tables, row-count deltas, schema changes)."""
    print(f"\n=== diff: {before}  ->  {after} ===")
    if not (is_sqlite_file(before) and is_sqlite_file(after)):
        print("Both files must be bare SQLite databases to diff.")
        return

    sig_before, sig_after = _table_signatures(before), _table_signatures(after)
    for table in sorted(set(sig_before) | set(sig_after)):
        b, a = sig_before.get(table), sig_after.get(table)
        if b is None:
            print(f"+ table added: {table} ({a[1]} rows)")
        elif a is None:
            print(f"- table removed: {table}")
        else:
            if b[1] != a[1]:
                print(f"~ {table}: rows {b[1]} -> {a[1]} (delta {a[1] - b[1]:+d})")
            if b[0] != a[0]:
                print(f"~ {table}: schema changed")


def main(argv: list) -> int:
    if len(argv) == 2:
        dump(argv[1])
    elif len(argv) == 3:
        dump(argv[1])
        dump(argv[2])
        diff(argv[1], argv[2])
    else:
        print(__doc__)
        print("Usage:\n  python inspect_pageset.py <file>\n"
              "  python inspect_pageset.py <before> <after>")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
