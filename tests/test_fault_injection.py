"""Interrupt every write an edit makes and require the page set to come back unchanged.

The builder's contract is that an edit is one transaction: if anything fails, the
working copy is exactly what it was. The existing rollback tests trigger one
failure each. These fail the Nth write for every N, so a statement added later
without a matching rollback cannot slip through.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from tdsnap import builder, obf, validate
from tdsnap.errors import PagesetError

WRITES = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}


def count_writes(conn, operation):
    seen = []

    def authorizer(action, *_):
        if action in WRITES:
            seen.append(action)
        return sqlite3.SQLITE_OK

    conn.set_authorizer(authorizer)
    try:
        operation()
    finally:
        conn.set_authorizer(None)
    return len(seen)


def fail_nth_write(conn, n):
    state = {"seen": 0}

    def authorizer(action, *_):
        if action in WRITES:
            state["seen"] += 1
            if state["seen"] == n:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    conn.set_authorizer(authorizer)


def assert_every_failure_rolls_back(make_pageset, operation):
    """*operation(ps)* must leave the page set untouched whichever write fails."""
    probe = make_pageset()
    total = count_writes(probe.conn, lambda: operation(probe))
    assert total > 0
    for n in range(1, total + 1):
        ps = make_pageset()
        before = validate.table_snapshot(ps.conn)
        fail_nth_write(ps.conn, n)
        try:
            with pytest.raises((sqlite3.DatabaseError, PagesetError)):
                operation(ps)
        finally:
            ps.conn.set_authorizer(None)
        assert not ps.conn.in_transaction, f"write {n} of {total} left a transaction open"
        after = validate.table_snapshot(ps.conn)
        assert validate.diff_snapshots(before, after) == [], f"write {n} of {total} leaked"


@pytest.fixture
def make_pageset(seeded_source, tmp_path):
    opened = []

    def make():
        from tdsnap.pageset import Pageset

        ps = Pageset(seeded_source, working_copy=str(tmp_path / f"w{len(opened)}.sps"))
        opened.append(ps)
        return ps

    yield make
    for ps in opened:
        ps.close()


def test_a_failed_new_page_leaves_nothing_behind(make_pageset):
    def operation(ps):
        builder.add_category_page(
            ps, "Fault", ["one", "two", "three"], ps.find_page_id_by_name("Home Page")
        )

    assert_every_failure_rolls_back(make_pageset, operation)


def test_a_failed_extension_leaves_nothing_behind(make_pageset):
    def operation(ps):
        builder.add_buttons_to_page(
            ps, ps.find_page_id_by_name("Home Page"), ["alpha", "beta", "gamma"]
        )

    assert_every_failure_rolls_back(make_pageset, operation)


def test_a_failed_board_import_leaves_nothing_behind(make_pageset):
    board = {
        "format": "open-board-0.1", "id": "a", "name": "Fault",
        "grid": {"rows": 2, "columns": 2, "order": [["1", "2"], ["3", None]]},
        "buttons": [
            {"id": "1", "label": "one"}, {"id": "2", "label": "two"},
            {"id": "3", "label": "three"},
        ],
    }

    def operation(ps):
        data = obf.read_bytes(json.dumps(board).encode())
        plan = obf.plan_import(
            data, grid=ps.grid_dimension(),
            existing_titles=[title for _, title in ps.list_pages()],
        )
        builder.add_linked_pages(ps, plan, ps.find_page_id_by_name("Home Page"))

    assert_every_failure_rolls_back(make_pageset, operation)
