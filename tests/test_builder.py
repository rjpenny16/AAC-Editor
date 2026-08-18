import json
import uuid

import pytest

from tdsnap import builder, validate
from tdsnap.builder import _normalize_items, add_category_page
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


def test_button_slots_follow_visual_preview(seeded_pageset):
    ps = seeded_pageset
    report = add_category_page(
        ps, "Positioned", [{"label": "later", "slot": 5},
                           {"label": "first", "slot": 0}], None,
    )
    positions = {
        row["Label"]: row["GridPosition"]
        for row in ps.conn.execute(
            "SELECT b.Label, ep.GridPosition FROM Button b "
            "JOIN ElementReference er ON er.Id = b.ElementReferenceId "
            "JOIN ElementPlacement ep ON ep.ElementReferenceId = er.Id "
            "WHERE b.Id IN (?, ?)", report["button_ids"],
        )
    }
    assert positions == {"later": "1,1", "first": "0,0"}


def test_parent_free_slot_respects_spanning_buttons(seeded_pageset):
    ps = seeded_pageset
    parent_id = ps.find_page_id_by_name("Home Page")
    ps.conn.execute("DELETE FROM ElementPlacement WHERE GridPosition = '1,0'")
    ps.conn.execute(
        "UPDATE ElementPlacement SET GridSpan = '2,1' WHERE GridPosition = '0,0'"
    )

    report = add_category_page(ps, "No Overlap", ["word"], parent_id)
    position = ps.conn.execute(
        "SELECT ep.GridPosition FROM ElementPlacement ep "
        "JOIN Button b ON b.ElementReferenceId = ep.ElementReferenceId "
        "WHERE b.Id = ?", (report["nav_button_id"],),
    ).fetchone()[0]
    assert position == "2,0"


def test_nested_transaction_remains_caller_owned(seeded_pageset):
    ps = seeded_pageset
    ps.conn.execute("UPDATE PageSetProperties SET Description = 'caller change'")
    assert ps.conn.in_transaction

    add_category_page(ps, "Nested", ["word"], None)

    assert ps.conn.in_transaction
    ps.conn.rollback()
    assert ps.conn.execute(
        "SELECT COUNT(*) FROM Page WHERE Title = 'Nested'"
    ).fetchone()[0] == 0
    assert ps.conn.execute(
        "SELECT Description FROM PageSetProperties"
    ).fetchone()[0] is None


@pytest.mark.parametrize(
    "items, message",
    [
        ([{"label": 1}], "label must be text"),
        ([{"label": "x", "message": 1}], "message.*must be text"),
        ([{"label": "x", "border_color": 1 << 40}], "signed 32-bit"),
        ([{"label": "x", "border_color": "#123456"}], "communicative-function colors"),
        ([{"label": "x", "border_color": 0}], "communicative-function colors"),  # black, not a function color
        ([{"label": "x", "slot": -1}], "non-negative integer"),
        ([{"label": "x", "symbol": "yes"}], "true or false"),
        (["same", "SAME"], "duplicate labels"),
        (["x" * 61], "maximum 60"),
        ([{"label": "x", "message": "m" * 201}], "maximum 200"),
    ],
)
def test_item_boundary_validation(items, message):
    with pytest.raises(PagesetError, match=message):
        _normalize_items(items)


def test_title_and_item_collection_boundaries(seeded_pageset):
    with pytest.raises(PagesetError, match="title must be text"):
        add_category_page(seeded_pageset, 1, ["x"], None)
    with pytest.raises(PagesetError, match="maximum 60"):
        add_category_page(seeded_pageset, "t" * 61, ["x"], None)
    with pytest.raises(PagesetError, match="provided as a list"):
        add_category_page(seeded_pageset, "Title", ("x",), None)


def test_argb_encoding():
    import pytest as _pytest

    from tdsnap.colors import argb_from_hex, hex_from_argb
    from tdsnap.errors import PagesetError

    # The gray border TD Snap uses on its own toolbar buttons.
    assert argb_from_hex("#888A8C") == -7828852
    assert hex_from_argb(-7828852) == "#888A8C"
    assert argb_from_hex("#1E88E5") == argb_from_hex("1E88E5")
    with _pytest.raises(PagesetError):
        argb_from_hex("#12")


def test_every_function_color_is_accepted_and_only_those():
    """The five clinical function colors (mirrored from state.js's FUNCTIONS
    map) are the only borders the write path accepts — see colors.py and
    ROADMAP.md's Phase 3."""
    from tdsnap.colors import FUNCTION_BORDER_COLORS, argb_from_hex

    for function, color in FUNCTION_BORDER_COLORS.items():
        [item] = _normalize_items([{"label": function, "border_color": color}])
        assert item["border_color"] == argb_from_hex(color)

    # A color one bit off any allowed value is rejected, not merely a wildly
    # different one — this is a real allowlist, not a loose sanity check.
    near_miss = argb_from_hex(FUNCTION_BORDER_COLORS["question"]) + 1
    with pytest.raises(PagesetError, match="communicative-function colors"):
        _normalize_items([{"label": "x", "border_color": near_miss}])


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
    with pytest.raises(PagesetError, match="already exists"):
        add_category_page(ps, "home page", ["a"], None)


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


# ---------------------------------------------------------------------------
# Adding to a page that already exists (Phase 4c)


@pytest.fixture
def home(seeded_pageset):
    """The seeded page set and the Id of the page it already has."""
    return seeded_pageset, seeded_pageset.find_page_id_by_name("Home Page")


