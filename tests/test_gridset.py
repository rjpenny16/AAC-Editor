"""Editing a .gridset file into a separate copy (tdsnap.gridset)."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from tdsnap import gridset, obf
from tdsnap.errors import PagesetError
from tdsnap.grid3 import Grid3Package

SETTINGS = ("<GridSetSettings><GridSetFileFormatVersion>1</GridSetFileFormatVersion>"
            "<StartGrid>Home</StartGrid></GridSetSettings>")
STYLES = """<StyleData><Styles>
  <Style Key="Default"><BorderColour>#112233FF</BorderColour></Style>
  <Style Key="Vocab cell"><BackColour>#FFFFFFFF</BackColour></Style>
  <Style Key="Navigation category style"><BackColour>#CCCCCCFF</BackColour></Style>
</Styles></StyleData>"""
PICTURE = b"\x89PNG not really a picture" * 50


def speak(x, y, label, message=None, style="Vocab cell"):
    return (f'<Cell X="{x}" Y="{y}"><Content><Commands><Command ID="Action.InsertText">'
            f'<Parameter Key="text"><p><s><r>{message or label}</r></s><s><r> </r></s></p>'
            f"</Parameter></Command></Commands><CaptionAndImage><Caption><p><s><r>{label}</r>"
            f"</s></p></Caption></CaptionAndImage><Style><BasedOnStyle>{style}</BasedOnStyle>"
            "</Style></Content></Cell>")


def jump(x, y, target, label=None):
    return (f'<Cell X="{x}" Y="{y}"><Content><Commands><Command ID="Jump.To">'
            f'<Parameter Key="grid">{target}</Parameter></Command></Commands>'
            f"<CaptionAndImage><Caption>{label or target}</Caption></CaptionAndImage>"
            "<Style><BasedOnStyle>Navigation category style</BasedOnStyle></Style>"
            "</Content></Cell>")


def blank(x, y):
    return (f'<Cell X="{x}" Y="{y}"><Content><Style><BasedOnStyle>Default</BasedOnStyle>'
            "</Style></Content></Cell>")


def grid_xml(cells, cols=3, rows=2):
    columns = "<ColumnDefinition/>" * cols
    row_defs = "<RowDefinition/>" * rows
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            f"<Grid><GridGuid>00000000-0000-0000-0000-000000000001</GridGuid>"
            f"<ColumnDefinitions>{columns}</ColumnDefinitions>"
            f"<RowDefinitions>{row_defs}</RowDefinitions><Cells>{''.join(cells)}</Cells>"
            "<WordList><Items><WordListItem>keep</WordListItem></Items></WordList></Grid>")


HOME = grid_xml([
    speak(0, 0, "hello"),
    speak(1, 0, "more", "more please"),
    blank(2, 0),
    jump(0, 1, "Food"),
    '<Cell X="1" Y="1"><Content><ContentType>Workspace</ContentType></Content></Cell>',
    # (2, 1) has no cell element at all: an empty square.
])
FOOD = grid_xml([speak(1, 0, "apple"), blank(2, 0)])


def make(tmp_path, *, filemap=True, grids=None, name="current"):
    path = tmp_path / name
    grids = grids or {"Home": HOME, "Food": FOOD}
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("Settings0/settings.xml", SETTINGS)
        package.writestr("Settings0/Styles/styles.xml", STYLES)
        for grid_name, xml in grids.items():
            package.writestr(f"Grids/{grid_name}/grid.xml", xml)
        package.writestr("Grids/Home/pic.png", PICTURE)
        if filemap:
            entries = "".join(
                f'<Entry StaticFile="Grids\\{grid_name}\\grid.xml"><DynamicFiles>'
                f"<File>Grids\\{grid_name}\\pic.png</File></DynamicFiles></Entry>"
                for grid_name in grids
            )
            package.writestr("FileMap.xml", f"<FileMap><Entries>{entries}</Entries></FileMap>")
    return str(path)


def home_id():
    return gridset.page_id("Home")


def state(path, number=None):
    with gridset.GridsetFile(path) as source:
        return source.page_state(number or home_id())


def read(path, name="Home"):
    with gridset.GridsetFile(path) as source:
        return source.grid(name)


def entries(path):
    with zipfile.ZipFile(path) as package:
        return {info.filename: package.read(info) for info in package.infolist()}


# -- reading -----------------------------------------------------------------


def test_reads_pages_start_grid_and_free_squares(tmp_path):
    path = make(tmp_path)
    assert gridset.is_gridset_file(path)
    with gridset.GridsetFile(path) as source:
        assert [page["title"] for page in source.pages()] == ["Food", "Home"]
        assert source.home_page_id() == home_id()
        assert source.grid_dimension() == (3, 2)
        assert source.labels_by_page()["Home"] == ["Food", "hello", "more"]
    current = state(path)
    # (2, 0) is a safe blank and (2, 1) has no cell element at all.
    assert current["free_slots"] == [2, 5]
    by_slot = {button["slot"]: button for button in current["buttons"]}
    assert by_slot[0]["editable"] and by_slot[1]["message"] == "more please"
    assert not by_slot[3]["editable"] and "opens another grid" in by_slot[3]["locked_reason"]
    assert not by_slot[4]["editable"]
    assert current["content_readable"] and current["can_edit_existing"]


def test_page_ids_are_stable_and_unknown_ids_are_refused(tmp_path):
    path = make(tmp_path)
    assert gridset.page_id("Home") == gridset.page_id("home") < 2**53
    with gridset.GridsetFile(path) as source, pytest.raises(PagesetError, match="not in this"):
        source.name_for(12345)


def test_session_copy_reads_outside_grid3_users_but_live_path_does_not(tmp_path):
    path = make(tmp_path, name="copy.gridset")
    with pytest.raises(PagesetError, match="local Grid user"):
        Grid3Package(path)
    with Grid3Package(path, session_copy=True) as package:
        assert "Home" in package.grid_names()


def test_refuses_password_protected_packages(tmp_path):
    path = make(tmp_path)
    with zipfile.ZipFile(path, "a") as package:
        package.writestr("secret.bin", b"x")
    # zipfile will not write an encrypted entry, so set the flag in the
    # central directory record by hand, which is what readers consult.
    data = bytearray(Path(path).read_bytes())
    record = data.rfind(b"PK\x01\x02")
    data[record + 8] |= 0x1
    Path(path).write_bytes(bytes(data))
    with pytest.raises(PagesetError, match="password"):
        gridset.GridsetFile(path)


def test_not_a_gridset(tmp_path):
    other = tmp_path / "other"
    other.write_bytes(b"SQLite format 3\x00")
    assert not gridset.is_gridset_file(str(other))


# -- editing one grid ----------------------------------------------------------


def test_adds_cells_to_a_blank_and_an_empty_square(tmp_path):
    path = make(tmp_path)
    dest = str(tmp_path / "out")
    report = gridset.edit_grid(path, dest, home_id(), items=[
        {"label": "drink", "slot": 2},
        {"label": "biscuit", "message": "I want a biscuit", "border_color": "#43A047"},
    ], expected_fingerprint=state(path)["fingerprint"])
    assert report["buttons"] == 2 and report["checks"]["content"] == "pass"
    grid = read(dest)
    drink, biscuit = grid.cell_at(2, 0), grid.cell_at(2, 1)
    assert drink.label == "drink" and drink.message == "drink"
    assert drink.commands == ("Action.InsertText",) and drink.style.key == "Vocab cell"
    assert biscuit.message == "I want a biscuit" and biscuit.style.border == "#43A047"
    before, after = entries(path), entries(dest)
    assert after["Grids/Home/pic.png"] == PICTURE
    assert after["Grids/Food/grid.xml"] == before["Grids/Food/grid.xml"]
    assert after["Grids/Home/grid.xml"].startswith(b'<?xml version="1.0"')


def test_change_move_and_remove(tmp_path):
    path = make(tmp_path)
    dest = str(tmp_path / "out")
    report = gridset.edit_grid(
        path, dest, home_id(),
        changes=[{"slot": 1, "label": "more!"}],
        moves=[{"slot": 1, "to": 2}],
        removals=[0],
        expected_fingerprint=state(path)["fingerprint"],
    )
    assert (report["changed"], report["moved"], report["removed"]) == (1, 1, 1)
    grid = read(dest)
    assert grid.cell_at(0, 0).safe_blank
    assert grid.cell_at(1, 0).safe_blank
    moved = grid.cell_at(2, 0)
    # A cell that spoke something other than its label keeps saying it.
    assert moved.label == "more!" and moved.message == "more please"
    assert moved.style.key == "Vocab cell"


def test_freed_cells_can_be_reused_in_the_same_edit(tmp_path):
    path = make(tmp_path)
    dest = str(tmp_path / "out")
    gridset.edit_grid(path, dest, home_id(), items=[{"label": "bye", "slot": 0}],
                      removals=[0], expected_fingerprint=state(path)["fingerprint"])
    assert read(dest).cell_at(0, 0).label == "bye"


@pytest.mark.parametrize("kwargs, message", [
    ({"removals": [3]}, "opens another grid"),
    ({"changes": [{"slot": 4, "label": "x"}]}, "Grid 3 content"),
    ({"removals": [2]}, "is empty"),
    ({"items": [{"label": "x", "slot": 0}]}, "not a safe empty"),
    ({"items": [{"label": "Hello"}]}, "Already on this grid"),
    ({"removals": [0], "changes": [{"slot": 0, "label": "x"}]}, "changed and removed"),
    ({"moves": [{"slot": 0, "to": 2}], "items": [{"label": "x", "slot": 2}]},
     "different empty space"),
    ({"items": [{"label": "x", "slot": 99}]}, "outside the grid"),
    ({}, "at least one"),
])
def test_invalid_edits_are_refused_before_anything_is_written(tmp_path, kwargs, message):
    path = make(tmp_path)
    dest = tmp_path / "out"
    with pytest.raises(PagesetError, match=message):
        gridset.edit_grid(path, str(dest), home_id(),
                          expected_fingerprint=state(path)["fingerprint"], **kwargs)
    assert not dest.exists()


def test_stale_or_missing_fingerprint_is_refused(tmp_path):
    path = make(tmp_path)
    with pytest.raises(PagesetError, match="fingerprint is required"):
        gridset.edit_grid(path, str(tmp_path / "out"), home_id(), items=["x"])
    with pytest.raises(PagesetError, match="changed after the preview"):
        gridset.edit_grid(path, str(tmp_path / "out"), home_id(), items=["x"],
                          expected_fingerprint="0" * 64)


def test_full_grid_has_no_room(tmp_path):
    path = make(tmp_path, grids={"Home": grid_xml([speak(0, 0, "a")], cols=1, rows=1)})
    with pytest.raises(PagesetError, match="no room"):
        gridset.edit_grid(path, str(tmp_path / "out"), home_id(), items=["b"],
                          expected_fingerprint=state(path)["fingerprint"])


def test_a_write_that_does_not_verify_keeps_nothing(tmp_path, monkeypatch):
    path = make(tmp_path)
    dest = tmp_path / "out"
    real = gridset._Writer.write_speaking

    def sloppy(self, name, position, label, message, style):
        real(self, name, position, label.upper(), message, style)

    monkeypatch.setattr(gridset._Writer, "write_speaking", sloppy)
    with pytest.raises(gridset.GridsetVerificationError) as raised:
        gridset.edit_grid(path, str(dest), home_id(), items=[{"label": "drink"}],
                          expected_fingerprint=state(path)["fingerprint"])
    assert any("does not say “drink”" in problem for problem in raised.value.problems)
    assert not dest.exists()


def test_verify_names_untouched_changes(tmp_path):
    path = make(tmp_path)
    tampered = tmp_path / "tampered"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(tampered, "w") as out:
        for info in source.infolist():
            data = source.read(info)
            if info.filename == "Grids/Food/grid.xml":
                data = data.replace(b"apple", b"pear")
            if info.filename == "Grids/Home/pic.png":
                data = b"changed"
            out.writestr(info, data)
    problems = gridset.verify(path, str(tampered), {}, {})
    assert any("Grids/Home/pic.png changed" in problem for problem in problems)
    assert any("on “Food” changed" in problem for problem in problems)


# -- new grids -------------------------------------------------------------------


def test_creates_a_linked_grid_shaped_like_its_parent(tmp_path):
    path = make(tmp_path)
    dest = str(tmp_path / "out")
    report = gridset.add_grid(path, dest, "Drinks", ["water", "juice"], home_id())
    assert report["page"] == "Drinks" and report["nav_button_id"] == 2
    with gridset.GridsetFile(dest) as result:
        drinks = result.grid("Drinks")
        assert (drinks.cols, drinks.rows) == (3, 2)
        assert drinks.cell_at(0, 0).commands == ("Jump.Back",)
        assert {cell.label for cell in drinks.cells} == {"Back", "water", "juice"}
        assert result.jump_targets("Home")[(2, 0)] == "Drinks"
        assert result.grid("Home").cell_at(2, 0).label == "Drinks"
    after = entries(dest)
    created = after["Grids/Drinks/grid.xml"]
    assert b"00000000-0000-0000-0000-000000000001" not in created
    assert b"keep" not in created  # the parent's word list does not come along
    assert b"Grids\\Drinks\\grid.xml" in after["FileMap.xml"]
    assert b"Grids\\Drinks\\pic.png" not in after["FileMap.xml"]


def test_new_grid_without_a_file_map(tmp_path):
    path = make(tmp_path, filemap=False)
    dest = str(tmp_path / "out")
    gridset.add_grid(path, dest, "Drinks", ["water"], home_id())
    assert "FileMap.xml" not in entries(dest)


def test_unrecognised_file_map_stops_grid_creation(tmp_path):
    path = make(tmp_path, filemap=False)
    with zipfile.ZipFile(path, "a") as package:
        package.writestr("FileMap.xml", "<FileMap><Something/></FileMap>")
    with pytest.raises(PagesetError, match="file map"):
        gridset.add_grid(path, str(tmp_path / "out"), "Drinks", ["water"], home_id())


@pytest.mark.parametrize("title, message", [
    ("Food", "already in this grid set"),
    ("a/b", "cannot contain"),
    ("Dots.", "cannot contain"),
    ("con", "Windows reserves"),
    ("LPT1.txt", "Windows reserves"),
    ("", "name"),
])
def test_new_grid_names_are_checked(tmp_path, title, message):
    path = make(tmp_path)
    with pytest.raises(PagesetError, match=message):
        gridset.add_grid(path, str(tmp_path / "out"), title, ["water"], home_id())


def test_new_grid_needs_an_empty_parent_cell(tmp_path):
    path = make(tmp_path, grids={"Home": grid_xml([speak(0, 0, "a")], cols=1, rows=1)})
    with pytest.raises(PagesetError, match="no empty cell"):
        gridset.add_grid(path, str(tmp_path / "out"), "New", ["b"], home_id())


# -- Open Board Format -------------------------------------------------------


def test_exports_grids_as_a_board_set(tmp_path):
    boardset = gridset.to_boardset(make(tmp_path))
    assert boardset["root"] == "Home"
    assert [board["name"] for board in boardset["boards"]] == ["Home", "Food"]
    home = boardset["boards"][0]
    by_label = {cell["label"]: cell for cell in home["cells"]}
    assert by_label["more"]["message"] == "more please"
    assert by_label["hello"]["message"] is None
    assert by_label["Food"]["link"] == "Food"
    assert any("Grid 3 content" in item["reason"] for item in boardset["skipped"])
    # The canonical model survives the .obz writer and reader.
    again = obf.read_bytes(obf.to_obz_bytes(boardset))
    assert [board["name"] for board in again["boards"]] == ["Home", "Food"]


def test_imports_an_obz_as_linked_grids(tmp_path):
    path = make(tmp_path)
    boardset = {
        "format": obf.FORMAT, "root": "a", "skipped": [], "notes": [],
        "boards": [
            {"id": "a", "name": "Snacks/Treats", "locale": None, "rows": 2, "columns": 2,
             "cells": [{"row": 0, "col": 0, "label": "crisps", "message": None,
                        "border": None, "link": None},
                       {"row": 0, "col": 1, "label": "Drinks", "message": None,
                        "border": None, "link": "b"}]},
            {"id": "b", "name": "Drinks", "locale": None, "rows": 1, "columns": 1,
             "cells": [{"row": 0, "col": 0, "label": "milk", "message": "milk please",
                        "border": "#43A047", "link": None}]},
        ],
    }
    plan = gridset.plan_import(path, boardset, home_id())
    titles = [page["title"] for page in plan["pages"]]
    assert titles == ["Snacks-Treats", "Drinks"]
    # Top-left squares belong to Back, so those buttons move along.
    assert all(cell["slot"] != 0 for page in plan["pages"] for cell in page["cells"])
    dest = str(tmp_path / "out")
    report = gridset.import_boards(path, dest, plan, home_id())
    assert report["pages"] == 2 and report["links"] == 1
    with gridset.GridsetFile(dest) as result:
        assert result.jump_targets("Home")[(2, 0)] == "Snacks-Treats"
        assert "Drinks" in result.jump_targets("Snacks-Treats").values()
        milk = next(cell for cell in result.grid("Drinks").cells if cell.label == "milk")
        assert milk.message == "milk please" and milk.style.border == "#43A047"


def test_obz_round_trip_keeps_labels_messages_and_links(tmp_path):
    path = make(tmp_path)
    exported = gridset.to_boardset(path)
    fresh = make(tmp_path, grids={"Start": grid_xml([], cols=3, rows=2)}, name="fresh")
    plan = gridset.plan_import(fresh, json.loads(json.dumps(exported)),
                               gridset.page_id("Start"))
    dest = str(tmp_path / "out")
    gridset.import_boards(fresh, dest, plan, gridset.page_id("Start"))
    again = gridset.to_boardset(dest)
    by_name = {board["name"]: board for board in again["boards"]}
    words = lambda board: {(c["label"], c["message"], c["link"]) for c in board["cells"]}  # noqa: E731
    assert words(by_name["Food"]) == {("apple", None, None)}
    home = by_name["Home"]
    assert {("more", "more please", None), ("Food", None, "Food")} <= words(home)

def test_obz_bytes_from_a_gridset_are_readable(tmp_path):
    data = obf.to_obz_bytes(gridset.to_boardset(make(tmp_path)))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert "manifest.json" in archive.namelist()


# -- the verifier, edge by edge ------------------------------------------------


def rewrite(path, dest, *, drop=(), add=None, replace=None):
    """A copy of *path* with entries dropped, added, or rewritten."""
    replace = replace or {}
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(dest, "w") as out:
        for info in source.infolist():
            if info.filename in drop:
                continue
            data = source.read(info)
            if info.filename in replace:
                data = replace[info.filename](data)
            out.writestr(info, data)
        for name, data in (add or {}).items():
            out.writestr(name, data)
    return str(dest)


def test_verify_reports_every_kind_of_drift(tmp_path):
    path = make(tmp_path)
    cases = {
        "missing": rewrite(path, tmp_path / "a", drop={"Grids/Home/pic.png"}),
        "extra": rewrite(path, tmp_path / "b", add={"stray.txt": b"x"}),
        "grid gone": rewrite(path, tmp_path / "c", drop={"Grids/Food/grid.xml"}),
        "layout": rewrite(path, tmp_path / "d", replace={
            "Grids/Food/grid.xml": lambda d: d.replace(b"<RowDefinition/>", b"", 1)}),
        "appeared": rewrite(path, tmp_path / "e", replace={
            "Grids/Food/grid.xml": lambda d: d.replace(
                b"</Cells>", speak(0, 1, "new").encode() + b"</Cells>")}),
    }
    assert "is missing from" in gridset.verify(path, cases["missing"], {}, {})[0]
    assert "appeared in the edited" in gridset.verify(path, cases["extra"], {}, {})[0]
    assert any("“Food” is missing" in p for p in gridset.verify(path, cases["grid gone"], {}, {}))
    assert any("changed its layout" in p for p in gridset.verify(path, cases["layout"], {}, {}))
    assert any("appeared although" in p for p in gridset.verify(path, cases["appeared"], {}, {}))
    broken = tmp_path / "broken"
    broken.write_bytes(b"not a zip")
    assert "could not be read back" in gridset.verify(path, str(broken), {}, {})[0]


def test_verify_checks_each_reviewed_cell(tmp_path):
    path = make(tmp_path)
    with gridset.GridsetFile(path) as source:
        hello = source.grid("Home").cell_at(0, 0)
    expect = {"Home": {
        (0, 0): ("blank",),
        (1, 0): ("speak", "other", None, None),
        (2, 0): ("moved", hello, "hello", None),
        (0, 1): ("jump", "Nowhere", "Food"),
        (1, 1): ("back",),
    }}
    problems = gridset.verify(path, path, expect, {"Ghost": "Home"})
    text = " ".join(problems)
    assert "(0, 0) on “Home” is not empty" in text
    assert "does not say “other”" in text
    assert "did not arrive intact" in text
    assert "does not open “Nowhere”" in text
    assert "has no Back cell" in text
    assert "the new grid “Ghost” is missing" in text
    bordered = {"Home": {(0, 0): ("speak", "hello", None, "#43A047")}}
    assert "lost its border colour" in gridset.verify(path, path, bordered, {})[0]
    # A new grid that is the wrong size or holds unreviewed cells.
    assert not any("not the size of" in p
                   for p in gridset.verify(path, path, {"Food": {}}, {"Food": "Home"}))
    odd = make(tmp_path, grids={"Home": HOME, "Food": FOOD,
                                "Tiny": grid_xml([speak(0, 0, "x")], cols=1, rows=1)},
               name="odd")
    text = " ".join(gridset.verify(path, odd, {}, {"Tiny": "Home"}))
    assert "is not the size of" in text and "holds something the review did not name" in text


# -- reading edge cases ------------------------------------------------------------


def test_packages_without_grids_or_with_clashing_names(tmp_path):
    empty = tmp_path / "empty"
    with zipfile.ZipFile(empty, "w") as package:
        package.writestr("Settings0/settings.xml", SETTINGS)
        package.writestr("Settings0/Styles/styles.xml", STYLES)
    with pytest.raises(PagesetError, match="no grids"):
        gridset.GridsetFile(str(empty))
    clash = make(tmp_path, grids={"Home": HOME, "home": FOOD}, filemap=False, name="clash")
    with pytest.raises(PagesetError, match="same name"):
        gridset.GridsetFile(clash)
    unreadable = tmp_path / "unreadable"
    unreadable.write_bytes(b"nope")
    with pytest.raises(PagesetError, match="not a readable package"):
        gridset.GridsetFile(str(unreadable))


def test_bad_coordinates_and_samples(tmp_path):
    bad = make(tmp_path, grids={"Home": grid_xml([jump(0, 0, "Home").replace('X="0"', 'X="a"')])},
               name="bad")
    with gridset.GridsetFile(bad) as source, pytest.raises(PagesetError, match="coordinates"):
        source.jump_targets("Home")
    with gridset.GridsetFile(make(tmp_path)) as source:
        assert source.label_samples(limit=2) == ["apple", "Food"]


def test_start_grid_falls_back_to_the_first(tmp_path):
    path = make(tmp_path, grids={"Alpha": FOOD}, filemap=False, name="nostart")
    with gridset.GridsetFile(path) as source:
        assert source.home_page_id() is None
        assert source.grid_dimension() == (3, 2)


def test_new_cells_use_the_grid_set_s_own_speaking_style(tmp_path):
    styles = STYLES.replace('<Style Key="Vocab cell"><BackColour>#FFFFFFFF</BackColour></Style>',
                            '<Style Key="Words"><BackColour>#FFFFFFFF</BackColour></Style>')
    path = tmp_path / "styled"
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("Settings0/settings.xml", SETTINGS)
        package.writestr("Settings0/Styles/styles.xml", styles)
        package.writestr("Grids/Home/grid.xml", grid_xml([speak(0, 0, "hi", style="Words")]))
    path = str(path)
    dest = str(tmp_path / "styled-out")
    gridset.edit_grid(path, dest, home_id(), items=["yes"],
                      expected_fingerprint=state(path)["fingerprint"])
    assert read(dest).cell_at(1, 0).style.key == "Words"


def test_change_gives_a_caption_to_a_cell_that_had_none_in_its_holder(tmp_path):
    cell = speak(0, 0, "hello").replace(
        "<CaptionAndImage><Caption><p><s><r>hello</r></s></p></Caption></CaptionAndImage>",
        "<CaptionAndImage><Caption>hello</Caption></CaptionAndImage>")
    path = make(tmp_path, grids={"Home": grid_xml([cell])}, filemap=False, name="plain")
    dest = str(tmp_path / "plain-out")
    gridset.edit_grid(path, dest, home_id(), changes=[{"slot": 0, "message": "hello there"}],
                      expected_fingerprint=state(path)["fingerprint"])
    changed = read(dest).cell_at(0, 0)
    assert changed.label == "hello" and changed.message == "hello there"


@pytest.mark.parametrize("kwargs, message", [
    ({"removals": [0], "moves": [{"slot": 0, "to": 2}]}, "moved and removed"),
    ({"removals": [0, 0]}, "same cell twice"),
    ({"items": [{"label": "a"}, {"label": "A"}]}, "duplicate"),
    ({"changes": [{"slot": 0}]}, "new label or message"),
    ({"changes": [{"slot": 0, "label": " "}]}, "needs a label"),
    ({"removals": [True]}, "whole number"),
])
def test_more_refusals(tmp_path, kwargs, message):
    path = make(tmp_path)
    with pytest.raises(PagesetError, match=message):
        gridset.edit_grid(path, str(tmp_path / "out"), home_id(),
                          expected_fingerprint=state(path)["fingerprint"], **kwargs)


def test_new_grid_link_slot_and_overflow(tmp_path):
    path = make(tmp_path)
    dest = str(tmp_path / "out")
    gridset.add_grid(path, dest, "Drinks", ["water"], home_id(), link_slot=5)
    with gridset.GridsetFile(dest) as result:
        assert result.jump_targets("Home")[(2, 1)] == "Drinks"
    with pytest.raises(PagesetError, match="not empty"):
        gridset.add_grid(path, dest, "More", ["water"], home_id(), link_slot=0)
    with pytest.raises(PagesetError, match="more words than"):
        gridset.add_grid(path, dest, "More", [str(n) for n in range(6)], home_id())
    with pytest.raises(PagesetError, match="at least one"):
        gridset.add_grid(path, dest, "More", [], home_id())
    with pytest.raises(PagesetError, match="must be text"):
        gridset.add_grid(path, dest, 5, ["x"], home_id())
    with pytest.raises(PagesetError, match="too long"):
        gridset.add_grid(path, dest, "x" * 61, ["x"], home_id())


def test_export_skips_what_open_board_cannot_carry(tmp_path):
    grid = grid_xml([
        jump(0, 0, "Missing"),
        '<Cell X="1" Y="0"><Content><Commands><Command ID="Jump.Back"/></Commands>'
        "<CaptionAndImage><Caption>Back</Caption></CaptionAndImage></Content></Cell>",
        '<Cell X="2" Y="0" ColumnSpan="2"><Content><CaptionAndImage><Caption>wide</Caption>'
        "</CaptionAndImage></Content></Cell>",
        '<Cell X="0" Y="1"><Content><Commands><Command ID="Settings.Exit"/></Commands>'
        "<CaptionAndImage><Caption>quit</Caption></CaptionAndImage></Content></Cell>",
    ], cols=4)
    boardset = gridset.to_boardset(make(tmp_path, grids={"Home": grid}, filemap=False))
    reasons = " ".join(item["reason"] for item in boardset["skipped"])
    for expected in ("not in this grid set", "Grid 3 navigation", "more than one square",
                     "runs a Grid 3 command"):
        assert expected in reasons
    assert boardset["boards"][0]["cells"] == []


def test_import_edges(tmp_path):
    tiny = make(tmp_path, grids={"Home": grid_xml([], cols=1, rows=1)}, filemap=False)
    boardset = {"format": obf.FORMAT, "root": "a", "skipped": [], "notes": [], "boards": [
        {"id": "a", "name": "A", "locale": None, "rows": 1, "columns": 1,
         "cells": [{"row": 0, "col": 0, "label": "x", "message": None, "border": None,
                    "link": None}]}]}
    plan = gridset.plan_import(tiny, boardset, home_id())
    assert plan["pages"][0]["cells"] == []
    assert "Back cell" in plan["skipped"][0]["reason"]
    full = make(tmp_path, grids={"Home": grid_xml([speak(0, 0, "a")], cols=1, rows=1)},
                filemap=False, name="full")
    with pytest.raises(PagesetError, match="no empty cell"):
        gridset.import_boards(full, str(tmp_path / "x"), plan, home_id())
    clash = dict(plan, pages=[dict(plan["pages"][0], title="Home")])
    roomy = make(tmp_path, name="roomy")
    with pytest.raises(PagesetError, match="already in this grid set"):
        gridset.import_boards(roomy, str(tmp_path / "y"), clash, home_id())


def test_imported_board_names_become_usable_grid_names():
    assert gridset._safe_title("a/b: c?") == "a-b- c-"
    assert gridset._safe_title("Nul") == "Nul board"
    assert gridset._safe_title("...") == "Board"
