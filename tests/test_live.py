import os
import re
import sqlite3
from types import SimpleNamespace

import pytest
from _pytest.outcomes import Failed

from tdsnap import live, templates
from tdsnap.errors import PagesetError


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


def test_active_pageset_is_bound_to_unique_visible_content(tmp_path, monkeypatch):
    for user_name, label in (("first", "Apple"), ("second", "Pear")):
        user = (tmp_path / "Packages" / "TobiiDynavox.Snap_test" /
                "LocalState" / "Users" / user_name)
        user.mkdir(parents=True)
        with sqlite3.connect(user / "Settings.ssf") as conn:
            conn.execute("CREATE TABLE UserSettings (PageSetGuid TEXT)")
            conn.execute("INSERT INTO UserSettings VALUES ('active')")
        with sqlite3.connect(user / "active.sps") as conn:
            conn.execute(
                "CREATE TABLE Page (Id INTEGER, Title TEXT, PageType INTEGER)"
            )
            conn.execute(
                "CREATE TABLE ElementReference (Id INTEGER, PageId INTEGER)"
            )
            conn.execute(
                "CREATE TABLE Button (Label TEXT, ElementReferenceId INTEGER)"
            )
            conn.execute("INSERT INTO Page VALUES (1, 'Eating', 1)")
            conn.execute("INSERT INTO ElementReference VALUES (1, 1)")
            conn.execute("INSERT INTO Button VALUES (?, 1)", (label,))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    selected = live._active_pageset_path("Eating", ["Apple"])

    assert selected.replace("\\", "/").endswith("first/active.sps")
    assert live._active_pageset_path("Eating") is None


def test_td_snap_window_requires_exact_packaged_application(monkeypatch):
    window = SimpleNamespace(Exists=lambda _timeout: True, ProcessId=42)
    auto = SimpleNamespace(WindowControl=lambda **_kwargs: window)
    expected = live.TD_SNAP_APP.removeprefix("shell:AppsFolder\\")
    monkeypatch.setattr(live, "_process_app_id", lambda _pid: expected)

    assert live._window(auto) is window

    monkeypatch.setattr(live, "_process_app_id", lambda _pid: "Other.App!App")
    with pytest.raises(PagesetError, match="not the installed TD Snap"):
        live._window(auto)


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


@pytest.mark.parametrize("custom_message", [False, True])
def test_live_grid_uses_saved_positions_for_a_sparse_page(tmp_path, monkeypatch, custom_message):
    pageset = tmp_path / "active.sps"
    positions = [("Question", 0, 0), ("Comment", 1, 1), ("Positive", 2, 3)]
    with sqlite3.connect(pageset) as connection:
        connection.execute("CREATE TABLE Page (Id INTEGER, Title TEXT, GridDimension TEXT)")
        connection.execute("CREATE TABLE PageLayout (Id INTEGER, PageLayoutSetting TEXT, PageId INTEGER)")
        connection.execute("CREATE TABLE Button (Label TEXT, Message TEXT, ElementReferenceId INTEGER)")
        connection.execute("CREATE TABLE ElementReference (Id INTEGER)")
        connection.execute("CREATE TABLE ElementPlacement (PageLayoutId INTEGER, ElementReferenceId INTEGER, GridPosition TEXT, Visible INTEGER)")
        connection.execute("INSERT INTO Page VALUES (1, 'Talk', NULL)")
        connection.execute("INSERT INTO PageLayout VALUES (2, '7,7,True,0', 1)")
        connection.execute("INSERT INTO PageLayout VALUES (3, '2,2,True,0', 1)")
        for reference, (label, column, row) in enumerate(positions, 1):
            connection.execute("INSERT INTO ElementReference VALUES (?)", (reference,))
            message = f"Let's talk about {label}" if custom_message else None
            connection.execute("INSERT INTO Button VALUES (?, ?, ?)", (label, message, reference))
            connection.execute(
                "INSERT INTO ElementPlacement VALUES (2, ?, ?, 1)",
                (reference, f"{column},{row}"),
            )
            connection.execute(
                "INSERT INTO ElementPlacement VALUES (3, ?, ?, 1)",
                (reference, f"{min(column, 1)},{min(row, 1)}"),
            )
    monkeypatch.setattr(live, "_active_pageset_path", lambda *_args: str(pageset))

    controls = []
    for label, column, row in positions:
        controls.append(SimpleNamespace(
            ControlTypeName="ButtonControl",
            Name=f"Let's talk about {label}" if custom_message else label,
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
    monkeypatch.setattr(live, "_active_pageset_path", lambda *_args: str(pageset))
    group = SimpleNamespace(
        Name="World Cup Final",
        BoundingRectangle=SimpleNamespace(left=0, top=0, right=700, bottom=700),
        GetChildren=lambda: [],
    )

    grid = live._grid(group)

    assert (len(grid.xs), len(grid.ys), grid.xs[0], grid.ys[0]) == (7, 7, 50, 50)


def test_activate_delegates_to_uia_with_td_snap_messages(monkeypatch):
    """The retry/fallback logic itself is pinned in tests/test_uia.py; this
    only proves TD Snap's wrapper wires the shared helper up correctly."""
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
    monkeypatch.setattr(live.uia.time, "sleep", lambda _seconds: None)

    live._activate(control)

    assert pattern.calls == 2

    with pytest.raises(PagesetError, match="TD Snap changed while the edit was running"):
        live._activate(None)


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


def test_live_add_button_requires_requested_spoken_message_field(monkeypatch):
    state = {"clicked": False, "undone": False}
    group = object()
    textbox = SimpleNamespace(
        ControlTypeName="EditControl", AutomationId="TextBox", IsEnabled=True
    )

    class Auto:
        def Click(self, _x, _y, waitTime):
            state["clicked"] = waitTime

    def find(_root, **criteria):
        if criteria.get("automation_id") == "MessageBox":
            return None
        return object()

    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint", lambda _group: (state["clicked"],))
    monkeypatch.setattr(live, "_physical_point", lambda *_args: (10, 20))
    monkeypatch.setattr(live, "_set_value", lambda *_args: None)
    monkeypatch.setattr(live, "_walk", lambda *_args: [(textbox, 10)])
    monkeypatch.setattr(live, "_find", find)
    monkeypatch.setattr(live, "_expand_editor", lambda _window: None)
    monkeypatch.setattr(
        live, "_undo_if_needed", lambda _window: state.update(undone=True)
    )

    with pytest.raises(PagesetError, match="spoken-message field"):
        live._add_button(
            Auto(), object(), live.Cell(50, 60, 40, 30), "hello", "speak this"
        )

    assert state["undone"] is True


def test_live_click_coordinates_scale_from_client_origin(monkeypatch):
    monkeypatch.setattr(live, "_client_origin", lambda _window: (1600, 80))
    monkeypatch.setattr(live, "_window_dpi", lambda _window: 120)

    assert live._physical_point(object(), 2000, 800) == (2100, 980)


def test_existing_page_remeasures_grid_in_edit_mode(monkeypatch):
    view_grid = live.Grid((10, 20), (30, 40), 8, 8)
    edit_grid = live.Grid((110, 120), (130, 140), 18, 18)
    grids = iter((view_grid, edit_grid, edit_grid))
    layouts = iter(([], [{"slot": 0, "label": "hello"}]))
    added = {}
    group = SimpleNamespace(GetChildren=lambda: [SimpleNamespace(Name="hello")])

    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ("baseline",))
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_grid", lambda _group: next(grids))
    monkeypatch.setattr(live, "_page_layout", lambda _group, _grid: next(layouts))
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_verify_page_state", lambda *_args, **_kwargs: None)
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


def test_existing_page_requires_review_fingerprint(monkeypatch):
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")

    with pytest.raises(PagesetError, match="review fingerprint is required"):
        live.add_to_existing_page("Eating", [{"label": "hello", "slot": 0}])


def test_existing_page_failure_restores_reviewed_baseline(monkeypatch):
    grid = live.Grid((10, 20), (30, 40), 8, 8)
    state = {"adds": 0, "restored": None, "exits": 0}
    group = SimpleNamespace(GetChildren=lambda: [])
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ("before",))
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    monkeypatch.setattr(live, "_page_layout", lambda *_args: [])
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(
        live, "_exit_edit_mode",
        lambda _window: state.update(exits=state["exits"] + 1),
    )

    def add(*_args):
        state["adds"] += 1
        if state["adds"] == 2:
            raise PagesetError("second add failed")
        return {"symbol": False, "border": True}

    monkeypatch.setattr(live, "_add_button", add)
    monkeypatch.setattr(
        live, "_restore_page_state",
        lambda _window, baseline, content, maximum: state.update(
            restored=(baseline, maximum)
        ),
    )

    with pytest.raises(PagesetError, match="original page was restored"):
        live.add_to_existing_page(
            "Eating",
            [
                {"label": "hello", "slot": 0, "symbol": False},
                {"label": "goodbye", "slot": 1, "symbol": False},
            ],
            "v1",
        )

    assert state["adds"] == 2
    assert state["restored"][0] == ("before",)
    assert state["exits"] == 1


def test_new_page_rejects_duplicate_title_before_editing(monkeypatch):
    group = SimpleNamespace(GetChildren=lambda: [])
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_navigate_to_parent", lambda *_args: "Topics")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_active_pageset_pages", lambda *_args: ["Snacks"])

    with pytest.raises(PagesetError, match="already exists"):
        live.add_topic_page("Snacks", [{"label": "Apple"}], "Topics")