def _placements(ps, page_id):
    return {
        row["Label"]: row["GridPosition"]
        for row in ps.conn.execute(
            "SELECT button.Label AS Label, placement.GridPosition AS GridPosition "
            "FROM Button button "
            "JOIN ElementReference ref ON ref.Id = button.ElementReferenceId "
            "JOIN ElementPlacement placement ON placement.ElementReferenceId = ref.Id "
            "WHERE ref.PageId = ?",
            (page_id,),
        )
    }


def test_buttons_land_in_the_cells_the_review_chose(home):
    ps, page_id = home
    layout = builder.layout_for_page(ps.conn, page_id, ps.grid_dimension())
    free = builder.free_slots(ps.conn, layout)

    report = builder.add_buttons_to_page(
        ps, page_id,
        [
            {"label": "Chips", "slot": free[1]},
            {"label": "Juice", "message": "I want juice", "slot": free[0]},
        ],
    )

    cols = report["grid"][0]
    placed = _placements(ps, page_id)
    assert placed["Chips"] == f"{free[1] % cols},{free[1] // cols}"
    assert placed["Juice"] == f"{free[0] % cols},{free[0] // cols}"
    assert report["layout_id"] == layout["Id"]
    assert validate.validate_added_buttons(ps.conn, report) == []
    assert validate.validate_pageset(ps.conn)["problems"] == []


def test_a_button_with_no_chosen_cell_takes_the_first_free_one(home):
    ps, page_id = home
    layout = builder.layout_for_page(ps.conn, page_id, ps.grid_dimension())
    first = builder.free_slots(ps.conn, layout)[0]

    report = builder.add_buttons_to_page(ps, page_id, ["Chips"])

    cols = report["grid"][0]
    assert _placements(ps, page_id)["Chips"] == f"{first % cols},{first // cols}"


def test_adding_to_an_existing_page_leaves_everything_else_alone(home):
    ps, page_id = home
    before = validate.table_snapshot(ps.conn)

    report = builder.add_buttons_to_page(ps, page_id, ["Chips"])

    problems = validate.check_roundtrip(before, validate.table_snapshot(ps.conn))
    assert problems == []
    assert validate.validate_added_buttons(ps.conn, report) == []


def test_adding_to_a_page_that_is_not_there_is_refused(home):
    ps, _ = home
    with pytest.raises(PagesetError, match="Vocabulary page Id 9999 not found"):
        builder.add_buttons_to_page(ps, 9999, ["Chips"])


def test_more_buttons_than_empty_cells_is_refused_before_anything_is_written(home):
    ps, page_id = home
    layout = builder.layout_for_page(ps.conn, page_id, ps.grid_dimension())
    free = len(builder.free_slots(ps.conn, layout))

    with pytest.raises(PagesetError, match=rf"don't fit: this page has {free} empty"):
        builder.add_buttons_to_page(
            ps, page_id, [f"word{index}" for index in range(free + 1)]
        )

    assert "word0" not in _placements(ps, page_id)


def test_an_empty_request_is_refused(home):
    ps, page_id = home
    with pytest.raises(PagesetError, match="Add at least one word or phrase"):
        builder.add_buttons_to_page(ps, page_id, [])


def test_extending_a_page_inside_a_caller_transaction_stays_caller_owned(home):
    ps, page_id = home
    ps.conn.execute("UPDATE PageSetProperties SET Description = 'caller change'")
    assert ps.conn.in_transaction

    builder.add_buttons_to_page(ps, page_id, ["Chips"])

    assert ps.conn.in_transaction
    ps.conn.rollback()
    assert "Chips" not in _placements(ps, page_id)
    assert ps.conn.execute(
        "SELECT Description FROM PageSetProperties"
    ).fetchone()[0] is None


def test_a_failed_extension_inside_a_caller_transaction_rolls_back_only_itself(home):
    ps, page_id = home
    ps.conn.execute("UPDATE PageSetProperties SET Description = 'caller change'")
    layout = builder.layout_for_page(ps.conn, page_id, ps.grid_dimension())
    taken = builder.free_slots(ps.conn, layout)[0]

    builder.add_buttons_to_page(ps, page_id, [{"label": "Chips", "slot": taken}])
    with pytest.raises(PagesetError, match="is not empty on this page"):
        builder.add_buttons_to_page(ps, page_id, [{"label": "Juice", "slot": taken}])

    placed = _placements(ps, page_id)
    assert "Chips" in placed and "Juice" not in placed
    assert ps.conn.execute(
        "SELECT Description FROM PageSetProperties"
    ).fetchone()[0] == "caller change"


def test_symbol_search_words_are_bounded_like_every_other_field():
    assert _normalize_items([{"label": "more please", "symbol_query": " more "}]) == [
        {"label": "more please", "message": None, "border_color": None, "slot": None,
         "symbol": True, "symbol_query": "more"},
    ]
    # An empty query means "search the label", which is the default anyway.
    assert _normalize_items([{"label": "x", "symbol_query": "  "}])[0]["symbol_query"] is None
    with pytest.raises(PagesetError, match="symbol search words for 'x' must be text"):
        _normalize_items([{"label": "x", "symbol_query": 5}])
    with pytest.raises(PagesetError, match="symbol search words for 'x' are too long"):
        _normalize_items([{"label": "x", "symbol_query": "q" * 61}])
