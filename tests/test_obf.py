"""Open Board Format: reading, writing, exporting, planning, and importing.

Deterministic, file in and file out, no UI automation — so this is where the
interchange work earns its confidence. The round-trip property tests at the end
generate board sets from a seeded random source and push each one through
every direction the app supports:

* ``.obz`` bytes and back (the writer and reader agree with each other);
* into a page set and back out (import, then export, loses nothing the
  exit criterion names: labels, messages, layout, links);
* out of a page set, into a fresh one, and out again (a clinician's export
  re-imports faithfully).
"""

import io
import json
import random
import sqlite3
import zipfile

import pytest

from tdsnap import builder, obf, validate
from tdsnap.cli import main
from tdsnap.colors import FUNCTION_BORDER_COLORS
from tdsnap.errors import PagesetError
from tdsnap.pageset import Pageset
from tdsnap.web import server

QUESTION = FUNCTION_BORDER_COLORS["question"]
POSITIVE = FUNCTION_BORDER_COLORS["positive"]


# ---------------------------------------------------------------------------
# building board files the way CoughDrop writes them


def coughdrop_board(board_id, name, rows, columns, order, buttons, **extra):
    """A board shaped like a CoughDrop export: integer button ids, images,
    licences, background colours, ``ext_coughdrop_*`` fields."""
    return {
        "format": "open-board-0.1",
        "id": board_id,
        "locale": "en",
        "name": name,
        "url": f"https://app.mycoughdrop.com/example/{board_id}",
        "license": {"type": "CC By", "copyright_notice_url": "https://example.org"},
        "ext_coughdrop_settings": {"private": False, "key": f"example/{board_id}"},
        "buttons": buttons,
        "grid": {"rows": rows, "columns": columns, "order": order},
        "images": [{"id": "img1", "url": "https://example.org/i.png",
                    "path": "images/i.png", "content_type": "image/png",
                    "width": 300, "height": 300}],
        "sounds": [],
        **extra,
    }


