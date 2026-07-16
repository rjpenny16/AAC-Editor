import sqlite3
from types import SimpleNamespace

from tdsnap import live


def test_live_lists_every_page_from_active_pageset(tmp_path, monkeypatch):
    user = (tmp_path / "Packages" / "TobiiDynavox.Snap_test" /
            "LocalState" / "Users" / "user")
    user.mkdir(parents=True)
    with sqlite3.connect(user / "Settings.ssf") as conn:
        conn.execute("CREATE TABLE UserSettings (PageSetGuid TEXT)")
        conn.execute("INSERT INTO UserSettings VALUES ('active')")
    with sqlite3.connect(user / "active.sps") as conn:
        conn.execute(
            "CREATE TABLE Page (Id INTEGER, UniqueId TEXT, Title TEXT, PageType INTEGER)"
        )
        conn.execute(
            "CREATE TABLE ElementReference (Id INTEGER, PageId INTEGER)"
        )
        conn.execute(
            "CREATE TABLE Button (Id INTEGER, Label TEXT, ElementReferenceId INTEGER)"
        )
        conn.execute(
            "CREATE TABLE ButtonPageLink (ButtonId INTEGER, PageUniqueId TEXT)"
        )
        conn.executemany("INSERT INTO Page VALUES (?, ?, ?, ?)", [
            (1, "core", "Core Words", 1),
            (2, "lists", "Word Lists", 1),
            (3, "nested", "Nested Page", 1),
            (4, "toolbar", "Tool Bar", 3),
        ])
        conn.executemany("INSERT INTO ElementReference VALUES (?, ?)", [
            (1, 4), (2, 1), (3, 2),
        ])
        conn.executemany("INSERT INTO Button VALUES (?, ?, ?)", [
            (1, "Core Words", 1), (2, "All Word Lists", 2), (3, "Nested", 3),
        ])
        conn.executemany("INSERT INTO ButtonPageLink VALUES (?, ?)", [
            (1, "core"), (2, "lists"), (3, "nested"),
        ])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert live._active_pageset_pages() == ["Core Words", "Nested Page", "Word Lists"]
    assert live._page_route("Topics Menu Page", "Nested Page") == [
        ("Core Words", "Core Words", True),
        ("All Word Lists", "Word Lists", False),
        ("Nested", "Nested Page", False),
    ]


def test_live_grid_finds_first_uncovered_cell():
    grid = live.Grid((50, 150), (50, 150), 80, 80)
    occupied = [
        SimpleNamespace(left=10, top=10, right=90, bottom=90),
        SimpleNamespace(left=110, top=10, right=190, bottom=90),
        SimpleNamespace(left=10, top=110, right=90, bottom=190),
    ]
    assert live._first_empty(grid, occupied) == live.Cell(150, 150, 80, 80)


def test_empty_cell_ignores_unnamed_edit_placeholders(monkeypatch):
    def button(name, left):
        return SimpleNamespace(
            Name=name,
            ControlTypeName="ButtonControl",
            BoundingRectangle=SimpleNamespace(
                left=left, top=10, right=left + 80, bottom=90,
            ),
        )

    group = SimpleNamespace(GetChildren=lambda: [
        button("Apple", 10), button("", 110),
    ])
    monkeypatch.setattr(live, "_page_group", lambda _window: group)

    assert live._empty_cell(
        object(), live.Grid((50, 150), (50,), 80, 80), allow_scroll=False
    ) == live.Cell(150, 50, 80, 80)


def test_live_grid_infers_rows_for_a_sparse_new_page():
    def button(column):
        left = 4 + column * 120
        return SimpleNamespace(
            ControlTypeName="ButtonControl",
            BoundingRectangle=SimpleNamespace(
                left=left, top=4, right=left + 110, bottom=113,
            ),
        )

    group = SimpleNamespace(
        GetChildren=lambda: [button(column) for column in range(7)],
        BoundingRectangle=SimpleNamespace(left=0, top=0, right=839, bottom=832),
    )

    grid = live._grid(group)

    assert len(grid.xs) == 7
    assert len(grid.ys) == 7
    assert grid.ys[0] == 4 + 109 // 2


