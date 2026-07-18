import os
import zipfile
import ctypes
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
    with pytest.raises(PagesetError, match="Protected"):
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


def test_edit_mode_cells_match_verified_geometry_and_accept_data_items():
    def node(kind, name, bounds, children=()):
        rect = SimpleNamespace(
            left=bounds[0], top=bounds[1], right=bounds[2], bottom=bounds[3],
        )
        return SimpleNamespace(
            ControlTypeName=kind, Name=name, BoundingRectangle=rect,
            GetChildren=lambda: list(children),
        )

    normal_cells = [
        node("DataItemControl", "hello", (0, 0, 10, 10)),
        node("ListItemControl", "", (10, 0, 20, 10)),
        node("DataItemControl", "", (0, 10, 10, 20)),
        node("ListItemControl", "", (10, 10, 20, 20)),
    ]
    normal = node("PaneControl", "", (0, 0, 20, 20), normal_cells)
    window = node("WindowControl", "", (0, 0, 20, 20), [normal])
    grid = SimpleNamespace(
        cols=2, rows=2,
        cells=[SimpleNamespace(label="hello"), *[SimpleNamespace(label="") for _ in range(3)]],
    )
    verified = grid3._live_cells(window, grid)

    edit_cells = [
        node("DataItemControl", "", (0, 0, 10, 10)),
        node("ListItemControl", "", (10, 0, 20, 10)),
        node("DataItemControl", "", (0, 10, 10, 20)),
        node("ListItemControl", "", (11, 10, 21, 20)),
    ]
    edit = node("PaneControl", "", (0, 0, 21, 20), edit_cells)
    matched = grid3._live_cells(
        node("WindowControl", "", (0, 0, 21, 20), [edit]), grid, verified,
    )

    assert set(matched) == {(0, 0), (1, 0), (0, 1)}
    assert matched[(1, 0)].control.ControlTypeName == "ListItemControl"


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
    with pytest.raises(PagesetError, match="not safe empty"):
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
    current = grid3.status()
    assert current["elevated"], "run the test process as administrator"
    assert current["running"] and not current["dirty"]
    assert any(marker in current["grid_set"].casefold() for marker in ("copy", "test", "(2)")), (
        "refusing to probe a grid set that is not clearly a disposable copy"
    )
    before = grid3.inspect_page()["fingerprint"]
    result = grid3.probe_accessibility()
    after = grid3.inspect_page()["fingerprint"]
    assert result["checks"]["undo_without_save"] == "pass"
    assert after == before
