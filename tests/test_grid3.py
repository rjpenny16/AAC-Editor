import ctypes
import os
import time
import zipfile
from types import SimpleNamespace

import pytest

from tdsnap import grid3
from tdsnap.errors import PagesetError

SETTINGS = """<Settings><GridSetFileFormatVersion>{version}</GridSetFileFormatVersion></Settings>"""
STYLES = """<StyleData><Styles>
  <Style Key="Default"><BorderColour>#112233FF</BorderColour><FontColour>#223344FF</FontColour></Style>
  <Style Key="Blank"><BackColour>#AABBCCFF</BackColour><BorderColour>#010203FF</BorderColour><FontColour>#102030FF</FontColour></Style>
  <Style Key="Other"><BackColour>#DDEEFFAA</BackColour></Style>
</Styles></StyleData>"""
GRID = """<Grid>
  <ColumnDefinitions>
    <ColumnDefinition Width="Small"/><ColumnDefinition/><ColumnDefinition Width="Large"/><ColumnDefinition/>
  </ColumnDefinitions>
  <RowDefinitions><RowDefinition/><RowDefinition Height="Large"/><RowDefinition/></RowDefinitions>
  <Cells>
    <Cell X="0" Y="0"><Content><Commands><Command ID="Action.InsertText"><Parameter Key="text"><p><s><r>hello</r></s><s><r> </r></s></p></Parameter></Command></Commands><CaptionAndImage><Caption><p><s><r>hello</r></s></p></Caption></CaptionAndImage><Style><BasedOnStyle>Default</BasedOnStyle></Style></Content></Cell>
    <Cell X="1" Y="0"><Content><CaptionAndImage/><Style><BasedOnStyle>Blank</BasedOnStyle></Style></Content></Cell>
    <Cell X="2" Y="0" ColumnSpan="2"><Content><Style><BasedOnStyle>Other</BasedOnStyle></Style></Content></Cell>
    <Cell X="0" Y="1"><Content><ContentType>AutoContent</ContentType><ContentSubType>Prediction</ContentSubType><Style><BasedOnStyle>Blank</BasedOnStyle></Style></Content></Cell>
    <Cell X="1" Y="1"><Content><ContentType>Workspace</ContentType><ContentSubType>Chat</ContentSubType><Style><BasedOnStyle>Blank</BasedOnStyle></Style></Content></Cell>
    <Cell X="2" Y="1"><Content><ContentType>LiveCell</ContentType><Style><BasedOnStyle>Blank</BasedOnStyle></Style></Content></Cell>
    <Cell X="3" Y="1"><Content><Commands><Command ID="Jump.To"/></Commands><Style><BasedOnStyle>Blank</BasedOnStyle></Style></Content></Cell>
    <Cell X="0" Y="2"><Content><CaptionAndImage xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:nil="true"/><Style><BasedOnStyle>Blank</BasedOnStyle></Style></Content></Cell>
    <Cell X="1" Y="2"><Content><Commands><Command ID="Prediction.PredictThis"><Parameter Key="wordlist"><WordList><Items><Item>one</Item></Items></WordList></Parameter></Command></Commands><Style><BasedOnStyle>Blank</BasedOnStyle></Style></Content></Cell>
    <Cell X="2" Y="2"><Content><CaptionAndImage><AudioDescription>hidden cue</AudioDescription></CaptionAndImage><Style><BasedOnStyle>Blank</BasedOnStyle></Style></Content></Cell>
    <Cell X="3" Y="2"><Content><Style><BasedOnStyle>Blank</BasedOnStyle><TileColour>#ABCDEF80</TileColour></Style></Content></Cell>
  </Cells>
</Grid>"""


def make_gridset(tmp_path, *, user="Alice", name="Test Set", version="1", grid_xml=GRID, protected=False):
    folder = tmp_path / "Users" / user / "Grid Sets"
    folder.mkdir(parents=True, exist_ok=True)
    suffix = ".gridsetx" if protected else ".gridset"
    path = folder / f"{name}{suffix}"
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("Settings0/settings.xml", SETTINGS.format(version=version))
        package.writestr("Settings0/Styles/styles.xml", STYLES)
        package.writestr("Grids/Home/grid.xml", grid_xml)
    return path


@pytest.fixture
def grid_root(tmp_path, monkeypatch):
    monkeypatch.setattr(grid3, "GRID3_ROOT", str(tmp_path))
    return tmp_path


