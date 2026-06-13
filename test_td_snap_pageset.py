"""Unit tests for the TD Snap page set editor.

These build a synthetic SQLite database matching the TD Snap schema, so they run
without TD Snap installed and give the project its first real test coverage.
"""

import os
import sqlite3
import tempfile

import pytest

import td_snap_pageset as ps

# Minimal TD Snap schema (subset our editor touches), used to build fixtures.
SCHEMA = """
CREATE TABLE Page (Id INTEGER PRIMARY KEY, UniqueId TEXT UNIQUE, Title TEXT,
                   Name TEXT, BackgroundColor INTEGER);
CREATE TABLE Button (Id INTEGER PRIMARY KEY, Label TEXT, Message TEXT,
                     NavigatePageId INTEGER, ElementReferenceId INTEGER,
                     LibrarySymbolId INTEGER, PageSetImageId INTEGER);
CREATE TABLE ElementReference (Id INTEGER PRIMARY KEY, PageId INTEGER,
                              ForegroundColor INTEGER, BackgroundColor INTEGER);
CREATE TABLE ElementPlacement (Id INTEGER PRIMARY KEY, ElementReferenceId INTEGER,
                              GridPosition TEXT, GridSpan TEXT NOT NULL DEFAULT '1,1');
CREATE TABLE PageSetData (Id INTEGER PRIMARY KEY, Identifier TEXT UNIQUE,
                          Data BLOB, RefCount INTEGER DEFAULT 1);
CREATE TABLE PageSetProperties (Id INTEGER PRIMARY KEY, Language TEXT);
"""


