"""Integration tests against a genuine TD Snap export (Motor Plan 40, 4.13).

The fixture is proprietary Tobii content and is not committed; run
``python scripts/fetch_fixture.py`` to download it. Tests are skipped when
it's absent.
"""

import contextlib
import json
import os
import shutil
import sqlite3
from types import SimpleNamespace

import pytest
from conftest import require_example

from tdsnap import live, validate
from tdsnap.builder import add_category_page
from tdsnap.pageset import Pageset

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


# ---------------------------------------------------------------------------
# Live-edit lookups, against the schema and the content TD Snap really ships
#
# Motor Plan 40 carries pages whose buttons speak a phrase quite unlike their
# label — "Respect how I communicate." speaks "You need to respect how I
# communicate." — and that is the button TD Snap publishes under the *message*
# as its accessibility name. Everything below is that case, read out of the
# real file rather than a fixture written to agree with the code.

SPOKEN_PAGE = "Advocacy and Protest"


def _install_user(root, user, source, tweak=None):
    """A TD Snap user on this machine, pointed at a copy of *source*."""
    folder = (root / "Packages" / "TobiiDynavox.Snap_test" / "LocalState"
              / "Users" / user)
    folder.mkdir(parents=True)
    with sqlite3.connect(folder / "Settings.ssf") as conn:
        conn.execute("CREATE TABLE UserSettings (PageSetGuid TEXT)")
        conn.execute("INSERT INTO UserSettings VALUES ('active')")
    pageset = folder / "active.sps"
    shutil.copyfile(source, pageset)
    if tweak:
        with sqlite3.connect(pageset) as conn:
            tweak(conn)
    return pageset


def _published_names(pageset, page=SPOKEN_PAGE):
    """The accessibility names TD Snap would publish for *page*'s buttons.

    Its name is the spoken message where there is one and the label
    otherwise, which is the whole difficulty these lookups exist for.
    """
    with contextlib.closing(
        sqlite3.connect(f"file:{pageset}?mode=ro", uri=True)
    ) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT b.Label, b.Message FROM Button b "
            "JOIN ElementReference er ON er.Id = b.ElementReferenceId "
            "JOIN Page p ON p.Id = er.PageId "
            "WHERE p.Title = ? AND p.PageType = 1",
            (page,),
        ).fetchall()
    return [
        (row["Message"] or row["Label"]).strip()
        for row in rows
        if (row["Message"] or row["Label"] or "").strip()
    ]


def _group(names, page=SPOKEN_PAGE):
    return SimpleNamespace(
        Name=page,
        GetChildren=lambda: [
            SimpleNamespace(Name=name, ControlTypeName="ButtonControl")
            for name in names
        ],
    )


def test_real_spoken_names_resolve_to_their_saved_labels(tmp_path, monkeypatch):
    example = require_example()
    _install_user(tmp_path, "alex", example)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    names = _published_names(example)
    assert names, "the fixture should carry this page"
    labels = live._accessible_labels(_group(names))

    # Every name the page publishes resolves, messages included.
    assert len(labels) == len(names)
    assert labels["you need to respect how i communicate."] == (
        "Respect how I communicate."
    )


def test_real_buttons_read_as_editable_rather_than_locked(tmp_path, monkeypatch):
    """Unresolved names used to leave a whole page locked out of editing."""
    example = require_example()
    _install_user(tmp_path, "alex", example)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    content = live._stored_page_content(SPOKEN_PAGE, _published_names(example))
    assert content is not None
    speakable = [entry for entry in content.values() if entry["kind"] == "speak"]
    assert len(speakable) > 30
    # The page's own navigation button stays locked, as it must.
    assert any(entry["kind"] == "navigate" for entry in content.values())


def test_a_second_user_on_this_machine_does_not_hide_either_page_set(
    tmp_path, monkeypatch
):
    example = require_example()
    alex = _install_user(tmp_path, "alex", example)
    _install_user(
        tmp_path, "sam", example,
        lambda conn: conn.execute(
            "DELETE FROM Button WHERE Label = 'Respect how I communicate.'"
        ),
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    # Both page sets came from the same TD Snap template, so the page title
    # alone decides nothing — which is exactly where this used to give up.
    assert live._active_pageset_path(SPOKEN_PAGE) is None

    found = live._active_pageset_path(SPOKEN_PAGE, _published_names(alex))
    assert found == os.path.realpath(str(alex))