def test_new_page_capacity_failure_rolls_back_provisional_page(monkeypatch):
    state = {"page": "Topics", "rollback": None}
    parent_group = SimpleNamespace(GetChildren=lambda: [])
    child_group = SimpleNamespace(GetChildren=lambda: [])
    grid = live.Grid((10,), (20,), 8, 8)
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_navigate_to_parent", lambda *_args: "Topics")
    monkeypatch.setattr(
        live, "_page_group",
        lambda _window: child_group if state["page"] == "Snacks" else parent_group,
    )
    monkeypatch.setattr(live, "_active_pageset_pages", lambda *_args: [])
    monkeypatch.setattr(live, "_find", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live, "_empty_cell", lambda *_args, **_kwargs: live.Cell(10, 20, 8, 8))
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    monkeypatch.setattr(
        live, "_fingerprint",
        lambda group: ("child",) if group is child_group else ("parent",),
    )
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)
    monkeypatch.setattr(
        live, "_create_page_link",
        lambda *_args: state.update(page="Snacks"),
    )
    monkeypatch.setattr(live, "_page_layout", lambda *_args: [])
    monkeypatch.setattr(
        live, "_rollback_new_page",
        lambda _auto, _window, parent, parent_baseline, page_baseline, maximum:
        state.update(
            rollback=(parent, parent_baseline, page_baseline, maximum)
        ),
    )

    with pytest.raises(PagesetError, match="provisional page and parent link were restored"):
        live.add_topic_page(
            "Snacks", [{"label": "Apple"}, {"label": "Pear"}], "Topics"
        )

    assert state["rollback"][:3] == ("Topics", ("parent",), ("child",))


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
        "apply_page_edits",
        lambda page, items, changes, removals, moves, fingerprint: {
            "page": page, "buttons": len(items), "changed": len(changes),
            "removed": len(removals), "moved": len(moves),
            "checks": {"td_snap_edit": "pass", "positions": "pass"},
            "warnings": [],
        },
    )
    monkeypatch.setattr(live, "last_edit", lambda: None)
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
    edited = client.post(
        "/api/tdsnap/edit-plan",
        json={
            "operation": "edit_page", "page": "Eating", "fingerprint": "abc",
            "items": [{"label": "Pizza", "slot": 1}],
            "changes": [{"slot": 0, "label": "Apples"}],
            "removals": [2],
            "moves": [{"slot": 3, "to": 5}],
        },
        headers={"X-TDSnap-Editor": "1"},
    ).get_json()
    assert edited["ok"] is True
    assert (edited["buttons"], edited["changed"], edited["removed"]) == (1, 1, 1)
    assert edited["moved"] == 1


def test_live_launches_td_snap_once(monkeypatch):
    opened = []
    monkeypatch.setattr(live.sys, "platform", "win32")
    monkeypatch.setattr(live, "status", lambda _include_pages=False: {"running": False})
    monkeypatch.setattr(live.os, "startfile", opened.append, raising=False)

    assert live.launch() == {"launched": True}
    assert opened == [live.TD_SNAP_APP]


# ---------------------------------------------------------------------------
# Changing and removing existing buttons
#
# The rules these pin are the ones that make a destructive edit safe to offer:
# only a plain speaking button is ever rewritten, prior content is captured
# before anything is touched, and a rollback is not believed until the content
# is back — not merely the shape.


def _pageset_with_page(tmp_path, monkeypatch, buttons, title="Eating"):
    """Build a minimal page set holding *buttons* on one vocabulary page.

    Each button is ``(label, message, command_flags, commands, links)``.
    """
    user = (tmp_path / "Packages" / "TobiiDynavox.Snap_test" /
            "LocalState" / "Users" / "user")
    user.mkdir(parents=True)
    with sqlite3.connect(user / "Settings.ssf") as conn:
        conn.execute("CREATE TABLE UserSettings (PageSetGuid TEXT)")
        conn.execute("INSERT INTO UserSettings VALUES ('active')")
    with sqlite3.connect(user / "active.sps") as conn:
        conn.execute("CREATE TABLE Page (Id INTEGER, Title TEXT, PageType INTEGER)")
        conn.execute("CREATE TABLE ElementReference (Id INTEGER, PageId INTEGER)")
        conn.execute(
            "CREATE TABLE Button (Id INTEGER, Label TEXT, Message TEXT, "
            "CommandFlags INTEGER, BorderColor INTEGER, LibrarySymbolId INTEGER, "
            "ElementReferenceId INTEGER)"
        )
        conn.execute("CREATE TABLE CommandSequence (SerializedCommands TEXT, ButtonId INTEGER)")
        conn.execute("CREATE TABLE ButtonPageLink (ButtonId INTEGER, PageUniqueId TEXT)")
        conn.execute("INSERT INTO Page VALUES (1, ?, 1)", (title,))
        conn.execute("INSERT INTO ElementReference VALUES (1, 1)")
        for index, spec in enumerate(buttons, start=1):
            label, message, flags, commands, links = spec[:5]
            border = spec[5] if len(spec) > 5 else None
            conn.execute(
                "INSERT INTO Button VALUES (?, ?, ?, ?, ?, ?, 1)",
                (index, label, message, flags, border, 0),
            )
            conn.execute("INSERT INTO CommandSequence VALUES (?, ?)", (commands, index))
            if links:
                conn.execute("INSERT INTO ButtonPageLink VALUES (?, 'other')", (index,))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


SPEAK = live.templates.SPEAK_COMMANDS
NAVIGATE = live.templates.navigate_commands("other")


def test_stored_content_separates_speaking_buttons_from_everything_else(
    tmp_path, monkeypatch
):
    _pageset_with_page(tmp_path, monkeypatch, [
        ("apple", "I want an apple", 8, SPEAK, 0, live.colors.argb_from_hex("#43A047")),
        ("Games", None, 9, NAVIGATE, 1),
        ("Clear", None, 8, '{"$type":"1","$values":[{"$type":"9"}]}', 0),
        ("Two things", None, 8,
         '{"$type":"1","$values":[{"$type":"3"},{"$type":"9"}]}', 0),
    ])

    content = live._stored_page_content("Eating")

    assert content["apple"]["kind"] == "speak"
    assert content["apple"]["message"] == "I want an apple"
    assert content["apple"]["function"] == "positive"
    # A page link and an action are indistinguishable from a speaking button in
    # the accessibility tree; only the stored command sequence tells them apart.
    assert content["games"]["kind"] == "navigate"
    assert content["clear"]["kind"] == "action"
    assert content["two things"]["kind"] == "action"


def test_a_label_used_twice_on_one_page_is_never_guessed_at(tmp_path, monkeypatch):
    _pageset_with_page(tmp_path, monkeypatch, [
        ("apple", "first", 8, SPEAK, 0),
        ("apple", "second", 8, SPEAK, 0),
        ("pear", None, 8, SPEAK, 0),
    ])

    content = live._stored_page_content("Eating")

    assert "apple" not in content
    assert content["pear"]["kind"] == "speak"


def test_stored_content_is_none_when_the_page_cannot_be_identified(tmp_path, monkeypatch):
    _pageset_with_page(tmp_path, monkeypatch, [("apple", None, 8, SPEAK, 0)])

    assert live._stored_page_content("Not A Page") is None
    assert live._stored_page_content("") is None


def test_inspect_page_says_which_buttons_can_be_edited_and_why_not(tmp_path, monkeypatch):
    _pageset_with_page(tmp_path, monkeypatch, [
        ("apple", "I want an apple", 8, SPEAK, 0),
        ("Games", None, 9, NAVIGATE, 1),
    ])
    grid = live.Grid((10, 20), (30,), 8, 8)
    group = SimpleNamespace(GetChildren=lambda: [], Name="Eating")
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_page_layout", lambda *_args: [
        {"slot": 0, "label": "apple"}, {"slot": 1, "label": "Games"},
    ])

    result = live.inspect_page()

    assert result["content_readable"] is True
    apple, games = result["buttons"]
    assert (apple["editable"], apple["message"]) == (True, "I want an apple")
    assert games["editable"] is False
    assert games["locked_reason"] == live.LOCK_REASONS["navigate"]


def test_inspect_page_locks_everything_when_content_cannot_be_read(monkeypatch):
    grid = live.Grid((10,), (30,), 8, 8)
    group = SimpleNamespace(GetChildren=lambda: [], Name="Eating")
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_page_layout", lambda *_args: [{"slot": 0, "label": "apple"}])
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): None)

    result = live.inspect_page()

    assert result["content_readable"] is False
    assert result["buttons"][0]["editable"] is False
    assert result["buttons"][0]["locked_reason"] == live.LOCK_REASONS["unreadable"]


def test_changes_and_removals_are_bounded_before_anything_runs():
    assert live._normalize_removals([2, 0, 2]) == [0, 2]
    with pytest.raises(PagesetError, match="non-negative cell number"):
        live._normalize_removals([-1])
    with pytest.raises(PagesetError, match="non-negative cell number"):
        live._normalize_removals([True])
    with pytest.raises(PagesetError, match="new label or a new spoken message"):
        live._normalize_changes([{"slot": 1}])
    with pytest.raises(PagesetError, match="changed twice"):
        live._normalize_changes([{"slot": 1, "label": "a"}, {"slot": 1, "label": "b"}])
    with pytest.raises(PagesetError, match="still needs a label"):
        live._normalize_changes([{"slot": 1, "label": "   "}])
    assert live._normalize_changes([{"slot": 1, "message": ""}]) == [
        {"slot": 1, "label": None, "message": ""}
    ]


def test_a_destructive_edit_is_refused_without_prior_content(monkeypatch):
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): None)

    with pytest.raises(PagesetError, match="couldn't read this page set's saved"):
        live._prior_content(
            "Eating", [{"slot": 0, "label": "x", "message": None}], [], [], {0: "apple"}
        )


def test_a_locked_button_is_named_and_refused_before_the_edit_starts(monkeypatch):
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): {
        "games": {"label": "Games", "message": None, "kind": "navigate"},
    })

    with pytest.raises(PagesetError, match=re.escape("'Games' can't be edited. This button opens")):
        live._prior_content("Eating", [], [0], [], {0: "Games"})


def test_a_button_that_moved_since_review_is_refused(monkeypatch):
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): {})

    with pytest.raises(PagesetError, match="no longer where they were"):
        live._prior_content("Eating", [], [7], [], {0: "apple"})