def test_parses_variable_grid_rich_text_styles_and_safe_blanks(grid_root):
    path = make_gridset(grid_root)
    with grid3.Grid3Package(str(path)) as package:
        model = package.grid("home")

    assert (model.cols, model.rows) == (4, 3)
    assert model.column_sizes == ("Small", "Normal", "Large", "Normal")
    assert model.row_sizes == ("Normal", "Large", "Normal")
    hello = model.cell_at(0, 0)
    assert hello.label == "hello"
    assert hello.message == "hello"
    assert hello.commands == ("Action.InsertText",)
    assert hello.safe_blank is False

    safe = {(cell.x, cell.y) for cell in model.cells if cell.safe_blank}
    assert safe == {(1, 0), (0, 2), (3, 2)}
    assert model.cell_at(1, 0).style.background == "#AABBCC"
    assert model.cell_at(3, 2).style.background == "#ABCDEF"


def test_locks_merged_special_command_wordlist_and_audio_cells(grid_root):
    path = make_gridset(grid_root)
    with grid3.Grid3Package(str(path)) as package:
        model = package.grid("Home")

    for position in ((2, 0), (0, 1), (1, 1), (2, 1), (3, 1), (1, 2), (2, 2)):
        assert model.cell_at(*position).safe_blank is False
    assert model.cell_at(2, 0).column_span == 2


def test_semantic_snapshot_includes_every_parsed_layout_field(grid_root):
    path = make_gridset(grid_root)
    with grid3.Grid3Package(str(path)) as package:
        model = package.grid("Home")

    snapshot = grid3._semantic(model)

    assert snapshot["grid"] == (
        "Home",
        4,
        3,
        ("Small", "Normal", "Large", "Normal"),
        ("Normal", "Large", "Normal"),
        None,
    )
    merged = snapshot["cells"][(2, 0)]
    assert merged[:2] == (2, 1)
    assert merged[3] is None
    assert merged[-1] is False


@pytest.mark.parametrize("version", ["2", "", "future"])
def test_rejects_unknown_gridset_formats(grid_root, version):
    path = make_gridset(grid_root, version=version)
    with pytest.raises(PagesetError, match="format"):
        grid3.Grid3Package(str(path))


def test_rejects_protected_malformed_and_outside_packages(grid_root, tmp_path):
    protected = make_gridset(grid_root, protected=True)
    with pytest.raises(PagesetError, match=r"protected .gridsetx"):
        grid3.Grid3Package(str(protected))

    malformed = grid_root / "Users" / "Alice" / "Grid Sets" / "Broken.gridset"
    malformed.write_bytes(b"not a zip")
    with pytest.raises(PagesetError, match="readable"):
        grid3.Grid3Package(str(malformed))

    outside = tmp_path / "outside.gridset"
    outside.write_bytes(b"anything")
    with pytest.raises(PagesetError, match="local Grid user"):
        grid3.Grid3Package(str(outside))


def test_active_title_resolves_gridset_user_dirty_state_and_ambiguity(grid_root):
    make_gridset(grid_root, user="Alice", name="Test Set")
    active = grid3._active_from_title("Grid 3 - Test Set - Home *")
    assert active.user == "Alice"
    assert active.grid_name == "Home"
    assert active.dirty is True

    make_gridset(grid_root, user="Bob", name="Test Set")
    with pytest.raises(PagesetError, match="more than one local Grid user"):
        grid3._active_from_title("Grid 3 - Test Set - Home")


def test_fingerprint_changes_when_active_grid_package_changes(grid_root):
    path = make_gridset(grid_root)
    active = grid3._active_from_title("Grid 3 - Test Set - Home")
    before = grid3._fingerprint(active)
    changed = GRID.replace("hidden cue", "different cue")
    make_gridset(grid_root, grid_xml=changed)
    os.utime(path, None)
    after = grid3._fingerprint(active)
    assert before != after


def test_activate_delegates_to_uia_with_grid3_messages(monkeypatch):
    """The retry/fallback logic itself is pinned in tests/test_uia.py; this
    only proves Grid 3's wrapper wires the shared helper up correctly."""
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
    monkeypatch.setattr(grid3.uia.time, "sleep", lambda _seconds: None)

    grid3._activate(control)

    assert pattern.calls == 2

    with pytest.raises(PagesetError, match="Grid 3's editor controls changed during the edit"):
        grid3._activate(None)


def test_wait_for_ignores_transient_package_errors(monkeypatch):
    """grid3.py's _wait_for swallows OSError/BadZipFile/KeyError; uia.py's
    shared wait_for does not by default (see tests/test_uia.py) — this pins
    that Grid 3-specific ignore list stays wired up."""
    monkeypatch.setattr(grid3.uia.time, "sleep", lambda _seconds: None)
    calls = iter([KeyError("mid-write"), "ready"])

    def flaky():
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    assert grid3._wait_for(flaky, "never") == "ready"


