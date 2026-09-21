"""Open Board Format interchange: file in, file out, and back again."""

import io
import json
import random
import sqlite3
import zipfile

import pytest

from tdsnap import obf
from tdsnap.errors import PagesetError
from tests.conftest import require_example


def board(**overrides):
    base = {
        "format": "open-board-0.1", "id": "snacks", "locale": "en", "name": "Snacks",
        "buttons": [
            {"id": "1", "label": "apple", "border_color": "rgb(30, 136, 229)"},
            {"id": "2", "label": "crisps", "vocalization": "crisps please"},
            {"id": "3", "label": "drinks", "load_board": {"id": "drinks", "path": "boards/drinks.obf"}},
            {"id": "4", "label": "space", "action": ":space"},
            {"id": "5", "label": ""},
            {"id": "6", "label": "gone", "hidden": True},
            {"id": "7", "label": "Apple"},
        ],
        "grid": {"rows": 2, "columns": 3, "order": [["1", "2", None], ["3", "4", "7"]]},
    }
    base.update(overrides)
    return base


def obz(boards, root=None, extra_names=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        paths = {b["id"]: f"boards/{b['id']}.obf" for b in boards}
        manifest = {"format": "open-board-0.1", "root": root or paths[boards[0]["id"]],
                    "paths": {"boards": paths, "images": {}, "sounds": {}}}
        archive.writestr("manifest.json", json.dumps(manifest))
        for b in boards:
            archive.writestr(paths[b["id"]], json.dumps(b))
        for name in extra_names:
            archive.writestr(name, "x")
    return buffer.getvalue()


def test_a_single_board_becomes_one_page_with_slots_functions_and_links():
    result = obf.read(json.dumps(board()).encode("utf-8"), "snacks.obf")
    assert result["root"] == 0 and len(result["pages"]) == 1
    page = result["pages"][0]
    assert page["title"] == "Snacks" and page["grid"] == {"cols": 3, "rows": 2}
    assert page["items"] == [
        {"label": "apple", "message": None, "slot": 0, "function": "question"},
        {"label": "crisps", "message": "crisps please", "slot": 1, "function": None},
    ]
    # A board this file does not hold is a link to nowhere, kept so the user is told.
    assert page["links"] == [{"slot": 3, "label": "drinks", "board": None}]
    # keyboard action, empty label, hidden, and a repeated label (case-insensitive)
    assert page["skipped"] == 4
    assert result["warnings"] == [
        "4 buttons on “Snacks” could not be imported (hidden, unlabelled, repeated, or a keyboard action)."
    ]


def test_an_obz_resolves_links_between_its_boards_and_names_the_root():
    drinks = board(id="drinks", name="Drinks", buttons=[
        {"id": "1", "label": "water"}, {"id": "2", "label": "back", "load_board": {"path": "boards/snacks.obf"}},
    ], grid={"rows": 1, "columns": 2, "order": [["1", "2"]]})
    result = obf.read(obz([drinks, board()], root="boards/snacks.obf"))
    titles = [page["title"] for page in result["pages"]]
    assert titles[result["root"]] == "Snacks"
    by_title = {page["title"]: page for page in result["pages"]}
    assert by_title["Snacks"]["links"][0]["board"] == titles.index("Drinks")
    # a link by path rather than id resolves the same way
    assert by_title["Drinks"]["links"][0]["board"] == titles.index("Snacks")


def test_bad_files_are_refused_with_a_reason():
    with pytest.raises(PagesetError, match="empty"):
        obf.read(b"")
    with pytest.raises(PagesetError, match="not an Open Board Format JSON"):
        obf.read(b"not json", "x.obf")
    with pytest.raises(PagesetError, match="not an Open Board Format board"):
        obf.read(b"[1, 2]", "x.obf")
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("readme.txt", "hi")
    with pytest.raises(PagesetError, match=r"no manifest.json"):
        obf.read(empty.getvalue())
    with pytest.raises(PagesetError, match="contains no boards"):
        obf.read(_manifest_only())
    # a manifest pointing outside the archive is ignored rather than followed
    escaped = obz([board()], root="../../etc/passwd")
    assert obf.read(escaped)["pages"][0]["title"] == "Snacks"


def _manifest_only():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "open-board-0.1", "paths": {}}))
    return buffer.getvalue()


def test_a_board_without_a_grid_still_imports_its_buttons():
    result = obf.read(json.dumps(board(grid={})).encode("utf-8"))
    page = result["pages"][0]
    assert page["grid"] == {"cols": 0, "rows": 0}
    assert [item["slot"] for item in page["items"]] == [None, None]
    assert any("has no grid" in warning for warning in result["warnings"])