def _fake_control(name):
    return SimpleNamespace(Name=name, ControlTypeName="ButtonControl")


def test_rollback_keeps_undoing_while_a_message_is_still_wrong(monkeypatch):
    """The regression that content-aware rollback exists for.

    Rewriting a spoken message changes neither a button's name nor its
    position, so a fingerprint-only rollback matched its baseline immediately
    and reported the page restored while the message stayed rewritten.
    """
    state = {"undos": 0, "message": "the new message"}
    undo = SimpleNamespace(IsEnabled=True)
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_page_group", lambda _window: object())
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ("unchanged",))
    monkeypatch.setattr(live, "_find", lambda *_args, **_kwargs: undo)
    monkeypatch.setattr(live, "_named_slots", lambda _window: {0: _fake_control("apple")})
    monkeypatch.setattr(
        live, "_spoken_message", lambda _window, _control: (True, state["message"])
    )
    monkeypatch.setattr(live.time, "sleep", lambda _seconds: None)

    def press():
        state["undos"] += 1
        if state["undos"] == 3:
            state["message"] = "I want an apple"

    monkeypatch.setattr(live, "_activate", lambda _control: press())

    live._restore_page_state(
        object(), ("unchanged",), {0: {"label": "apple", "message": "I want an apple"}}, 8
    )

    assert state["undos"] == 3


def test_rollback_reports_failure_when_the_prior_content_never_comes_back(monkeypatch):
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_page_group", lambda _window: object())
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ("unchanged",))
    monkeypatch.setattr(live, "_find", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live, "_named_slots", lambda _window: {0: _fake_control("apple")})
    monkeypatch.setattr(live, "_spoken_message", lambda _window, _control: (True, "wrong"))

    with pytest.raises(PagesetError, match="could not verify restoration"):
        live._restore_page_state(
            object(), ("unchanged",), {0: {"label": "apple", "message": "right"}}, 2
        )


def test_verification_fails_when_a_button_the_edit_never_named_changed(monkeypatch):
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_open_button_editor", lambda *_args: None)
    monkeypatch.setattr(live, "_expand_editor", lambda _window: None)
    monkeypatch.setattr(live, "_activate", lambda _control: None)
    monkeypatch.setattr(live, "_filled_label_field", lambda _window, _label: None)
    monkeypatch.setattr(live, "_named_slots", lambda _window: {
        0: _fake_control("apple"), 1: _fake_control("banana"),
    })

    live._verify_page_state(object(), [], [], {0: "apple", 1: "banana"})
    with pytest.raises(PagesetError, match="which this edit was not meant to touch"):
        live._verify_page_state(object(), [], [], {0: "apple", 1: "pear"})


def test_verification_reads_label_when_accessibility_name_is_message(monkeypatch):
    control = _fake_control("I want to talk about Freida McFadden.")
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_open_button_editor", lambda *_args: None)
    monkeypatch.setattr(live, "_expand_editor", lambda _window: None)
    monkeypatch.setattr(live, "_activate", lambda _control: None)
    monkeypatch.setattr(live, "_named_slots", lambda _window: {0: control})
    monkeypatch.setattr(live, "_filled_label_field", lambda _window, label:
                        object() if label == "Freida McFadden" else None)
    monkeypatch.setattr(live, "_spoken_message", lambda *_args: (True, control.Name))
    live._verify_page_state(object(), [{
        "slot": 0, "label": "Freida McFadden", "message": control.Name,
    }])
    with pytest.raises(PagesetError, match="reviewed cell"):
        live._verify_page_state(object(), [{
            "slot": 0, "label": "Wrong label", "message": control.Name,
        }])


def test_reading_selected_button_reselects_after_click_toggles_it_off(monkeypatch):
    state = {"selected": True, "clicks": 0}
    control = SimpleNamespace(BoundingRectangle=SimpleNamespace(
        left=0, top=0, right=100, bottom=100,
    ))
    field = SimpleNamespace(ControlTypeName="EditControl", AutomationId="TextBox",
                            IsEnabled=True)

    def click(*_args, **_kwargs):
        state["selected"] = not state["selected"]
        state["clicks"] += 1

    monkeypatch.setattr(live, "_automation", lambda: SimpleNamespace(Click=click))
    monkeypatch.setattr(live, "_physical_point", lambda _window, x, y: (x, y))
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_expand_editor", lambda _window: None)
    monkeypatch.setattr(live, "_walk", lambda *_args:
                        [(field, 10)] if state["selected"] else [])
    live._open_button_editor(object(), control)
    assert state == {"selected": True, "clicks": 2}


def test_preview_resolves_spoken_name_to_saved_label(monkeypatch):
    control = _fake_control("I want to talk about Freida McFadden.")
    control.BoundingRectangle = SimpleNamespace(left=0, top=0, right=100, bottom=100)
    group = SimpleNamespace(Name="Books", GetChildren=lambda: [control])
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): {
        "freida mcfadden": {"label": "Freida McFadden", "message": control.Name},
    })
    assert live._page_layout(group, live.Grid((50,), (50,), 100, 100)) == [
        {"slot": 0, "label": "Freida McFadden"},
    ]


def test_verification_fails_when_a_removed_button_is_still_there(monkeypatch):
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_named_slots", lambda _window: {0: _fake_control("apple")})

    with pytest.raises(PagesetError, match="did not verify the removal of 'apple'"):
        live._verify_page_state(object(), [], [0], {})


def test_a_removal_stops_when_td_snap_exposes_no_delete_action(monkeypatch):
    monkeypatch.setattr(live, "_select_button", lambda *_args: object())
    monkeypatch.setattr(live, "_expand_editor", lambda _window: None)
    monkeypatch.setattr(live, "_delete_action", lambda _window: None)

    with pytest.raises(PagesetError, match="did not expose a way to delete 'apple'"):
        live._remove_button(object(), object(), live.Cell(1, 2, 3, 4), "apple")


def test_the_delete_action_is_found_by_id_or_by_name():
    def control(name="", automation_id="", control_type="ButtonControl"):
        return SimpleNamespace(
            Name=name, AutomationId=automation_id, ControlTypeName=control_type,
            IsEnabled=True, GetChildren=lambda: [],
            BoundingRectangle=SimpleNamespace(left=0, top=0, right=40, bottom=20),
        )

    by_id = control(automation_id="DeleteButton")
    window = control()
    window.GetChildren = lambda: [control(name="Cancel"), by_id]
    assert live._delete_action(window) is by_id

    named = control(name="Delete Button")
    window.GetChildren = lambda: [control(name="Cancel"), named]
    assert live._delete_action(window) is named

    window.GetChildren = lambda: [control(name="Cancel")]
    assert live._delete_action(window) is None


def test_the_editor_must_already_hold_the_reviewed_label_before_it_is_rewritten():
    def field(value):
        return SimpleNamespace(
            ControlTypeName="EditControl", AutomationId="TextBox", IsEnabled=True,
            GetValuePattern=lambda value=value: SimpleNamespace(Value=value),
            GetChildren=lambda: [],
        )

    wanted = field("aple")
    window = SimpleNamespace(
        ControlTypeName="PaneControl", AutomationId="", IsEnabled=True,
        GetValuePattern=lambda: None,
        GetChildren=lambda: [field("something else"), wanted],
    )

    assert live._filled_label_field(window, "aple") is wanted
    assert live._filled_label_field(window, "pear") is None


def test_an_edit_removes_changes_and_adds_in_that_order(monkeypatch):
    grid = live.Grid((10, 20, 30), (40,), 8, 8)
    performed = []
    group = SimpleNamespace(GetChildren=lambda: [])
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ("before",))
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    # The layout as reviewed, then as it stands once the edit has run.
    layouts = iter((
        [{"slot": 0, "label": "aple"}, {"slot": 1, "label": "old"}],
        [{"slot": 0, "label": "apple"}, {"slot": 2, "label": "pear"}],
    ))
    monkeypatch.setattr(live, "_page_layout", lambda *_args: next(layouts))
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): {
        "aple": {"label": "aple", "message": "I want an aple", "kind": "speak"},
        "old": {"label": "old", "message": None, "kind": "speak"},
    })
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)
    monkeypatch.setattr(
        live, "_remove_button",
        lambda _auto, _window, _cell, label, _message=None: performed.append(
            ("remove", label)
        ),
    )
    monkeypatch.setattr(
        live, "_change_button",
        lambda _auto, _window, _cell, current, label, message: performed.append(
            ("change", current, label, message)
        ),
    )
    monkeypatch.setattr(
        live, "_add_button",
        lambda _auto, _window, _cell, label, *_args: performed.append(("add", label)) or {
            "symbol": False, "border": True,
        },
    )
    verified = {}
    monkeypatch.setattr(
        live, "_verify_page_state",
        lambda _window, expected, removed, untouched: verified.update(
            expected=expected, removed=removed, untouched=untouched
        ),
    )

    report = live.apply_page_edits(
        "Eating",
        [{"label": "pear", "slot": 2, "symbol": False}],
        [{"slot": 0, "label": "apple", "message": "I want an apple"}],
        [1],
        [],
        "v1",
    )

    assert performed == [
        ("remove", "old"),
        ("change", "aple", "apple", "I want an apple"),
        ("add", "pear"),
    ]
    assert (report["buttons"], report["changed"], report["removed"]) == (1, 1, 1)
    assert report["checks"]["changed_content"] == "pass"
    assert report["checks"]["removed_buttons"] == "pass"
    assert report["checks"]["untouched_buttons"] == "pass"
    assert verified["removed"] == [1]
    assert verified["untouched"] == {}
    assert {item["label"] for item in verified["expected"]} == {"pear", "apple"}