def test_ui_access_token_allows_grid3_without_administrator(monkeypatch):
    closed = []

    def open_token(_process, _access, token):
        token._obj.value = 7
        return True

    def token_info(_token, token_class, value, _length, returned):
        assert token_class == 26
        value._obj.value = 1
        returned._obj.value = ctypes.sizeof(ctypes.c_ulong)
        return True

    windll = SimpleNamespace(
        shell32=SimpleNamespace(IsUserAnAdmin=lambda: False),
        kernel32=SimpleNamespace(
            GetCurrentProcess=lambda: 1,
            CloseHandle=lambda token: closed.append(token.value),
        ),
        advapi32=SimpleNamespace(
            OpenProcessToken=open_token,
            GetTokenInformation=token_info,
        ),
    )
    monkeypatch.setattr(grid3.sys, "platform", "win32")
    monkeypatch.setattr(grid3.ctypes, "windll", windll, raising=False)

    assert grid3.has_ui_access() is True
    assert closed == [7]


def test_grid3_window_prefers_native_hwnd(monkeypatch):
    control = SimpleNamespace(Name="Grid 3 - Test Set - Home")
    auto = SimpleNamespace(
        ControlFromHandle=lambda handle: control if handle == 42 else None,
        GetRootControl=lambda: pytest.fail("UIA root fallback should not be used"),
    )
    monkeypatch.setattr(grid3, "_native_windows", lambda _prefix: [42])

    assert grid3._window(auto) is control


def _node(kind, name, automation_id="", bounds=(0, 0, 10, 10), children=()):
    rect = SimpleNamespace(left=bounds[0], top=bounds[1], right=bounds[2], bottom=bounds[3])
    return SimpleNamespace(
        ControlTypeName=kind, Name=name, AutomationId=automation_id,
        BoundingRectangle=rect, GetChildren=lambda: list(children),
    )


def test_live_cells_map_grid3_cell_ids_in_viewer_and_edit_mode():
    viewer = _node("WindowControl", "", children=[_node("GroupControl", "", children=[
        _node("DataItemControl", "hello", "Cell (0,0)", (0, 0, 10, 10)),
        _node("DataItemControl", "", "Cell (1,0)", (10, 0, 20, 10)),
        _node("TextControl", "Menu"),
    ])])
    mapped = grid3._live_cells(viewer, {(0, 0), (1, 0)})
    assert mapped[(1, 0)].rect.left == 10 and mapped[(0, 0)].control.Name == "hello"

    editor = _node("WindowControl", "", children=[_node("ListControl", "", "GridItems", children=[
        _node("ListItemControl", "Cell (0,0)", "Cell_0_0", (0, 0, 10, 10)),
        _node("ListItemControl", "Cell (1,0)", "Cell_1_0", (10, 0, 20, 10)),
    ])])
    edit = grid3._live_cells(editor, {(0, 0), (1, 0)}, editing=True)
    assert edit[(1, 0)].control.AutomationId == "Cell_1_0"

    # A cell the XML declares but the window does not expose fails closed;
    # nothing is ever located by screen position.
    with pytest.raises(PagesetError, match="1 of 3 missing in Edit Mode"):
        grid3._live_cells(editor, {(0, 0), (1, 0), (2, 0)}, editing=True)
    with pytest.raises(PagesetError, match="unverified screen coordinates"):
        grid3._live_cells(viewer, {(0, 0), (5, 5)})


def test_cell_kinds_lock_everything_but_plain_write_cells(grid_root):
    make_gridset(grid_root)
    grid = grid3._fresh_grid(grid3._active_from_title("Grid 3 - Test Set - Home"))
    kinds = {(cell.x, cell.y): grid3._cell_kind(cell) for cell in grid.cells}
    assert kinds[(0, 0)] == "speak"
    assert kinds[(1, 0)] == "blank"
    assert kinds[(2, 0)] == "span"
    assert kinds[(0, 1)] == "content"
    assert kinds[(3, 1)] == "jump"
    assert kinds[(1, 2)] == "action"
    described = grid3._describe_cell(grid.cell_at(0, 0), 0)
    assert described["editable"] and described["message"] == "hello"
    locked = grid3._describe_cell(grid.cell_at(3, 1), 7)
    assert not locked["editable"] and "opens another grid" in locked["locked_reason"]