def make_obz(boards: dict, root: str, manifest_extra=None, extra_files=None) -> bytes:
    """Zip *boards* ({path: document}) into an .obz with a manifest naming *root*."""
    manifest = {
        "format": "open-board-0.1",
        "root": root,
        "paths": {
            "boards": {doc["id"]: path for path, doc in boards.items()},
            "images": {"img1": "images/i.png"},
            "sounds": {},
        },
    }
    manifest.update(manifest_extra or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for path, doc in boards.items():
            archive.writestr(path, json.dumps(doc))
        archive.writestr("images/i.png", b"\x89PNG not really")
        for path, data in (extra_files or {}).items():
            archive.writestr(path, data)
    return buffer.getvalue()


def coughdrop_set() -> bytes:
    """Three boards: a home board linking to Food and Feelings, Feelings linking
    home. Carries everything a real export does that this app cannot bring
    across, so the reader's exclusions are exercised on realistic input."""
    home = coughdrop_board("1_100", "Quick Core", 2, 3, [[1, 2, 3], [4, 6, 5]], [
        {"id": 1, "label": "I", "border_color": "rgb(255, 255, 255)",
         "background_color": "rgb(255, 255, 170)", "image_id": "img1"},
        {"id": 2, "label": "want", "vocalization": "I want", "image_id": "img1",
         "border_color": "rgb(30, 136, 229)"},
        {"id": 3, "label": "food", "load_board": {
            "id": "1_101", "key": "example/food", "path": "board_1_101.obf",
            "url": "https://app.mycoughdrop.com/example/food"}},
        {"id": 4, "label": "feelings", "load_board": {"id": "1_102", "path": "board_1_102.obf"}},
        {"id": 5, "label": "clear", "action": ":clear"},
        {"id": 6, "label": "hidden word", "hidden": True},
    ])
    food = coughdrop_board("1_101", "Food", 1, 3, [[1, 2, 3]], [
        {"id": 1, "label": "apple", "border_color": "rgba(67, 160, 71, 1)"},
        {"id": 2, "label": "cookie", "vocalization": "I would like a cookie"},
        {"id": 3, "label": "web", "url": "https://example.org"},
    ])
    feelings = coughdrop_board("1_102", "Feelings", 1, 2, [[1, 2]], [
        {"id": 1, "label": "happy"},
        {"id": 2, "label": "home", "load_board": {"id": "1_100", "path": "board_1_100.obf"}},
    ])
    return make_obz({
        "board_1_100.obf": home,
        "board_1_101.obf": food,
        "board_1_102.obf": feelings,
    }, "board_1_100.obf")


def cells_of(board):
    return {(cell["row"], cell["col"]): cell for cell in board["cells"]}


def reasons(boardset):
    return {(entry["board"], entry["label"]): entry["reason"] for entry in boardset["skipped"]}


# ---------------------------------------------------------------------------
# reading


def test_a_coughdrop_obz_reads_into_the_canonical_model():
    boardset = obf.read_bytes(coughdrop_set())
    assert boardset["root"] == "1_100"
    assert [board["name"] for board in boardset["boards"]] == ["Quick Core", "Food", "Feelings"]

    home = cells_of(boardset["boards"][0])
    assert home[(0, 0)]["label"] == "I" and home[(0, 0)]["message"] is None
    assert home[(0, 1)]["message"] == "I want"
    assert home[(0, 1)]["border"] == QUESTION
    assert home[(0, 2)]["link"] == "1_101"
    assert home[(1, 0)]["link"] == "1_102"
    assert (1, 2) not in home  # the :clear action

    food = cells_of(boardset["boards"][1])
    assert food[(0, 0)]["border"] == POSITIVE  # rgba, alpha ignored
    assert food[(0, 1)]["message"] == "I would like a cookie"

    feelings = cells_of(boardset["boards"][2])
    assert feelings[(0, 1)]["link"] == "1_100"

    why = reasons(boardset)
    assert "action (:clear)" in why[("Quick Core", "clear")]
    assert why[("Quick Core", "hidden word")] == "is hidden on the original board"
    assert why[("Food", "web")] == "opens a web link"
    assert any("Pictures on 2 buttons" in note for note in boardset["notes"])


def test_a_single_obf_reads_and_its_outside_links_are_named():
    board = coughdrop_board("b", "Snacks", 1, 2, [["1", "2"]], [
        {"id": "1", "label": "chips"},
        {"id": "2", "label": "more", "load_board": {"id": "elsewhere", "path": "x.obf"}},
    ])
    boardset = obf.read_bytes(json.dumps(board).encode("utf-8"))
    assert [cell["label"] for cell in boardset["boards"][0]["cells"]] == ["chips"]
    assert reasons(boardset)[("Snacks", "more")] == "opens a board that is not in this file"


def test_links_resolve_by_path_when_the_id_does_not_match():
    one = coughdrop_board("one", "One", 1, 1, [["a"]], [
        {"id": "a", "label": "go", "load_board": {"path": "./boards\\two.obf"}}])
    two = coughdrop_board("two", "Two", 1, 1, [["a"]], [{"id": "a", "label": "hi"}])
    boardset = obf.read_bytes(make_obz({"boards/one.obf": one, "boards/two.obf": two},
                                       "boards/one.obf"))
    assert boardset["boards"][0]["cells"][0]["link"] == "two"


def test_every_unrepresentable_button_is_named_with_its_reason():
    board = coughdrop_board("b", "Mixed", 3, 3, [["1", "2", "3"], ["4", "5", "6"],
                                                   ["7", "1", None]], [
        {"id": "1", "label": "same"},
        {"id": "2", "label": "SAME"},
        {"id": "3", "label": "", "image_id": "img1"},
        {"id": "4", "label": "x" * 61},
        {"id": "5", "label": "long", "vocalization": "y" * 201},
        {"id": "6", "label": "spell", "actions": [":speak", "+a"]},
        {"id": "7", "label": "self", "load_board": {"id": "b"}},
        {"id": "8", "label": "off grid"},
    ])
    boardset = obf.read_bytes(json.dumps(board).encode("utf-8"))
    assert [cell["label"] for cell in boardset["boards"][0]["cells"]] == ["same"]
    why = reasons(boardset)
    assert why[("Mixed", "SAME")] == "appears more than once on this board"
    assert why[("Mixed", "")] == "has no label, only a picture"
    assert "longer than 60" in why[("Mixed", "x" * 60 + "…")]
    assert "longer than 200" in why[("Mixed", "long")]
    assert "(+a)" in why[("Mixed", "spell")]
    assert why[("Mixed", "self")] == "opens the board it is on"
    assert why[("Mixed", "off grid")] == "is not placed on the board's grid"


def test_a_board_without_a_grid_is_laid_out_in_listed_order():
    board = {"format": "open-board-0.1", "id": 7, "name": "Loose",
             "buttons": [{"id": n, "label": f"w{n}"} for n in range(5)]}
    boardset = obf.read_bytes(json.dumps(board).encode("utf-8"))
    loose = boardset["boards"][0]
    assert loose["id"] == "7"
    assert (loose["rows"], loose["columns"]) == (2, 3)
    assert [(cell["row"], cell["col"]) for cell in loose["cells"]] == [
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]


@pytest.mark.parametrize("value, expected", [
    ("rgb(30, 136, 229)", QUESTION),
    ("rgba(30,136,229,0.5)", QUESTION),
    ("#1e88e5", QUESTION),
    ("#abc", "#AABBCC"),
    ("rgb(300, 0, 0)", "#FF0000"),
    ("red", None),
    ("rgb(1, 2)", None),
    (None, None),
    (42, None),
])
def test_colors_are_read_only_when_they_are_unambiguous(value, expected):
    assert obf.parse_color(value) == expected


@pytest.mark.parametrize("data, message", [
    (b"not json at all", "not valid JSON"),
    (json.dumps([1, 2]).encode(), "expected a JSON object"),
    (json.dumps({"format": "something-else", "buttons": []}).encode(),
     "not in Open Board Format"),
    (json.dumps({"format": "open-board-0.1", "buttons": {}}).encode(), "not a list"),
    (b"\xff\xfe\x00bad", "not valid JSON"),
])
def test_files_that_are_not_boards_are_refused_by_name(data, message):
    with pytest.raises(PagesetError, match=message):
        obf.read_bytes(data)


def test_a_zip_without_a_manifest_is_not_an_obz():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("board.obf", "{}")
    with pytest.raises(PagesetError, match=r"no manifest\.json"):
        obf.read_bytes(buffer.getvalue())


def test_a_damaged_zip_is_refused():
    with pytest.raises(PagesetError, match=r"could not be opened|damaged"):
        obf.read_bytes(b"PK\x03\x04" + b"\x00" * 64)


def test_reading_is_bounded(monkeypatch):
    board = coughdrop_board("b", "B", 1, 1, [["1"]], [{"id": "1", "label": "hi"}])
    data = make_obz({"b.obf": board}, "b.obf")
    monkeypatch.setattr(obf, "MAX_ZIP_ENTRIES", 2)
    with pytest.raises(PagesetError, match="reads at most 2"):
        obf.read_bytes(data)
    monkeypatch.setattr(obf, "MAX_ZIP_ENTRIES", 100)
    monkeypatch.setattr(obf, "MAX_BOARD_BYTES", 50)
    with pytest.raises(PagesetError, match="larger than AAC Editor will read"):
        obf.read_bytes(data)
    monkeypatch.setattr(obf, "MAX_BOARD_BYTES", 4 * 1024 * 1024)
    monkeypatch.setattr(obf, "MAX_TOTAL_JSON_BYTES", 100)
    with pytest.raises(PagesetError, match="larger in total"):
        obf.read_bytes(data)
    monkeypatch.setattr(obf, "MAX_TOTAL_JSON_BYTES", 48 * 1024 * 1024)
    monkeypatch.setattr(obf, "MAX_BOARDS", 0)
    with pytest.raises(PagesetError, match="imports at most 0"):
        obf.read_bytes(data)


def test_manifest_quirks_are_tolerated():
    one = coughdrop_board("one", "One", 1, 1, [["1"]], [{"id": "1", "label": "a"}])
    two = coughdrop_board("two", "Two", 1, 1, [["1"]], [{"id": "1", "label": "b"}])
    # No board listing: every .obf in the archive is read, and a root that is
    # not a board falls back to the first one. Paths escaping the archive are
    # ignored rather than followed.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"root": "../../etc/passwd"}))
        archive.writestr("a/one.obf", json.dumps(one))
        archive.writestr("b/two.obf", json.dumps(two))
    boardset = obf.read_bytes(buffer.getvalue())
    assert [board["name"] for board in boardset["boards"]] == ["One", "Two"]
    assert boardset["root"] == "one"

    missing = make_obz({"one.obf": one}, "one.obf",
                       manifest_extra={"paths": {"boards": {"one": "one.obf",
                                                            "gone": "gone.obf"}}})
    boardset = obf.read_bytes(missing)
    assert reasons(boardset)[("gone.obf", "")].startswith("is listed in the manifest")

    twin = coughdrop_board("one", "Twin", 1, 1, [["1"]], [{"id": "1", "label": "c"}])
    boardset = obf.read_bytes(make_obz({"one.obf": one, "twin.obf": twin}, "one.obf"))
    assert [board["name"] for board in boardset["boards"]] == ["One"]
    assert "shares its id" in reasons(boardset)[("Twin", "")]


def test_boards_come_root_first_then_in_link_order():
    a = coughdrop_board("a", "A", 1, 1, [["1"]], [
        {"id": "1", "label": "to c", "load_board": {"id": "c"}}])
    b = coughdrop_board("b", "B", 1, 1, [["1"]], [{"id": "1", "label": "b"}])
    c = coughdrop_board("c", "C", 1, 1, [["1"]], [{"id": "1", "label": "c"}])
    boardset = obf.read_bytes(make_obz({"b.obf": b, "c.obf": c, "a.obf": a}, "a.obf"))
    assert [board["id"] for board in boardset["boards"]] == ["a", "c", "b"]


def test_read_accepts_a_path(tmp_path):
    path = tmp_path / "set.obz"
    path.write_bytes(coughdrop_set())
    assert len(obf.read(str(path))["boards"]) == 3


# ---------------------------------------------------------------------------
# writing


def test_writing_follows_the_format():
    boardset = obf.read_bytes(coughdrop_set())
    data = obf.to_obz_bytes(boardset)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "open-board-0.1"
        assert manifest["root"] == "boards/1.obf"
        assert "Symbols are not included" in manifest["ext_aac_editor_note"]
        home = json.loads(archive.read(manifest["root"]))
    assert home["format"] == "open-board-0.1"
    assert home["images"] == [] and home["ext_aac_editor_symbols"] == "omitted"
    assert home["grid"]["order"][0] == ["1", "2", "3"]
    by_label = {button["label"]: button for button in home["buttons"]}
    assert by_label["want"]["vocalization"] == "I want"
    assert by_label["want"]["border_color"] == "rgb(30, 136, 229)"
    assert by_label["food"]["load_board"] == {"id": "1_101", "path": "boards/2.obf"}
    assert "vocalization" not in by_label["I"]


def test_write_obz_is_atomic(tmp_path):
    boardset = obf.read_bytes(coughdrop_set())
    dest = tmp_path / "out.obz"
    obf.write_obz(boardset, str(dest))
    assert obf.read(str(dest))["boards"] == boardset["boards"]
    assert [path.name for path in tmp_path.iterdir()] == ["out.obz"]


# ---------------------------------------------------------------------------
# a page set, exported


def rich_pageset(seeded_pageset):
    """The seeded set plus a topic page with messages, a function colour, and a
    link back home — everything an export has to carry."""
    home = seeded_pageset.find_page_id_by_name("Home Page")
    builder.add_category_page(seeded_pageset, "Snacks", [
        {"label": "chips", "slot": 5},
        {"label": "more", "message": "I want more please", "border_color": QUESTION,
         "slot": 0},
    ], home)
    return seeded_pageset


def test_a_page_set_exports_labels_messages_layout_and_links(seeded_pageset):
    ps = rich_pageset(seeded_pageset)
    boardset = obf.export_pageset(ps.conn)
    by_name = {board["name"]: board for board in boardset["boards"]}
    assert boardset["boards"][0]["name"] == "Home Page"  # the page set's home
    home = cells_of(by_name["Home Page"])
    assert home[(0, 0)] == {"row": 0, "col": 0, "label": "hello", "message": None,
                            "border": None, "link": None}
    snacks_id = by_name["Snacks"]["id"]
    assert [cell["link"] for cell in by_name["Home Page"]["cells"]].count(snacks_id) == 1
    snacks = cells_of(by_name["Snacks"])
    assert (by_name["Snacks"]["rows"], by_name["Snacks"]["columns"]) == (3, 4)
    assert snacks[(0, 0)]["message"] == "I want more please"
    assert snacks[(0, 0)]["border"] == QUESTION
    assert snacks[(1, 1)]["label"] == "chips"
    # Food has never been laid out in TD Snap: it still travels, empty, so the
    # link to it survives.
    assert by_name["Food"]["cells"] == []
    assert any(cell["link"] == by_name["Food"]["id"] for cell in by_name["Home Page"]["cells"])
    assert boardset["notes"] == [obf.SYMBOLS_NOTE]
    summary = obf.export_summary(boardset)
    assert summary == {"boards": 3, "buttons": 5, "links": 2, "root": "Home Page",
                       "skipped": [], "notes": [obf.SYMBOLS_NOTE]}


def insert_cell(conn, page_id, position, label, commands, flags=8, span="1,1",
                link=None, border=None):
    """A raw cell on *page_id*'s first layout, for shapes the builder never makes."""
    layout = conn.execute("SELECT Id FROM PageLayout WHERE PageId = ?", (page_id,)).fetchone()[0]
    ref = conn.execute("INSERT INTO ElementReference (ElementType, PageId) VALUES (0, ?)",
                       (page_id,)).lastrowid
    button = conn.execute(
        "INSERT INTO Button (Label, CommandFlags, UniqueId, ElementReferenceId, "
        "BorderColor, BorderThickness) VALUES (?, ?, 'u', ?, ?, ?)",
        (label, flags, ref, border, 3.0 if border is not None else 0.0),
    ).lastrowid
    if commands is not None:
        conn.execute("INSERT INTO CommandSequence (SerializedCommands, ButtonId) VALUES (?, ?)",
                     (commands, button))
    conn.execute("INSERT INTO ElementPlacement (GridPosition, GridSpan, Visible, "
                 "ElementReferenceId, PageLayoutId) VALUES (?, ?, 1, ?, ?)",
                 (position, span, ref, layout))
    if link:
        conn.execute("INSERT INTO ButtonPageLink (ButtonId, PageUniqueId) VALUES (?, ?)",
                     (button, link))


def test_what_an_export_cannot_carry_is_named(seeded_pageset):
    conn = seeded_pageset.conn
    home = seeded_pageset.find_page_id_by_name("Home Page")
    speak = '{"$type":"1","$values":[{"$type":"3","MessageAction":0}]}'
    insert_cell(conn, home, "2,0", "clear", '{"$type":"1","$values":[{"$type":"7"}]}')
    insert_cell(conn, home, "3,0", "back",
                '{"$type":"1","$values":[{"$type":"2","LinkedPageId":"virtual"}]}',
                flags=9, link="virtual")
    insert_cell(conn, home, "0,1", "", speak)
    insert_cell(conn, home, "9,9", "far away", speak)
    insert_cell(conn, home, "0,0", "on top", speak)
    insert_cell(conn, home, "1,1", "broken", "not json")
    insert_cell(conn, home, "2,1", "silent", None)
    insert_cell(conn, home, "3,1", "coloured", speak, border=-1)
    conn.commit()
    boardset = obf.export_pageset(conn)
    why = reasons(boardset)
    assert "TD Snap action" in why[("Home Page", "clear")]
    assert "not one of this page set's own pages" in why[("Home Page", "back")]
    assert why[("Home Page", "")] == "has no label, only a picture"
    assert why[("Home Page", "far away")] == "sits outside the page's grid"
    assert why[("Home Page", "on top")] == "shares its cell with another button"
    assert why[("Home Page", "broken")] == "has no command AAC Editor can read"
    assert why[("Home Page", "silent")] == "has no command AAC Editor can read"
    home_cells = cells_of(boardset["boards"][0])
    assert home_cells[(1, 3)]["border"] == "#FFFFFF"


def test_an_empty_page_set_has_nothing_to_export(seeded_pageset):
    seeded_pageset.conn.execute("UPDATE Page SET PageType = 3")
    with pytest.raises(PagesetError, match="no vocabulary pages"):
        obf.export_pageset(seeded_pageset.conn)


# ---------------------------------------------------------------------------
# planning


def test_a_board_that_fits_keeps_every_button_in_its_cell():
    boardset = obf.read_bytes(coughdrop_set())
    plan = obf.plan_import(boardset, grid=(4, 3), existing_titles=["Food", "Home Page"])
    titles = [page["title"] for page in plan["pages"]]
    assert titles == ["Quick Core", "Food (2)", "Feelings"]
    assert plan["pages"][1]["renamed"] and not plan["pages"][0]["renamed"]
    home = {cell["label"]: cell for cell in plan["pages"][0]["cells"]}
    assert home["I"]["slot"] == 0 and home["feelings"]["slot"] == 4
    assert home["want"]["border_color"] == QUESTION
    assert home["I"]["border_color"] is None
    assert any("1 button border colour is not" in note for note in plan["notes"])
    assert plan["counts"] == {"pages": 3, "buttons": 8, "links": 3}


def test_a_larger_board_is_laid_out_in_reading_order_and_overflow_is_named():
    order = [[f"{r}{c}" for c in range(4)] for r in range(2)]
    buttons = [{"id": f"{r}{c}", "label": f"w{r}{c}"} for r in range(2) for c in range(4)]
    boardset = obf.read_bytes(json.dumps(
        coughdrop_board("big", "Big", 2, 4, order, buttons)).encode())
    plan = obf.plan_import(boardset, grid=(3, 2), existing_titles=[])
    page = plan["pages"][0]
    assert page["rearranged"] and page["source_grid"] == {"rows": 2, "cols": 4}
    assert [(cell["label"], cell["slot"]) for cell in page["cells"]] == [
        ("w00", 0), ("w01", 1), ("w02", 2), ("w03", 3), ("w10", 4), ("w11", 5)]
    why = reasons(plan)
    assert why[("Big", "w12")] == "does not fit on a 3 by 2 page"


def test_titles_are_made_unique_within_the_length_limit():
    taken = {"x" * 60}
    assert obf._unique_title("x" * 70, taken) == "x" * 56 + " (2)"
    assert obf._unique_title("", set()) == "Board"


def test_plan_refuses_nothing_to_import_and_too_much():
    with pytest.raises(PagesetError, match="no boards"):
        obf.plan_import({"boards": [], "root": ""}, grid=(2, 2), existing_titles=[])
    board = {"id": "a", "name": "A", "rows": 1, "columns": 1, "cells": []}
    many = {"root": "a", "boards": [dict(board, id=str(n)) for n in range(101)]}
    with pytest.raises(PagesetError, match="at most 100"):
        obf.plan_import(many, grid=(2, 2), existing_titles=[])
    dangling = {"root": "a", "boards": [dict(board, cells=[
        {"row": 0, "col": 0, "label": "x", "message": None, "border": None, "link": "zz"}])]}
    with pytest.raises(PagesetError, match="not being imported"):
        obf.plan_import(dangling, grid=(2, 2), existing_titles=[])


# ---------------------------------------------------------------------------
# the write path


def import_into(ps, data, parent="Home Page"):
    plan = obf.plan_import(obf.read_bytes(data), grid=ps.grid_dimension(),
                           existing_titles=[title for _, title in ps.list_pages()])
    baseline = validate.validate_pageset(ps.conn)
    before = validate.table_snapshot(ps.conn)
    report = builder.add_linked_pages(ps, plan, ps.find_page_id_by_name(parent))
    after = validate.table_snapshot(ps.conn)
    result = validate.validate_pageset(ps.conn)
    problems = (validate.check_roundtrip(before, after)
                + validate.validate_imported_pages(ps.conn, report)
                + result["problems"] + validate.new_warnings(baseline, result))
    return plan, report, problems


def test_a_coughdrop_obz_imports_as_linked_pages(seeded_pageset):
    _, report, problems = import_into(seeded_pageset, coughdrop_set())
    assert problems == []
    conn = seeded_pageset.conn
    titles = {title for _, title in seeded_pageset.list_pages()}
    assert {"Quick Core", "Food (2)", "Feelings"} <= titles

    def targets(page_title):
        return {
            row["Label"]: row["Target"]
            for row in conn.execute(
                "SELECT b.Label, t.Title AS Target FROM Button b "
                "JOIN ElementReference r ON r.Id = b.ElementReferenceId "
                "JOIN Page p ON p.Id = r.PageId "
                "JOIN ButtonPageLink l ON l.ButtonId = b.Id "
                "JOIN Page t ON t.UniqueId = l.PageUniqueId WHERE p.Title = ?",
                (page_title,))
        }

    assert targets("Quick Core") == {"food": "Food (2)", "feelings": "Feelings"}
    assert targets("Feelings") == {"home": "Quick Core"}
    assert targets("Home Page")["Quick Core"] == "Quick Core"
    spoken = dict(conn.execute(
        "SELECT Label, Message FROM Button WHERE Label IN ('want', 'cookie')").fetchall())
    assert spoken == {"want": "I want", "cookie": "I would like a cookie"}
    assert report["grid"] == (4, 3)


def test_a_failed_import_writes_nothing(seeded_pageset, monkeypatch):
    conn = seeded_pageset.conn
    before = validate.table_snapshot(conn)
    plan = obf.plan_import(obf.read_bytes(coughdrop_set()), grid=(4, 3), existing_titles=[
        title for _, title in seeded_pageset.list_pages()])
    real = builder._insert_cell
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 5:
            raise PagesetError("disk went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(builder, "_insert_cell", flaky)
    with pytest.raises(PagesetError, match="disk went away"):
        builder.add_linked_pages(seeded_pageset, plan, 1)
    assert validate.table_snapshot(conn) == before


def good_plan(ps):
    return obf.plan_import(obf.read_bytes(coughdrop_set()), grid=ps.grid_dimension(),
                           existing_titles=[title for _, title in ps.list_pages()])


@pytest.mark.parametrize("tamper, message", [
    (lambda plan: plan.update(grid={"cols": 9, "rows": 9}), "different grid"),
    (lambda plan: plan.update(pages=[]), "no boards"),
    (lambda plan: plan.update(pages=plan["pages"] * 40), "at most 100"),
    (lambda plan: plan["pages"][1].update(board_id=plan["pages"][0]["board_id"]),
     "share an id"),
    (lambda plan: plan["pages"][1].update(board_id=""), "needs an id"),
    (lambda plan: plan["pages"][1].update(title="Quick Core"), "both be called"),
    (lambda plan: plan["pages"][0].update(title="home page"), "already exists"),
    (lambda plan: plan["pages"][0].update(cells="nope"), "must be a list"),
    (lambda plan: plan["pages"][0]["cells"].append("nope"), "not readable"),
    (lambda plan: plan["pages"][0]["cells"][2].update(link="nowhere"), "not being imported"),
    (lambda plan: plan["pages"][0]["cells"][2].update(message="hi"), "cannot also speak"),
    (lambda plan: plan["pages"][0]["cells"][0].update(slot=12), "no cell"),
    (lambda plan: plan["pages"][0]["cells"][0].update(slot=None), "no cell"),
    (lambda plan: plan["pages"][0]["cells"][1].update(slot=0), "same cell"),
    (lambda plan: plan["pages"][0]["cells"][0].update(border_color="#123456"),
     "not one of the supported"),
])
def test_the_write_path_holds_a_plan_to_its_own_standard(seeded_pageset, tamper, message):
    plan = good_plan(seeded_pageset)
    tamper(plan)
    before = validate.table_snapshot(seeded_pageset.conn)
    with pytest.raises(PagesetError, match=message):
        builder.add_linked_pages(seeded_pageset, plan, 1)
    assert validate.table_snapshot(seeded_pageset.conn) == before


def test_the_parent_must_exist_and_have_room(seeded_pageset):
    plan = good_plan(seeded_pageset)
    with pytest.raises(PagesetError, match="not found"):
        builder.add_linked_pages(seeded_pageset, plan, 999)
    conn = seeded_pageset.conn
    home = seeded_pageset.find_page_id_by_name("Home Page")
    for index in range(2, 12):
        insert_cell(conn, home, f"{index % 4},{index // 4}", f"filler {index}",
                    '{"$type":"1","$values":[{"$type":"3"}]}')
    conn.commit()
    with pytest.raises(PagesetError, match="grid is full"):
        builder.add_linked_pages(seeded_pageset, plan, home)


def test_add_linked_pages_nests_inside_an_open_transaction(seeded_pageset):
    conn = seeded_pageset.conn
    conn.execute("BEGIN")
    report = builder.add_linked_pages(seeded_pageset, good_plan(seeded_pageset), 1)
    assert conn.in_transaction
    conn.commit()
    assert validate.validate_imported_pages(conn, report) == []
    conn.execute("BEGIN")
    plan = good_plan(seeded_pageset)
    plan["pages"][0]["title"] = "Home Page"
    with pytest.raises(PagesetError):
        builder.add_linked_pages(seeded_pageset, plan, 1)
    conn.rollback()


def test_validation_catches_an_import_that_went_wrong(seeded_pageset):
    _, report, problems = import_into(seeded_pageset, coughdrop_set())
    assert problems == []
    conn = seeded_pageset.conn
    home = report["pages"][0]
    link = next(spec for spec in home["buttons"] if spec["link_unique_id"])
    speak = next(spec for spec in home["buttons"] if not spec["link_unique_id"])
    conn.execute("UPDATE ButtonPageLink SET PageUniqueId = 'x' WHERE ButtonId = ?", (link["id"],))
    conn.execute("UPDATE Button SET CommandFlags = 8 WHERE Id = ?", (link["id"],))
    conn.execute("UPDATE CommandSequence SET SerializedCommands = '{}' WHERE ButtonId = ?",
                 (link["id"],))
    conn.execute("UPDATE Button SET CommandFlags = 9 WHERE Id = ?", (speak["id"],))
    conn.execute(
        "UPDATE ElementPlacement SET GridPosition = '3,2' WHERE ElementReferenceId = "
        "(SELECT ElementReferenceId FROM Button WHERE Id = ?)", (speak["id"],))
    conn.execute(
        "UPDATE ElementReference SET PageId = ? WHERE Id = "
        "(SELECT ElementReferenceId FROM Button WHERE Id = ?)",
        (seeded_pageset.find_page_id_by_name("Food"), report["nav_button_id"]))
    problems = validate.validate_imported_pages(conn, report)
    text = "\n".join(problems)
    assert "is not flagged as a page link" in text
    assert "does not open the page it came from" in text
    assert "command does not open its page" in text
    assert "should speak and link nowhere" in text
    assert "is not in cell 0,0" in text
    assert "not on the chosen page" in text
    missing = dict(report, nav_button_id=10**9)
    assert "Link button 'Quick Core' is missing." in validate.validate_imported_pages(
        conn, missing)


# ---------------------------------------------------------------------------
# the command line


def test_cli_export_then_import_round_trips(seeded_source, tmp_path, capsys):
    obz = tmp_path / "set.obz"
    assert main(["export-obz", seeded_source, "-o", str(obz)]) == 0
    out = capsys.readouterr().out
    assert "Exported 2 page(s), 2 button(s) and 1 link(s)" in out
    assert "Symbols are not included" in out

    assert main(["import-obz", seeded_source, str(obz), "--parent-name", "Home Page",
                 "-o", str(tmp_path / "edited.sps")]) == 0
    out = capsys.readouterr().out
    assert "Added 2 page(s) with 2 button(s) and 1 link(s)" in out
    assert "'Home Page' is called 'Home Page (2)'" in out
    assert "All validation checks passed." in out
    conn = sqlite3.connect(tmp_path / "edited.sps")
    try:
        titles = {row[0] for row in conn.execute("SELECT Title FROM Page WHERE PageType = 1")}
    finally:
        conn.close()
    assert {"Home Page (2)", "Food (2)"} <= titles


def test_cli_names_what_it_left_out(seeded_source, tmp_path, capsys):
    obz = tmp_path / "boards.obz"
    obz.write_bytes(coughdrop_set())
    assert main(["import-obz", seeded_source, str(obz), "--parent-id", "1",
                 "-o", str(tmp_path / "out.sps")]) == 0
    out = capsys.readouterr().out
    assert "Not imported (3):" in out
    assert "'clear' on 'Quick Core' performs an action" in out
    assert "note: 1 button border colour" in out

    assert main(["export-obz", str(tmp_path / "out.sps")]) == 0
    assert (tmp_path / "out.obz").exists()


def test_cli_refuses_to_overwrite_the_page_set(seeded_source, capsys):
    assert main(["export-obz", seeded_source, "-o", seeded_source]) == 1
    assert "Refusing to overwrite" in capsys.readouterr().err


def test_cli_import_reports_a_failed_validation(seeded_source, tmp_path, capsys, monkeypatch):
    obz = tmp_path / "boards.obz"
    obz.write_bytes(coughdrop_set())
    monkeypatch.setattr(validate, "validate_imported_pages", lambda conn, report: ["boom"])
    assert main(["import-obz", seeded_source, str(obz), "--parent-id", "1",
                 "-o", str(tmp_path / "out.sps")]) == 1
    assert "boom" in capsys.readouterr().err
    assert not (tmp_path / "out.sps").exists()


# ---------------------------------------------------------------------------
# the web endpoints


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setattr(server, "_sessions", {})
    (tmp_path / "sessions").mkdir()
    return server.app.test_client()


HEADERS = {"X-TDSnap-Token": server.API_TOKEN}


def open_session(client, source):
    with open(source, "rb") as handle:
        data = client.post("/api/pageset", data={"file": (io.BytesIO(handle.read()), "t.sps")},
                           headers=HEADERS).get_json()
    assert data["ok"], data
    return data["session_id"]


def post_boards(client, url, data, **form):
    return client.post(url, data={"file": (io.BytesIO(data), "set.obz"), **form},
                       headers=HEADERS)


def test_reading_a_board_file_writes_nothing(client):
    data = post_boards(client, "/api/obf/read", coughdrop_set()).get_json()
    assert data["ok"] and data["filename"] == "set.obz"
    assert [board["name"] for board in data["boardset"]["boards"]] == [
        "Quick Core", "Food", "Feelings"]
    refused = post_boards(client, "/api/obf/read", b"nope").get_json()
    assert not refused["ok"] and "not valid JSON" in refused["error"]
    missing = client.post("/api/obf/read", data={}, headers=HEADERS).get_json()
    assert missing["error"] == "No file was uploaded."
    assert client.post("/api/obf/read").status_code == 403


class _UnseekableUpload(io.BytesIO):
    """An upload stream the way Python 3.9 gives it: SpooledTemporaryFile had
    no seekable() before 3.11, and zipfile needs one."""

    @property
    def seekable(self):
        raise AttributeError("seekable")


def test_a_board_upload_does_not_need_a_seekable_stream(client, monkeypatch):
    monkeypatch.setattr(server.app.request_class, "_get_file_stream",
                        lambda self, *args, **kwargs: _UnseekableUpload())
    monkeypatch.setattr(server.tempfile, "SpooledTemporaryFile",
                        lambda *args, **kwargs: _UnseekableUpload())
    data = post_boards(client, "/api/obf/read", coughdrop_set()).get_json()
    assert data["ok"], data
    assert len(data["boardset"]["boards"]) == 3


def test_the_import_is_reviewed_then_applied_through_the_session(client, seeded_source):
    session = open_session(client, seeded_source)
    review = post_boards(client, f"/api/pageset/{session}/boards", coughdrop_set(),
                         parent_page_id="1").get_json()
    assert review["ok"], review
    assert review["plan"]["parent"] == {"id": 1, "title": "Home Page"}
    assert review["plan"]["counts"] == {"pages": 3, "buttons": 8, "links": 3}

    applied = client.post(f"/api/pageset/{session}/boards/apply",
                          json={"fingerprint": review["fingerprint"]}, headers=HEADERS)
    data = applied.get_json()
    assert data["ok"], data
    assert data["pages"] == 3 and data["buttons"] == 8 and data["links"] == 3
    assert data["root"]["title"] == "Quick Core"
    assert set(data["checks"].values()) == {"pass"}
    assert data["edits"] == 1
    pages = client.get(f"/api/pageset/{session}/pages").get_json()["pages"]
    assert {"Quick Core", "Food (2)", "Feelings"} <= {page["title"] for page in pages}

    again = client.post(f"/api/pageset/{session}/boards/apply",
                        json={"fingerprint": review["fingerprint"]}, headers=HEADERS)
    assert "no reviewed import waiting" in again.get_json()["error"]


def test_an_import_refuses_a_page_set_that_changed_since_review(client, seeded_source):
    session = open_session(client, seeded_source)
    review = post_boards(client, f"/api/pageset/{session}/boards", coughdrop_set(),
                         parent_page_id="1").get_json()
    added = client.post(f"/api/pageset/{session}/page", headers=HEADERS,
                        json={"title": "Feelings", "items": ["sad"], "parent_page_id": 1})
    assert added.get_json()["ok"]
    refused = client.post(f"/api/pageset/{session}/boards/apply",
                          json={"fingerprint": review["fingerprint"]}, headers=HEADERS)
    assert "changed after the import was reviewed" in refused.get_json()["error"]
    blank = client.post(f"/api/pageset/{session}/boards/apply", json={}, headers=HEADERS)
    assert "fingerprint is required" in blank.get_json()["error"]


def test_an_import_needs_a_parent_with_room(client, seeded_source):
    session = open_session(client, seeded_source)
    bad = post_boards(client, f"/api/pageset/{session}/boards", coughdrop_set(),
                      parent_page_id="home").get_json()
    assert "Choose the page" in bad["error"]
    conn = sqlite3.connect(server._current_path(session))
    for index in range(2, 12):
        insert_cell(conn, 1, f"{index % 4},{index // 4}", f"f{index}", "{}")
    conn.commit()
    conn.close()
    full = post_boards(client, f"/api/pageset/{session}/boards", coughdrop_set(),
                       parent_page_id="1").get_json()
    assert "no empty space" in full["error"]


def test_an_import_that_fails_validation_saves_nothing(client, seeded_source, monkeypatch):
    session = open_session(client, seeded_source)
    review = post_boards(client, f"/api/pageset/{session}/boards", coughdrop_set(),
                         parent_page_id="1").get_json()
    monkeypatch.setattr(validate, "validate_imported_pages", lambda conn, report: ["boom"])
    response = client.post(f"/api/pageset/{session}/boards/apply",
                           json={"fingerprint": review["fingerprint"]}, headers=HEADERS)
    assert response.status_code == 422
    assert response.get_json()["problems"] == ["boom"]
    pages = client.get(f"/api/pageset/{session}/pages").get_json()["pages"]
    assert "Quick Core" not in {page["title"] for page in pages}


def test_a_file_session_exports_to_obz(client, seeded_source):
    session = open_session(client, seeded_source)
    summary = client.get(f"/api/pageset/{session}/export").get_json()
    assert summary["ok"] and summary["boards"] == 2 and summary["root"] == "Home Page"
    response = client.get(f"/api/pageset/{session}/export.obz")
    assert response.status_code == 200
    assert "t.obz" in response.headers["Content-Disposition"]
    boardset = obf.read_bytes(response.get_data())
    assert [board["name"] for board in boardset["boards"]] == ["Home Page", "Food"]


def test_live_export_reads_the_page_set_td_snap_has_open(client, seeded_source, monkeypatch):
    monkeypatch.setattr(server.live, "_active_pageset_path", lambda page=None: seeded_source)
    summary = client.get("/api/tdsnap/export").get_json()
    assert summary["ok"] and summary["boards"] == 2
    response = client.get("/api/tdsnap/export.obz")
    assert "TD Snap page set.obz" in response.headers["Content-Disposition"]
    assert len(obf.read_bytes(response.get_data())["boards"]) == 2

    monkeypatch.setattr(server.live, "_active_pageset_path", lambda page=None: None)
    for path in ("/api/tdsnap/export", "/api/tdsnap/export.obz"):
        assert "could not tell which page set" in client.get(path).get_json()["error"]


def test_live_export_reports_an_unreadable_page_set(client, tmp_path, monkeypatch):
    broken = tmp_path / "broken.sps"
    broken.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    monkeypatch.setattr(server.live, "_active_pageset_path", lambda page=None: str(broken))
    for path in ("/api/tdsnap/export", "/api/tdsnap/export.obz"):
        assert "could not be read" in client.get(path).get_json()["error"]


# ---------------------------------------------------------------------------
# round-trip properties


WORDS = ["more", "all done", "help", "eat", "drink", "play", "go", "stop", "yes", "no",
         "mine", "want", "like", "big", "little", "hot", "cold", "¿qué?", "café",
         "I need a break", "look", "again"]
MESSAGES = [None, None, None, "I want more please", "Can you help me?", "¡Vamos!"]
BORDERS = [None, None, *FUNCTION_BORDER_COLORS.values()]


def seeded(seed):
    """A reproducible source for the generated board sets; not a secret."""
    return random.Random(seed)  # noqa: S311


def random_boardset(rng, grid=(4, 3)):
    """A board set this app can represent in full on a *grid* page set."""
    cols, rows = grid
    count = rng.randint(1, 5)
    ids = [f"board-{n}-{rng.randint(0, 999)}" for n in range(count)]
    boards = []
    for index, board_id in enumerate(ids):
        board_rows, board_cols = rng.randint(1, rows), rng.randint(1, cols)
        cells_available = [(r, c) for r in range(board_rows) for c in range(board_cols)]
        rng.shuffle(cells_available)
        labels = rng.sample(WORDS, k=min(len(WORDS), len(cells_available)))
        cells = []
        for (row, col), label in zip(cells_available[:rng.randint(0, len(labels))], labels):
            others = [other for other in ids if other != board_id]
            if others and rng.random() < 0.3:
                cells.append({"row": row, "col": col, "label": f"to {label}",
                              "message": None, "border": None, "link": rng.choice(others)})
                continue
            message = rng.choice(MESSAGES)
            cells.append({"row": row, "col": col, "label": label,
                          "message": message if message != label else None,
                          "border": rng.choice(BORDERS), "link": None})
        cells.sort(key=lambda cell: (cell["row"], cell["col"]))
        boards.append({"id": board_id, "name": f"Topic {index} {rng.choice(WORDS)}",
                       "locale": rng.choice([None, "en", "es-US"]),
                       "rows": board_rows, "columns": board_cols, "cells": cells})
    return {"format": obf.FORMAT, "root": ids[0], "boards": obf._order_boards(boards, ids[0]),
            "skipped": [], "notes": []}


def comparable(board, names):
    """A board as the exit criterion sees it: labels, messages, layout, links by name."""
    return sorted(
        (cell["row"], cell["col"], cell["label"], cell["message"], cell["border"],
         names.get(cell["link"]))
        for cell in board["cells"]
    )


@pytest.mark.parametrize("seed", range(40))
def test_obz_bytes_round_trip(seed):
    boardset = random_boardset(seeded(seed))
    back = obf.read_bytes(obf.to_obz_bytes(boardset))
    assert back["root"] == boardset["root"]
    assert back["boards"] == boardset["boards"]
    assert back["skipped"] == []


@pytest.mark.parametrize("seed", range(25))
def test_import_then_export_loses_nothing(seed, seeded_pageset):
    boardset = random_boardset(seeded(seed))
    _, report, problems = import_into(seeded_pageset, obf.to_obz_bytes(boardset))
    assert problems == []
    exported = obf.export_pageset(seeded_pageset.conn)
    assert exported["skipped"] == []
    title_of = {page["board_id"]: page["title"] for page in report["pages"]}
    by_title = {board["name"]: board for board in exported["boards"]}
    exported_names = {board["id"]: board["name"] for board in exported["boards"]}
    for board in boardset["boards"]:
        copy = by_title[title_of[board["id"]]]
        # Grid positions survive because every generated board fits the page
        # set's grid; the page itself is the page set's size.
        assert (copy["rows"], copy["columns"]) == (3, 4)
        assert comparable(copy, exported_names) == comparable(board, title_of)


@pytest.mark.parametrize("seed", range(15))
def test_export_then_import_into_a_fresh_page_set_round_trips(seed, seeded_pageset,
                                                              seeded_source, tmp_path):
    import_into(seeded_pageset, obf.to_obz_bytes(random_boardset(seeded(seed))))
    first = obf.export_pageset(seeded_pageset.conn)

    with Pageset(seeded_source, working_copy=str(tmp_path / "fresh.sps")) as fresh:
        _, report, problems = import_into(fresh, obf.to_obz_bytes(first))
        assert problems == []
        second = obf.export_pageset(fresh.conn)

    title_of = {page["board_id"]: page["title"] for page in report["pages"]}
    renamed = {board["id"]: title_of[board["id"]] for board in first["boards"]}
    second_names = {board["id"]: board["name"] for board in second["boards"]}
    by_title = {board["name"]: board for board in second["boards"]}
    for board in first["boards"]:
        copy = by_title[renamed[board["id"]]]
        assert comparable(copy, second_names) == comparable(board, renamed)