def test_an_edit_that_would_leave_two_buttons_sharing_a_label_is_refused(monkeypatch):
    grid = live.Grid((10, 20), (30,), 8, 8)
    group = SimpleNamespace(GetChildren=lambda: [])
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ("before",))
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    monkeypatch.setattr(live, "_page_layout", lambda *_args: [
        {"slot": 0, "label": "aple"}, {"slot": 1, "label": "pear"},
    ])
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): {
        "aple": {"label": "aple", "message": None, "kind": "speak"},
        "pear": {"label": "pear", "message": None, "kind": "speak"},
    })

    with pytest.raises(PagesetError, match="end up with the same label: pear"):
        live.apply_page_edits("Eating", [], [{"slot": 0, "label": "pear"}], [], [], "v1")


def test_a_removed_cell_frees_its_space_for_a_new_button(monkeypatch):
    grid = live.Grid((10, 20), (30,), 8, 8)
    group = SimpleNamespace(GetChildren=lambda: [])
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ("before",))
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    layouts = iter((
        [{"slot": 0, "label": "aple"}],
        [{"slot": 0, "label": "apple"}],
    ))
    monkeypatch.setattr(live, "_page_layout", lambda *_args: next(layouts))
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): {
        "aple": {"label": "aple", "message": None, "kind": "speak"},
    })
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_remove_button", lambda *_args: None)
    monkeypatch.setattr(live, "_verify_page_state", lambda *_args, **_kwargs: None)
    added = {}
    monkeypatch.setattr(
        live, "_add_button",
        lambda _auto, _window, cell, label, *_args: added.update(cell=cell, label=label) or {
            "symbol": False, "border": True,
        },
    )

    report = live.apply_page_edits(
        "Eating", [{"label": "apple", "slot": 0, "symbol": False}], [], [0], [], "v1"
    )

    assert added["label"] == "apple"
    assert (report["buttons"], report["removed"]) == (1, 1)


def test_a_failed_change_restores_the_content_it_captured(monkeypatch):
    grid = live.Grid((10, 20), (30,), 8, 8)
    restored = {}
    mode = {"editing": False}
    group = SimpleNamespace(GetChildren=lambda: [])
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: object())
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint", lambda _group:
                        ("edit geometry",) if mode["editing"] else ("browse geometry",))
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: "v1")
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    monkeypatch.setattr(live, "_page_layout", lambda *_args: [{"slot": 0, "label": "aple"}])
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): {
        "aple": {"label": "aple", "message": "I want an aple", "kind": "speak"},
    })
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: mode.update(editing=True))
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)

    def fail(*_args):
        raise PagesetError("TD Snap did not save the new label 'apple'.")

    monkeypatch.setattr(live, "_change_button", fail)
    monkeypatch.setattr(
        live, "_restore_page_state",
        lambda _window, baseline, content, maximum: restored.update(
            baseline=baseline, content=content
        ),
    )

    with pytest.raises(PagesetError, match="original page was restored"):
        live.apply_page_edits("Eating", [], [{"slot": 0, "label": "apple"}], [], [], "v1")

    assert restored["baseline"] == ("edit geometry",)
    assert restored["content"] == {0: {"label": "aple", "message": "I want an aple"}}


def test_clearing_a_spoken_message_is_verified_like_any_other_change(monkeypatch):
    """"" is a request ("speak the label again"), not an absent one."""
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_named_slots", lambda _window: {0: _fake_control("apple")})
    monkeypatch.setattr(
        live, "_spoken_message", lambda _window, _control: (True, "still speaking this")
    )

    with pytest.raises(PagesetError, match="did not verify the spoken message"):
        live._verify_page_state(object(), [{"slot": 0, "label": "apple", "message": ""}])

    monkeypatch.setattr(live, "_spoken_message", lambda _window, _control: (True, ""))
    live._verify_page_state(object(), [{"slot": 0, "label": "apple", "message": ""}])
    # A button nobody asked about is never selected just to read its message.
    monkeypatch.setattr(
        live, "_spoken_message",
        lambda *_args: pytest.fail("an unrequested message must not be read"),
    )
    live._verify_page_state(object(), [{"slot": 0, "label": "apple", "message": None}])


# ---------------------------------------------------------------------------
# Phase 4c: moving and swapping existing buttons


def test_moves_are_bounded_and_shaped_before_anything_runs():
    with pytest.raises(PagesetError, match="non-negative cell number"):
        live._normalize_moves([{"slot": 0, "to": -1}])
    with pytest.raises(PagesetError, match="different cell to move to"):
        live._normalize_moves([{"slot": 2, "to": 2}])
    with pytest.raises(PagesetError, match="cannot be moved twice"):
        live._normalize_moves([{"slot": 0, "to": 1}, {"slot": 0, "to": 2}])
    with pytest.raises(PagesetError, match="into the same cell"):
        live._normalize_moves([{"slot": 0, "to": 3}, {"slot": 1, "to": 3}])
    # Two buttons pointing at each other is a swap, not a collision.
    assert live._normalize_moves([{"slot": 1, "to": 0}, {"slot": 0, "to": 1}]) == [
        {"slot": 0, "to": 1}, {"slot": 1, "to": 0},
    ]


def test_a_move_into_an_empty_cell_is_a_single_drag():
    plan = [{"slot": 0, "to": 5, "label": "apple"}]
    assert live._move_order(plan, {0, 1}, 12) == [(0, 5, "apple")]


def test_two_buttons_trading_places_go_through_a_spare_cell():
    """Never a drop onto an occupied cell — see the comment above _move_order."""
    plan = [
        {"slot": 0, "to": 1, "label": "apple"},
        {"slot": 1, "to": 0, "label": "pear"},
    ]

    steps = live._move_order(plan, {0, 1}, 4)

    assert steps == [(0, 2, "apple"), (1, 0, "pear"), (2, 1, "apple")]
    # Every drag lands somewhere that is empty at the moment it runs.
    filled = {0, 1}
    for source, target, _label in steps:
        assert target not in filled
        filled.discard(source)
        filled.add(target)
    assert filled == {0, 1}


def test_a_ring_of_moves_is_broken_by_parking_one_button():
    plan = [
        {"slot": 0, "to": 1, "label": "a"},
        {"slot": 1, "to": 2, "label": "b"},
        {"slot": 2, "to": 0, "label": "c"},
    ]

    steps = live._move_order(plan, {0, 1, 2}, 5)

    assert steps[0] == (0, 3, "a")
    assert steps[-1] == (3, 1, "a")
    assert sorted(steps) == sorted([(0, 3, "a"), (1, 2, "b"), (2, 0, "c"), (3, 1, "a")])


def test_a_chain_of_moves_needs_no_spare_cell():
    plan = [
        {"slot": 0, "to": 1, "label": "a"},
        {"slot": 1, "to": 2, "label": "b"},
    ]

    # "b" leaves cell 1 before "a" arrives, so a full page still works.
    assert live._move_order(plan, {0, 1}, 3) == [(1, 2, "b"), (0, 1, "a")]


def test_a_swap_on_a_full_page_is_refused_by_name():
    plan = [
        {"slot": 0, "to": 1, "label": "apple"},
        {"slot": 1, "to": 0, "label": "pear"},
    ]

    with pytest.raises(PagesetError, match="no empty cell to move a button through"):
        live._move_order(plan, {0, 1}, 2)


def test_a_move_is_verified_against_both_cells(monkeypatch):
    grid = live.Grid((10, 20), (30,), 8, 8)
    dragged = []
    auto = SimpleNamespace(
        DragDrop=lambda *args, **kwargs: dragged.append(args),
    )
    monkeypatch.setattr(live, "_physical_point", lambda _window, x, y: (x, y))
    slots = iter((
        {0: _fake_control("apple")},          # still in the cell it started in
        {1: _fake_control("apple")},          # arrived, and the old cell is empty
    ))
    monkeypatch.setattr(live, "_named_slots", lambda _window: next(slots))

    live._move_button(auto, object(), grid, 0, 1, "apple")

    assert dragged == [(10, 30, 20, 30)]


def test_a_move_that_td_snap_never_performs_is_reported(monkeypatch):
    grid = live.Grid((10, 20), (30,), 8, 8)
    auto = SimpleNamespace(DragDrop=lambda *args, **kwargs: None)
    monkeypatch.setattr(live, "_physical_point", lambda _window, x, y: (x, y))
    monkeypatch.setattr(live, "_named_slots", lambda _window: {0: _fake_control("apple")})
    monkeypatch.setattr(live, "_wait_for", _immediate_wait_for)

    with pytest.raises(PagesetError, match="did not move the 'apple' button"):
        live._move_button(auto, object(), grid, 0, 1, "apple")

    # An installation whose automation layer cannot drag says so instead of
    # silently leaving the button where it was.
    with pytest.raises(PagesetError, match="did not expose a way to move 'apple'"):
        live._move_button(SimpleNamespace(), object(), grid, 0, 1, "apple")


def _immediate_wait_for(callback, message, timeout=8, ignore=()):
    """A _wait_for that gives up at once, so a failure test doesn't sleep."""
    value = callback()
    if value:
        return value
    raise PagesetError(message)


def _stub_live_page(monkeypatch, *, layouts, content, grid=None, fingerprint="v1"):
    """Wire up a fake TD Snap page so apply_page_edits can run off-Windows.

    *layouts* is consumed once per read: the page as reviewed, then the page as
    it stands after the edit. *fingerprint* is the token the page reports — one
    string for both reads, or a pair to model the page's token changing as the
    edit lands, which is what an undo is later guarded against.
    """
    grid = grid or live.Grid((10, 20, 30, 40), (50, 60), 8, 8)
    group = SimpleNamespace(GetChildren=lambda: [])
    tokens = iter(
        fingerprint if isinstance(fingerprint, (list, tuple)) else [fingerprint] * 4
    )
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: SimpleNamespace(
        DragDrop=lambda *args, **kwargs: None,
    ))
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda *_args: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ("before",))
    monkeypatch.setattr(live, "_fingerprint_token", lambda _group: next(tokens))
    monkeypatch.setattr(live, "_grid", lambda _group: grid)
    reads = iter(layouts)
    monkeypatch.setattr(live, "_page_layout", lambda *_args: next(reads))
    monkeypatch.setattr(live, "_stored_page_content", lambda _page, _names=(): content)
    monkeypatch.setattr(live, "_enter_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_collapse_editor", lambda _window: None)
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_verify_page_state", lambda *_args, **_kwargs: None)
    return grid


