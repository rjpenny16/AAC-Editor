import json
import uuid

import pytest

from tdsnap import validate
from tdsnap.builder import add_category_page
from tdsnap.errors import PagesetError


@pytest.fixture
def built(seeded_pageset):
    """A 7-word page linked from Home Page, plus the report."""
    ps = seeded_pageset
    parent_id = ps.find_page_id_by_name("Home Page")
    report = add_category_page(
        ps, "Snacks", ["Chips", "Apple", "Banana", "Yogurt", "Juice", "Milk", "Pear"],
        parent_id,
    )
    return ps, parent_id, report


def test_page_row(built):
    ps, _, report = built
    page = ps.conn.execute(
        "SELECT * FROM Page WHERE Id = ?", (report["page_id"],)
    ).fetchone()
    assert page["Title"] == "Snacks"
    assert page["PageType"] == 1
    assert uuid.UUID(page["UniqueId"])  # valid GUID
    assert page["SerializedMetadata"] is None
    assert page["Timestamp"] > 638_700_000_000_000_000  # .NET ticks, recent
    assert page["SyncHash"] is not None


def test_layout_and_placements(built):
    ps, _, report = built
    layouts = ps.conn.execute(
        "SELECT * FROM PageLayout WHERE PageId = ?", (report["page_id"],)
    ).fetchall()
    assert len(layouts) == 1
    assert layouts[0]["PageLayoutSetting"] == "4,3,True,0"
    placements = ps.conn.execute(
        "SELECT * FROM ElementPlacement WHERE PageLayoutId = ? "
        "ORDER BY GridPosition",
        (layouts[0]["Id"],),
    ).fetchall()
    assert len(placements) == 7
    positions = {p["GridPosition"] for p in placements}
    assert positions == {"0,0", "1,0", "2,0", "3,0", "0,1", "1,1", "2,1"}
    for placement in placements:
        assert placement["GridSpan"] == "1,1"
        assert placement["Visible"] == 1
        assert placement["PageLayoutId"] == layouts[0]["Id"]


def test_buttons_and_commands(built):
    ps, _, report = built
    for button_id in report["button_ids"]:
        button = ps.conn.execute(
            "SELECT * FROM Button WHERE Id = ?", (button_id,)
        ).fetchone()
        assert button["CommandFlags"] == 8
        assert button["Message"] is None
        assert uuid.UUID(button["UniqueId"])
        assert button["LibrarySymbolId"] == 0
        assert button["PageSetImageId"] == 0
        sequences = ps.conn.execute(
            "SELECT SerializedCommands FROM CommandSequence WHERE ButtonId = ?",
            (button_id,),
        ).fetchall()
        assert len(sequences) == 1
        commands = json.loads(sequences[0][0])
        assert commands["$values"][0]["$type"] == "3"


def test_nav_button(built):
    ps, parent_id, report = built
    nav_id = report["nav_button_id"]
    button = ps.conn.execute(
        "SELECT * FROM Button WHERE Id = ?", (nav_id,)
    ).fetchone()
    assert button["CommandFlags"] == 9
    assert button["Label"] == "Snacks"

    link = ps.conn.execute(
        "SELECT * FROM ButtonPageLink WHERE ButtonId = ?", (nav_id,)
    ).fetchone()
    assert link["PageUniqueId"] == report["page_unique_id"]

    commands = json.loads(
        ps.conn.execute(
            "SELECT SerializedCommands FROM CommandSequence WHERE ButtonId = ?",
            (nav_id,),
        ).fetchone()[0]
    )
    nav_command = commands["$values"][0]
    assert nav_command["$type"] == "2"
    assert nav_command["LinkedPageId"] == report["page_unique_id"]
    assert nav_command["IsVisit"] is False

    # The nav ref lives on the parent page, in a free slot of its layout.
    ref = ps.conn.execute(
        "SELECT * FROM ElementReference WHERE Id = ?",
        (button["ElementReferenceId"],),
    ).fetchone()
    assert ref["PageId"] == parent_id


def test_syncdata_and_stamps(built):
    ps, parent_id, report = built
    page = ps.conn.execute(
        "SELECT * FROM Page WHERE Id = ?", (report["page_id"],)
    ).fetchone()
    sync = ps.conn.execute(
        "SELECT * FROM SyncData WHERE UniqueId = ?", (report["page_unique_id"],)
    ).fetchone()
    assert sync["Timestamp"] == page["Timestamp"]
    assert sync["SyncHash"] == page["SyncHash"]
    assert sync["Deleted"] == 0
    assert sync["Description"] == "Snacks"

    parent = ps.conn.execute(
        "SELECT * FROM Page WHERE Id = ?", (parent_id,)
    ).fetchone()
    assert parent["Timestamp"] == page["Timestamp"]  # bumped to the edit time
    pageset_stamp = ps.conn.execute(
        "SELECT PageSetTimestamp FROM Synchronization"
    ).fetchone()[0]
    assert pageset_stamp == page["Timestamp"]


