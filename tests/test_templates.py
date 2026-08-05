"""Row-cloning tests.

``clone_row`` is how every new button and page gets a body: it copies a row
TD Snap itself wrote and overrides only the fields we understand. If the copy
silently drops columns, the edit still "succeeds" and the damage only shows up
when TD Snap opens the page set — so the copying itself needs direct tests,
not just the end-to-end ones that go through ``add_category_page``.
"""

import sqlite3

import pytest

from tdsnap import templates
from tdsnap.errors import PagesetError


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE Button ("
        "  Id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  Label TEXT, Message TEXT, CommandFlags INTEGER, BorderColor INTEGER"
        ")"
    )
    connection.execute(
        "INSERT INTO Button (Label, Message, CommandFlags, BorderColor) "
        "VALUES ('Apple', 'I want an apple', 8, -7828852)"
    )
    return connection


def template_row(conn):
    return conn.execute("SELECT * FROM Button WHERE Id = 1").fetchone()


def test_clone_copies_every_column_from_the_template(conn):
    """The regression that matters: a sqlite3.Row must be read by column name.

    sqlite3.Row implements the sequence protocol, so `name in row` searches the
    row's values rather than its keys. Copying under that mistake produces a
    row of NULLs that still inserts cleanly.
    """
    new_id = templates.clone_row(conn, "Button", template_row(conn), {"Label": "Banana"})
    clone = conn.execute("SELECT * FROM Button WHERE Id = ?", (new_id,)).fetchone()

    assert clone["Label"] == "Banana"          # the override
    assert clone["Message"] == "I want an apple"  # inherited, not NULL
    assert clone["CommandFlags"] == 8
    assert clone["BorderColor"] == -7828852


def test_clone_assigns_a_fresh_primary_key(conn):
    new_id = templates.clone_row(conn, "Button", template_row(conn), {})
    assert new_id != 1
    assert conn.execute("SELECT COUNT(*) FROM Button").fetchone()[0] == 2


def test_clone_rejects_columns_the_table_does_not_have(conn):
    """A typo must fail loudly rather than silently dropping the value."""
    with pytest.raises(PagesetError, match="Nonexistent"):
        templates.clone_row(conn, "Button", template_row(conn), {"Nonexistent": 1})


def test_clone_accepts_a_plain_mapping_template(conn):
    """Callers pass sqlite3.Row today; a dict must behave identically."""
    plain = {"Label": "Pear", "Message": "m", "CommandFlags": 8, "BorderColor": 1}
    new_id = templates.clone_row(conn, "Button", plain, {})
    clone = conn.execute("SELECT * FROM Button WHERE Id = ?", (new_id,)).fetchone()
    assert clone["Label"] == "Pear"
    assert clone["CommandFlags"] == 8


def test_clone_fills_columns_the_template_lacks_with_null(conn):
    partial = {"Label": "Plum"}
    new_id = templates.clone_row(conn, "Button", partial, {})
    clone = conn.execute("SELECT * FROM Button WHERE Id = ?", (new_id,)).fetchone()
    assert clone["Label"] == "Plum"
    assert clone["Message"] is None


def test_filtered_overrides_drops_columns_this_schema_lacks(conn):
    kept = templates.filtered_overrides(
        conn, "Button", {"Label": "x", "SymbolColorDataId": 3}
    )
    assert kept == {"Label": "x"}


def test_navigate_commands_carries_the_page_id():
    commands = templates.navigate_commands("abc-123")
    assert "abc-123" in commands
    assert '"$type":"2"' in commands