def test_an_edit_removes_moves_changes_and_adds_in_that_order(monkeypatch):
    performed = []
    _stub_live_page(
        monkeypatch,
        layouts=[
            [{"slot": 0, "label": "aple"}, {"slot": 1, "label": "old"},
             {"slot": 2, "label": "pear"}],
            [{"slot": 0, "label": "apple"}, {"slot": 3, "label": "pear"},
             {"slot": 1, "label": "plum"}],
        ],
        content={
            "aple": {"label": "aple", "message": "I want an aple", "kind": "speak"},
            "old": {"label": "old", "message": None, "kind": "speak"},
            "pear": {"label": "pear", "message": None, "kind": "speak"},
        },
    )
    monkeypatch.setattr(
        live, "_remove_button",
        lambda _auto, _window, _cell, label, _message=None: performed.append(
            ("remove", label)
        ),
    )
    monkeypatch.setattr(
        live, "_move_button",
        lambda _auto, _window, _grid, source, target, label: performed.append(
            ("move", label, source, target)
        ),
    )
    monkeypatch.setattr(
        live, "_change_button",
        lambda _auto, _window, _cell, current, label, message: performed.append(
            ("change", current, label, message)
        ),
    )
    monkeypatch.setattr(
        live, "_add_button",
        lambda _auto, _window, _cell, label, *_args: performed.append(("add", label)) or {
            "symbol": False, "symbol_source": None, "border": True,
        },
    )

    report = live.apply_page_edits(
        "Eating",
        [{"label": "plum", "slot": 1, "symbol": False}],
        [{"slot": 0, "label": "apple", "message": "I want an apple"}],
        [1],
        [{"slot": 2, "to": 3}],
        "v1",
    )

    # Removals free cells first, then moves run while every label is still the
    # one the review named, then changes, then additions — and "plum" lands in
    # the cell "old" just left.
    assert performed == [
        ("remove", "old"),
        ("move", "pear", 2, 3),
        ("change", "aple", "apple", "I want an apple"),
        ("add", "plum"),
    ]
    assert (report["changed"], report["moved"], report["buttons"]) == (1, 1, 1)
    assert report["removed"] == 1
    assert report["checks"]["moved_buttons"] == "pass"
    assert report["checks"]["untouched_buttons"] == "pass"


def test_a_change_to_a_moving_button_is_made_in_the_cell_it_lands_in(monkeypatch):
    changed = {}
    grid = _stub_live_page(
        monkeypatch,
        layouts=[
            [{"slot": 0, "label": "aple"}],
            [{"slot": 3, "label": "apple"}],
        ],
        content={"aple": {"label": "aple", "message": None, "kind": "speak"}},
    )
    monkeypatch.setattr(live, "_move_button", lambda *_args: None)
    monkeypatch.setattr(
        live, "_change_button",
        lambda _auto, _window, cell, current, label, message: changed.update(
            cell=cell, current=current, label=label
        ),
    )
    verified = {}
    monkeypatch.setattr(
        live, "_verify_page_state",
        lambda _window, expected, removed, untouched: verified.update(
            expected=expected, removed=removed
        ),
    )

    live.apply_page_edits(
        "Eating", [], [{"slot": 0, "label": "apple"}], [], [{"slot": 0, "to": 3}], "v1"
    )

    assert changed["cell"] == live._cell_at(grid, 3)
    assert changed["current"] == "aple"
    # Named once, in its destination, with its new label — not twice.
    assert verified["expected"] == [{"slot": 3, "label": "apple", "message": None}]
    assert verified["removed"] == [0]


def test_a_move_onto_a_button_that_is_staying_is_refused_by_name(monkeypatch):
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "apple"}, {"slot": 1, "label": "pear"}]],
        content={
            "apple": {"label": "apple", "message": None, "kind": "speak"},
            "pear": {"label": "pear", "message": None, "kind": "speak"},
        },
    )

    with pytest.raises(PagesetError, match=r"in the way of a move.*pear"):
        live.apply_page_edits("Eating", [], [], [], [{"slot": 0, "to": 1}], "v1")


def test_a_button_cannot_be_moved_and_removed_at_once(monkeypatch):
    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)

    with pytest.raises(PagesetError, match="moved and removed in the same edit"):
        live.apply_page_edits("Eating", [], [], [1], [{"slot": 1, "to": 2}], "v1")


def test_a_moved_button_must_be_editable_like_any_other(monkeypatch):
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "Games"}]],
        content={"games": {"label": "Games", "message": None, "kind": "navigate"}},
    )

    with pytest.raises(PagesetError, match="'Games' can't be edited"):
        live.apply_page_edits("Eating", [], [], [], [{"slot": 0, "to": 1}], "v1")


def test_a_failed_move_restores_the_content_it_captured(monkeypatch):
    restored = {}
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "apple"}]],
        content={"apple": {"label": "apple", "message": "I want one", "kind": "speak"}},
    )

    def fail(*_args):
        raise PagesetError("TD Snap did not move the 'apple' button to the cell you chose.")

    monkeypatch.setattr(live, "_move_button", fail)
    monkeypatch.setattr(
        live, "_restore_page_state",
        lambda _window, baseline, content, maximum: restored.update(
            baseline=baseline, content=content
        ),
    )

    with pytest.raises(PagesetError, match="original page was restored"):
        live.apply_page_edits("Eating", [], [], [], [{"slot": 0, "to": 1}], "v1")

    assert restored["content"] == {0: {"label": "apple", "message": "I want one"}}


# ---------------------------------------------------------------------------
# Phase 4b: undo my last change


@pytest.fixture(autouse=True)
def _forget_retained_edit():
    """No test inherits another's undo snapshot (it is module state by design)."""
    live.forget_last_edit()
    yield
    live.forget_last_edit()


def _applied(monkeypatch, items=None, changes=None, removals=None, moves=None, *,
             layouts, content):
    """Run one successful edit and hand back what an undo of it would do."""
    items, changes = items or [], changes or []
    removals, moves = removals or [], moves or []
    _stub_live_page(monkeypatch, layouts=layouts, content=content)
    monkeypatch.setattr(live, "_remove_button", lambda *_args: None)
    monkeypatch.setattr(live, "_move_button", lambda *_args: None)
    monkeypatch.setattr(live, "_change_button", lambda *_args: None)
    monkeypatch.setattr(live, "_add_button", lambda *_args: {
        "symbol": True, "symbol_source": "library", "border": True,
    })
    report = live.apply_page_edits("Eating", items, changes, removals, moves, "v1")
    return report, live.last_edit()


def test_nothing_is_offered_to_undo_before_an_edit_has_run():
    assert live.last_edit() is None
    with pytest.raises(PagesetError, match="no change left to undo"):
        live.undo_last_edit()


def test_an_applied_edit_is_described_the_way_the_review_screen_reads_it(monkeypatch):
    _report, undo = _applied(
        monkeypatch,
        items=[{"label": "plum", "slot": 3}],
        changes=[{"slot": 0, "label": "apple", "message": "I want an apple"}],
        removals=[1],
        moves=[{"slot": 2, "to": 4}],
        layouts=[
            [{"slot": 0, "label": "aple"}, {"slot": 1, "label": "old"},
             {"slot": 2, "label": "pear"}],
            [{"slot": 0, "label": "apple"}, {"slot": 4, "label": "pear"},
             {"slot": 3, "label": "plum"}],
        ],
        content={
            "aple": {"label": "aple", "message": "I want an aple", "kind": "speak"},
            "old": {"label": "old", "message": "the old one", "kind": "speak",
                    "border_color": None, "symbol": False},
            "pear": {"label": "pear", "message": None, "kind": "speak"},
        },
    )

    assert undo["page"] == "Eating"
    # Undo puts back what was removed, takes away what was added, restores the
    # text that was changed, and sends the moved button home.
    assert undo["restores"]["adds"] == [{"label": "old", "message": "the old one"}]
    assert undo["restores"]["removals"] == [{"label": "plum", "message": None}]
    assert undo["restores"]["changes"] == [{
        "label": "aple", "message": "I want an aple",
        "from": {"label": "apple", "message": "I want an apple"},
    }]
    assert undo["restores"]["moves"] == [{"label": "pear", "slot": 4, "to": 2}]


def test_undoing_replays_the_reverse_edit_against_the_page_it_left_behind(monkeypatch):
    _stub_live_page(
        monkeypatch,
        layouts=[
            [{"slot": 0, "label": "aple"}],
            [{"slot": 0, "label": "apple"}],
        ],
        content={"aple": {"label": "aple", "message": "I want an aple", "kind": "speak"}},
        # The page's token as the edit found it, then as the edit left it.
        fingerprint=["before-edit", "after-edit"],
    )
    monkeypatch.setattr(live, "_change_button", lambda *_args: None)
    live.apply_page_edits(
        "Eating", [], [{"slot": 0, "label": "apple", "message": "I want an apple"}],
        [], [], "before-edit",
    )

    # The page as the edit left it, and the token it now carries.
    replayed = {}
    _stub_live_page(
        monkeypatch,
        layouts=[
            [{"slot": 0, "label": "apple"}],
            [{"slot": 0, "label": "aple"}],
        ],
        # TD Snap has not written the edit back to the page-set file yet, which
        # is exactly the state the retained snapshot exists to cover.
        content={},
        fingerprint="after-edit",
    )
    monkeypatch.setattr(
        live, "_change_button",
        lambda _auto, _window, _cell, current, label, message: replayed.update(
            current=current, label=label, message=message
        ),
    )

    report = live.undo_last_edit()

    assert replayed == {"current": "apple", "label": "aple", "message": "I want an aple"}
    assert report["undone"] is True
    assert report["checks"]["undone"] == "pass"
    # Single level: undoing is not itself undoable.
    assert live.last_edit() is None


