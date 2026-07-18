"""Database validation: run after every edit, and on demand via ``verify``.

Three layers:

* SQLite-level: ``integrity_check`` and ``foreign_key_check``.
* Pageset-level (``validate_pageset``): orphan and linkage scans expressed in
  terms of the rules a working TD Snap file obeys — every placement belongs to
  a layout, every button has exactly one command sequence, every page link
  points at an existing page, every live page has a SyncData ledger row.
* Edit-level (``validate_new_page``): the full chain for a page this tool just
  built, plus a table-snapshot diff proving nothing else was touched.
"""

import hashlib
import sqlite3
import uuid as uuid_module
from typing import Dict, List

from . import schema
from .errors import PagesetError


def sqlite_checks(conn: sqlite3.Connection) -> List[str]:
    """Return problems reported by SQLite itself (empty list = clean)."""
    problems = []
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        problems.append(f"integrity_check: {result}")
    fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    for row in fk_rows:
        problems.append(
            f"foreign_key_check: table {row[0]} rowid {row[1]} references "
            f"missing row in {row[2]}"
        )
    return problems


def validate_pageset(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    """Scan any page set for the linkage rules TD Snap relies on.

    Returns ``{"problems": [...], "warnings": [...]}``. Problems are states no
    working file exhibits; warnings are states shipped Tobii content does
    exhibit (Back/Home buttons link to a virtual page GUID, and system
    dashboard/keyboard pages have no SyncData row), so an edit is only wrong
    if it *adds* warnings. Read-only, safe on a user's untouched export.
    """
    problems = list(sqlite_checks(conn))
    warnings: List[str] = []

    def count(query: str, *params) -> int:
        return conn.execute(query, params).fetchone()[0]

    orphan_placements = count(
        "SELECT COUNT(*) FROM ElementPlacement ep WHERE ep.PageLayoutId IS NULL "
        "OR NOT EXISTS (SELECT 1 FROM PageLayout pl WHERE pl.Id = ep.PageLayoutId)"
    )
    if orphan_placements:
        problems.append(
            f"{orphan_placements} ElementPlacement row(s) have no PageLayout "
            "(this is the pattern that crashed TD Snap before)."
        )

    dangling_refs = count(
        "SELECT COUNT(*) FROM ElementPlacement ep WHERE ep.ElementReferenceId "
        "IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ElementReference er "
        "WHERE er.Id = ep.ElementReferenceId)"
    )
    if dangling_refs:
        problems.append(
            f"{dangling_refs} ElementPlacement row(s) point at a missing "
            "ElementReference."
        )

    ref_no_page = count(
        "SELECT COUNT(*) FROM ElementReference er WHERE er.PageId IS NOT NULL "
        "AND er.PageId != 0 AND NOT EXISTS "
        "(SELECT 1 FROM Page p WHERE p.Id = er.PageId)"
    )
    if ref_no_page:
        problems.append(
            f"{ref_no_page} ElementReference row(s) point at a missing Page."
        )

    button_no_ref = count(
        "SELECT COUNT(*) FROM Button b WHERE b.ElementReferenceId IS NOT NULL "
        "AND b.ElementReferenceId != 0 AND NOT EXISTS "
        "(SELECT 1 FROM ElementReference er WHERE er.Id = b.ElementReferenceId)"
    )
    if button_no_ref:
        problems.append(
            f"{button_no_ref} Button row(s) point at a missing ElementReference."
        )

    button_no_commands = count(
        "SELECT COUNT(*) FROM Button b WHERE NOT EXISTS "
        "(SELECT 1 FROM CommandSequence cs WHERE cs.ButtonId = b.Id)"
    )
    if button_no_commands:
        problems.append(
            f"{button_no_commands} Button row(s) have no CommandSequence "
            "(every real TD Snap button has exactly one)."
        )

    button_multi_commands = count(
        "SELECT COUNT(*) FROM (SELECT ButtonId FROM CommandSequence "
        "GROUP BY ButtonId HAVING COUNT(*) > 1)"
    )
    if button_multi_commands:
        problems.append(
            f"{button_multi_commands} Button row(s) have more than one "
            "CommandSequence."
        )

    broken_links = count(
        "SELECT COUNT(*) FROM ButtonPageLink l WHERE NOT EXISTS "
        "(SELECT 1 FROM Page p WHERE p.UniqueId = l.PageUniqueId)"
    )
    if broken_links:
        warnings.append(
            f"{broken_links} ButtonPageLink row(s) point at a page UniqueId "
            "not present in this file (normal for shipped Back/Home buttons)."
        )

    null_page_uuid = count(
        "SELECT COUNT(*) FROM Page WHERE UniqueId IS NULL OR UniqueId = ''"
    )
    if null_page_uuid:
        problems.append(f"{null_page_uuid} Page row(s) have no UniqueId.")

    dup_page_uuid = count(
        "SELECT COUNT(*) FROM (SELECT UniqueId FROM Page WHERE UniqueId IS NOT "
        "NULL GROUP BY UniqueId HAVING COUNT(*) > 1)"
    )
    if dup_page_uuid:
        problems.append(f"{dup_page_uuid} duplicated Page UniqueId value(s).")

    occupied = {}
    overlaps = set()
    invalid_placements = 0
    for row in conn.execute(
        "SELECT ep.Id, ep.PageLayoutId, ep.GridPosition, ep.GridSpan, "
        "pl.PageLayoutSetting FROM ElementPlacement ep "
        "JOIN PageLayout pl ON pl.Id = ep.PageLayoutId WHERE ep.Visible = 1"
    ):
        try:
            cols, rows = schema.parse_grid(row["PageLayoutSetting"])
            col, grid_row = schema.parse_grid_position(row["GridPosition"])
            col_span, row_span = schema.parse_grid_span(row["GridSpan"])
        except PagesetError:
            invalid_placements += 1
            continue
        for x in range(col, col + col_span):
            for y in range(grid_row, grid_row + row_span):
                cell = (row["PageLayoutId"], x, y)
                if cell in occupied:
                    overlaps.add(cell)
                occupied[cell] = row["Id"]
    if invalid_placements:
        problems.append(
            f"{invalid_placements} visible ElementPlacement row(s) have an "
            "invalid grid position/span."
        )
    if overlaps:
        problems.append(
            f"{len(overlaps)} grid cell(s) hold more than one visible button."
        )

    pages_no_syncdata = count(
        "SELECT COUNT(*) FROM Page p WHERE p.PageType = 1 AND NOT EXISTS "
        "(SELECT 1 FROM SyncData s WHERE s.UniqueId = p.UniqueId)"
    )
    if pages_no_syncdata:
        warnings.append(
            f"{pages_no_syncdata} vocabulary page(s) have no SyncData ledger "
            "row (normal for shipped dashboard/keyboard pages)."
        )

    sync_mismatch = count(
        "SELECT COUNT(*) FROM Page p JOIN SyncData s ON s.UniqueId = p.UniqueId "
        "WHERE p.PageType = 1 AND s.Deleted = 0 AND s.Timestamp != p.Timestamp"
    )
    if sync_mismatch:
        problems.append(
            f"{sync_mismatch} page(s) whose SyncData Timestamp disagrees with "
            "the Page row."
        )

    return {"problems": problems, "warnings": warnings}


def new_warnings(before: Dict[str, List[str]], after: Dict[str, List[str]]) -> List[str]:
    """Warnings present after an edit that weren't there before it."""
    return [w for w in after["warnings"] if w not in before["warnings"]]


def _is_guid(value) -> bool:
    try:
        uuid_module.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def validate_new_page(conn: sqlite3.Connection, report: Dict) -> List[str]:
    """Check the complete chain for a page just built by ``add_category_page``."""
    problems = []
    page_uuid = report["page_unique_id"]
    page_id = report["page_id"]
    expected_buttons = len(report["button_ids"])

    page = conn.execute("SELECT * FROM Page WHERE Id = ?", (page_id,)).fetchone()
    if page is None:
        return [f"New page Id {page_id} is missing."]
    if page["UniqueId"] != page_uuid or not _is_guid(page["UniqueId"]):
        problems.append("New page's UniqueId is wrong or not a GUID.")

    layouts = conn.execute(
        "SELECT * FROM PageLayout WHERE PageId = ?", (page_id,)
    ).fetchall()
    if len(layouts) != 1:
        problems.append(f"New page has {len(layouts)} PageLayout rows; expected 1.")
        return problems
    layout_id = layouts[0]["Id"]

    placements = conn.execute(
        "SELECT * FROM ElementPlacement WHERE PageLayoutId = ?", (layout_id,)
    ).fetchall()
    if len(placements) != expected_buttons:
        problems.append(
            f"New page has {len(placements)} placements; expected {expected_buttons}."
        )
    for placement in placements:
        if not placement["GridSpan"]:
            problems.append("A new placement is missing GridSpan.")
        ref = conn.execute(
            "SELECT * FROM ElementReference WHERE Id = ?",
            (placement["ElementReferenceId"],),
        ).fetchone()
        if ref is None or ref["PageId"] != page_id:
            problems.append("A new placement's ElementReference is broken.")
            continue
        button = conn.execute(
            "SELECT * FROM Button WHERE ElementReferenceId = ?", (ref["Id"],)
        ).fetchone()
        if button is None:
            problems.append("A new cell has no Button.")
            continue
        if not _is_guid(button["UniqueId"]):
            problems.append(f"Button {button['Id']} has no GUID UniqueId.")
        sequences = conn.execute(
            "SELECT COUNT(*) FROM CommandSequence WHERE ButtonId = ?",
            (button["Id"],),
        ).fetchone()[0]
        if sequences != 1:
            problems.append(
                f"Button {button['Id']} has {sequences} CommandSequence rows; "
                "expected 1."
            )

    # Every requested button must exist with exactly the requested content:
    # label shown, message spoken (phrase buttons), border color + 3px
    # thickness (function coding). Catches silent drops or mixups.
    for spec in report.get("buttons", []):
        button = conn.execute(
            "SELECT * FROM Button WHERE Id = ?", (spec["id"],)
        ).fetchone()
        if button is None:
            problems.append(f"Requested button {spec['label']!r} is missing.")
            continue
        if button["Label"] != spec["label"]:
            problems.append(
                f"Button {spec['id']} label is {button['Label']!r}; "
                f"expected {spec['label']!r}."
            )
        if button["Message"] != spec.get("message"):
            problems.append(
                f"Button {spec['label']!r} speaks {button['Message']!r}; "
                f"expected {spec.get('message')!r}."
            )
        expected_border = spec.get("border_color")
        if button["BorderColor"] != expected_border:
            problems.append(
                f"Button {spec['label']!r} border color is "
                f"{button['BorderColor']!r}; expected {expected_border!r}."
            )
        if expected_border is not None and not button["BorderThickness"]:
            problems.append(
                f"Button {spec['label']!r} has a border color but no "
                "border thickness."
            )

    sync = conn.execute(
        "SELECT * FROM SyncData WHERE UniqueId = ?", (page_uuid,)
    ).fetchone()
    if sync is None:
        problems.append("New page has no SyncData row.")
    elif sync["Timestamp"] != page["Timestamp"] or sync["SyncHash"] != page["SyncHash"]:
        problems.append("New page's SyncData row disagrees with the Page row.")

    if report.get("nav_button_id") is not None:
        nav_id = report["nav_button_id"]
        link = conn.execute(
            "SELECT * FROM ButtonPageLink WHERE ButtonId = ?", (nav_id,)
        ).fetchone()
        if link is None or link["PageUniqueId"] != page_uuid:
            problems.append("Navigation button's ButtonPageLink is missing/wrong.")
        commands = conn.execute(
            "SELECT SerializedCommands FROM CommandSequence WHERE ButtonId = ?",
            (nav_id,),
        ).fetchone()
        if commands is None or page_uuid not in (commands[0] or ""):
            problems.append(
                "Navigation button's CommandSequence doesn't reference the new page."
            )

    return problems


# Tables add_category_page is allowed to touch. Anything else changing is a bug.
EXPECTED_CHANGED_TABLES = frozenset(
    {
        "Page",
        "PageLayout",
        "ElementReference",
        "Button",
        "CommandSequence",
        "ElementPlacement",
        "ButtonPageLink",
        "SyncData",
        "Synchronization",
        "PageSetProperties",
        "sqlite_sequence",
    }
)


def table_snapshot(conn: sqlite3.Connection) -> Dict[str, Dict[str, object]]:
    """Hash every table and retain keyed rows for tables the writer may touch."""
    snapshot = {}
    for table in schema.tables(conn):
        digest = hashlib.sha256()
        cursor = conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
        columns = tuple(description[0] for description in cursor.description)
        key_name = (
            "name" if table == "sqlite_sequence" else
            "UniqueId" if table == "SyncData" else "Id"
        )
        key_index = columns.index(key_name) if (
            table in EXPECTED_CHANGED_TABLES and key_name in columns
        ) else None
        rows = {}
        count = 0
        for row in cursor:
            values = tuple(row)
            digest.update(repr(values).encode("utf-8", "backslashreplace"))
            if key_index is not None:
                rows[values[key_index]] = values
            count += 1
        snapshot[table] = {
            "count": count,
            "digest": digest.hexdigest(),
            "columns": columns if key_index is not None else (),
            "rows": rows,
        }
    return snapshot


def diff_snapshots(
    before: Dict[str, Dict[str, object]], after: Dict[str, Dict[str, object]]
) -> List[str]:
    """Return the names of tables whose contents differ between snapshots."""
    changed = []
    for table in sorted(set(before) | set(after)):
        if before.get(table) != after.get(table):
            changed.append(table)
    return changed


def check_roundtrip(
    before: Dict[str, Dict[str, object]], after: Dict[str, Dict[str, object]]
) -> List[str]:
    """Reject unexpected table changes and mutations to pre-existing rows."""
    problems = []
    unexpected = [
        table for table in diff_snapshots(before, after)
        if table not in EXPECTED_CHANGED_TABLES
    ]
    if unexpected:
        problems.append(
            "Tables changed that the edit should never touch: "
            + ", ".join(unexpected)
        )
    removed_tables = sorted(set(before) - set(after))
    if removed_tables:
        problems.append(
            "Tables disappeared during the edit: " + ", ".join(removed_tables)
        )

    allowed_columns = {
        "Page": {"Timestamp"},
        "SyncData": {"Timestamp"},
        "Synchronization": {"PageSetTimestamp"},
        "PageSetProperties": {"Timestamp"},
        "sqlite_sequence": {"seq"},
    }
    changed_existing = {}
    for table in sorted(EXPECTED_CHANGED_TABLES & before.keys() & after.keys()):
        old, new = before[table], after[table]
        old_columns = old["columns"]
        new_columns = new["columns"]
        if old_columns != new_columns:
            problems.append(f"Table {table}'s schema changed during the edit.")
            continue
        old_rows = old["rows"]
        new_rows = new["rows"]
        removed = set(old_rows) - set(new_rows)
        if removed:
            problems.append(f"Table {table} lost {len(removed)} pre-existing row(s).")
        changed = []
        for key in set(old_rows) & set(new_rows):
            if old_rows[key] == new_rows[key]:
                continue
            changed_columns = {
                column
                for column, old_value, new_value in zip(
                    old_columns, old_rows[key], new_rows[key]
                )
                if old_value != new_value
            }
            if not changed_columns <= allowed_columns.get(table, set()):
                problems.append(
                    f"Pre-existing {table} row {key!r} changed unexpected columns: "
                    + ", ".join(sorted(changed_columns))
                    + "."
                )
            changed.append(key)
        changed_existing[table] = changed

    for table in ("Page", "SyncData", "Synchronization", "PageSetProperties"):
        if len(changed_existing.get(table, [])) > 1:
            problems.append(f"The edit changed more than one pre-existing {table} row.")

    page_ids = changed_existing.get("Page", [])
    sync_ids = changed_existing.get("SyncData", [])
    if page_ids or sync_ids:
        page_columns = before["Page"]["columns"]
        sync_columns = before["SyncData"]["columns"]
        page_unique_ids = {
            before["Page"]["rows"][key][page_columns.index("UniqueId")]
            for key in page_ids
        }
        sync_unique_ids = {
            before["SyncData"]["rows"][key][sync_columns.index("UniqueId")]
            for key in sync_ids
        }
        if page_unique_ids != sync_unique_ids:
            problems.append(
                "The pre-existing Page and SyncData timestamp changes target "
                "different pages."
            )
    return problems