def test_write_produces_a_valid_obz_with_load_board_links_and_no_images():
    pages = [
        {"title": "Home", "grid": {"cols": 2, "rows": 2},
         "items": [{"label": "hello", "message": None, "slot": 0, "function": None}],
         "links": [{"slot": 3, "label": "Snacks", "board": 1}]},
        {"title": "Snacks", "grid": {"cols": 2, "rows": 1},
         "items": [{"label": "apple", "message": "an apple please", "slot": 1, "function": "positive"}],
         "links": []},
    ]
    data = obf.write(pages, name="Test Set")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "open-board-0.1"
        assert manifest["root"] == "boards/001-home.obf"
        assert manifest["paths"]["images"] == {} and manifest["paths"]["sounds"] == {}
        home = json.loads(archive.read("boards/001-home.obf"))
        snacks = json.loads(archive.read(manifest["paths"]["boards"]["2"]))
    assert home["grid"] == {"rows": 2, "columns": 2, "order": [["1", None], [None, "2"]]}
    link = next(b for b in home["buttons"] if b["label"] == "Snacks")
    assert link["load_board"] == {"id": "2", "path": "boards/002-snacks.obf"}
    assert snacks["buttons"] == [{"label": "apple", "vocalization": "an apple please",
                                  "border_color": "#43A047", "id": "1"}]
    assert snacks["images"] == [] and "without symbols" in snacks["description_html"]


def test_write_places_unslotted_buttons_in_the_first_free_cells():
    data = obf.write([{"title": "P", "grid": {"cols": 2, "rows": 1},
                       "items": [{"label": "b", "slot": 1}, {"label": "a", "slot": None}]}])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        page = json.loads(archive.read("boards/001-p.obf"))
    assert page["grid"]["order"] == [["2", "1"]]


def test_write_refuses_nothing_and_too_much():
    with pytest.raises(PagesetError, match="no pages"):
        obf.write([])
    with pytest.raises(PagesetError, match="More than 2000"):
        obf.write([{"title": str(n), "grid": {"cols": 1, "rows": 1}, "items": []} for n in range(2001)])


@pytest.mark.parametrize("seed", range(12))
def test_round_trip_keeps_labels_messages_layout_functions_and_links(seed):
    rng = random.Random(seed)  # noqa: S311 - reproducible test data, not security
    functions = [None, "question", "comment", "positive", "negative", "personal"]
    pages = []
    count = rng.randint(1, 4)
    for index in range(count):
        cols, rows = rng.randint(1, 6), rng.randint(1, 5)
        slots = list(range(cols * rows))
        rng.shuffle(slots)
        items, links = [], []
        for n in range(rng.randint(0, min(6, cols * rows))):
            label = f"w{index}-{n}"
            items.append({"label": label, "slot": slots.pop(),
                          "message": f"{label} please" if rng.random() < 0.4 else None,
                          "function": rng.choice(functions)})
        while slots and rng.random() < 0.5:
            links.append({"slot": slots.pop(), "label": f"go{index}-{len(links)}",
                          "board": rng.randrange(count)})
        pages.append({"title": f"Page {index}", "grid": {"cols": cols, "rows": rows},
                      "items": items, "links": links})
    again = obf.read(obf.write(pages))
    assert again["root"] == 0
    assert len(again["pages"]) == len(pages)
    for before, after in zip(pages, again["pages"]):
        assert after["title"] == before["title"] and after["grid"] == before["grid"]
        key = lambda item: item["slot"]  # noqa: E731
        assert sorted(after["items"], key=key) == sorted(before["items"], key=key)
        assert sorted(after["links"], key=key) == sorted(before["links"], key=key)
        assert after["skipped"] == 0


def test_pages_from_the_seeded_page_set_carry_home_first_speech_and_links(seeded_source):
    with sqlite3.connect(f"file:{seeded_source}?mode=ro", uri=True) as conn:
        pages = obf.pages_from_pageset(conn)
    assert [page["title"] for page in pages] == ["Home Page", "Food"]
    home = pages[0]
    assert home["grid"] == {"cols": 4, "rows": 3}
    assert home["items"] == [{"label": "hello", "message": None, "slot": 0, "function": None}]
    assert home["links"] == [{"slot": 1, "label": "Food", "board": 1}]
    data = obf.write(pages, name="seed")
    again = obf.read(data)
    assert again["pages"][0]["links"][0]["board"] == 1
    assert again["pages"][1]["title"] == "Food"


def test_the_real_fixture_exports_every_page_and_reads_back():
    example = require_example()
    with sqlite3.connect(f"file:{example}?mode=ro", uri=True) as conn:
        pages = obf.pages_from_pageset(conn)
    assert len(pages) > 10
    total_items = sum(len(page["items"]) for page in pages)
    total_links = sum(len(page["links"]) for page in pages)
    assert total_items > 100 and total_links > 10
    # every link that names a page resolves to one; none is dangling
    for page in pages:
        for link in page["links"]:
            assert link["board"] is None or 0 <= link["board"] < len(pages)
    again = obf.read(obf.write(pages, name="Example"))
    assert [page["title"] for page in again["pages"]] == [page["title"] for page in pages]
    # Reading keeps one button per label on a page (a repeated label is ambiguous
    # to edit), so a page that really carries two "calibration" buttons reads
    # back with one; everything else survives.
    distinct = sum(
        len({item["label"].casefold() for item in page["items"]}) for page in pages
    )
    assert sum(len(page["items"]) for page in again["pages"]) == distinct
    assert total_items - distinct < 5