def test_an_undo_is_refused_once_anything_else_touches_the_page(monkeypatch):
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "aple"}], [{"slot": 0, "label": "apple"}]],
        content={"aple": {"label": "aple", "message": None, "kind": "speak"}},
        fingerprint=["v1", "v2"],
    )
    monkeypatch.setattr(live, "_change_button", lambda *_args: None)
    live.apply_page_edits("Eating", [], [{"slot": 0, "label": "apple"}], [], [], "v1")

    # A sync, or somebody editing in TD Snap, moves the page on. The retained
    # snapshot is then refused by the ordinary fingerprint guard.
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "apple"}]],
        content={"apple": {"label": "apple", "message": None, "kind": "speak"}},
        fingerprint="somebody-else-edited",
    )

    with pytest.raises(PagesetError, match="target page changed after preview"):
        live.undo_last_edit()
    # Still offered: nothing was written, so a refreshed page can still undo.
    assert live.last_edit() is not None


def test_undo_says_up_front_what_it_cannot_bring_back(monkeypatch):
    """A re-created button is a new button — its symbol and any unusual border
    come back on a best-effort basis, and the review says so."""
    _report, undo = _applied(
        monkeypatch,
        removals=[0],
        layouts=[[{"slot": 0, "label": "old"}], []],
        content={"old": {
            "label": "old", "message": None, "kind": "speak",
            # A border TD Snap wrote that is not one of the five clinical colors.
            "border_color": live.colors.argb_from_hex("#123456"), "symbol": True,
        }},
    )
    assert undo["restores"]["adds"] == [{"label": "old", "message": None}]

    warnings = " ".join(undo["warnings"])
    assert "border color AAC Editor doesn't write" in warnings
    assert "fresh TD Snap symbol search" in warnings


def test_a_failed_edit_leaves_the_earlier_undo_intact(monkeypatch):
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "aple"}], [{"slot": 0, "label": "apple"}]],
        content={"aple": {"label": "aple", "message": None, "kind": "speak"}},
    )
    monkeypatch.setattr(live, "_change_button", lambda *_args: None)
    live.apply_page_edits("Eating", [], [{"slot": 0, "label": "apple"}], [], [], "v1")
    first = live.last_edit()

    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "apple"}]],
        content={"apple": {"label": "apple", "message": None, "kind": "speak"}},
    )

    def fail(*_args):
        raise PagesetError("TD Snap did not save the new label 'apples'.")

    monkeypatch.setattr(live, "_change_button", fail)
    monkeypatch.setattr(live, "_restore_page_state", lambda *_args: None)

    with pytest.raises(PagesetError, match="original page was restored"):
        live.apply_page_edits("Eating", [], [{"slot": 0, "label": "apples"}], [], [], "v1")

    # The rolled-back edit changed nothing, so the change before it is still
    # the last one — and still undoable.
    assert live.last_edit() == first


def test_forgetting_the_retained_edit_stops_offering_it(monkeypatch):
    _applied(
        monkeypatch,
        removals=[0],
        layouts=[[{"slot": 0, "label": "old"}], []],
        content={"old": {"label": "old", "message": None, "kind": "speak"}},
    )
    assert live.last_edit() is not None

    live.forget_last_edit()

    assert live.last_edit() is None


# ---------------------------------------------------------------------------
# Phase 4c: symbol control


def test_a_button_can_carry_its_own_symbol_search_words(monkeypatch):
    searched = []
    monkeypatch.setattr(live, "_fingerprint", lambda _group: ())
    monkeypatch.setattr(live, "_page_group", lambda _window: object())
    monkeypatch.setattr(live, "_physical_point", lambda _window, x, y: (x, y))
    monkeypatch.setattr(live, "_empty_label_field", lambda _window: _fake_control(""))
    monkeypatch.setattr(live, "_set_value", lambda _control, _value: None)
    monkeypatch.setattr(live, "_wait_for", lambda callback, *_a, **_k: callback() or True)
    monkeypatch.setattr(live, "_expand_editor", lambda _window: None)
    monkeypatch.setattr(live, "_find", lambda *_args, **_kwargs: _fake_control("x"))
    monkeypatch.setattr(
        live, "_choose_symbol",
        lambda _window, query: searched.append(query) or "library",
    )
    auto = SimpleNamespace(Click=lambda *_args, **_kwargs: None)

    result = live._add_button(
        auto, object(), live.Cell(1, 2, 3, 4), "more please",
        use_symbol=True, symbol_query="more",
    )

    # The label is a phrase TD Snap would find nothing for; the search words are.
    assert searched == ["more"]
    assert (result["symbol"], result["symbol_source"]) == (True, "library")


def test_the_result_names_which_buttons_ended_up_without_a_symbol(monkeypatch):
    _stub_live_page(
        monkeypatch,
        layouts=[[], [
            {"slot": 0, "label": "apple"},
            {"slot": 1, "label": "more please"},
            {"slot": 2, "label": "thirsty"},
        ]],
        content={},
    )
    outcomes = iter((
        {"symbol": True, "symbol_source": "library", "border": True},
        {"symbol": False, "symbol_source": None, "border": True},
        {"symbol": True, "symbol_source": "web", "border": True},
    ))
    monkeypatch.setattr(live, "_add_button", lambda *_args: next(outcomes))

    report = live.apply_page_edits(
        "Eating",
        [
            {"label": "apple", "slot": 0},
            {"label": "more please", "slot": 1},
            {"label": "thirsty", "slot": 2},
        ],
        [], [], [], "v1",
    )

    assert report["checks"]["symbols"] == "partial"
    warnings = " ".join(report["warnings"])
    assert '"more please"' in warnings
    assert "It was added without one" in warnings
    assert '"thirsty"' in warnings and "web image" in warnings
    assert [entry["source"] for entry in report["symbols"]] == ["library", None, "web"]


def test_a_button_that_skips_the_symbol_is_not_counted_as_a_failure(monkeypatch):
    _stub_live_page(monkeypatch, layouts=[[], [{"slot": 0, "label": "apple"}]], content={})
    monkeypatch.setattr(live, "_add_button", lambda *_args: {
        "symbol": False, "symbol_source": None, "border": True,
    })

    report = live.apply_page_edits(
        "Eating", [{"label": "apple", "slot": 0, "symbol": False}], [], [], [], "v1"
    )

    assert report["checks"]["symbols"] == "pass"
    assert report["warnings"] == []


def test_named_lists_read_as_a_sentence():
    assert live._named_list(["apple"]) == '"apple"'
    assert live._named_list(["apple", "pear"]) == '"apple" and "pear"'
    assert live._named_list(["a", "b", "c"]) == '"a", "b" and "c"'


# ---------- multi-page batch ----------


def _batch_entry(page, label="apple"):
    return {"page": page, "items": [{"label": label, "slot": 0}], "fingerprint": "v1"}


def _fake_apply(monkeypatch, behaviour):
    """Replace the single-page write path so a batch's sequencing is what's tested.

    *behaviour* maps a page name to what that page does: a dict is returned as
    its report, an exception is raised.
    """
    seen = []

    def apply_one(page, items=(), changes=(), removals=(), moves=(), fingerprint=None):
        seen.append(page)
        outcome = behaviour[page]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(live, "apply_page_edits", apply_one)
    return seen


def _report(page, buttons=1):
    return {"page": page, "buttons": buttons, "changed": 0, "removed": 0, "moved": 0,
            "checks": {"td_snap_edit": "pass"}, "symbols": [], "warnings": []}


def test_a_batch_applies_each_page_in_the_order_it_was_queued(monkeypatch):
    seen = _fake_apply(monkeypatch, {
        "Eating": _report("Eating"),
        "Games": _report("Games"),
        "Swimming": _report("Swimming"),
    })

    result = live.apply_batch(
        [_batch_entry("Eating"), _batch_entry("Games"), _batch_entry("Swimming")]
    )

    assert seen == ["Eating", "Games", "Swimming"]
    assert [entry["status"] for entry in result["results"]] == ["applied"] * 3
    assert result["applied"] == 3
    # Single-level undo covers the last page applied, and says which one.
    assert result["undo_page"] == "Swimming"


def test_a_refused_page_does_not_strand_the_pages_queued_behind_it(monkeypatch):
    """A refusal wrote nothing, so the rest of the queue is still safe to run."""
    refusal = PagesetError("The target page changed after preview.")
    assert refusal.page_touched is False
    seen = _fake_apply(monkeypatch, {
        "Eating": _report("Eating"),
        "Games": refusal,
        "Swimming": _report("Swimming"),
    })

    result = live.apply_batch(
        [_batch_entry("Eating"), _batch_entry("Games"), _batch_entry("Swimming")]
    )

    assert seen == ["Eating", "Games", "Swimming"]
    assert [entry["status"] for entry in result["results"]] == [
        "applied", "refused", "applied",
    ]
    assert "changed after preview" in result["results"][1]["error"]
    assert result["applied"] == 2
    assert result["undo_page"] == "Swimming"


def test_a_page_that_was_edited_and_restored_stops_the_batch(monkeypatch):
    """Continuing would drive a different page while TD Snap is in a state the
    automation already failed to understand."""
    failure = PagesetError("TD Snap did not verify it. The original page was restored.")
    failure.page_touched = True
    seen = _fake_apply(monkeypatch, {
        "Eating": _report("Eating"),
        "Games": failure,
        "Swimming": _report("Swimming"),
    })

    result = live.apply_batch(
        [_batch_entry("Eating"), _batch_entry("Games"), _batch_entry("Swimming")]
    )

    # Swimming was never attempted, and says so rather than being left out.
    assert seen == ["Eating", "Games"]
    assert result["results"] == [
        {"page": "Eating", "status": "applied", "report": _report("Eating")},
        {"page": "Games", "status": "failed",
         "error": "TD Snap did not verify it. The original page was restored."},
        {"page": "Swimming", "status": "skipped"},
    ]
    assert result["applied"] == 1
    assert result["undo_page"] == "Eating"