def test_live_grid_ignores_a_button_that_spans_multiple_columns():
    def button(column, row, span=1):
        left = 10 + column * 110
        return SimpleNamespace(
            ControlTypeName="ButtonControl",
            BoundingRectangle=SimpleNamespace(
                left=left, top=20 + row * 90,
                right=left + 100 * span + 10 * (span - 1),
                bottom=100 + row * 90,
            ),
        )

    controls = [button(column, row) for row in range(5) for column in range(7)]
    controls.append(button(0, 6, span=2))
    group = SimpleNamespace(
        GetChildren=lambda: controls,
        BoundingRectangle=SimpleNamespace(left=0, top=0, right=780, bottom=650),
    )

    grid = live._grid(group)

    assert len(grid.xs) == 7
    assert len(grid.ys) == 7


def test_live_grid_uses_saved_positions_for_a_sparse_page(tmp_path, monkeypatch):
    pageset = tmp_path / "active.sps"
    positions = [("Question", 0, 0), ("Comment", 1, 1), ("Positive", 2, 3)]
    with sqlite3.connect(pageset) as connection:
        connection.execute("CREATE TABLE Page (Id INTEGER, Title TEXT, GridDimension TEXT)")
        connection.execute("CREATE TABLE PageLayout (Id INTEGER, PageLayoutSetting TEXT, PageId INTEGER)")
        connection.execute("CREATE TABLE Button (Label TEXT, ElementReferenceId INTEGER)")
        connection.execute("CREATE TABLE ElementReference (Id INTEGER)")
        connection.execute("CREATE TABLE ElementPlacement (PageLayoutId INTEGER, ElementReferenceId INTEGER, GridPosition TEXT, Visible INTEGER)")
        connection.execute("INSERT INTO Page VALUES (1, 'Talk', NULL)")
        connection.execute("INSERT INTO PageLayout VALUES (2, '7,7,True,0', 1)")
        connection.execute("INSERT INTO PageLayout VALUES (3, '2,2,True,0', 1)")
        for reference, (label, column, row) in enumerate(positions, 1):
            connection.execute("INSERT INTO ElementReference VALUES (?)", (reference,))
            connection.execute("INSERT INTO Button VALUES (?, ?)", (label, reference))
            connection.execute(
                "INSERT INTO ElementPlacement VALUES (2, ?, ?, 1)",
                (reference, f"{column},{row}"),
            )
            connection.execute(
                "INSERT INTO ElementPlacement VALUES (3, ?, ?, 1)",
                (reference, f"{min(column, 1)},{min(row, 1)}"),
            )
    monkeypatch.setattr(live, "_active_pageset_path", lambda: str(pageset))

    controls = []
    for label, column, row in positions:
        controls.append(SimpleNamespace(
            ControlTypeName="ButtonControl", Name=label,
            BoundingRectangle=SimpleNamespace(
                left=60 + column * 100, top=165 + row * 90,
                right=140 + column * 100, bottom=235 + row * 90,
            ),
        ))
    group = SimpleNamespace(
        Name="Talk", GetChildren=lambda: controls,
        BoundingRectangle=SimpleNamespace(left=0, top=0, right=800, bottom=800),
    )

    grid = live._grid(group)

    assert grid.xs == (100, 200, 300, 400, 500, 600, 700)
    assert grid.ys == (200, 290, 380, 470, 560, 650, 740)


def test_preview_slot_maps_to_live_grid_cell():
    grid = live.Grid((50, 150, 250), (60, 160), 80, 70)
    assert live._cell_at(grid, 4) == live.Cell(150, 160, 80, 70)
    assert live._cell_at(grid, 6) is None


def test_sparse_page_grid_is_anchored_to_its_first_created_button():
    template = live.Grid((50, 150, 250), (60, 160, 260), 80, 70)
    button = SimpleNamespace(BoundingRectangle=SimpleNamespace(
        left=410, top=520, right=490, bottom=590,
    ))

    grid = live._anchored_grid(template, button, 4)

    assert grid.xs == (350, 450, 550)
    assert grid.ys == (455, 555, 655)


