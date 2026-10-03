"""The exported-file routes, driven with a Grid 3 .gridset instead of a TD Snap page set."""

import io
import json
import zipfile

import pytest

from tdsnap import gridset
from tests.test_gridset import make
from tests.test_web import client, token_headers, upload  # noqa: F401 - fixture

HOME = gridset.page_id("Home")
FOOD = gridset.page_id("Food")


@pytest.fixture
def session(client, tmp_path):  # noqa: F811 - the client fixture
    response = upload(client, make(tmp_path), "My Grids.gridset")
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def layout(client, session_id, page_id=HOME):  # noqa: F811
    return client.get(f"/api/pageset/{session_id}/page/{page_id}/layout").get_json()


def test_upload_reports_format_grids_and_limits(session):
    assert session["format"] == "gridset"
    assert [page["title"] for page in session["pages"]] == ["Food", "Home"]
    assert session["home_page_id"] == HOME
    assert session["grid"] == {"cols": 3, "rows": 2}
    assert any("gridsetx" in line for line in session["limits"]["cannot"])


def test_summary_layout_capacity_and_vocabulary(client, session):  # noqa: F811
    sid = session["session_id"]
    summary = client.get(f"/api/pageset/{sid}").get_json()
    assert summary["format"] == "gridset" and summary["edits"] == 0
    page = layout(client, sid)
    assert page["page"] == "Home" and page["free_slots"] == [2, 5]
    assert page["can_edit_existing"] is True
    capacity = client.get(f"/api/pageset/{sid}/page/{FOOD}/capacity").get_json()
    assert capacity["free_cells"] == 5
    words = client.get(f"/api/pageset/{sid}/vocabulary").get_json()
    assert words["labels"]["Food"] == ["apple"]


def test_add_change_and_download(client, session):  # noqa: F811
    sid = session["session_id"]
    added = client.post(
        f"/api/pageset/{sid}/page/{HOME}/buttons",
        json={"items": [{"label": "drink", "slot": 2}],
              "fingerprint": layout(client, sid)["fingerprint"]},
        headers=token_headers(),
    )
    assert added.status_code == 200, added.get_json()
    assert added.get_json()["edits"] == 1
    edited = client.post(
        f"/api/pageset/{sid}/page/{HOME}/edit",
        json={"changes": [{"slot": 0, "label": "hi"}], "removals": [1],
              "moves": [{"slot": 2, "to": 5}],
              "fingerprint": layout(client, sid)["fingerprint"]},
        headers=token_headers(),
    )
    assert edited.status_code == 200, edited.get_json()
    body = edited.get_json()
    assert (body["changed"], body["removed"], body["moved"]) == (1, 1, 1)
    download = client.get(f"/api/pageset/{sid}/download")
    assert 'My Grids.edited.gridset' in download.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(download.data)) as package:
        home = package.read("Grids/Home/grid.xml")
    assert b"hi" in home and b"drink" in home


def test_stale_fingerprint_and_locked_cells(client, session):  # noqa: F811
    sid = session["session_id"]
    stale = client.post(
        f"/api/pageset/{sid}/page/{HOME}/buttons",
        json={"items": ["x"], "fingerprint": "0" * 64}, headers=token_headers(),
    )
    assert stale.status_code == 400 and "changed after" in stale.get_json()["error"]
    locked = client.post(
        f"/api/pageset/{sid}/page/{HOME}/edit",
        json={"removals": [3], "fingerprint": layout(client, sid)["fingerprint"]},
        headers=token_headers(),
    )
    assert locked.status_code == 400 and "opens another grid" in locked.get_json()["error"]


def test_failed_verification_keeps_the_session_copy(client, session, monkeypatch):  # noqa: F811
    sid = session["session_id"]
    before = layout(client, sid)["fingerprint"]
    monkeypatch.setattr(gridset, "verify", lambda *_args: ["something drifted"])
    response = client.post(
        f"/api/pageset/{sid}/page/{HOME}/buttons",
        json={"items": ["drink"], "fingerprint": before}, headers=token_headers(),
    )
    assert response.status_code == 422
    assert response.get_json()["problems"] == ["something drifted"]
    assert layout(client, sid)["fingerprint"] == before


def test_new_linked_grid(client, session):  # noqa: F811
    sid = session["session_id"]
    response = client.post(
        f"/api/pageset/{sid}/page",
        json={"title": "Drinks", "items": ["water"], "parent_page_id": HOME},
        headers=token_headers(),
    )
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["page_id"] == gridset.page_id("Drinks")
    titles = [page["title"] for page in
              client.get(f"/api/pageset/{sid}/pages").get_json()["pages"]]
    assert titles == ["Drinks", "Food", "Home"]


def test_obz_export_and_import(client, session):  # noqa: F811
    sid = session["session_id"]
    summary = client.get(f"/api/pageset/{sid}/export").get_json()
    assert summary["boards"] == 2 and summary["root"] == "Home"
    exported = client.get(f"/api/pageset/{sid}/export.obz")
    assert exported.status_code == 200
    planned = client.post(
        f"/api/pageset/{sid}/boards",
        data={"file": (io.BytesIO(exported.data), "boards.obz"), "parent_page_id": str(HOME)},
        headers=token_headers(),
    )
    assert planned.status_code == 200, planned.get_json()
    plan = planned.get_json()
    assert [page["title"] for page in plan["plan"]["pages"]] == ["Home (2)", "Food (2)"]
    applied = client.post(f"/api/pageset/{sid}/boards/apply",
                          json={"fingerprint": plan["fingerprint"]}, headers=token_headers())
    assert applied.status_code == 200, applied.get_json()
    assert applied.get_json()["root"]["title"] == "Home (2)"
    assert json.dumps(applied.get_json()["checks"])


def test_edit_route_refuses_td_snap_files(client, seeded_source):  # noqa: F811
    sid = upload(client, seeded_source).get_json()["session_id"]
    response = client.post(f"/api/pageset/{sid}/page/1/edit",
                           json={"removals": [0], "fingerprint": "x"},
                           headers=token_headers())
    assert response.status_code == 400
    assert "not available for exported TD Snap files" in response.get_json()["error"]
    assert client.get(f"/api/pageset/{sid}").get_json()["format"] == "sps"


@pytest.mark.parametrize("filename, data, message", [
    ("vocab.ce", b"PK-ish but not", "Chat Editor"),
    ("WordPower.gridsetx", b"\x00" * 64, "protected .gridsetx"),
    ("notes.txt", b"hello", "is not a TD Snap page set"),
])
def test_unsupported_uploads_say_why(client, filename, data, message):  # noqa: F811
    response = client.post("/api/pageset",
                           data={"file": (io.BytesIO(data), filename)},
                           headers=token_headers())
    assert response.status_code == 400
    assert message in response.get_json()["error"]
