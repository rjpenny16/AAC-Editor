"""Integration tests against a genuine TD Snap export (Motor Plan 40, 4.13).

The fixture is proprietary Tobii content and is not committed; run
``python scripts/fetch_fixture.py`` to download it. Tests are skipped when
it's absent.
"""

import json
import shutil

import pytest

from tdsnap import validate
from tdsnap.builder import add_category_page
from tdsnap.pageset import Pageset

from conftest import require_example

WORDS = [
    "Chips", "Apple", "Banana", "Crackers", "Yogurt", "Cheese",
    "Juice", "Cookies", "Pretzels", "Grapes", "Popcorn", "Raisins",
]

# Tables add_category_page must leave byte-identical in the real file.
UNTOUCHED_TABLES = [
    "PageSetData", "VocabList", "VocabListEntry", "Whiteboard",
    "WhiteboardDoodlePath", "WhiteboardImage", "ScanGroup", "SymbolColorData",
    "ButtonUsage", "ButtonUsageBlock", "MessageWindowElement", "PageExtra",
]


@pytest.fixture(scope="module")
def edited(tmp_path_factory):
    """Build a Snacks page in a copy of the real file; yield paths + report."""
    example = require_example()
    tmp = tmp_path_factory.mktemp("integration")
    source = tmp / "real.sps"
    shutil.copyfile(example, source)

    with Pageset(str(source)) as ps:
        # "My Things" is a mostly-empty page in Motor Plan 40 with room for
        # the nav button ("Home Page" is genuinely full).
        parent_id = ps.find_page_id_by_name("My Things")
        baseline = validate.validate_pageset(ps.conn)
        before = validate.table_snapshot(ps.conn)
        report = add_category_page(ps, "Snacks", WORDS, parent_id)
        after = validate.table_snapshot(ps.conn)
        out = ps.save_as(str(tmp / "real.edited.sps"))

    return {
        "out": out,
        "report": report,
        "parent_id": parent_id,
        "baseline": baseline,
        "before": before,
        "after": after,
    }


def test_snapshot_diff_only_expected_tables(edited):
    assert validate.check_roundtrip(edited["before"], edited["after"]) == []
    for table in UNTOUCHED_TABLES:
        assert edited["before"][table] == edited["after"][table], (
            f"{table} should be byte-identical after the edit"
        )


def test_reopen_and_validate(edited):
    """Re-open the saved file cold, like TD Snap would, and re-check everything."""
    with Pageset(edited["out"]) as ps:
        result = validate.validate_pageset(ps.conn)
        assert result["problems"] == []
        assert validate.new_warnings(edited["baseline"], result) == []
        assert validate.validate_new_page(ps.conn, edited["report"]) == []


def test_topic_page_with_phrases_and_colors(edited, tmp_path):
    """Build a color-coded quick-fire topic page on the real file."""
    from tdsnap.colors import argb_from_hex

    source = tmp_path / "topic.sps"
    shutil.copyfile(edited["out"], source)
    items = [
        {"label": "What's for lunch?", "message": "What are we having for lunch?",
         "border_color": "#1E88E5"},
        {"label": "Smells great", "message": "That smells really great!",
         "border_color": "#43A047"},
        {"label": "Not hungry", "message": "I am not hungry right now.",
         "border_color": "#E53935"},
    ]
    with Pageset(str(source)) as ps:
        parent_id = ps.find_page_id_by_name("My Actions")
        report = add_category_page(ps, "Lunch Talk", items, parent_id)
        assert validate.validate_new_page(ps.conn, report) == []
        assert validate.validate_pageset(ps.conn)["problems"] == []
        out = ps.save_as(str(tmp_path / "topic.edited.sps"))

    with Pageset(out) as ps:
        rows = ps.conn.execute(
            "SELECT b.Label, b.Message, b.BorderColor, b.BorderThickness "
            "FROM Page p "
            "JOIN ElementReference er ON er.PageId = p.Id "
            "JOIN Button b ON b.ElementReferenceId = er.Id "
            "WHERE p.UniqueId = ? ORDER BY b.Id",
            (report["page_unique_id"],),
        ).fetchall()
        assert [(r["Label"], r["Message"]) for r in rows] == [
            (i["label"], i["message"]) for i in items
        ]
        assert [r["BorderColor"] for r in rows] == [
            argb_from_hex(i["border_color"]) for i in items
        ]
        assert all(r["BorderThickness"] == 3.0 for r in rows)


def test_reconstruct_page_like_a_reader(edited):
    """Rebuild the new page with obf-node-style joins and check the content."""
    with Pageset(edited["out"]) as ps:
        report = edited["report"]
        rows = ps.conn.execute(
            "SELECT b.Label, b.CommandFlags, ep.GridPosition, "
            "cs.SerializedCommands "
            "FROM Page p "
            "JOIN PageLayout pl ON pl.PageId = p.Id "
            "JOIN ElementPlacement ep ON ep.PageLayoutId = pl.Id "
            "JOIN ElementReference er ON er.Id = ep.ElementReferenceId "
            "JOIN Button b ON b.ElementReferenceId = er.Id "
            "JOIN CommandSequence cs ON cs.ButtonId = b.Id "
            "WHERE p.UniqueId = ? ORDER BY ep.Id",
            (report["page_unique_id"],),
        ).fetchall()
        assert [row["Label"] for row in rows] == WORDS
        assert rows[0]["GridPosition"] == "0,0"
        assert rows[8]["GridPosition"] == "0,1"  # 8-column grid wraps
        assert all(row["CommandFlags"] == 8 for row in rows)

        # The nav button on "My Things" points at the new page.
        nav = ps.conn.execute(
            "SELECT b.Label, cs.SerializedCommands, l.PageUniqueId "
            "FROM Button b "
            "JOIN CommandSequence cs ON cs.ButtonId = b.Id "
            "JOIN ButtonPageLink l ON l.ButtonId = b.Id "
            "WHERE b.Id = ?",
            (report["nav_button_id"],),
        ).fetchone()
        assert nav["Label"] == "Snacks"
        assert nav["PageUniqueId"] == report["page_unique_id"]
        command = json.loads(nav["SerializedCommands"])["$values"][0]
        assert command == {
            "$type": "2",
            "LinkedPageId": report["page_unique_id"],
            "IsVisit": False,
        }