def test_page_layout_maps_existing_buttons_to_slots():
    def button(name, left, top, right, bottom):
        return SimpleNamespace(
            ControlTypeName="ButtonControl", Name=name,
            BoundingRectangle=SimpleNamespace(left=left, top=top, right=right, bottom=bottom),
        )

    group = SimpleNamespace(GetChildren=lambda: [
        button("Apple", 10, 20, 90, 80),
        button("", 110, 20, 190, 80),
        button("Pizza", 110, 120, 190, 180),
    ])
    grid = live.Grid((50, 150), (50, 150), 80, 60)
    assert live._page_layout(group, grid) == [
        {"slot": 0, "label": "Apple"},
        {"slot": 3, "label": "Pizza"},
    ]


def test_page_name_prefers_the_top_title(monkeypatch):
    def control(name, top, bottom):
        return SimpleNamespace(
            Name=name, ControlTypeName="TextControl",
            BoundingRectangle=SimpleNamespace(
                left=10, top=top, right=200, bottom=bottom,
            ),
        )

    group = SimpleNamespace(
        Name="Topic: Shopping",
        BoundingRectangle=SimpleNamespace(left=0, top=100, right=300, bottom=500),
    )
    title = control("Topic: Shopping", 10, 30)
    message = control("E of ", 40, 90)
    monkeypatch.setattr(live, "_walk", lambda _window, _depth: [(title, 3), (message, 4)])

    assert live._page_name(object(), group) == "Topic: Shopping"


def test_grid_uses_saved_dimensions_for_a_completely_blank_page(tmp_path, monkeypatch):
    pageset = tmp_path / "active.sps"
    with sqlite3.connect(pageset) as connection:
        connection.execute("CREATE TABLE Page (Id INTEGER, Title TEXT, GridDimension TEXT)")
        connection.execute(
            "CREATE TABLE PageLayout (Id INTEGER, PageLayoutSetting TEXT, PageId INTEGER)"
        )
        connection.execute("INSERT INTO Page VALUES (1, 'World Cup Final', NULL)")
        connection.execute("INSERT INTO PageLayout VALUES (1, '7,7,True,0', 1)")
    monkeypatch.setattr(live, "_active_pageset_path", lambda: str(pageset))
    group = SimpleNamespace(
        Name="World Cup Final",
        BoundingRectangle=SimpleNamespace(left=0, top=0, right=700, bottom=700),
        GetChildren=lambda: [],
    )

    grid = live._grid(group)

    assert (len(grid.xs), len(grid.ys), grid.xs[0], grid.ys[0]) == (7, 7, 50, 50)


def test_activate_retries_while_td_snap_is_busy(monkeypatch):
    class BusyError(Exception):
        hresult = -2147220992

    class Pattern:
        calls = 0

        def Invoke(self):
            self.calls += 1
            if self.calls == 1:
                raise BusyError

    pattern = Pattern()
    control = SimpleNamespace(GetInvokePattern=lambda: pattern)
    monkeypatch.setattr(live.time, "sleep", lambda _seconds: None)

    live._activate(control)

    assert pattern.calls == 2


def test_open_page_accepts_td_snap_internal_page_name(monkeypatch):
    state = {"name": "Topics Menu Page"}

    class Pattern:
        def Invoke(self):
            state["name"] = "Topic: Custom 5"

    class Link:
        def GetInvokePattern(self):
            return Pattern()

    monkeypatch.setattr(live, "_page_name", lambda _window: state["name"])
    assert live._open_page_button(object(), Link(), "About Me") == "Topic: Custom 5"


