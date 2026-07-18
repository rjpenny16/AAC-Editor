import hashlib
import pathlib
import sqlite3

import pytest

from tdsnap import schema
from tdsnap.errors import PagesetError
from tdsnap.pageset import Pageset, is_sqlite_file


def test_introspection_matches_snapshot(seeded_pageset):
    conn = seeded_pageset.conn
    assert "Page" in schema.tables(conn)
    cols = schema.columns(conn, "Page")
    assert "UniqueId" in cols and "PageType" in cols
    assert "Name" not in cols  # the guessed column that crashed TD Snap
    assert schema.primary_key(conn, "Page") == "Id"
    assert schema.schema_version(conn) == "4.13"


def test_parse_grid():
    assert schema.parse_grid("8,5") == (8, 5)
    assert schema.parse_grid("4,3,True,0") == (4, 3)
    with pytest.raises(PagesetError):
        schema.parse_grid("bogus")
    with pytest.raises(PagesetError):
        schema.parse_grid(None)


def test_parse_grid_geometry_is_exact_and_positive():
    assert schema.parse_grid_position("0,2") == (0, 2)
    assert schema.parse_grid_span("2,1") == (2, 1)
    for invalid in ("-1,0", "1,2,3", None):
        with pytest.raises(PagesetError):
            schema.parse_grid_position(invalid)
    for invalid in ("0,1", "1,-1", "1,2,3", None):
        with pytest.raises(PagesetError):
            schema.parse_grid_span(invalid)


def test_rejects_non_sqlite(tmp_path):
    junk = tmp_path / "junk.sps"
    junk.write_bytes(b"not a database at all")
    assert not is_sqlite_file(str(junk))
    with pytest.raises(PagesetError):
        Pageset(str(junk))


def test_rejects_wrong_sqlite(tmp_path):
    other = tmp_path / "other.sps"
    conn = sqlite3.connect(str(other))
    conn.execute("CREATE TABLE Unrelated (x)")
    conn.commit()
    conn.close()
    with pytest.raises(PagesetError, match="missing tables"):
        Pageset(str(other))


def test_source_file_never_mutated(seeded_source, tmp_path):
    before = hashlib.sha256(pathlib.Path(seeded_source).read_bytes()).hexdigest()
    with Pageset(seeded_source, working_copy=str(tmp_path / "wc.sps")) as ps:
        from tdsnap.builder import add_category_page

        add_category_page(ps, "Words", ["a", "b"], None)
        ps.save_as(str(tmp_path / "out.sps"))
    after = hashlib.sha256(pathlib.Path(seeded_source).read_bytes()).hexdigest()
    assert before == after


def test_save_as_rejects_source_unless_explicitly_trusted(seeded_source, tmp_path):
    from tdsnap.builder import add_category_page

    before = hashlib.sha256(pathlib.Path(seeded_source).read_bytes()).hexdigest()
    with Pageset(
        seeded_source, working_copy=str(tmp_path / "wc.sps"), cleanup=True
    ) as ps:
        add_category_page(ps, "Words", ["a"], None)
        with pytest.raises(PagesetError, match="overwrite the original"):
            ps.save_as(seeded_source)
        assert hashlib.sha256(pathlib.Path(seeded_source).read_bytes()).hexdigest() == before
        ps.save_as(seeded_source, allow_source_overwrite=True)
    assert hashlib.sha256(pathlib.Path(seeded_source).read_bytes()).hexdigest() != before
    assert is_sqlite_file(seeded_source)


def test_save_as_is_atomic_and_keeps_edits_after_copy_failure(
    seeded_source, tmp_path, monkeypatch
):
    from tdsnap import pageset as pageset_module
    from tdsnap.builder import add_category_page

    destination = tmp_path / "existing.sps"
    destination.write_bytes(b"previous destination")
    original_copy = pageset_module.shutil.copyfile
    with Pageset(seeded_source, cleanup=True) as ps:
        add_category_page(ps, "Words", ["a"], None)

        def fail_after_partial_copy(_source, temporary):
            pathlib.Path(temporary).write_bytes(b"partial")
            raise OSError("simulated copy failure")

        monkeypatch.setattr(pageset_module.shutil, "copyfile", fail_after_partial_copy)
        with pytest.raises(OSError, match="simulated copy failure"):
            ps.save_as(str(destination))
        assert destination.read_bytes() == b"previous destination"
        assert ps.conn.execute(
            "SELECT COUNT(*) FROM Page WHERE Title = 'Words'"
        ).fetchone()[0] == 1

        monkeypatch.setattr(pageset_module.shutil, "copyfile", original_copy)
        ps.save_as(str(destination))
    assert is_sqlite_file(str(destination))


def test_automatic_working_copies_are_unique_and_cleaned(seeded_source):
    first = Pageset(seeded_source, cleanup=True)
    second = Pageset(seeded_source, cleanup=True)
    try:
        assert first.working_path != second.working_path
        assert pathlib.Path(first.working_path).exists()
        assert pathlib.Path(second.working_path).exists()
    finally:
        first.close()
        second.close()
    assert not pathlib.Path(first.working_path).exists()
    assert not pathlib.Path(second.working_path).exists()


def test_constructor_failure_removes_automatic_scratch(tmp_path):
    wrong = tmp_path / "wrong.sps"
    with sqlite3.connect(wrong) as conn:
        conn.execute("CREATE TABLE Unrelated (x)")
    with pytest.raises(PagesetError):
        Pageset(str(wrong))
    assert list(tmp_path.glob("wrong.editing-*.sps")) == []


def test_mutation_gate_rejects_unsupported_or_incomplete_schema(
    seeded_source, tmp_path
):
    with sqlite3.connect(seeded_source) as conn:
        conn.execute("UPDATE PageSetProperties SET SchemaVersion = '5.0'")
    with pytest.raises(PagesetError, match="not supported"):
        Pageset(seeded_source, cleanup=True)

    incomplete = tmp_path / "incomplete.sps"
    from conftest import build_seeded_db

    build_seeded_db(str(incomplete))
    with sqlite3.connect(incomplete) as conn:
        conn.execute("ALTER TABLE Page RENAME COLUMN Timestamp TO OtherTimestamp")
    with pytest.raises(PagesetError, match="missing required columns"):
        Pageset(str(incomplete), cleanup=True)


def test_list_pages_and_grid(seeded_pageset):
    pages = dict(seeded_pageset.list_pages())
    assert "Home Page" in pages.values()
    assert seeded_pageset.grid_dimension() == (4, 3)
    home_id = seeded_pageset.find_page_id_by_name("home page")
    assert pages[home_id] == "Home Page"
    with pytest.raises(PagesetError):
        seeded_pageset.find_page_id_by_name("No Such Page")