def test_a_batch_that_fails_on_its_first_page_applied_nothing(monkeypatch):
    failure = PagesetError("The original page was restored.")
    failure.page_touched = True
    _fake_apply(monkeypatch, {"Eating": failure})

    result = live.apply_batch([_batch_entry("Eating"), _batch_entry("Games")])

    assert result["applied"] == 0
    assert result["undo_page"] is None
    assert [entry["status"] for entry in result["results"]] == ["failed", "skipped"]


def test_the_same_page_queued_twice_is_refused_before_anything_runs(monkeypatch):
    """The second entry's fingerprint predates the first one landing."""
    seen = _fake_apply(monkeypatch, {"Eating": _report("Eating")})

    with pytest.raises(PagesetError, match="queued more than once"):
        live.apply_batch([_batch_entry("Eating"), _batch_entry("eating", "pear")])

    assert seen == []


def test_an_empty_batch_is_refused(monkeypatch):
    with pytest.raises(PagesetError, match="Queue at least one page"):
        live.apply_batch([])


def test_a_batch_longer_than_the_cap_is_refused_before_anything_runs(monkeypatch):
    seen = _fake_apply(monkeypatch, {})

    with pytest.raises(PagesetError, match="No more than 10 pages"):
        live.apply_batch([_batch_entry(f"Page {index}") for index in range(11)])

    assert seen == []


def test_a_rollback_marks_the_error_as_having_touched_the_page(monkeypatch):
    """The marker `apply_batch` stops on is set by the real write path.

    Without this the batch's stop rule would rest on an assumption about
    `apply_page_edits` rather than on what it actually does.
    """
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "aple"}]],
        content={"aple": {"label": "aple", "message": None, "kind": "speak"}},
        grid=live.Grid((10, 20), (30,), 8, 8),
    )

    def fail(*_args):
        raise PagesetError("TD Snap did not save the new label.")

    monkeypatch.setattr(live, "_change_button", fail)
    monkeypatch.setattr(live, "_restore_page_state", lambda *_args: None)

    with pytest.raises(PagesetError) as caught:
        live.apply_page_edits("Eating", [], [{"slot": 0, "label": "apple"}], [], [], "v1")
    assert caught.value.page_touched is True


def test_a_refusal_before_any_writing_is_not_marked_as_touching_the_page(monkeypatch):
    """The other half: a stale fingerprint must not stop a whole batch."""
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "apple"}]],
        content={"apple": {"label": "apple", "message": None, "kind": "speak"}},
        grid=live.Grid((10, 20), (30,), 8, 8),
        fingerprint="moved-on",
    )

    with pytest.raises(PagesetError) as caught:
        live.apply_page_edits("Eating", [{"label": "pear", "slot": 1}], [], [], [], "v1")
    assert "changed after preview" in str(caught.value)
    assert caught.value.page_touched is False


# ---------------------------------------------------------------------------
# TD Snap names a button after its spoken message
#
# Every test below covers one place where a saved label was matched directly
# against a live accessibility name. TD Snap publishes a button's spoken
# message as that name whenever one is set, so each of these looked a button
# straight past itself — and did so silently, as a `None` indistinguishable
# from "that button is gone". Together they accounted for the bulk of failed
# live edits, because adding a word that speaks a phrase is the ordinary case,
# not the exotic one.


def _spoken_button(message, left=0, top=0):
    """A grid button TD Snap has named after its spoken message."""
    return SimpleNamespace(
        Name=message, ControlTypeName="ButtonControl", AutomationId="",
        IsEnabled=True, GetChildren=lambda: [],
        BoundingRectangle=SimpleNamespace(
            left=left, top=top, right=left + 80, bottom=top + 80,
        ),
    )


def test_a_grid_button_is_found_by_label_message_or_resolved_name():
    control = _spoken_button("I am all done now")
    group = SimpleNamespace(
        ControlTypeName="GroupControl", GetChildren=lambda: [control],
    )

    # The message the caller already knows about.
    assert live._grid_button(group, "all done", "I am all done now") is control
    # The same name resolved through the stored page set instead.
    assert live._grid_button(
        group, "all done", resolved={"i am all done now": "all done"}
    ) is control
    # Neither: the label alone still matches a button that speaks it.
    assert live._grid_button(group, "I am all done now") is control
    assert live._grid_button(group, "all done") is None
    assert live._grid_button(group, "") is None


def test_a_removal_answers_the_confirmation_for_a_button_that_speaks(monkeypatch):
    """The prompt used to be skipped, leaving TD Snap's dialog open.

    ``_confirm_removal`` asked "is the button still there?" by its label. For
    a button named after its message the answer was always "no", so it
    returned without answering — and the next step clicked into the dialog
    that was still on screen.
    """
    group = SimpleNamespace(
        ControlTypeName="GroupControl",
        GetChildren=lambda: [_spoken_button("I am all done now")],
    )
    confirm = SimpleNamespace(Name="Delete")
    answered = []
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_accessible_labels", lambda _group: {})
    monkeypatch.setattr(live, "_find", lambda *_args, **_kwargs: confirm)
    monkeypatch.setattr(live, "_activate", lambda control: answered.append(control))

    live._confirm_removal(object(), "all done", "I am all done now")
    assert answered == [confirm]

    # A button that really is gone still answers nothing.
    answered.clear()
    monkeypatch.setattr(
        live, "_page_group",
        lambda _window: SimpleNamespace(
            ControlTypeName="GroupControl", GetChildren=lambda: [],
        ),
    )
    live._confirm_removal(object(), "all done", "I am all done now")
    assert answered == []


def test_a_removal_waits_for_a_button_that_speaks_to_actually_go(monkeypatch):
    """The wait used to pass before the delete had happened at all."""
    present = [_spoken_button("I am all done now")]
    group = SimpleNamespace(
        ControlTypeName="GroupControl", GetChildren=lambda: list(present),
    )
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_accessible_labels", lambda _group: {})
    monkeypatch.setattr(live, "_select_button", lambda *_args: object())
    monkeypatch.setattr(live, "_expand_editor", lambda _window: None)
    monkeypatch.setattr(live, "_delete_action", lambda _window: SimpleNamespace())
    monkeypatch.setattr(live, "_activate", lambda _control: None)
    monkeypatch.setattr(live, "_confirm_removal", lambda *_args: None)
    monkeypatch.setattr(live, "_wait_for", lambda callback, message, **_kw: (
        callback() or pytest.fail(f"waited past a button still on the page: {message}")
    ))

    with pytest.raises(Failed):
        live._remove_button(
            object(), object(), live.Cell(1, 2, 3, 4),
            "all done", "I am all done now",
        )

    present.clear()
    live._remove_button(
        object(), object(), live.Cell(1, 2, 3, 4), "all done", "I am all done now",
    )


def test_a_removal_hands_the_prior_message_down_to_the_delete(monkeypatch):
    """apply_page_edits knows the message; the delete has to be told."""
    removed = []
    _stub_live_page(
        monkeypatch,
        layouts=[[{"slot": 0, "label": "all done"}], []],
        content={"all done": {
            "label": "all done", "message": "I am all done now", "kind": "speak",
        }},
        grid=live.Grid((10, 20), (30,), 8, 8),
    )
    monkeypatch.setattr(
        live, "_remove_button",
        lambda _auto, _window, _cell, label, message=None: removed.append(
            (label, message)
        ),
    )

    live.apply_page_edits("Eating", [], [], [0], [], "v1")
    assert removed == [("all done", "I am all done now")]


def test_an_added_button_that_speaks_a_phrase_is_not_rolled_back(monkeypatch):
    """The single largest source of failed live edits.

    After leaving edit mode the page is re-read by name. A button that was
    just given a spoken message is named after it, and the page set on disk
    has not caught up yet — so the name could not be resolved back to the
    label, every such addition was reported missing, and the edit the user
    had just reviewed was rolled back under them.
    """
    rolled_back = []
    _stub_live_page(
        monkeypatch,
        layouts=[[], [{"slot": 0, "label": "I would like some more, please"}]],
        content={},
        grid=live.Grid((10, 20), (30,), 8, 8),
    )
    monkeypatch.setattr(
        live, "_add_button",
        lambda *_args, **_kwargs: {"symbol": False, "border": True},
    )
    monkeypatch.setattr(live, "_record_last_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        live, "_restore_page_state",
        lambda *_args, **_kwargs: rolled_back.append(True),
    )

    report = live.apply_page_edits(
        "Eating",
        [{"label": "more", "message": "I would like some more, please",
          "slot": 0, "symbol": False}],
        [], [], [], "v1",
    )

    assert rolled_back == []
    assert report["buttons"] == 1
    assert report["checks"]["td_snap_edit"] == "pass"


def test_a_moved_button_keeps_speaking_and_still_verifies(monkeypatch):
    """A move sets no message, but the button carries the one it had."""
    rolled_back = []
    _stub_live_page(
        monkeypatch,
        layouts=[
            [{"slot": 0, "label": "all done"}],
            [{"slot": 1, "label": "I am all done now"}],
        ],
        content={"all done": {
            "label": "all done", "message": "I am all done now", "kind": "speak",
        }},
        grid=live.Grid((10, 20), (30,), 8, 8),
    )
    monkeypatch.setattr(live, "_move_button", lambda *_args: None)
    monkeypatch.setattr(live, "_record_last_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        live, "_restore_page_state",
        lambda *_args, **_kwargs: rolled_back.append(True),
    )

    report = live.apply_page_edits("Eating", [], [], [], [{"slot": 0, "to": 1}], "v1")
    assert rolled_back == []
    assert report["moved"] == 1