def test_create_page_opens_new_link_when_dialog_stays_on_parent(monkeypatch):
    state = {"page": "Main List: Personal", "linked": False, "opened": None}
    group = object()
    choice = object()
    create = object()
    link = object()
    textbox = SimpleNamespace(
        ControlTypeName="EditControl", Name="Page name", AutomationId="",
        BoundingRectangle=SimpleNamespace(left=0, right=10),
    )

    monkeypatch.setattr(live, "_click_empty_icon", lambda *_args: choice)
    monkeypatch.setattr(live, "_walk", lambda *_args: [(textbox, 1)])
    monkeypatch.setattr(live, "_set_value", lambda *_args: None)
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_page_name", lambda _window: state["page"])
    monkeypatch.setattr(
        live, "_find",
        lambda root, **criteria: (
            create if criteria.get("name") == "Create" else
            link if state["linked"] and criteria.get("name") == "My Restaurants" else
            None
        ),
    )
    monkeypatch.setattr(
        live, "_activate", lambda control: state.update(linked=True)
        if control is create else None,
    )
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(
        live, "_open_page_button",
        lambda _window, control, title: (
            state.update(page="Topic: Custom 5", opened=control) or "Topic: Custom 5"
        ),
    )

    live._create_page_link(
        object(), object(), "My Restaurants", live.Cell(10, 20, 30, 40)
    )

    assert state["opened"] is link


def test_symbol_search_results_include_web_images(monkeypatch):
    def result(name, right=10):
        return SimpleNamespace(
            ControlTypeName="ListItemControl", Name=name,
            BoundingRectangle=SimpleNamespace(left=0, right=right),
        )

    symbol = result("SymbolLibrarySearchResult 1")
    web = result("MyTdxWebImage { ImageUrl = https://example.com/image.jpg }")
    monkeypatch.setattr(live, "_walk", lambda *_args: [
        (symbol, 1), (web, 1), (result("Other"), 1),
        (result("MyTdxWebImage hidden", right=0), 1),
    ])

    assert live._search_results(object()) == [symbol]
    assert live._search_results(object(), web=True) == [web]


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
    monkeypatch.setattr(live, "_physical_point", lambda *_args: (10, 20))
    monkeypatch.setattr(
        live, "_set_value", lambda _textbox, value: state.update(value=value)
    )
    monkeypatch.setattr(live, "_walk", lambda *_args: [(textbox, 10)])
    monkeypatch.setattr(live, "_find", lambda *_args, **_kwargs: object())

    live._add_button(Auto(), object(), live.Cell(50, 60, 40, 30), "hello")

    assert state["clicked"] == (10, 20, 0.2)
    assert state["value"] == "hello"


def test_live_click_coordinates_scale_from_client_origin(monkeypatch):
    monkeypatch.setattr(live, "_client_origin", lambda _window: (1600, 80))
    monkeypatch.setattr(live, "_window_dpi", lambda _window: 120)

    assert live._physical_point(object(), 2000, 800) == (2100, 980)


def test_existing_page_remeasures_grid_in_edit_mode(monkeypatch):
    view_grid = live.Grid((10, 20), (30, 40), 8, 8)
    edit_grid = live.Grid((110, 120), (130, 140), 18, 18)
    grids = iter((view_grid, edit_grid))
    added = {}
    group = SimpleNamespace(GetChildren=lambda: [SimpleNamespace(Name="hello")])

    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_grid", lambda _group: next(grids))
    monkeypatch.setattr(live, "_page_layout", lambda _group, _grid: [])
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)
    monkeypatch.setattr(
        live, "_add_button",
        lambda _auto, _window, cell, *_args: added.update(cell=cell) or {
            "symbol": False, "border": True,
        },
    )

    live.add_to_existing_page(
        "Eating", [{"label": "hello", "slot": 0, "symbol": False}], "v1"
    )

    assert added["cell"] == live.Cell(110, 130, 18, 18)


def test_live_web_endpoints(monkeypatch):
    from tdsnap.web.server import API_TOKEN, app

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
    monkeypatch.setattr(live, "launch", lambda: {"launched": True})
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
    launched = client.post(
        "/api/tdsnap/launch", headers={"X-TDSnap-Token": API_TOKEN}
    ).get_json()
    assert launched["launched"] is True
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


def test_live_launches_td_snap_once(monkeypatch):
    opened = []
    monkeypatch.setattr(live.sys, "platform", "win32")
    monkeypatch.setattr(live, "status", lambda _include_pages=False: {"running": False})
    monkeypatch.setattr(live.os, "startfile", opened.append, raising=False)

    assert live.launch() == {"launched": True}
    assert opened == [live.TD_SNAP_APP]
