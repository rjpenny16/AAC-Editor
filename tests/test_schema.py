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


def test_list_pages_and_grid(seeded_pageset):
    pages = dict(seeded_pageset.list_pages())
    assert "Home Page" in pages.values()
    assert seeded_pageset.grid_dimension() == (4, 3)
    home_id = seeded_pageset.find_page_id_by_name("home page")
    assert pages[home_id] == "Home Page"
    with pytest.raises(PagesetError):
        seeded_pageset.find_page_id_by_name("No Such Page")
