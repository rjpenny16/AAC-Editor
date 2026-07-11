"""Headless command line for editing TD Snap page sets.

    python -m tdsnap list <file>            show vocabulary pages
    python -m tdsnap add <file> --title Snacks --items "Chips,Apple" \
        --parent-name "Home Page"           build a page + nav button
    python -m tdsnap verify <file>          run all safety checks on any file
    python -m tdsnap inspect <file>         show schema version, grid, tables
"""

import argparse
import sqlite3
import sys
from typing import List, Optional

from . import builder, schema, validate
from .errors import PagesetError
from .pageset import Pageset, default_output_path, is_sqlite_file
from .ticks import ticks_to_datetime


def _open_readonly(path: str) -> sqlite3.Connection:
    """Open *path* directly but read-only (verify/inspect never copy or write)."""
    if not is_sqlite_file(path):
        raise PagesetError(f"{path!r} is not a SQLite database.")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _cmd_list(args) -> int:
    conn = _open_readonly(args.pageset)
    try:
        schema.require_tables(conn)
        pages = [
            (row["Id"], row["DisplayName"])
            for row in conn.execute(
                "SELECT Id, COALESCE(NULLIF(Title, ''), 'Page ' || Id) AS "
                "DisplayName FROM Page WHERE PageType = 1 "
                "ORDER BY DisplayName COLLATE NOCASE"
            )
        ]
    finally:
        conn.close()
    if not pages:
        print("(no vocabulary pages found)")
        return 0
    width = max(len(str(page_id)) for page_id, _ in pages)
    for page_id, name in pages:
        print(f"{page_id:>{width}}  {name}")
    return 0


def _cmd_add(args) -> int:
    items = [item.strip() for item in args.items.split(",") if item.strip()]
    with Pageset(args.pageset) as ps:
        if args.parent_id is not None:
            parent_id: Optional[int] = args.parent_id
        elif args.parent_name is not None:
            parent_id = ps.find_page_id_by_name(args.parent_name)
        else:
            parent_id = None

        baseline = validate.validate_pageset(ps.conn)
        before = validate.table_snapshot(ps.conn)
        report = builder.add_category_page(ps, args.title, items, parent_id)
        after = validate.table_snapshot(ps.conn)

        result = validate.validate_pageset(ps.conn)
        problems = (
            validate.check_roundtrip(before, after)
            + validate.validate_new_page(ps.conn, report)
            + result["problems"]
            + validate.new_warnings(baseline, result)
        )
        if problems:
            print("Validation FAILED — no file was written:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1

        dest = ps.save_as(args.output)

    print(
        f"Added page '{args.title}' (Id {report['page_id']}) with "
        f"{len(report['button_ids'])} buttons."
    )
    if report["nav_button_id"] is not None:
        print(f"Linked from parent page Id {parent_id}.")
    print(f"All validation checks passed.")
    print(f"Wrote edited page set to: {dest}")
    print("Import it into a TEST TD Snap user first — see docs/IMPORT_SAFETY.md.")
    return 0


def _cmd_verify(args) -> int:
    conn = _open_readonly(args.pageset)
    try:
        result = validate.validate_pageset(conn)
        problems, warnings = result["problems"], result["warnings"]
        if args.show_sync:
            print("Sync fields (for debugging import failures):")
            for row in conn.execute(
                "SELECT p.Id, p.Title, p.Timestamp, p.SyncHash FROM Page p "
                "WHERE p.PageType = 1 ORDER BY p.Timestamp DESC LIMIT 10"
            ):
                when = ticks_to_datetime(row["Timestamp"]).isoformat()
                print(
                    f"  Page {row['Id']} {row['Title']!r}: Timestamp={row['Timestamp']} "
                    f"({when}) SyncHash={row['SyncHash']}"
                )
    finally:
        conn.close()

    for warning in warnings:
        print(f"note: {warning}")
    if problems:
        print(f"{len(problems)} problem(s) found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK — no problems found.")
    return 0


def _cmd_inspect(args) -> int:
    conn = _open_readonly(args.pageset)
    try:
        version = schema.schema_version(conn)
        print(f"SchemaVersion: {version or '(unknown)'}")
        row = conn.execute(
            "SELECT FriendlyName, GridDimension, Language FROM PageSetProperties "
            "LIMIT 1"
        ).fetchone()
        if row:
            print(f"Page set:      {row['FriendlyName']}")
            print(f"Grid:          {row['GridDimension']}")
            print(f"Language:      {row['Language']}")
        print("Tables:")
        for table, count in sorted(schema.table_counts(conn).items()):
            print(f"  {table:<24} {count:>7} rows")
    finally:
        conn.close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tdsnap",
        description="Safely edit a TD Snap page set (.sps/.spb). The original "
        "file is never modified; an edited copy is written.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list the vocabulary pages in a page set")
    p_list.add_argument("pageset")
    p_list.set_defaults(func=_cmd_list)

    p_add = sub.add_parser("add", help="add a category page of speaking buttons")
    p_add.add_argument("pageset")
    p_add.add_argument("--title", required=True, help="title of the new page")
    p_add.add_argument(
        "--items", required=True,
        help='comma-separated button labels, e.g. "Water,Juice,Soda"',
    )
    group = p_add.add_mutually_exclusive_group()
    group.add_argument("--parent-id", type=int, default=None,
                       help="Id of the page to link from (see 'list')")
    group.add_argument("--parent-name", default=None,
                       help="name of the page to link from (case-insensitive)")
    p_add.add_argument("-o", "--output", default=None,
                       help="where to write the edited file "
                            "(default: <name>.edited<ext>)")
    p_add.set_defaults(func=_cmd_add)

    p_verify = sub.add_parser(
        "verify", help="run all safety checks on a page set (read-only)"
    )
    p_verify.add_argument("pageset")
    p_verify.add_argument("--show-sync", action="store_true",
                          help="also print recent pages' Timestamp/SyncHash")
    p_verify.set_defaults(func=_cmd_verify)

    p_inspect = sub.add_parser(
        "inspect", help="show a page set's schema version, grid and tables"
    )
    p_inspect.add_argument("pageset")
    p_inspect.set_defaults(func=_cmd_inspect)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PagesetError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
