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


def test_preview_slot_maps_to_live_grid_cell():
    grid = live.Grid((50, 150, 250), (60, 160), 80, 70)
    assert live._cell_at(grid, 4) == live.Cell(150, 160, 80, 70)
    assert live._cell_at(grid, 6) is None


def test_page_layout_maps_existing_buttons_to_slots():
    def button(name, left, top, right, bottom):
        return SimpleNamespace(
            ControlTypeName="ButtonControl", Name=name,
            BoundingRectangle=SimpleNamespace(left=left, top=top, right=right, bottom=bottom),
        )

    group = SimpleNamespace(GetChildren=lambda: [
        button("Apple", 10, 20, 90, 80),
        button("Pizza", 110, 120, 190, 180),
    ])
    grid = live.Grid((50, 150), (50, 150), 80, 60)
    assert live._page_layout(group, grid) == [
        {"slot": 0, "label": "Apple"},
        {"slot": 3, "label": "Pizza"},
    ]


def test_live_page_link_uses_double_click():
    state = {"double": 0}

    class Link:
        def DoubleClick(self, simulateMove=False):
            state["double"] += 1

    live._double_activate(Link())
    assert state["double"] == 1


def test_open_page_accepts_td_snap_internal_page_name(monkeypatch):
    state = {"name": "Topics Menu Page"}

    class Link:
        def DoubleClick(self, simulateMove=False):
            state["name"] = "Topic: Custom 5"

    monkeypatch.setattr(
        live, "_page_group", lambda _window: SimpleNamespace(Name=state["name"])
    )
    assert live._open_page_button(object(), Link(), "About Me") == "Topic: Custom 5"


def test_live_click_coordinates_follow_td_snap_window_dpi(monkeypatch):
    monkeypatch.setattr(live, "_window_dpi", lambda _window: 120)
    assert live._physical_point(object(), 832.34, 541.32) == (1040, 677)


def test_live_add_button_uses_hidden_accessibility_textbox(monkeypatch):
    state = {"clicked": False, "value": None}
    group = object()
    textbox = SimpleNamespace(
        ControlTypeName="EditControl", AutomationId="TextBox", IsEnabled=True
    )

    class Auto:
        def Click(self, x, y, waitTime):
            state["clicked"] = (x, y, waitTime)

    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(
        live, "_fingerprint", lambda _group: ("after",) if state["clicked"] else ("before",)
    )
    monkeypatch.setattr(live, "_physical_point", lambda _window, _x, _y: (10, 20))
    monkeypatch.setattr(live, "_walk", lambda _root, _depth=9: [(textbox, 10)])
    monkeypatch.setattr(
        live, "_set_value", lambda _textbox, value: state.update(value=value)
    )
    monkeypatch.setattr(live, "_find", lambda *_args, **_kwargs: object())

    live._add_button(Auto(), object(), live.Cell(50, 60, 40, 30), "hello")

    assert state["clicked"] == (10, 20, 0.2)
    assert state["value"] == "hello"


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
    monkeypatch.setattr(
        live,
        "inspect_page",
        lambda page: {
            "page": page, "grid": {"cols": 2, "rows": 2},
            "buttons": [{"slot": 0, "label": "Apple"}],
            "free_slots": [1, 2, 3], "fingerprint": "abc",
        },
    )
    monkeypatch.setattr(
        live,
        "add_to_existing_page",
        lambda page, items, fingerprint: {
            "page": page, "buttons": len(items),
            "checks": {"td_snap_edit": "pass", "positions": "pass"},
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
    layout = client.get("/api/tdsnap/page-layout?page=Eating").get_json()
    assert layout["buttons"][0]["label"] == "Apple"
    existing = client.post(
        "/api/tdsnap/edit-plan",
        json={
            "operation": "add_to_existing_page", "page": "Eating",
            "fingerprint": "abc", "items": [{"label": "Pizza", "slot": 1}],
        },
        headers={"X-TDSnap-Editor": "1"},
    ).get_json()
    assert existing["ok"] is True
    assert existing["buttons"] == 1