def _make_pageset(path: str) -> None:
    """Write a valid SQLite page set with one home page to *path*."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO Page (Id, UniqueId, Title, Name) VALUES (1, 'home-uid', 'Home', 'Home')"
    )
    conn.commit()
    conn.close()


@pytest.fixture
def pageset_path(tmp_path):
    path = str(tmp_path / "sample.sps")
    _make_pageset(path)
    return path


def test_open_pageset_rejects_non_sqlite(tmp_path):
    bogus = tmp_path / "notdb.sps"
    bogus.write_text("this is not a database")
    with pytest.raises(ps.PagesetError):
        ps.open_pageset(str(bogus))


def test_open_pageset_copies_and_preserves_original(pageset_path):
    before = os.path.getsize(pageset_path)
    conn = ps.open_pageset(pageset_path)
    try:
        ps.add_category_page(conn, "Places", ["Walmart", "Target"], parent_page_id=1)
    finally:
        conn.close()
    # Original untouched; a separate .editing copy was created.
    assert os.path.getsize(pageset_path) == before


def test_list_pages(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        assert ps.list_pages(conn) == [(1, "Home")]
    finally:
        conn.close()


def test_add_category_page_creates_page_and_buttons(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        items = ["Walmart", "McDonald's", "Taco Bell"]
        new_id = ps.add_category_page(conn, "Favorite Places", items, parent_page_id=1)

        # New page exists with the right title.
        page = conn.execute(
            "SELECT Title, Name, UniqueId FROM Page WHERE Id = ?", (new_id,)
        ).fetchone()
        assert page["Title"] == "Favorite Places"
        assert page["UniqueId"]  # a generated UUID

        # One button per item lives on the new page, with Message = spoken text.
        item_buttons = conn.execute(
            "SELECT b.Label, b.Message FROM Button b "
            "JOIN ElementReference er ON b.ElementReferenceId = er.Id "
            "WHERE er.PageId = ? ORDER BY b.Id",
            (new_id,),
        ).fetchall()
        assert [r["Label"] for r in item_buttons] == items
        assert [r["Message"] for r in item_buttons] == items

        # Each item button has a placement; first is top-left.
        placements = conn.execute(
            "SELECT ep.GridPosition, ep.GridSpan FROM ElementPlacement ep "
            "JOIN ElementReference er ON ep.ElementReferenceId = er.Id "
            "WHERE er.PageId = ? ORDER BY ep.Id",
            (new_id,),
        ).fetchall()
        assert placements[0]["GridPosition"] == "0,0"
        assert all(p["GridSpan"] == "1,1" for p in placements)
    finally:
        conn.close()


def test_navigation_button_added_to_parent(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        new_id = ps.add_category_page(conn, "Places", ["A", "B"], parent_page_id=1)

        nav = conn.execute(
            "SELECT b.Label, b.NavigatePageId FROM Button b "
            "JOIN ElementReference er ON b.ElementReferenceId = er.Id "
            "WHERE er.PageId = 1",
        ).fetchone()
        assert nav["Label"] == "Places"
        assert nav["NavigatePageId"] == new_id
    finally:
        conn.close()


def test_grid_wraps_across_columns(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        items = [f"w{i}" for i in range(6)]
        new_id = ps.add_category_page(conn, "Grid", items, parent_page_id=1, cols=4)
        positions = [
            r["GridPosition"]
            for r in conn.execute(
                "SELECT ep.GridPosition FROM ElementPlacement ep "
                "JOIN ElementReference er ON ep.ElementReferenceId = er.Id "
                "WHERE er.PageId = ? ORDER BY ep.Id",
                (new_id,),
            )
        ]
        # 6 items, 4 columns -> row 0 fills, then wraps to row 1.
        assert positions == ["0,0", "1,0", "2,0", "3,0", "0,1", "1,1"]
    finally:
        conn.close()


def test_next_free_slot_skips_occupied_home_cells(pageset_path):
    # Pre-place a button at 0,0 on home so the nav button must go to 1,0.
    conn = ps.open_pageset(pageset_path)
    try:
        conn.execute("INSERT INTO ElementReference (Id, PageId) VALUES (99, 1)")
        conn.execute(
            "INSERT INTO ElementPlacement (Id, ElementReferenceId, GridPosition, GridSpan) "
            "VALUES (99, 99, '0,0', '1,1')"
        )
        conn.commit()

        ps.add_category_page(conn, "Places", ["A"], parent_page_id=1, cols=4)
        nav_pos = conn.execute(
            "SELECT ep.GridPosition FROM ElementPlacement ep "
            "JOIN ElementReference er ON ep.ElementReferenceId = er.Id "
            "WHERE er.PageId = 1 AND ep.Id != 99"
        ).fetchone()
        assert nav_pos["GridPosition"] == "1,0"
    finally:
        conn.close()


def test_add_category_page_rejects_empty_items(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        with pytest.raises(ps.PagesetError):
            ps.add_category_page(conn, "Empty", [], parent_page_id=1)
    finally:
        conn.close()


def test_add_category_page_rejects_unknown_parent(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        with pytest.raises(ps.PagesetError):
            ps.add_category_page(conn, "X", ["a"], parent_page_id=999)
    finally:
        conn.close()


def test_save_as_writes_importable_copy(pageset_path, tmp_path):
    conn = ps.open_pageset(pageset_path)
    try:
        ps.add_category_page(conn, "Places", ["Walmart"], parent_page_id=1)
        out = str(tmp_path / "edited.sps")
        ps.save_as(conn, out)
    finally:
        conn.close()

    assert ps.is_sqlite_file(out)
    check = sqlite3.connect(out)
    try:
        titles = [r[0] for r in check.execute("SELECT Title FROM Page")]
        assert "Places" in titles
    finally:
        check.close()


def test_find_page_id_by_name_is_case_insensitive(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        assert ps.find_page_id_by_name(conn, "home") == 1
        assert ps.find_page_id_by_name(conn, "HOME") == 1
    finally:
        conn.close()


def test_find_page_id_by_name_unknown_raises(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        with pytest.raises(ps.PagesetError):
            ps.find_page_id_by_name(conn, "Nope")
    finally:
        conn.close()


def test_find_page_id_by_name_ambiguous_raises(pageset_path):
    conn = ps.open_pageset(pageset_path)
    try:
        # A second page sharing the same name makes the lookup ambiguous.
        conn.execute(
            "INSERT INTO Page (Id, UniqueId, Title, Name) "
            "VALUES (2, 'home2-uid', 'Home', 'Home')"
        )
        conn.commit()
        with pytest.raises(ps.PagesetError):
            ps.find_page_id_by_name(conn, "Home")
    finally:
        conn.close()


# --- Command-line interface -------------------------------------------------

def test_cli_list_prints_pages(pageset_path, capsys):
    rc = ps.main(["list", pageset_path])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Home" in out
    assert "1" in out


def test_cli_add_creates_edited_file(pageset_path, capsys):
    rc = ps.main([
        "add", pageset_path,
        "--title", "Drinks",
        "--items", "Water, Juice ,Soda",
        "--parent-name", "Home",
    ])
    assert rc == 0

    out_path = ps._default_output_path(pageset_path)
    assert ps.is_sqlite_file(out_path)
    check = sqlite3.connect(out_path)
    try:
        titles = [r[0] for r in check.execute("SELECT Title FROM Page")]
        assert "Drinks" in titles
        # Whitespace around comma-separated items is trimmed.
        labels = {
            r[0] for r in check.execute(
                "SELECT b.Label FROM Button b "
                "JOIN ElementReference er ON b.ElementReferenceId = er.Id "
                "JOIN Page p ON er.PageId = p.Id WHERE p.Title = 'Drinks'"
            )
        }
        assert labels == {"Water", "Juice", "Soda"}
        # A navigation button was added to Home.
        nav = check.execute(
            "SELECT b.Label FROM Button b "
            "JOIN ElementReference er ON b.ElementReferenceId = er.Id "
            "WHERE er.PageId = 1"
        ).fetchone()
        assert nav[0] == "Drinks"
    finally:
        check.close()


def test_cli_add_honors_output_flag(pageset_path, tmp_path):
    out = str(tmp_path / "custom.sps")
    rc = ps.main([
        "add", pageset_path, "--title", "Colors",
        "--items", "Red,Green,Blue", "-o", out,
    ])
    assert rc == 0
    assert ps.is_sqlite_file(out)


def test_cli_add_empty_items_returns_error(pageset_path, capsys):
    rc = ps.main(["add", pageset_path, "--title", "X", "--items", "  , "])
    assert rc == 1
    assert "Error" in capsys.readouterr().err