def test_ids_come_from_autoincrement(built):
    ps, _, report = built
    seq = dict(
        ps.conn.execute("SELECT name, seq FROM sqlite_sequence").fetchall()
    )
    assert seq["Page"] == report["page_id"]
    assert seq["Button"] == max(
        report["button_ids"] + [report["nav_button_id"]]
    )


def test_validators_pass(built):
    ps, _, report = built
    assert validate.validate_new_page(ps.conn, report) == []
    result = validate.validate_pageset(ps.conn)
    assert result["problems"] == []
    assert result["warnings"] == []


def test_phrase_and_border_buttons(seeded_pageset):
    """Topic-page items: short label + full spoken phrase + function color."""
    from tdsnap.colors import argb_from_hex

    ps = seeded_pageset
    parent_id = ps.find_page_id_by_name("Home Page")
    report = add_category_page(
        ps,
        "About Me",
        [
            {"label": "How are you?", "message": "How are you doing today?",
             "border_color": "#1E88E5"},                     # question → blue
            {"label": "Love it", "message": "I really love this!",
             "border_color": "#43A047"},                     # positive → green
            {"label": "dog", "border_color": None},          # plain word
            "cat",                                           # plain string still works
        ],
        parent_id,
    )

    rows = {
        row["Label"]: row
        for row in ps.conn.execute(
            "SELECT * FROM Button WHERE Id IN (%s)"
            % ",".join("?" * len(report["button_ids"])),
            report["button_ids"],
        )
    }
    question = rows["How are you?"]
    assert question["Message"] == "How are you doing today?"
    assert question["BorderColor"] == argb_from_hex("#1E88E5")
    assert question["BorderThickness"] == 3.0
    assert rows["Love it"]["BorderColor"] == argb_from_hex("#43A047")
    assert rows["dog"]["Message"] is None
    assert rows["dog"]["BorderColor"] is None
    assert rows["dog"]["BorderThickness"] == 0.0
    assert rows["cat"]["Message"] is None

    # The report carries the specs and validation checks them.
    from tdsnap import validate

    assert validate.validate_new_page(ps.conn, report) == []


def test_argb_encoding():
    from tdsnap.colors import argb_from_hex, hex_from_argb
    from tdsnap.errors import PagesetError
    import pytest as _pytest

    # The gray border TD Snap uses on its own toolbar buttons.
    assert argb_from_hex("#888A8C") == -7828852
    assert hex_from_argb(-7828852) == "#888A8C"
    assert argb_from_hex("#1E88E5") == argb_from_hex("1E88E5")
    with _pytest.raises(PagesetError):
        argb_from_hex("#12")


def test_error_paths(seeded_pageset):
    ps = seeded_pageset
    with pytest.raises(PagesetError, match="title"):
        add_category_page(ps, "  ", ["a"], None)
    with pytest.raises(PagesetError, match="no words"):
        add_category_page(ps, "Empty", ["  ", ""], None)
    with pytest.raises(PagesetError, match="don't fit"):
        add_category_page(ps, "Too Big", [f"w{i}" for i in range(13)], None)
    with pytest.raises(PagesetError, match="not found"):
        add_category_page(ps, "Orphan", ["a"], parent_page_id=99999)


def test_rollback_on_failure(seeded_pageset):
    ps = seeded_pageset
    before = validate.table_snapshot(ps.conn)
    with pytest.raises(PagesetError):
        add_category_page(ps, "Orphan", ["a"], parent_page_id=99999)
    after = validate.table_snapshot(ps.conn)
    assert validate.diff_snapshots(before, after) == []


def test_parent_grid_full(seeded_pageset):
    ps = seeded_pageset
    parent_id = ps.find_page_id_by_name("Home Page")
    # Each added page puts one nav button on the parent; its 4x3 grid starts
    # with 2 seeded cells, so 10 nav buttons fill it exactly.
    add_category_page(ps, "Filler One", [f"a{i}" for i in range(5)], parent_id)
    add_category_page(ps, "Filler Two", [f"b{i}" for i in range(5)], parent_id)
    used = ps.conn.execute(
        "SELECT COUNT(*) FROM ElementPlacement ep "
        "JOIN PageLayout pl ON ep.PageLayoutId = pl.Id WHERE pl.PageId = ?",
        (parent_id,),
    ).fetchone()[0]
    assert used == 4  # hello, Food, Filler One, Filler Two
    for i in range(8):
        add_category_page(ps, f"Filler {i + 3}", ["x"], parent_id)
    with pytest.raises(PagesetError, match="grid is full"):
        add_category_page(ps, "One Too Many", ["x"], parent_id)