def test_a_cell_holding_something_else_entirely_still_fails(monkeypatch):
    """Accepting the spoken name must not accept just any name."""
    rolled_back = []
    _stub_live_page(
        monkeypatch,
        layouts=[[], [{"slot": 0, "label": "something else"}]],
        content={},
        grid=live.Grid((10, 20), (30,), 8, 8),
    )
    monkeypatch.setattr(
        live, "_add_button",
        lambda *_args, **_kwargs: {"symbol": False, "border": True},
    )
    monkeypatch.setattr(
        live, "_restore_page_state",
        lambda *_args, **_kwargs: rolled_back.append(True),
    )

    with pytest.raises(PagesetError, match="did not verify the edited button"):
        live.apply_page_edits(
            "Eating",
            [{"label": "more", "message": "I would like some more, please",
              "slot": 0, "symbol": False}],
            [], [], [], "v1",
        )
    assert rolled_back == [True]


def test_navigation_finds_a_page_link_that_speaks_a_message(monkeypatch):
    """Route steps come from the page set by label; the grid shows messages."""
    link = _spoken_button("let's talk about snacks")
    group = SimpleNamespace(
        ControlTypeName="GroupControl", GetChildren=lambda: [link],
    )
    opened = []
    pages = iter(["Eating", "Eating", "Snacks", "Snacks"])
    monkeypatch.setattr(live, "_exit_edit_mode", lambda _window: None)
    monkeypatch.setattr(live, "_page_name", lambda _window: next(pages))
    monkeypatch.setattr(live, "_page_group", lambda _window: group)
    monkeypatch.setattr(live, "_named_page_buttons", lambda _group: ["Snacks"])
    monkeypatch.setattr(
        live, "_page_route", lambda *_args: [("Snacks", "Snacks", False)]
    )
    monkeypatch.setattr(live, "_find", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        live, "_accessible_labels",
        lambda _group: {"let's talk about snacks": "Snacks"},
    )
    monkeypatch.setattr(
        live, "_open_page_button",
        lambda _window, button, _name: opened.append(button),
    )
    monkeypatch.setattr(live, "_wait_for", lambda callback, _message, **_kw: callback())

    assert live._navigate_to_parent(object(), "Snacks") == "Snacks"
    assert opened == [link]


# ---------------------------------------------------------------------------
# More than one TD Snap user on one computer
#
# An SLP with a caseload, or a family with two AAC users, has a TD Snap user
# per person and so a page set per person. Page titles do not tell them apart
# — every page set built from the same TD Snap template carries the same ones
# — so the app fell back to "I cannot identify this page set", which locks
# every button out of editing and leaves every spoken name unresolved. The
# names the app has already measured off the live page are what distinguish
# them, and they were being dropped on the floor.


def _install_pageset(root, user_name, buttons, page="Eating"):
    """One TD Snap user with one page set. *buttons* is [(label, message)]."""
    user = (root / "Packages" / "TobiiDynavox.Snap_test" / "LocalState"
            / "Users" / user_name)
    user.mkdir(parents=True)
    with sqlite3.connect(user / "Settings.ssf") as conn:
        conn.execute("CREATE TABLE UserSettings (PageSetGuid TEXT)")
        conn.execute("INSERT INTO UserSettings VALUES ('active')")
    with sqlite3.connect(user / "active.sps") as conn:
        conn.execute("CREATE TABLE Page (Id INTEGER, Title TEXT, PageType INTEGER)")
        conn.execute("CREATE TABLE ElementReference (Id INTEGER, PageId INTEGER)")
        conn.execute(
            "CREATE TABLE Button (Id INTEGER, Label TEXT, Message TEXT, "
            "ElementReferenceId INTEGER, CommandFlags INTEGER)"
        )
        conn.execute("CREATE TABLE CommandSequence (ButtonId INTEGER, "
                     "SerializedCommands TEXT)")
        conn.execute("CREATE TABLE ButtonPageLink (ButtonId INTEGER, "
                     "PageUniqueId TEXT)")
        conn.execute("INSERT INTO Page VALUES (1, ?, 1)", (page,))
        conn.execute("INSERT INTO ElementReference VALUES (1, 1)")
        for index, (label, message) in enumerate(buttons, start=1):
            conn.execute(
                "INSERT INTO Button VALUES (?, ?, ?, 1, ?)",
                (index, label, message, templates.COMMAND_FLAGS_SPEAK),
            )
            conn.execute(
                "INSERT INTO CommandSequence VALUES (?, ?)",
                (index, '{"$type":"1","$values":[{"$type":"3"}]}'),
            )
    return user / "active.sps"


def test_the_right_page_set_is_found_among_several_on_one_machine(
    tmp_path, monkeypatch
):
    alex = _install_pageset(
        tmp_path, "alex", [("more", None), ("all done", "I am all done now")]
    )
    _install_pageset(
        tmp_path, "sam", [("more", None), ("all done", "finished for today")]
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    # Both page sets have an "Eating" page and a "more" button, so the title
    # alone still decides nothing — and that is the case that used to fail.
    assert live._active_pageset_path("Eating") is None

    # The names TD Snap is publishing right now settle it. The second is a
    # spoken message rather than a label, which is what the live page shows.
    found = live._active_pageset_path("Eating", ["more", "I am all done now"])
    assert found == os.path.realpath(str(alex))


def test_stored_content_reads_through_on_a_multi_user_machine(tmp_path, monkeypatch):
    _install_pageset(
        tmp_path, "alex", [("more", None), ("all done", "I am all done now")]
    )
    _install_pageset(tmp_path, "sam", [("more", None), ("all done", "finished")])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert live._stored_page_content("Eating") is None
    assert live._stored_page_content("Eating", ["more", "all done"]) is None
    content = live._stored_page_content("Eating", ["more", "I am all done now"])
    assert content is not None
    assert content["all done"]["message"] == "I am all done now"
    assert content["all done"]["kind"] == "speak"


def test_a_destructive_edit_is_not_refused_just_for_having_a_neighbour(
    tmp_path, monkeypatch
):
    """The refusal this fix exists to stop.

    ``_prior_content`` could not read the page set, so it refused every
    change, move, and removal on the whole machine with "couldn't read this
    page set's saved button content".
    """
    _install_pageset(
        tmp_path, "alex", [("more", None), ("all done", "I am all done now")]
    )
    _install_pageset(tmp_path, "sam", [("more", None), ("all done", "finished")])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    by_slot = {0: "more", 1: "all done"}
    prior = live._prior_content(
        "Eating", [], [1], [], by_slot,
        visible_names=["more", "I am all done now"],
    )
    assert prior[1]["label"] == "all done"
    assert prior[1]["message"] == "I am all done now"


def test_a_spoken_name_resolves_on_a_multi_user_machine(tmp_path, monkeypatch):
    _install_pageset(
        tmp_path, "alex", [("more", None), ("all done", "I am all done now")]
    )
    _install_pageset(tmp_path, "sam", [("more", None), ("all done", "finished")])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    group = SimpleNamespace(Name="Eating", GetChildren=lambda: [
        _spoken_button("more", left=0),
        _spoken_button("I am all done now", left=100),
    ])
    assert live._accessible_labels(group)["i am all done now"] == "all done"
    assert live._page_layout(group, live.Grid((40, 140), (40,), 100, 100)) == [
        {"slot": 0, "label": "more"},
        {"slot": 1, "label": "all done"},
    ]


def test_a_page_set_without_a_message_column_is_still_matched(tmp_path, monkeypatch):
    """Older TD Snap builds wrote page sets without Button.Message.

    Naming a column that does not exist fails the whole read, which on this
    path silently rules the page set out rather than reporting anything.
    """
    user = (tmp_path / "Packages" / "TobiiDynavox.Snap_test" / "LocalState"
            / "Users" / "alex")
    user.mkdir(parents=True)
    with sqlite3.connect(user / "Settings.ssf") as conn:
        conn.execute("CREATE TABLE UserSettings (PageSetGuid TEXT)")
        conn.execute("INSERT INTO UserSettings VALUES ('active')")
    with sqlite3.connect(user / "active.sps") as conn:
        conn.execute("CREATE TABLE Page (Id INTEGER, Title TEXT, PageType INTEGER)")
        conn.execute("CREATE TABLE ElementReference (Id INTEGER, PageId INTEGER)")
        conn.execute("CREATE TABLE Button (Label TEXT, ElementReferenceId INTEGER)")
        conn.execute("INSERT INTO Page VALUES (1, 'Eating', 1)")
        conn.execute("INSERT INTO ElementReference VALUES (1, 1)")
        conn.execute("INSERT INTO Button VALUES ('more', 1)")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert live._pageset_matches_visible_page(
        str(user / "active.sps"), "Eating", ["more"]
    )
    assert not live._pageset_matches_visible_page(
        str(user / "active.sps"), "Eating", ["not here"]
    )


def test_a_restored_failure_reads_as_two_sentences(monkeypatch):
    """The message a user sees most when an edit fails.

    It is built by appending "The original page was restored." to whatever
    failed, and the failures that name a button end on the button's own
    label — so it used to read "…reviewed cells: juice The original page was
    restored.", which looks like something was cut off.
    """
    _stub_live_page(
        monkeypatch,
        layouts=[[], []],
        content={},
        grid=live.Grid((10, 20), (30,), 8, 8),
    )
    monkeypatch.setattr(
        live, "_add_button",
        lambda *_args, **_kwargs: {"symbol": False, "border": True},
    )
    monkeypatch.setattr(live, "_restore_page_state", lambda *_args, **_kwargs: None)

    with pytest.raises(PagesetError) as caught:
        live.apply_page_edits(
            "Eating", [{"label": "juice", "slot": 0, "symbol": False}], [], [], [], "v1",
        )
    assert str(caught.value) == (
        "TD Snap did not verify the edited button(s) in their reviewed cells: "
        "juice. The original page was restored."
    )


def test_a_message_that_already_ends_a_sentence_is_left_alone():
    assert live._sentence("Restored.") == "Restored."
    assert live._sentence("Which buttons?") == "Which buttons?"
    assert live._sentence("These ones:") == "These ones:"
    assert live._sentence("  no full stop  ") == "no full stop."
    assert live._sentence("") == ""
