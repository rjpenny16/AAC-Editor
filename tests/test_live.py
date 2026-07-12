from types import SimpleNamespace

from tdsnap import live


def test_live_grid_finds_first_uncovered_cell():
    grid = live.Grid((50, 150), (50, 150), 80, 80)
    occupied = [
        SimpleNamespace(left=10, top=10, right=90, bottom=90),
        SimpleNamespace(left=110, top=10, right=190, bottom=90),
        SimpleNamespace(left=10, top=110, right=90, bottom=190),
    ]
    assert live._first_empty(grid, occupied) == live.Cell(150, 150, 80, 80)


def test_live_web_endpoints(monkeypatch):
    from tdsnap.web.server import app

    monkeypatch.setattr(
        live,
        "status",
        lambda: {
            "available": True,
            "running": True,
            "unlocked": True,
            "page": "Topics Menu Page",
            "grid": {"cols": 6, "rows": 6},
        },
    )
    monkeypatch.setattr(
        live,
        "add_topic_page",
        lambda title, items, parent: {
            "page": title,
            "parent": parent,
            "buttons": len(items),
            "checks": {"td_snap_edit": "pass"},
            "warnings": [],
        },
    )
    client = app.test_client()

    assert client.get("/api/tdsnap/status").get_json()["running"] is True
    rejected = client.post(
        "/api/tdsnap/page", json={"title": "Snacks", "items": ["chips"]}
    ).get_json()
    assert rejected["ok"] is False
    result = client.post(
        "/api/tdsnap/page",
        json={"title": "Snacks", "items": ["chips", "apple"]},
        headers={"X-TDSnap-Editor": "1"},
    ).get_json()
    assert result["ok"] is True
    assert result["page"] == "Snacks"
    assert result["buttons"] == 2