def test_duplicate_and_invalid_target_validation_happens_before_automation(grid_root, monkeypatch):
    make_gridset(grid_root)
    active = grid3._active_from_title("Grid 3 - Test Set - Home")
    monkeypatch.setattr(grid3, "is_elevated", lambda: True)
    monkeypatch.setattr(grid3, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(
        grid3, "_active_context",
        lambda: (object(), object(), active, grid3._fresh_grid(active)),
    )
    fingerprint = grid3._fingerprint(active)

    with pytest.raises(PagesetError, match="Already on this grid"):
        grid3.add_to_existing_page([{"label": "hello", "slot": 1}], fingerprint)
    with pytest.raises(PagesetError, match="safe empty"):
        grid3.add_to_existing_page([{"label": "new", "slot": 0}], fingerprint)
    with pytest.raises(PagesetError, match="duplicate labels"):
        grid3.add_to_existing_page([
            {"label": "new", "slot": 1}, {"label": "NEW", "slot": 8},
        ], fingerprint)


@pytest.mark.skipif(
    os.environ.get("GRID3_LIVE_E2E") != "1",
    reason="set GRID3_LIVE_E2E=1 with a disposable Grid 3 copy open",
)
def test_live_grid3_edit_mode_probe_is_reversible():
    current = _disposable_grid3()
    before = grid3.inspect_page()["fingerprint"]
    result = grid3.probe_accessibility()
    after = grid3.inspect_page()["fingerprint"]
    assert result["checks"]["undo_without_save"] == "pass"
    assert after == before
    assert current["page"] == grid3.status()["page"]


def _disposable_grid3():
    current = grid3.status()
    assert current["elevated"], "run the test process as administrator"
    assert current["running"] and not current["dirty"]
    assert any(marker in current["grid_set"].casefold() for marker in ("copy", "test", "(2)")), (
        "refusing to edit a grid set that is not clearly a disposable copy"
    )
    return current


@pytest.mark.skipif(
    os.environ.get("GRID3_LIVE_E2E") != "1",
    reason="set GRID3_LIVE_E2E=1 with a disposable Grid 3 copy open",
)
def test_live_grid3_edit_matrix_and_undo_restore_the_grid_exactly():
    """Add, change, move, remove and undo on the open grid, verified from the file.

    Keep the keyboard and mouse alone while it runs: every step types into
    Grid 3, and the write path refuses to type into anything else.
    """
    _disposable_grid3()
    layout = grid3.inspect_page()
    free = layout["free_slots"]
    assert len(free) >= 3, "open a grid with at least three empty single cells"
    first, second, third = free[:3]
    original = grid3._semantic(grid3._fresh_grid(grid3._active_from_title(
        grid3._window(grid3._automation()).Name)))

    added = grid3.edit_page(
        items=[{"label": "aac editor one", "slot": first},
               {"label": "aac editor two", "message": "aac editor two please", "slot": second}],
        fingerprint=layout["fingerprint"],
    )
    assert added["checks"]["content"] == "pass"
    grid = grid3._fresh_grid(grid3._active_from_title(grid3._window(grid3._automation()).Name))
    assert grid.cell_for_slot(second).message == "aac editor two please"

    edited = grid3.edit_page(
        changes=[{"slot": first, "label": "aac editor uno"}],
        moves=[{"slot": second, "to": third}],
        fingerprint=grid3.inspect_page()["fingerprint"],
    )
    assert edited["checks"]["changed_content"] == "pass"
    assert edited["checks"]["moved_buttons"] == "pass"
    grid = grid3._fresh_grid(grid3._active_from_title(grid3._window(grid3._automation()).Name))
    assert grid.cell_for_slot(first).label == "aac editor uno"
    assert grid.cell_for_slot(third).message == "aac editor two please"
    assert grid.cell_for_slot(second).safe_blank

    undone = grid3.undo_last_edit()
    assert undone["checks"]["undone"] == "pass"
    grid = grid3._fresh_grid(grid3._active_from_title(grid3._window(grid3._automation()).Name))
    assert grid.cell_for_slot(first).label == "aac editor one"
    assert grid.cell_for_slot(second).message == "aac editor two please"

    removed = grid3.edit_page(removals=[first, second], fingerprint=grid3.inspect_page()["fingerprint"])
    assert removed["checks"]["removed_buttons"] == "pass"
    restored = grid3._semantic(grid3._fresh_grid(grid3._active_from_title(
        grid3._window(grid3._automation()).Name)))
    # Everything but the two cells that were written and cleared is exactly as it was.
    touched = {(slot % grid.cols, slot // grid.cols) for slot in (first, second)}
    assert {k: v for k, v in restored["cells"].items() if k not in touched} == {
        k: v for k, v in original["cells"].items() if k not in touched
    }


@pytest.mark.skipif(
    os.environ.get("GRID3_LIVE_E2E") != "1",
    reason="set GRID3_LIVE_E2E=1 with a disposable Grid 3 copy open",
)
def test_live_grid3_creates_and_links_a_grid():
    _disposable_grid3()
    layout = grid3.inspect_page()
    assert layout["free_slots"], "open a grid with an empty single cell for the link"
    # A fresh name each run: the grid stays in the disposable copy afterwards.
    title = f"AAC Editor live test {int(time.time())}"
    active = grid3._active_from_title(grid3._window(grid3._automation()).Name)
    cols = layout["grid"]["cols"]
    report = grid3.add_topic_page(
        title, [{"label": "apple", "slot": 1}, {"label": "juice", "slot": cols + 1}],
        fingerprint=layout["fingerprint"],
    )
    assert report["checks"]["created_grid"] == "pass"
    assert report["checks"]["linked_grid"] == "pass"
    created = grid3._fresh_grid(active, title)
    assert (created.cols, created.rows) == (layout["grid"]["cols"], layout["grid"]["rows"])
    assert "Jump.Back" in created.cell_at(0, 0).commands
    assert created.cell_at(1, 0).label == "apple" and created.cell_at(1, 1).label == "juice"
    parent = grid3._fresh_grid(active, layout["page"])
    link = parent.cell_for_slot(layout["free_slots"][0])
    assert "Jump.To" in link.commands and link.label == title
    # Grid 3 is left showing the new grid.
    assert grid3.status()["page"] == title


# ---------------------------------------------------------------------------
# A stand-in for Grid 3's Edit Mode: records what the write path asks of the
# ribbon, and on "save" rewrites the grid-set package the way Grid 3 would.
# Every verification and rollback decision then runs against real XML.

CELL_TEMPLATE = (
    '<Cell X="{x}" Y="{y}"><Content>{commands}{caption}'
    "<Style><BasedOnStyle>{style}</BasedOnStyle></Style></Content></Cell>"
)
BACK_CELL = (
    '<Cell X="0" Y="0"><Content><Commands><Command ID="Jump.Back"/></Commands>'
    "<CaptionAndImage><Caption>Back</Caption></CaptionAndImage>"
    "<Style><BasedOnStyle>Navigation category style</BasedOnStyle></Style></Content></Cell>"
)


def _cell_xml(x, y, label, message=None, style="Vocab cell", jump=None):
    if jump:
        commands = ('<Commands><Command ID="Jump.To"><Parameter Key="grid">'
                    f"{jump}</Parameter></Command></Commands>")
    elif label:
        commands = ('<Commands><Command ID="Action.InsertText"><Parameter Key="text">'
                    f"<p><s><r>{message or label}</r></s></p></Parameter></Command></Commands>")
    else:
        commands = ""
    caption = f"<CaptionAndImage><Caption>{label}</Caption></CaptionAndImage>" if label else ""
    return CELL_TEMPLATE.format(x=x, y=y, commands=commands, caption=caption, style=style)


def _grid_xml(cols, rows, cells):
    columns = "".join("<ColumnDefinition/>" for _ in range(cols))
    row_defs = "".join("<RowDefinition/>" for _ in range(rows))
    body = "".join(
        cells.get((x, y)) or _cell_xml(x, y, "", style="Default")
        for y in range(rows) for x in range(cols)
    )
    return (f"<Grid><ColumnDefinitions>{columns}</ColumnDefinitions>"
            f"<RowDefinitions>{row_defs}</RowDefinitions><Cells>{body}</Cells></Grid>")


def _name_field():
    field = SimpleNamespace(value=None)
    field.GetValuePattern = lambda: SimpleNamespace(
        SetValue=lambda value: setattr(field, "value", value))
    return field


class FakeGrid3:
    """Simulates Grid 3 for one grid set: a 3x2 Home grid with 'hello' at (0,0)."""

    def __init__(self, monkeypatch, root, *, faithful=True):
        self.cols, self.rows = 3, 2
        self.cells = {(0, 0): ("hello", "hi there")}   # position -> (label, message)
        self.grids = {}                                  # created grids: name -> cells
        self.links = {}                                  # position -> grid name
        self.faithful = faithful
        self.actions = []
        self.rollbacks = []
        self.dirty = False
        self.saved = 0
        self.selected = None
        self.current_grid = "Home"
        self.dialog = "dialog"
        self.dialog_page = None
        self.name_field = _name_field()
        self.path = make_gridset(root, grid_xml=self.render("Home"))
        self.active = grid3._active_from_title("Grid 3 - Test Set - Home")
        m = monkeypatch
        m.setattr(grid3, "is_elevated", lambda: True)
        m.setattr(grid3, "_desktop_unlocked", lambda: True)
        m.setattr(grid3, "_active_context", lambda require_clean=True: (
            object(), object(), self.active, grid3._fresh_grid(self.active)))
        m.setattr(grid3, "_live_cells", lambda window, positions, editing=False: {
            position: grid3._LiveCell(SimpleNamespace(position=position), None)
            for position in positions})
        m.setattr(grid3, "_enter_edit_mode", lambda auto, window, active: "editor")
        m.setattr(grid3, "_leave_edit_mode", lambda auto: self.actions.append("leave"))
        m.setattr(grid3, "_select_cell", lambda editor, position: self.select(position))
        m.setattr(grid3, "_ribbon_button", lambda editor, name: name)
        m.setattr(grid3, "_activate", self.press)
        m.setattr(grid3, "_label_cell", lambda auto, editor, label: self.label(label))
        m.setattr(grid3, "_set_message", lambda auto, editor, message, label: self.message(message))
        m.setattr(grid3, "_write_cell", self.write)
        m.setattr(grid3, "_save", lambda auto: self.save())
        m.setattr(grid3, "_dirty", lambda auto: self.dirty)
        m.setattr(grid3, "_restore_unsaved",
                  lambda auto, maximum: self.rollbacks.append("unsaved"))
        m.setattr(grid3, "_rollback_saved",
                  lambda auto, restored, maximum: self.rollbacks.append("saved"))
        m.setattr(grid3, "_wait_for", self.wait_for)
        m.setattr(grid3, "_dialog", lambda auto, title: self.dialog)
        m.setattr(grid3, "_find_id", self.find_id)
        m.setattr(grid3, "_button_by_text", lambda root, text, depth=12: text)
        m.setattr(grid3, "_field_after", lambda root, label: self.name_field)
        m.setattr(grid3, "_find_named", lambda root, name, kind=None: name)
        m.setattr(grid3, "_title_of", lambda auto: f"Grid 3 - Test Set - {self.current_grid}")
        m.setattr(grid3, "_window", lambda auto: "editor")
        grid3.forget_last_edit()

    @staticmethod
    def wait_for(callback, message, timeout=8):
        value = callback()
        if value is None or value is False:
            raise PagesetError(message)
        return value

    # -- what the write path drives ------------------------------------------
    def select(self, position):
        self.selected = position
        self.actions.append(("select", position))

    def press(self, control, **_kwargs):
        self.actions.append(("press", control))
        if control == "Delete":
            self.cells.pop(self.selected, None)
        elif control == "Copy":
            self.clipboard = self.cells.get(self.selected)
        elif control == "Paste":
            self.cells[self.selected] = self.clipboard
        elif control == "New Grid":
            self.dialog_page = "new"
        elif control == "OKButton" and self.dialog_page == "new":
            self.grids[self.name_field.value] = {}
            self.links[self.selected] = self.name_field.value
            self.dialog = None
        elif control == "FollowJump_ButtonCommandParameter":
            self.current_grid = self.links[self.selected]
        self.dirty = True

    def label(self, label):
        self.actions.append(("label", label))
        self.cells[self.selected] = (label, label)
        self.dirty = True

    def message(self, message):
        self.actions.append(("message", message))
        self.cells[self.selected] = (self.cells[self.selected][0], message)

    def write(self, auto, editor, item):
        self.actions.append(("write", item["label"]))
        target = self.grids[self.current_grid] if self.current_grid != "Home" else self.cells
        target[self.selected] = (item["label"], item["message"] or item["label"])
        self.dirty = True
        return 2, 1

    def find_id(self, root, automation_id, depth=12):
        if automation_id == "FollowJump_ButtonCommandParameter" and not self.links:
            return None
        return automation_id

    # -- what Grid 3 does on save ---------------------------------------------
    def render(self, name):
        if name == "Home":
            cells = {position: _cell_xml(*position, label, message)
                     for position, (label, message) in self.cells.items()}
            for position, target in self.links.items():
                cells[position] = _cell_xml(
                    *position, target, style="Navigation category style", jump=target)
        else:
            cells = {(0, 0): BACK_CELL}
            for position, (label, message) in self.grids[name].items():
                cells[position] = _cell_xml(*position, label, message)
        return _grid_xml(self.cols, self.rows, cells)

    def save(self):
        self.saved += 1
        if not self.faithful and self.saved == 1:
            # Grid 3 "loses" the last cell written; the verification must notice.
            target = self.grids[self.current_grid] if self.current_grid != "Home" else self.cells
            target.pop(max(target))
        with zipfile.ZipFile(self.path, "w") as package:
            package.writestr("Settings0/settings.xml", SETTINGS.format(version="1"))
            package.writestr("Settings0/Styles/styles.xml", STYLES)
            package.writestr("Grids/Home/grid.xml", self.render("Home"))
            for name in self.grids:
                package.writestr(f"Grids/{name}/grid.xml", self.render(name))
        self.dirty = False


def test_edit_page_removes_changes_and_adds_in_one_verified_save(grid_root, monkeypatch):
    fake = FakeGrid3(monkeypatch, grid_root)
    fake.cells[(1, 0)] = ("bye", "bye")
    fake.save()
    fingerprint = grid3._fingerprint(fake.active)

    report = grid3.edit_page(
        items=[{"label": "new", "message": "brand new", "slot": 5}],
        changes=[{"slot": 0, "label": "hey"}],
        removals=[1],
        fingerprint=fingerprint,
    )

    assert report["checks"]["removed_buttons"] == "pass"
    assert report["checks"]["changed_content"] == "pass"
    assert (report["buttons"], report["removed"], report["changed"]) == (1, 1, 1)
    assert fake.rollbacks == [] and fake.saved == 2
    # Removals first, then changes, then additions.
    driven = [action for action in fake.actions if action[0] in ("select", "press", "label", "write")]
    assert driven[:5] == [
        ("select", (1, 0)), ("press", "Delete"), ("select", (0, 0)), ("label", "hey"),
        ("select", (2, 1)),
    ]
    grid = grid3._fresh_grid(fake.active)
    assert grid.cell_at(1, 0).safe_blank and grid.cell_at(0, 0).label == "hey"
    assert grid.cell_at(2, 1).message == "brand new"
    # The inverse is remembered for undo.
    undo = grid3.last_edit()
    assert undo["page"] == "Home"
    assert undo["restores"] == {
        "adds": [{"label": "bye", "message": "bye"}],
        "changes": [{"label": "hello", "message": "hi there", "from": {"label": "hey", "message": "hi there"}}],
        "removals": [{"label": "new", "message": "brand new"}],
        "moves": [],
    }


def test_edit_page_moves_a_cell_by_copy_paste_delete(grid_root, monkeypatch):
    fake = FakeGrid3(monkeypatch, grid_root)
    fingerprint = grid3._fingerprint(fake.active)
    report = grid3.edit_page(moves=[{"slot": 0, "to": 4}], fingerprint=fingerprint)
    assert report["checks"]["moved_buttons"] == "pass"
    assert [action for action in fake.actions if action[0] == "press"][:3] == [
        ("press", "Copy"), ("press", "Paste"), ("press", "Delete"),
    ]
    grid = grid3._fresh_grid(fake.active)
    assert grid.cell_at(0, 0).safe_blank
    assert grid.cell_at(1, 1).label == "hello" and grid.cell_at(1, 1).message == "hi there"


def test_edit_page_rolls_back_a_save_that_does_not_match_the_review(grid_root, monkeypatch):
    fake = FakeGrid3(monkeypatch, grid_root, faithful=False)
    fingerprint = grid3._fingerprint(fake.active)
    with pytest.raises(PagesetError, match=r"restored: cell \(2, 0\) says nothing \(the cell is empty\), not “two”"):
        grid3.edit_page(items=[{"label": "one", "slot": 1}, {"label": "two", "slot": 2}],
                        fingerprint=fingerprint)
    assert fake.rollbacks == ["saved"]
    assert fake.actions[-1] == "leave"
    assert grid3.last_edit() is None


def test_edit_page_refuses_locked_cells_and_conflicting_plans_before_automation(grid_root, monkeypatch):
    make_gridset(grid_root)
    active = grid3._active_from_title("Grid 3 - Test Set - Home")
    monkeypatch.setattr(grid3, "is_elevated", lambda: True)
    monkeypatch.setattr(grid3, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(grid3, "_active_context",
                        lambda: (object(), object(), active, grid3._fresh_grid(active)))
    monkeypatch.setattr(grid3, "_enter_edit_mode",
                        lambda *args: (_ for _ in ()).throw(AssertionError("automation ran")))
    fingerprint = grid3._fingerprint(active)
    with pytest.raises(PagesetError, match="opens another grid"):
        grid3.edit_page(changes=[{"slot": 7, "label": "x"}], fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="covers more than one square"):
        grid3.edit_page(removals=[2], fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="changed and removed"):
        grid3.edit_page(changes=[{"slot": 0, "label": "x"}], removals=[0], fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="is empty in Grid 3"):
        grid3.edit_page(removals=[1], fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="safe empty"):
        grid3.edit_page(moves=[{"slot": 0, "to": 4}], fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="changed after preview"):
        grid3.edit_page(removals=[0], fingerprint="stale")


def test_undo_reverses_the_last_edit_through_the_same_write_path(grid_root, monkeypatch):
    fake = FakeGrid3(monkeypatch, grid_root)
    fingerprint = grid3._fingerprint(fake.active)
    grid3.edit_page(items=[{"label": "new", "slot": 1}], changes=[{"slot": 0, "label": "hey"}],
                    fingerprint=fingerprint)
    report = grid3.undo_last_edit()
    assert report["checks"]["undone"] == "pass"
    grid = grid3._fresh_grid(fake.active)
    assert grid.cell_at(1, 0).safe_blank
    assert grid.cell_at(0, 0).label == "hello" and grid.cell_at(0, 0).message == "hi there"
    assert grid3.last_edit() is None
    with pytest.raises(PagesetError, match="no change left to undo"):
        grid3.undo_last_edit()


def test_add_topic_page_creates_links_populates_and_verifies(grid_root, monkeypatch):
    fake = FakeGrid3(monkeypatch, grid_root)
    fingerprint = grid3._fingerprint(fake.active)
    report = grid3.add_topic_page(
        "Snacks",
        [{"label": "apple", "slot": 1}, {"label": "crisps", "message": "crisps please", "slot": 4}],
        fingerprint=fingerprint,
    )
    assert report["page"] == "Snacks" and report["parent"] == "Home"
    assert report["checks"]["created_grid"] == "pass"
    assert report["checks"]["linked_grid"] == "pass"
    assert fake.name_field.value == "Snacks"
    # The link went into the first safe blank of the open grid.
    assert fake.links == {(1, 0): "Snacks"}
    parent = grid3._fresh_grid(fake.active)
    assert parent.cell_at(1, 0).label == "Snacks" and "Jump.To" in parent.cell_at(1, 0).commands
    created = grid3._fresh_grid(fake.active, "Snacks")
    assert (created.cols, created.rows) == (3, 2)
    assert "Jump.Back" in created.cell_at(0, 0).commands
    assert created.cell_at(1, 0).label == "apple"
    assert created.cell_at(1, 1).message == "crisps please"
    assert fake.rollbacks == [] and fake.actions[-1] == "leave"
    assert grid3.last_edit() is None


def test_add_topic_page_validates_name_slots_and_link_before_automation(grid_root, monkeypatch):
    make_gridset(grid_root)
    active = grid3._active_from_title("Grid 3 - Test Set - Home")
    monkeypatch.setattr(grid3, "is_elevated", lambda: True)
    monkeypatch.setattr(grid3, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(grid3, "_active_context",
                        lambda: (object(), object(), active, grid3._fresh_grid(active)))
    monkeypatch.setattr(grid3, "_enter_edit_mode",
                        lambda *args: (_ for _ in ()).throw(AssertionError("automation ran")))
    fingerprint = grid3._fingerprint(active)
    with pytest.raises(PagesetError, match="already exists"):
        grid3.add_topic_page("home", [{"label": "a", "slot": 1}], fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="top-left"):
        grid3.add_topic_page("Snacks", [{"label": "a", "slot": 0}], fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="top-left"):
        grid3.add_topic_page("Snacks", [{"label": "a", "slot": 99}], fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="hold the link"):
        grid3.add_topic_page("Snacks", [{"label": "a", "slot": 1}], link_slot=0,
                             fingerprint=fingerprint)
    with pytest.raises(PagesetError, match="Give the new grid a name"):
        grid3.add_topic_page("  ", [{"label": "a", "slot": 1}], fingerprint=fingerprint)


def test_add_topic_page_rolls_back_when_the_new_grid_does_not_verify(grid_root, monkeypatch):
    fake = FakeGrid3(monkeypatch, grid_root, faithful=False)
    fingerprint = grid3._fingerprint(fake.active)
    with pytest.raises(PagesetError, match=r"cell \(2, 0\) of “Snacks” says nothing"):
        grid3.add_topic_page("Snacks", [{"label": "apple", "slot": 1}, {"label": "pear", "slot": 2}],
                             fingerprint=fingerprint)
    assert fake.rollbacks == ["saved"] and fake.actions[-1] == "leave"
