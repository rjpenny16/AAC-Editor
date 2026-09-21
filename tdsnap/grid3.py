"""Read and edit the grid currently open in Grid 3 on Windows.

Grid-set packages are read only here.  Grid 3 performs every mutation and save
so its sync identity and versioning remain intact.
"""

from __future__ import annotations

import contextlib
import copy
import ctypes
import glob
import hashlib
import os
import re
import sys
import zipfile
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from . import uia
from .builder import _normalize_items
from .errors import PagesetError
from .live import _desktop_unlocked, _focus_window

GRID3_EXE = os.path.join(
    # the real Windows variable is spelled ProgramFiles(x86)
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),  # noqa: SIM112
    "Smartbox", "Grid 3", "Grid 3.exe",
)
GRID3_ROOT = os.path.join(
    os.environ.get("PUBLIC", r"C:\Users\Public"),
    "Documents", "Smartbox", "Grid 3",
)
_CELL_TYPES = {
    "ButtonControl", "CustomControl", "DataItemControl", "GroupControl",
    "ListItemControl", "PaneControl",
}
_SUPPORTED_FORMAT = "1"
_MAX_XML_BYTES = 16 * 1024 * 1024
# Every entry inside a .gridsetx (WordPower and other licensed vocabularies) is
# encrypted by Grid 3, so AAC Editor cannot read the grid before an edit or
# check it afterwards — and it will not try to get around the encryption.
PROTECTED_MESSAGE = (
    "This is a protected .gridsetx grid set (WordPower is one). Grid 3 encrypts "
    "its contents, so AAC Editor cannot read the grid to verify an edit and does "
    "not support it. Edit it in Grid 3 directly."
)


@dataclass(frozen=True)
class Grid3Style:
    key: str = "Default"
    background: str | None = None
    border: str | None = None
    foreground: str | None = None


@dataclass(frozen=True)
class Grid3Cell:
    x: int
    y: int
    column_span: int
    row_span: int
    label: str
    image: str | None
    commands: tuple[str, ...]
    content_type: str | None
    content_subtype: str | None
    style: Grid3Style
    message: str | None
    safe_blank: bool

    @property
    def slot(self) -> int:
        return self.y * 10_000 + self.x  # stable across non-rectangular layouts


@dataclass(frozen=True)
class Grid3Grid:
    name: str
    cols: int
    rows: int
    column_sizes: tuple[str, ...]
    row_sizes: tuple[str, ...]
    cells: tuple[Grid3Cell, ...]
    background: str | None

    def cell_at(self, x: int, y: int) -> Grid3Cell | None:
        return next((cell for cell in self.cells if cell.x == x and cell.y == y), None)

    def cell_for_slot(self, slot: int) -> Grid3Cell | None:
        # Frontend slots remain row-major; the internal stable slot above is not
        # sent over the API.
        x, y = slot % self.cols, slot // self.cols
        return self.cell_at(x, y)


@dataclass(frozen=True)
class ActiveGrid3:
    path: str
    grid_name: str
    window_title: str
    dirty: bool
    user: str


@dataclass
class _LiveCell:
    control: object
    rect: object


def _grid3_root() -> str:
    return GRID3_ROOT


def _grid3_exe() -> str:
    return GRID3_EXE


def has_ui_access() -> bool:
    if sys.platform != "win32":
        return False
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        advapi32.OpenProcessToken.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
        ]
        advapi32.GetTokenInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        token = wintypes.HANDLE()
        value = wintypes.DWORD()
        size = wintypes.DWORD()
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
        ):
            return False
        try:
            return bool(
                advapi32.GetTokenInformation(
                    token, 26, ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(size)
                ) and value.value
            )
        finally:
            kernel32.CloseHandle(token)
    except (AttributeError, OSError):
        return False


def is_elevated() -> bool:
    return has_ui_access()


def _automation():
    return uia.automation(
        "Live Grid 3 editing is available on Windows only.",
        "Windows automation is not installed. Reinstall AAC Editor.",
    )


# See tdsnap/uia.py's module docstring for why each of these shares its
# implementation with live.py's helper of the same name, and why the
# retry/tolerance/depth chosen there is correct for Grid 3 too.
_walk = uia.walk


def _activate(control) -> None:
    return uia.activate(
        control, missing_message="Grid 3's editor controls changed during the edit."
    )


def _native_windows(title_prefix: str) -> list[int]:
    if sys.platform != "win32":
        return []
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    handles = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL

    @callback_type
    def collect(handle, _parameter):
        # Edit Mode is a second top-level window with the viewer's title; the
        # viewer stays alive but hidden behind it, so only visible windows count.
        length = user32.GetWindowTextLengthW(handle) if user32.IsWindowVisible(handle) else 0
        if length:
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, title, len(title))
            if title.value.startswith(title_prefix):
                handles.append(handle)
        return True

    user32.EnumWindows(collect, 0)
    return handles


def _window(auto):
    for handle in _native_windows("Grid 3 - "):
        control = auto.ControlFromHandle(handle)
        if control:
            return control
    for control in auto.GetRootControl().GetChildren():
        if (control.Name or "").startswith("Grid 3 - "):
            return control
    raise PagesetError("Open Grid 3 to the grid you want to edit, then reconnect.")


_process_path = uia.process_image_path


def _verify_process(window) -> None:
    actual = _process_path(getattr(window, "ProcessId", 0))
    expected = os.path.realpath(_grid3_exe())
    if not actual:
        raise PagesetError("AAC Editor could not verify the Grid 3 process executable.")
    if os.path.normcase(os.path.realpath(actual)) != os.path.normcase(expected):
        raise PagesetError("The detected window is not the installed Grid 3 application.")


def _file_version(path: str) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        ]
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = [
            wintypes.LPCVOID, wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT),
        ]
        version.VerQueryValueW.restype = wintypes.BOOL
        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, buffer):
            return None
        pointer = ctypes.c_void_p()
        length = wintypes.UINT()
        if not version.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return None
        words = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
        return ".".join(map(str, (
            words[2] >> 16, words[2] & 0xFFFF,
            words[3] >> 16, words[3] & 0xFFFF,
        )))
    except (AttributeError, OSError, ValueError):
        return None


def _packages() -> list[str]:
    root = _grid3_root()
    return [
        path for path in glob.glob(
            os.path.join(root, "Users", "*", "Grid Sets", "*.gridset*")
        )
        if path.casefold().endswith((".gridset", ".gridsetx"))
    ]


def _active_from_title(title: str) -> ActiveGrid3:
    if not title.startswith("Grid 3 - "):
        raise PagesetError("Grid 3 is not showing an open grid.")
    body = title[len("Grid 3 - "):]
    matches = []
    for path in _packages():
        stem = Path(path).stem
        prefix = stem + " - "
        if body.casefold().startswith(prefix.casefold()):
            matches.append((len(stem), path, body[len(prefix):]))
    if not matches:
        raise PagesetError(
            "AAC Editor could not match the open Grid 3 grid set to a local user."
        )
    longest = max(length for length, _, _ in matches)
    matches = [(path, grid) for length, path, grid in matches if length == longest]
    if len(matches) != 1:
        users = sorted({Path(path).parents[1].name for path, _ in matches})
        raise PagesetError(
            "The open grid set exists for more than one local Grid user: "
            + ", ".join(users) + ". Keep only the intended user copy open."
        )
    path, grid_name = matches[0]
    if path.lower().endswith(".gridsetx"):
        raise PagesetError(PROTECTED_MESSAGE)
    grid_name = grid_name.rstrip()
    dirty = grid_name.endswith("*")
    grid_name = grid_name[:-1].rstrip() if dirty else grid_name
    return ActiveGrid3(
        path=os.path.realpath(path),
        grid_name=grid_name,
        window_title=title,
        dirty=dirty,
        user=Path(path).parents[1].name,
    )


def _text(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path)
    if found is None:
        return None
    value = "".join(found.itertext()).strip()
    return value or None


def _rich_text(node: ET.Element | None, path: str = ".") -> str | None:
    """Read Grid's formatted p/s/r text without XML indentation whitespace."""
    if node is None:
        return None
    found = node if path == "." else node.find(path)
    if found is None:
        return None
    runs = found.findall(".//r")
    if runs:
        value = "".join(run.text or "" for run in runs).strip()
    else:
        value = "".join(found.itertext()).strip()
    return value or None


def _css_color(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 9 and value.startswith("#"):
        return value[:7]
    return value if len(value) in {4, 7} and value.startswith("#") else None


class Grid3Package:
    def __init__(self, path: str):
        if path.lower().endswith(".gridsetx"):
            raise PagesetError(PROTECTED_MESSAGE)
        if not path.lower().endswith(".gridset"):
            raise PagesetError("Only unprotected .gridset files are supported.")
        real = os.path.realpath(path)
        allowed = os.path.realpath(os.path.join(_grid3_root(), "Users"))
        try:
            inside = os.path.normcase(os.path.commonpath([real, allowed])) == os.path.normcase(allowed)
        except ValueError:
            inside = False
        if not inside:
            raise PagesetError("Grid 3 files must come from a local Grid user.")
        try:
            self.zip = zipfile.ZipFile(real)
        except (OSError, zipfile.BadZipFile) as exc:
            raise PagesetError("The Grid 3 grid set is not a readable package.") from exc
        self.path = real
        try:
            settings = self._xml("Settings0/settings.xml")
            version = _text(settings, "GridSetFileFormatVersion")
            if version != _SUPPORTED_FORMAT:
                raise PagesetError(
                    f"Grid set format {version or 'unknown'} is not supported."
                )
            self.styles = self._styles()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self.zip.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def _xml(self, name: str) -> ET.Element:
        try:
            # parses the user's own local grid set, bounded by _MAX_XML_BYTES
            return ET.fromstring(self._bytes(name))  # noqa: S314
        except KeyError as exc:
            raise PagesetError(f"Grid set is missing {name!r}.") from exc
        except ET.ParseError as exc:
            raise PagesetError(f"Grid set contains invalid XML in {name!r}.") from exc

    def _bytes(self, name: str) -> bytes:
        try:
            info = self.zip.getinfo(name)
        except KeyError as exc:
            raise PagesetError(f"Grid set is missing {name!r}.") from exc
        if info.file_size > _MAX_XML_BYTES:
            raise PagesetError(f"Grid set XML entry {name!r} is unexpectedly large.")
        try:
            return self.zip.read(info)
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            raise PagesetError(f"Grid set XML entry {name!r} is not readable.") from exc

    def _styles(self) -> dict[str, Grid3Style]:
        root = self._xml("Settings0/Styles/styles.xml")
        raw = {node.get("Key", ""): node for node in root.findall("./Styles/Style")}
        cache: dict[str, Grid3Style] = {}

        def resolve(key: str, seen=()) -> Grid3Style:
            if key in cache:
                return cache[key]
            if key in seen:
                return Grid3Style(key=key)
            node = raw.get(key)
            if node is None:
                return Grid3Style(key=key)
            parent_key = _text(node, "BasedOnStyle")
            parent = resolve(parent_key, (*seen, key)) if parent_key else Grid3Style()
            style = Grid3Style(
                key=key,
                background=_css_color(_text(node, "BackColour")) or parent.background,
                border=_css_color(_text(node, "BorderColour")) or parent.border,
                foreground=_css_color(_text(node, "FontColour")) or parent.foreground,
            )
            cache[key] = style
            return style

        for key in raw:
            resolve(key)
        return cache

    def grid_names(self) -> list[str]:
        names = []
        for name in self.zip.namelist():
            if name.startswith("Grids/") and name.endswith("/grid.xml"):
                names.append(name[len("Grids/"):-len("/grid.xml")])
        return names

    def grid(self, requested: str) -> Grid3Grid:
        names = {name.casefold(): name for name in self.grid_names()}
        actual = names.get(requested.casefold())
        if actual is None:
            raise PagesetError(f"Grid 3's active grid {requested!r} was not found in the grid set.")
        root = self._xml(f"Grids/{actual}/grid.xml")
        column_nodes = root.findall("./ColumnDefinitions/ColumnDefinition")
        row_nodes = root.findall("./RowDefinitions/RowDefinition")
        if not column_nodes or not row_nodes:
            raise PagesetError("The active Grid 3 grid has no usable row/column layout.")
        cells = tuple(self._cell(node) for node in root.findall("./Cells/Cell"))
        return Grid3Grid(
            name=actual,
            cols=len(column_nodes),
            rows=len(row_nodes),
            column_sizes=tuple(node.get("Width", "Normal") for node in column_nodes),
            row_sizes=tuple(node.get("Height", "Normal") for node in row_nodes),
            cells=cells,
            background=_css_color(_text(root, "BackgroundColour")),
        )

    def _cell(self, node: ET.Element) -> Grid3Cell:
        content = node.find("Content")
        content = content if content is not None else ET.Element("Content")
        style_node = content.find("Style")
        style_key = _text(style_node, "BasedOnStyle") or "Default"
        base = self.styles.get(style_key, Grid3Style(key=style_key))
        style = Grid3Style(
            key=style_key,
            background=(
                _css_color(_text(style_node, "BackColour"))
                or _css_color(_text(style_node, "TileColour"))
                or base.background
            ),
            border=_css_color(_text(style_node, "BorderColour")) or base.border,
            foreground=_css_color(_text(style_node, "FontColour")) or base.foreground,
        )
        commands = tuple(
            command.get("ID", "") for command in content.findall("./Commands/Command")
            if command.get("ID")
        )
        message = None
        for command in content.findall("./Commands/Command"):
            if command.get("ID") == "Action.InsertText":
                for parameter in command.findall("Parameter"):
                    if parameter.get("Key") == "text":
                        message = _rich_text(parameter)
                        break
        label = _rich_text(content, "./CaptionAndImage/Caption") or ""
        image = _text(content, "./CaptionAndImage/Image")
        content_type = _text(content, "ContentType")
        content_subtype = _text(content, "ContentSubType")
        allowed_blank_nodes = {"Style", "CaptionAndImage", "Commands"}
        containers_empty = all(
            child.tag == "Style"
            or (not "".join(child.itertext()).strip() and not list(child))
            or (
                child.tag == "CaptionAndImage"
                and not "".join(child.itertext()).strip()
            )
            for child in content
        )
        try:
            x = int(node.get("X", "0"))
            y = int(node.get("Y", "0"))
            column_span = int(node.get("ColumnSpan", "1"))
            row_span = int(node.get("RowSpan", "1"))
        except ValueError as exc:
            raise PagesetError("The active Grid 3 grid has invalid cell coordinates.") from exc
        safe_blank = (
            not label and not image and not commands and not content_type and not content_subtype
            and all(child.tag in allowed_blank_nodes for child in content)
            and containers_empty
            and column_span == 1 and row_span == 1
        )
        return Grid3Cell(
            x=x, y=y, column_span=column_span, row_span=row_span,
            label=label, image=image, commands=commands,
            content_type=content_type, content_subtype=content_subtype,
            style=style, message=message, safe_blank=safe_blank,
        )


def _fingerprint(active: ActiveGrid3) -> str:
    stat = os.stat(active.path)
    with Grid3Package(active.path) as package:
        actual = {name.casefold(): name for name in package.grid_names()}[active.grid_name.casefold()]
        payload = package._bytes(f"Grids/{actual}/grid.xml")
    value = "\0".join([
        active.window_title, active.path, str(stat.st_size), str(stat.st_mtime_ns),
        hashlib.sha256(payload).hexdigest(),
    ])
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rect(control):
    try:
        rect = control.BoundingRectangle
        if rect.right > rect.left and rect.bottom > rect.top:
            return rect
    # best-effort geometry probe; failure falls back to stored layout
    except Exception:  # noqa: S110
        pass
    return None



# ---------------------------------------------------------------------------
# accessible cells
#
# Grid 3 names every cell control after its grid coordinates, in both of its
# windows: the viewer (an Avalonia window) exposes ``DataItemControl`` items
# with ``AutomationId="Cell (x,y)"``; Edit Mode (a separate WPF window that
# replaces the viewer after F11) exposes ``ListItemControl`` items with
# ``AutomationId="Cell_x_y"``. Those ids are the only cell locator used here —
# no rect clustering, no coordinate guessing — and any cell the grid-set XML
# declares that the window does not expose fails the operation closed.

_VIEWER_CELL_ID = re.compile(r"^Cell \((\d+),(\d+)\)$")
_EDITOR_CELL_ID = re.compile(r"^Cell_(\d+)_(\d+)$")
_VIEWER_WALK_DEPTH = 24  # the viewer's cells sit ~18 levels below the window
_EDITOR_WALK_DEPTH = 8  # Edit Mode's cells sit 3 levels down, ribbon buttons 4


def _positions(grid: Grid3Grid) -> set[tuple[int, int]]:
    return {(cell.x, cell.y) for cell in grid.cells}


def _live_cells(
    window, positions, editing: bool = False,
) -> dict[tuple[int, int], _LiveCell]:
    """Map every (x, y) in *positions* to its accessible control, or fail closed."""
    pattern = _EDITOR_CELL_ID if editing else _VIEWER_CELL_ID
    depth = _EDITOR_WALK_DEPTH if editing else _VIEWER_WALK_DEPTH
    found: dict[tuple[int, int], _LiveCell] = {}
    for control, _ in _walk(window, depth):
        match = pattern.match(getattr(control, "AutomationId", "") or "")
        if not match:
            continue
        rect = _rect(control)
        if rect is not None:
            found[(int(match[1]), int(match[2]))] = _LiveCell(control, rect)
    wanted = set(positions)
    missing = wanted - set(found)
    if missing or not wanted:
        raise PagesetError(
            "Grid 3 did not expose an accessible control for every cell of this grid "
            f"({len(missing)} of {len(wanted)} missing"
            f"{' in Edit Mode' if editing else ''}). "
            "AAC Editor will not use unverified screen coordinates."
        )
    return {position: found[position] for position in wanted}


def _active_context(require_clean=True):
    auto = _automation()
    window = _window(auto)
    _verify_process(window)
    active = _active_from_title(window.Name or "")
    if require_clean and active.dirty:
        raise PagesetError("Save or discard the changes already open in Grid 3, then reconnect.")
    with Grid3Package(active.path) as package:
        grid = package.grid(active.grid_name)
    return auto, window, active, grid


def status(include_layout=False) -> dict:
    result = {
        "available": sys.platform == "win32",
        "installed": os.path.isfile(_grid3_exe()),
        "running": False,
        "unlocked": _desktop_unlocked(),
        "elevated": is_elevated(),
        "needs_elevation": False,
    }
    if not result["available"] or not result["installed"]:
        return result
    result["version"] = _file_version(_grid3_exe())
    tested = tuple(
        value.strip() for value in os.environ.get("GRID3_TESTED_VERSIONS", "3.0.93").split(",")
        if value.strip()
    )
    if result["version"] and not result["version"].startswith(tested):
        result["compatibility_warning"] = (
            f"Grid 3 {result['version']} has not been certified with this AAC Editor build. "
            "The Edit Mode compatibility check must pass before editing."
        )
    if not result["elevated"]:
        result["needs_elevation"] = True
        return result
    try:
        auto = _automation()
        window = _window(auto)
        _verify_process(window)
        active = _active_from_title(window.Name or "")
        with Grid3Package(active.path) as package:
            grid = package.grid(active.grid_name)
    except PagesetError as exc:
        result["error"] = str(exc)
        return result
    result.update(
        running=True,
        grid_set=Path(active.path).stem,
        page=grid.name,
        user=active.user,
        grid={"cols": grid.cols, "rows": grid.rows},
        dirty=active.dirty,
        needs_elevation=not result["elevated"],
    )
    if include_layout and result["elevated"] and not active.dirty:
        try:
            result.update(inspect_page())
        except PagesetError as exc:
            result["supported"] = False
            result["error"] = str(exc)
    return result


# What each kind of occupied cell is, and why AAC Editor will not change it.
# A "speak" cell is a plain Write cell: one Action.InsertText command, one
# grid square, no picture-only or list content. Everything else is locked.
LOCK_REASONS = {
    "jump": "This cell opens another grid, so AAC Editor leaves it alone.",
    "action": "This cell runs a Grid 3 command, so AAC Editor leaves it alone.",
    "span": "This cell covers more than one square, so AAC Editor leaves it alone.",
    "content": "This cell holds Grid 3 content (a word list, picture or app), "
               "so AAC Editor leaves it alone.",
}


def _cell_kind(cell: Grid3Cell) -> str:
    if cell.column_span != 1 or cell.row_span != 1:
        return "span"
    if cell.content_type or cell.content_subtype:
        return "content"
    if not cell.commands:
        return "blank" if cell.safe_blank else "content"
    if cell.commands == ("Action.InsertText",):
        return "speak" if cell.label else "content"
    if any(command.startswith("Jump.") for command in cell.commands):
        return "jump"
    return "action"


def _describe_cell(cell: Grid3Cell, slot: int) -> dict:
    kind = _cell_kind(cell)
    return {
        "slot": slot, "label": cell.label, "existing": True,
        "message": cell.message, "function": None, "symbol": bool(cell.image),
        "editable": kind == "speak",
        "locked_reason": None if kind == "speak" else LOCK_REASONS[kind],
    }


def inspect_page() -> dict:
    if not is_elevated():
        raise PagesetError("Restart AAC Editor with administrator access for Grid 3.")
    _auto, window, active, grid = _active_context()
    live = _live_cells(window, _positions(grid))
    live_rects = [item.rect for item in live.values()]
    grid_left = min(rect.left for rect in live_rects)
    grid_top = min(rect.top for rect in live_rects)
    grid_right = max(rect.right for rect in live_rects)
    grid_bottom = max(rect.bottom for rect in live_rects)
    grid_width = max(1, grid_right - grid_left)
    grid_height = max(1, grid_bottom - grid_top)
    cells = []
    free_slots = []
    buttons = []
    for cell in grid.cells:
        rect = live[(cell.x, cell.y)].rect
        slot = cell.y * grid.cols + cell.x
        if cell.safe_blank:
            free_slots.append(slot)
        else:
            buttons.append(_describe_cell(cell, slot))
        cells.append({
            "slot": slot, "x": cell.x, "y": cell.y,
            "column_span": cell.column_span, "row_span": cell.row_span,
            "label": cell.label, "occupied": not cell.safe_blank,
            "safe_blank": cell.safe_blank,
            "image": bool(cell.image), "style": {
                "key": cell.style.key, "background": cell.style.background,
                "border": cell.style.border, "foreground": cell.style.foreground,
            },
            "rect": {
                "left": (rect.left - grid_left) / grid_width,
                "top": (rect.top - grid_top) / grid_height,
                "width": (rect.right - rect.left) / grid_width,
                "height": (rect.bottom - rect.top) / grid_height,
            },
        })
    return {
        "supported": True,
        "grid_set": Path(active.path).stem,
        "page": grid.name,
        "grid": {"cols": grid.cols, "rows": grid.rows},
        "background": grid.background,
        "preview_aspect": grid_width / grid_height,
        "buttons": buttons,
        "cells": cells,
        "free_slots": free_slots,
        # The grid-set XML is the stored content, so every occupied cell's
        # label and message are known before an edit touches it.
        "content_readable": True,
        "fingerprint": _fingerprint(active),
        "undo": last_edit(),
    }


# ---------------------------------------------------------------------------
# Edit Mode primitives


def _foreground_process_id() -> int:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(process_id))
    return process_id.value


def _require_grid3_foreground(auto) -> None:
    """Refuse to type unless Grid 3 owns the keyboard.

    Every keystroke below goes to whichever window is in front. If the user
    (or another app) took the foreground mid-edit, a label, an Enter or a
    Ctrl+Z would land in their document instead; one attempt is made to
    bring Grid 3 back, and after that the edit stops rather than typing.
    """
    window = _window(auto)
    if _foreground_process_id() == getattr(window, "ProcessId", -1):
        return
    with contextlib.suppress(PagesetError):
        _focus_window(window)
    if _foreground_process_id() != getattr(window, "ProcessId", -1):
        raise PagesetError(
            "Another window took the keyboard away from Grid 3 during the edit. "
            "Nothing was typed into it. Bring Grid 3 to the front, then try again."
        )


def _send(auto, keys: str, wait=0.35) -> None:
    _require_grid3_foreground(auto)
    auto.SendKeys(keys, waitTime=wait)


def _find_named(window, name: str, control_type=None):
    wanted = name.casefold()
    for control, _ in _walk(window, 12):
        if (control.Name or "").strip().casefold() == wanted and (
            control_type is None or control.ControlTypeName == control_type
        ):
            return control
    return None


def _find_id(root, automation_id: str, depth=12):
    for control, _ in _walk(root, depth):
        if (getattr(control, "AutomationId", "") or "") == automation_id:
            return control
    return None


def _button_by_text(root, text: str, depth=12):
    """A button whose only accessible name is the label text inside it.

    Grid 3's dialog buttons are unnamed; their caption is a child TextControl
    carrying a WPF mnemonic underscore ("_New Grid").
    """
    for control, _ in _walk(root, depth):
        if control.ControlTypeName != "ButtonControl":
            continue
        for child, _ in _walk(control, 3):
            if (child.Name or "").replace("_", "").strip().casefold() == text.casefold():
                return control
    return None


def _field_after(root, label: str):
    """The first text field that follows the TextControl reading *label*."""
    seen = False
    for control, _ in _walk(root, 12):
        if control.ControlTypeName == "TextControl" and (control.Name or "").strip() == label:
            seen = True
            continue
        if seen and control.ControlTypeName == "EditControl":
            return control
    return None


def _require_normal_mode(window) -> None:
    if _find_named(window, "Finish Editing"):
        raise PagesetError("Finish the existing Grid 3 Edit Mode session, then reconnect.")


def _wait_for(callback, message, timeout=uia.WAIT_DEFAULT_TIMEOUT):
    # Grid 3's callbacks read a grid-set package mid-edit, which can raise
    # these transiently while Grid 3 is still writing the file; TD Snap's
    # callbacks only ever touch the live control tree, so this ignore list
    # is Grid 3-specific rather than something tdsnap/uia.py hard-codes.
    return uia.wait_for(
        callback, message, timeout, ignore=(OSError, zipfile.BadZipFile, KeyError)
    )


def _title_of(auto) -> str:
    return _window(auto).Name or ""


def _dirty(auto) -> bool:
    return _title_of(auto).rstrip().endswith("*")


def _select_ribbon_tab(editor, name: str) -> None:
    # The ribbon keeps whichever tab the user last opened; every Home-tab
    # button (Change Label, Delete, Copy, Paste) is absent from the tree
    # while Layout or Style is showing.
    tab = _find_named(editor, name, "TabItemControl")
    if tab is None:
        raise PagesetError(f"Grid 3's {name} ribbon tab was not accessible.")
    _activate(tab)


def _enter_edit_mode(auto, window, active):
    """Press F11 and return the Edit Mode window, which replaces the viewer."""
    _require_normal_mode(window)
    _focus_window(window)
    _send(auto, "{F11}")

    def editor_window():
        candidate = _window(auto)
        return candidate if _find_named(candidate, "Finish Editing") else None

    editor = _wait_for(editor_window, "Grid 3 did not enter a verifiable Edit Mode after F11.")
    reopened = _active_from_title(editor.Name or "")
    if (reopened.path, reopened.grid_name) != (active.path, active.grid_name):
        raise PagesetError("Grid 3 changed grids while entering Edit Mode.")
    _select_ribbon_tab(editor, "Home")
    return editor


def _leave_edit_mode(auto) -> None:
    # Best effort: by the time this runs the edit is either verified or
    # rolled back, and a foreground refusal here must not hide that outcome.
    with contextlib.suppress(PagesetError):
        _send(auto, "{F11}")
    # The viewer takes a moment to come back; the edit itself is already
    # verified by now, so not seeing it return is not a failure of the edit.
    with contextlib.suppress(PagesetError):
        _wait_for(
            lambda: (
                not _find_named(window := _window(auto), "Finish Editing")
                and (window.Name or "").startswith("Grid 3 - ")
            ) or None,
            "", timeout=5,
        )


def _ribbon_button(editor, name: str):
    return _wait_for(
        lambda: _find_named(editor, name, "ButtonControl"),
        f"Grid 3's {name} control was not accessible.",
    )


def _select_cell(editor, position: tuple[int, int]) -> None:
    """Select one Edit Mode cell, looked up afresh by its id.

    Paste, Delete and a new Write command all rebuild the cell's control, so
    a control found before the edit began may no longer be the live one.
    """
    fresh = _wait_for(
        lambda: _live_cells(editor, {position}, editing=True).get(position),
        "A reviewed cell was not accessible in Grid 3 Edit Mode.",
    )
    _activate(fresh.control)


def _semantic(grid: Grid3Grid) -> dict:
    return {
        "grid": (
            grid.name,
            grid.cols,
            grid.rows,
            grid.column_sizes,
            grid.row_sizes,
            grid.background,
        ),
        "cells": {
            (cell.x, cell.y): (
                cell.column_span,
                cell.row_span,
                cell.label,
                cell.image,
                cell.commands,
                cell.content_type,
                cell.content_subtype,
                cell.style,
                cell.message,
                cell.safe_blank,
            )
            for cell in grid.cells
        },
    }


def _fresh_grid(active: ActiveGrid3, name: str | None = None) -> Grid3Grid:
    with Grid3Package(active.path) as package:
        return package.grid(name or active.grid_name)


def _grid_names(active: ActiveGrid3) -> set[str]:
    with Grid3Package(active.path) as package:
        return {name.casefold() for name in package.grid_names()}


def _send_text(auto, value: str) -> None:
    """Type literal user text without treating braces as automation keys."""
    _require_grid3_foreground(auto)
    auto.SendKeys(value, interval=0.01, waitTime=0.15, charMode=True)


_UNSAVED_LEFT = (
    " The unsaved edit is still open in Grid 3's Edit Mode: press Undo there until the "
    "title loses its *, or choose Finish Editing and discard the changes."
)


def _restore_unsaved(auto, maximum: int) -> None:
    """Undo only until Grid 3 reports the originally clean document again."""
    try:
        for _ in range(maximum + 3):
            if not _dirty(auto):
                return
            _send(auto, "{Ctrl}z", wait=0.12)
    except PagesetError as exc:
        raise PagesetError(str(exc) + _UNSAVED_LEFT) from exc
    raise PagesetError("Grid 3 could not restore the clean pre-edit state." + _UNSAVED_LEFT)


def _save(auto) -> None:
    _send(auto, "{Ctrl}s", wait=0.6)
    _wait_for(lambda: not _dirty(auto), "Grid 3 did not finish saving.", timeout=12)


def _rollback_saved(auto, restored, maximum: int) -> None:
    """Undo and save one history step at a time, stopping exactly when *restored()*."""
    for _ in range(maximum):
        _send(auto, "{Ctrl}z", wait=0.1)
        _send(auto, "{Ctrl}s", wait=0.35)
        _wait_for(
            lambda: not _dirty(auto), "Grid 3 did not finish saving the rollback.", timeout=4,
        )
        try:
            if restored():
                return
        except (OSError, zipfile.BadZipFile, PagesetError):
            pass
    raise PagesetError("Grid 3 could not restore the verified pre-edit content.")


def _label_cell(auto, editor, label: str) -> None:
    """Rename the selected cell through Change Label's inline editor."""
    toggle = _ribbon_button(editor, "Change Label")
    pattern = getattr(toggle, "GetTogglePattern", lambda: None)()
    # Ctrl+W opens the label editor by itself; pressing Change Label again
    # would close it, so only open it when it is off.
    if pattern is None:
        _activate(toggle)
    elif pattern.ToggleState != 1:
        pattern.Toggle()
    # The label editor only exists once it has focus; typing any earlier lands
    # in whichever control had it before.
    _wait_for(
        lambda: getattr(auto.GetFocusedControl(), "ControlTypeName", "") == "EditControl",
        "Grid 3's label editor did not take focus.",
    )
    _send(auto, "{Ctrl}a", wait=0.05)
    _send_text(auto, label)
    _send(auto, "{Enter}")


def _set_message(auto, editor, message: str, label: str) -> None:
    """Make the selected Write cell speak *message*, deterministically.

    The sidebar's "Same as cell label" switch is an unnamed toggle. While it
    is on, the text field mirrors the label; switching it on copies the
    spoken text *onto the label*, so it is never switched on here. Grid 3
    stores no flag for it — a cell speaks its label when the two texts
    match — so the text is always written out explicitly instead.
    """
    # The sidebar is rebuilt after a label edit, so controls are waited for.
    pattern = _wait_for(
        lambda: getattr(
            _find_id(editor, "CheckBoxCommandParameter"), "GetTogglePattern", lambda: None,
        )(),
        "Grid 3's 'Same as cell label' switch was not accessible.",
    )
    if pattern.ToggleState == 1:
        if message == label:
            return
        pattern.Toggle()
    field = _wait_for(
        lambda: _find_id(editor, "CommandParameterEditor") or _find_id(editor, "userControl"),
        "Grid 3's separate spoken-text field was not accessible.",
    )
    setter = getattr(field, "GetValuePattern", lambda: None)()
    if setter:
        setter.SetValue(message)
        return
    # A text Grid 3 has already symbolised shows as a symbol strip that takes
    # typing but has no value pattern.
    field.SetFocus()
    _wait_for(
        lambda: getattr(auto.GetFocusedControl(), "AutomationId", "") == "userControl",
        "Grid 3's spoken-text editor did not take focus.",
    )
    _send(auto, "{Ctrl}a", wait=0.05)
    _send_text(auto, message)
    _send(auto, "{Tab}", wait=0.4)


def _spoken_after_change(was: Grid3Cell, change: dict) -> tuple[str, str]:
    """The (label, message) a reviewed change leaves a cell speaking.

    A message given with the change wins; an empty one means "speak the
    label again"; with none given, a cell that spoke something other than
    its label keeps saying it, and one that spoke its label follows the
    new label.
    """
    label = change.get("label", was.label)
    message = change.get("message")
    if message:
        return label, message
    if message is None and was.message and was.message != was.label:
        return label, was.message
    return label, label


def _try_symbol(auto, editor, label: str) -> bool:
    """Pick the symbol Grid 3's Picture Browser captions exactly as *label*.

    Find Picture opens the browser as its own window, pre-searched with the
    cell's text. Whatever happens, the browser is closed again before the
    edit goes on: an open dialog would swallow the save that follows.
    """
    find_picture = _find_named(editor, "Find Picture", "ButtonControl")
    if not find_picture:
        return False
    _activate(find_picture)
    try:
        dialog = _wait_for(lambda: _dialog(auto, "Picture Browser"), "", timeout=5)
    except PagesetError:
        return False
    wanted = label.strip().casefold()

    def exact_tile():
        return next((
            control for control, _ in _walk(dialog, 8)
            if control.ControlTypeName == "ListItemControl"
            and (control.Name or "").strip().casefold() == wanted
        ), None)

    try:
        tile = _wait_for(exact_tile, "", timeout=4)
    except PagesetError:
        tile = None
    if tile is not None:
        _activate(tile)
        _activate(_find_id(dialog, "OKButton", 6))
    else:
        _activate(_find_id(dialog, "CancelButton", 6))
    _wait_for(
        lambda: _dialog(auto, "Picture Browser") is None,
        "Grid 3's Picture Browser did not close.",
    )
    return tile is not None


def _write_cell(auto, editor, item: dict) -> tuple[int, int]:
    """Turn the selected blank into a Write cell; returns (undo steps, symbols)."""
    _send(auto, "{Ctrl}w")
    steps = 1
    _label_cell(auto, editor, item["label"])
    steps += 1
    if item["message"] and item["message"] != item["label"]:
        _set_message(auto, editor, item["message"], item["label"])
        steps += 1
    symbols = 0
    if item.get("symbol", True) and _try_symbol(auto, editor, item["label"]):
        symbols = 1
        steps += 1
    return steps, symbols


def _dialog(auto, title: str):
    """The Grid 3 dialog window named *title*, verified to belong to Grid 3."""
    for handle in _native_windows(title):
        control = auto.ControlFromHandle(handle)
        if control and (control.Name or "") == title:
            _verify_process(control)
            return control
    return None


def _speaks(cell: Grid3Cell | None, label: str, message: str | None) -> bool:
    return (
        cell is not None
        and cell.label == label
        and "Action.InsertText" in cell.commands
        and cell.message == (message or label)
    )


def _at(grid: Grid3Grid, slot: int) -> tuple[int, int]:
    return slot % grid.cols, slot // grid.cols


def _said(cell: Grid3Cell | None) -> str:
    if cell is None or cell.safe_blank:
        return "nothing (the cell is empty)"
    return f"“{cell.label}” speaking “{cell.message or cell.label}”"


# ---------------------------------------------------------------------------
# compatibility probe


def probe_accessibility() -> dict:
    """Exercise Grid 3 Edit Mode without saving any vocabulary or file change."""
    if not _desktop_unlocked():
        raise PagesetError("Unlock Windows before checking Grid 3 editing.")
    if not is_elevated():
        raise PagesetError("Restart AAC Editor with administrator access for Grid 3.")
    auto, window, active, grid = _active_context()
    blank = next((cell for cell in grid.cells if cell.safe_blank), None)
    if blank is None:
        raise PagesetError(
            "This grid has no safe empty single cell. Choose a grid with an empty cell."
        )
    baseline = _semantic(grid)
    before = _fingerprint(active)
    probe_label = "AAC Editor compatibility check"
    undo_steps = 0
    _live_cells(window, _positions(grid))
    editor = _enter_edit_mode(auto, window, active)
    try:
        live = _live_cells(editor, _positions(grid), editing=True)
        _select_cell(editor, (blank.x, blank.y))
        _send(auto, "{Ctrl}w")
        undo_steps += 1
        _wait_for(
            lambda: _find_named(editor, "Write"),
            "Grid 3 did not expose the provisional Write command.",
        )
        _label_cell(auto, editor, probe_label)
        undo_steps += 1
        _wait_for(
            lambda: _dirty(auto),
            "Grid 3 did not report the provisional compatibility edit.",
        )
        _restore_unsaved(auto, undo_steps)
        _wait_for(
            lambda: _semantic(_fresh_grid(active)) == baseline,
            "The compatibility check could not verify the unchanged grid-set file.",
        )
        if _fingerprint(active) != before:
            raise PagesetError("The Grid 3 file changed during the compatibility check.")
    except Exception:
        _restore_unsaved(auto, undo_steps)
        _leave_edit_mode(auto)
        raise
    _leave_edit_mode(auto)
    return {
        "supported": True,
        "grid": {"cols": grid.cols, "rows": grid.rows},
        "accessible_cells": len(live),
        "control_fingerprint": hashlib.sha256(
            "|".join(sorted(
                f"{getattr(item.control, 'ControlTypeName', '')}:"
                f"{getattr(item.control, 'AutomationId', '')}"
                for item in live.values()
            )).encode("utf-8")
        ).hexdigest(),
        "checks": {
            "window_title": "pass", "cell_bounds": "pass",
            "edit_mode": "pass", "write_command": "pass",
            "label": "pass", "undo_without_save": "pass",
        },
    }


# ---------------------------------------------------------------------------
# editing the open grid


def _normalize_changes(changes) -> list[dict]:
    normalized = []
    for change in changes or ():
        entry = {"slot": int(change["slot"])}
        if change.get("label") is not None:
            entry["label"] = str(change["label"]).strip()
            if not entry["label"]:
                raise PagesetError("A changed cell needs a label.")
        if change.get("message") is not None:
            entry["message"] = str(change["message"]).strip()
        if "label" not in entry and "message" not in entry:
            raise PagesetError("A change must give the cell a new label or message.")
        normalized.append(entry)
    return normalized


def _normalize_moves(moves) -> list[dict]:
    return [{"slot": int(move["slot"]), "to": int(move["to"])} for move in moves or ()]


def _speak_cell(grid: Grid3Grid, slot: int, what: str) -> Grid3Cell:
    cell = grid.cell_for_slot(slot)
    if cell is None or cell.safe_blank:
        raise PagesetError(f"The cell to {what} is empty in Grid 3. Reconnect and review again.")
    kind = _cell_kind(cell)
    if kind != "speak":
        raise PagesetError(f"AAC Editor can't {what} “{cell.label}”: {LOCK_REASONS[kind]}")
    return cell


def _blank_cell(grid: Grid3Grid, slot, what: str) -> Grid3Cell:
    cell = grid.cell_for_slot(slot) if slot is not None else None
    if cell is None or not cell.safe_blank:
        raise PagesetError(f"The space to {what} is not a safe empty Grid 3 cell.")
    return cell


_LAST_EDIT: dict | None = None


def _remember(active: ActiveGrid3, before: Grid3Grid, after: Grid3Grid,
              plan: dict, fingerprint: str) -> None:
    """Keep the inverse of an applied edit so it can be undone through edit_page.

    ``restores`` uses the same shapes the review screen renders for TD Snap,
    so an undo is reviewed by the same lists as the edit that caused it.
    """
    global _LAST_EDIT
    moved = {move["slot"]: move["to"] for move in plan["moves"]}
    inverse = {
        "items": [
            {"label": (old := before.cell_for_slot(slot)).label, "message": old.message,
             "slot": slot, "symbol": bool(old.image)}
            for slot in plan["removals"]
        ],
        "changes": [
            {"slot": moved.get(change["slot"], change["slot"]),
             "label": (old := before.cell_for_slot(change["slot"])).label,
             # "" is a request — "speak the label again" — and is how the
             # original message is restored when there wasn't one.
             "message": old.message if old.message != old.label else ""}
            for change in plan["changes"]
        ],
        "removals": [item["slot"] for item in plan["items"]],
        "moves": [{"slot": move["to"], "to": move["slot"]} for move in plan["moves"]],
    }
    restores = {
        "adds": [
            {"label": (old := before.cell_for_slot(slot)).label, "message": old.message}
            for slot in plan["removals"]
        ],
        "changes": [
            {
                "label": (old := before.cell_for_slot(change["slot"])).label,
                "message": old.message if old.message != old.label else "",
                "from": {
                    "label": (now := after.cell_for_slot(moved.get(change["slot"], change["slot"]))).label,
                    "message": now.message if now.message != now.label else "",
                },
            }
            for change in plan["changes"]
        ],
        "removals": [{"label": item["label"], "message": item["message"]} for item in plan["items"]],
        "moves": [
            {"label": before.cell_for_slot(move["slot"]).label, "slot": move["to"], "to": move["slot"]}
            for move in plan["moves"]
        ],
    }
    _LAST_EDIT = {
        "page": before.name,
        "grid_set": Path(active.path).stem,
        "grid": {"cols": before.cols, "rows": before.rows},
        "restores": restores,
        "warnings": ([
            "A cell that was removed comes back with a freshly searched symbol, "
            "which may differ from the one it had."
        ] if plan["removals"] else []),
        "plan": inverse,
        "fingerprint": fingerprint,
    }


def forget_last_edit() -> None:
    global _LAST_EDIT
    _LAST_EDIT = None


def last_edit():
    """What an undo would do right now, or ``None`` when there is nothing to undo."""
    if _LAST_EDIT is None:
        return None
    return copy.deepcopy({key: _LAST_EDIT[key] for key in ("page", "grid", "restores", "warnings")})


def undo_last_edit() -> dict:
    snapshot = _LAST_EDIT
    if snapshot is None:
        raise PagesetError(
            "There is no change left to undo. AAC Editor can only undo a Grid 3 edit it "
            "made while this window has been open, and only before anything else "
            "changes the grid."
        )
    plan = snapshot["plan"]
    report = edit_page(
        plan["items"], plan["changes"], plan["removals"], plan["moves"],
        snapshot["fingerprint"], _undoing=True,
    )
    report["checks"]["undone"] = "pass"
    report["warnings"] = [*report["warnings"], *snapshot["warnings"]]
    return report


def edit_page(items=(), changes=(), removals=(), moves=(), fingerprint=None,
              *, _undoing=False) -> dict:
    """Add, change, move, and remove reviewed cells on the grid open in Grid 3.

    One Edit Mode session, one save, and one rollback cover the whole edit.
    Removals run first (they free the cells a move or an addition may be aimed
    at), then moves, then changes, then additions — every slot in the request
    names the cell as it was reviewed.
    """
    normalized = _normalize_items(list(items or []))
    changes = _normalize_changes(changes)
    removals = [int(slot) for slot in removals or ()]
    moves = _normalize_moves(moves)
    if not (normalized or changes or removals or moves):
        raise PagesetError("Add at least one word or phrase.")
    if not _desktop_unlocked():
        raise PagesetError("Unlock Windows before editing Grid 3.")
    if not is_elevated():
        raise PagesetError("Restart AAC Editor with administrator access for Grid 3.")
    auto, window, active, grid = _active_context()
    if not fingerprint:
        raise PagesetError("The Grid 3 review fingerprint is required. Reconnect and review again.")
    if _fingerprint(active) != fingerprint:
        raise PagesetError("The Grid 3 grid changed after preview. Reconnect and review again.")

    # -- plan validation, entirely before any automation ----------------------
    changed = {change["slot"] for change in changes}
    moved = {move["slot"]: move["to"] for move in moves}
    if set(removals) & changed:
        raise PagesetError("A cell can't be changed and removed in the same edit.")
    if set(removals) & set(moved):
        raise PagesetError("A cell can't be moved and removed in the same edit.")
    if len(set(removals)) != len(removals) or len(moved) != len(moves):
        raise PagesetError("The reviewed Grid 3 edit names the same cell twice.")
    for slot in removals:
        _speak_cell(grid, slot, "remove")
    for change in changes:
        _speak_cell(grid, change["slot"], "change")
    for move in moves:
        _speak_cell(grid, move["slot"], "move")
    # Cells freed by a removal or a move may be reused within the same edit.
    freed = set(removals) | set(moved)
    destinations = [move["to"] for move in moves] + [item.get("slot") for item in normalized]
    if any(slot is None for slot in destinations) or len(set(destinations)) != len(destinations):
        raise PagesetError("Review and place every new or moved cell in a different empty space.")
    for slot in destinations:
        if slot not in freed:
            _blank_cell(grid, slot, "fill")
    existing = {
        cell.label.casefold() for cell in grid.cells
        if cell.label and (cell.y * grid.cols + cell.x) not in set(removals) | changed
    }
    planned = [item["label"].casefold() for item in normalized] + [
        change["label"].casefold() for change in changes if "label" in change
    ]
    duplicates = [label for label in planned if label in existing]
    if duplicates:
        raise PagesetError("Already on this grid: " + ", ".join(duplicates) + ".")
    if len(set(planned)) != len(planned):
        raise PagesetError("The reviewed Grid 3 vocabulary contains duplicate labels.")

    baseline = _semantic(grid)
    positions = _positions(grid)
    _live_cells(window, positions)
    editor = _enter_edit_mode(auto, window, active)
    undo_steps = 0
    symbols = 0
    rollback_verified = False
    restored = lambda: _semantic(_fresh_grid(active)) == baseline  # noqa: E731
    try:
        _live_cells(editor, positions, editing=True)  # every reviewed cell must be exposed
        for slot in removals:
            _select_cell(editor, _at(grid, slot))
            _activate(_ribbon_button(editor, "Delete"))
            undo_steps += 1
        for move in moves:
            _select_cell(editor, _at(grid, move["slot"]))
            _activate(_ribbon_button(editor, "Copy"))
            _select_cell(editor, _at(grid, move["to"]))
            _activate(_ribbon_button(editor, "Paste"))
            _select_cell(editor, _at(grid, move["slot"]))
            _activate(_ribbon_button(editor, "Delete"))
            undo_steps += 2
        for change in changes:
            # A change to a cell that is also moving names where it was
            # reviewed; by now that cell sits in its new square.
            _select_cell(editor, _at(grid, moved.get(change["slot"], change["slot"])))
            label, message = _spoken_after_change(grid.cell_for_slot(change["slot"]), change)
            if "label" in change:
                _label_cell(auto, editor, label)
                undo_steps += 1
            _set_message(auto, editor, message, label)
            undo_steps += 1
        for item in normalized:
            _select_cell(editor, _at(grid, item["slot"]))
            steps, found = _write_cell(auto, editor, item)
            undo_steps += steps
            symbols += found
        _save(auto)
        updated = _wait_for(
            lambda: (fresh if _semantic(fresh := _fresh_grid(active)) != baseline else None),
            "Grid 3 did not save the requested cells.", timeout=12,
        )
        after = _semantic(updated)
        touched = {_at(grid, slot) for slot in set(removals) | changed | set(moved) | set(destinations)}
        problems = []
        if after["grid"] != baseline["grid"]:
            problems.append("the grid's layout changed")
        problems.extend(
            f"cell {position} changed although it was not part of the edit"
            for position, value in baseline["cells"].items()
            if position not in touched and after["cells"].get(position) != value
        )
        for slot in removals:
            fresh = updated.cell_for_slot(slot)
            if fresh is None or not fresh.safe_blank:
                problems.append(f"cell {_at(grid, slot)} is not empty after its removal")
        for move in moves:
            was = grid.cell_for_slot(move["slot"])
            fresh = updated.cell_for_slot(move["to"])
            gone = updated.cell_for_slot(move["slot"])
            if gone is None or not gone.safe_blank:
                problems.append(f"cell {_at(grid, move['slot'])} is not empty after its move")
            if fresh is None or not (
                fresh.commands == was.commands and fresh.image == was.image
                and fresh.style == was.style and (move["slot"] in changed or (
                    fresh.label == was.label and fresh.message == was.message
                ))
            ):
                problems.append(f"“{was.label}” did not arrive intact at {_at(grid, move['to'])}")
        for change in changes:
            was = grid.cell_for_slot(change["slot"])
            fresh = updated.cell_for_slot(moved.get(change["slot"], change["slot"]))
            label, message = _spoken_after_change(was, change)
            if not _speaks(fresh, label, message):
                problems.append(
                    f"“{was.label}” now says {_said(fresh)}, not “{label}” speaking “{message}”"
                )
            elif fresh.style != was.style:
                problems.append(f"“{label}” lost its style")
        for item in normalized:
            # Grid 3 gives a freshly written blank its own Write-cell style
            # ("Vocab cell"), so a new cell is verified on content, not style.
            fresh = updated.cell_for_slot(item["slot"])
            if not _speaks(fresh, item["label"], item["message"]):
                problems.append(
                    f"cell {_at(grid, item['slot'])} says {_said(fresh)}, not “{item['label']}”"
                    f" speaking “{item['message'] or item['label']}”"
                )
        if problems:
            _rollback_saved(auto, restored, max(undo_steps, len(normalized) * 4) + 8)
            rollback_verified = True
            raise PagesetError(
                "Grid 3 did not save what was reviewed, so the original grid was "
                "restored: " + "; ".join(problems) + "."
            )
    except Exception:
        if not rollback_verified:
            if restored():
                _restore_unsaved(auto, undo_steps)
            else:
                _rollback_saved(auto, restored, max(undo_steps, len(normalized) * 4) + 8)
        _leave_edit_mode(auto)
        raise
    _leave_edit_mode(auto)
    plan = {"items": normalized, "changes": changes, "removals": removals, "moves": moves}
    if _undoing:
        forget_last_edit()
    else:
        _remember(active, grid, updated, plan, _fingerprint(active))
    expected_symbols = sum(item.get("symbol", True) for item in normalized)
    checks = {
        "grid3_edit": "pass", "target_grid": "pass", "content": "pass",
        "positions": "pass", "style_preserved": "pass", "untouched_buttons": "pass",
        "save_completed": "pass",
    }
    if changes:
        checks["changed_content"] = "pass"
    if moves:
        checks["moved_buttons"] = "pass"
    if removals:
        checks["removed_buttons"] = "pass"
    if normalized:
        checks["symbols"] = "pass" if symbols == expected_symbols else "partial"
    return {
        "page": grid.name,
        "grid_set": Path(active.path).stem,
        "buttons": len(normalized),
        "changed": len(changes), "moved": len(moves), "removed": len(removals),
        "checks": checks,
        "warnings": ([
            f"Grid 3 could not choose a verified symbol for {expected_symbols - symbols} cell(s)."
        ] if symbols < expected_symbols else []),
    }


def add_to_existing_page(items, fingerprint=None) -> dict:
    return edit_page(items, fingerprint=fingerprint)


# ---------------------------------------------------------------------------
# creating and linking a grid


def add_topic_page(title, items, link_slot=None, fingerprint=None) -> dict:
    """Create a new grid, populate it, and link it from a blank on the open grid.

    Grid 3's own "Create cell → Jump to → New grid" flow does the creating, so
    the new grid carries whatever Grid 3 gives a new grid in this grid set:
    the parent's column and row count, and a Back cell in the top-left
    square. Its Rows/Columns pickers are deliberately left untouched — their
    result depends on how they are driven rather than on the value chosen —
    so the new grid is always the parent's size.
    """
    title = str(title or "").strip()
    normalized = _normalize_items(items)
    if not title:
        raise PagesetError("Give the new grid a name.")
    if not normalized:
        raise PagesetError("Add at least one word or phrase.")
    if not _desktop_unlocked():
        raise PagesetError("Unlock Windows before editing Grid 3.")
    if not is_elevated():
        raise PagesetError("Restart AAC Editor with administrator access for Grid 3.")
    auto, window, active, grid = _active_context()
    if not fingerprint:
        raise PagesetError("The Grid 3 review fingerprint is required. Reconnect and review again.")
    if _fingerprint(active) != fingerprint:
        raise PagesetError("The Grid 3 grid changed after preview. Reconnect and review again.")
    if title.casefold() in _grid_names(active):
        raise PagesetError(f"A grid named “{title}” already exists in this grid set.")
    if link_slot is None:
        link_slot = next(
            (cell.y * grid.cols + cell.x for cell in grid.cells if cell.safe_blank), None
        )
        if link_slot is None:
            raise PagesetError(
                f"“{grid.name}” has no safe empty cell to hold the link to the new grid."
            )
    link = _blank_cell(grid, link_slot, "hold the link")
    slots = [item.get("slot") for item in normalized]
    if any(slot is None for slot in slots) or len(set(slots)) != len(slots):
        raise PagesetError("Review and place every new cell in a different empty space.")
    new_positions = {(x, y) for y in range(grid.rows) for x in range(grid.cols)}
    for slot in slots:
        position = _at(grid, slot)
        if position == (0, 0) or position not in new_positions:
            raise PagesetError(
                "Every new cell must sit inside the new grid, and not in its top-left "
                "square, which Grid 3 uses for the Back cell."
            )
    labels = [item["label"].casefold() for item in normalized]
    if len(set(labels)) != len(labels):
        raise PagesetError("The reviewed Grid 3 vocabulary contains duplicate labels.")

    baseline = _semantic(grid)
    positions = _positions(grid)
    _live_cells(window, positions)
    editor = _enter_edit_mode(auto, window, active)
    undo_steps = 0
    symbols = 0
    rollback_verified = False

    def restored() -> bool:
        return (
            _semantic(_fresh_grid(active)) == baseline
            and title.casefold() not in _grid_names(active)
        )

    try:
        _live_cells(editor, positions, editing=True)  # every reviewed cell must be exposed
        _select_cell(editor, (link.x, link.y))
        _activate(_wait_for(
            lambda: _button_by_text(editor, "Create Cell", depth=6),
            "Grid 3's Create Cell control was not accessible.",
        ))
        dialog = _wait_for(
            lambda: _dialog(auto, "Create Cell"), "Grid 3's Create Cell dialog did not open."
        )
        _activate(_wait_for(
            lambda: _find_id(dialog, "Jump to"), "Grid 3's Jump to cell type was not accessible."
        ))
        _activate(_wait_for(
            lambda: _find_id(dialog, "OKButton", 6), "Grid 3's OK control was not accessible."
        ))
        # The Jump to page draws a thumbnail of every grid in the set before
        # its buttons respond, which on a large set takes well over the
        # usual wait.
        _activate(_wait_for(
            lambda: _button_by_text(dialog, "New Grid"),
            "Grid 3's New Grid control was not accessible.", timeout=30,
        ))
        name_field = _wait_for(
            lambda: _field_after(dialog, "Name for new grid"),
            "Grid 3's new grid name field was not accessible.", timeout=20,
        )
        setter = getattr(name_field, "GetValuePattern", lambda: None)()
        if setter is None:
            raise PagesetError("Grid 3's new grid name field did not accept a value.")
        setter.SetValue(title)
        _activate(_wait_for(
            lambda: _find_id(dialog, "OKButton", 6), "Grid 3's OK control was not accessible."
        ))
        undo_steps += 1
        _wait_for(
            lambda: _dialog(auto, "Create Cell") is None and _dirty(auto),
            "Grid 3 did not create the linked grid.",
        )
        _wait_for(
            lambda: _find_named(editor, f"Jump to {title}"),
            "Grid 3 did not link the new grid from the reviewed cell.",
        )
        _activate(_wait_for(
            lambda: _find_id(editor, "FollowJump_ButtonCommandParameter", 14),
            "Grid 3's Follow Jump control was not accessible.",
        ))
        _wait_for(
            lambda: _active_from_title(_title_of(auto)).grid_name.casefold() == title.casefold(),
            "Grid 3 did not open the new grid for editing.",
        )
        editor = _window(auto)
        _live_cells(editor, new_positions, editing=True)  # the new grid, fully exposed
        for item in normalized:
            _select_cell(editor, _at(grid, item["slot"]))
            steps, found = _write_cell(auto, editor, item)
            undo_steps += steps
            symbols += found
        _save(auto)
        created = _wait_for(
            lambda: _fresh_grid(active, title), "Grid 3 did not save the new grid.", timeout=12,
        )
        parent = _fresh_grid(active)
        after = _semantic(parent)
        problems = []
        if after["grid"] != baseline["grid"]:
            problems.append(f"the layout of “{grid.name}” changed")
        problems.extend(
            f"cell {position} of “{grid.name}” changed although it was not part of the edit"
            for position, value in baseline["cells"].items()
            if position != (link.x, link.y) and after["cells"].get(position) != value
        )
        linked = parent.cell_at(link.x, link.y)
        if linked is None or "Jump.To" not in linked.commands or linked.label != title:
            problems.append(f"cell {(link.x, link.y)} of “{grid.name}” does not jump to “{title}”")
        if (created.cols, created.rows) != (grid.cols, grid.rows):
            problems.append(
                f"“{title}” is {created.cols} by {created.rows}, not {grid.cols} by {grid.rows}"
            )
        back = created.cell_at(0, 0)
        if back is None or "Jump.Back" not in back.commands:
            problems.append(f"“{title}” has no Back cell in its top-left square")
        filled = {_at(grid, item["slot"]) for item in normalized}
        for item in normalized:
            fresh = created.cell_at(*_at(grid, item["slot"]))
            if not _speaks(fresh, item["label"], item["message"]):
                problems.append(
                    f"cell {_at(grid, item['slot'])} of “{title}” says {_said(fresh)}, not "
                    f"“{item['label']}” speaking “{item['message'] or item['label']}”"
                )
        problems.extend(
            f"cell {(cell.x, cell.y)} of “{title}” is not empty"
            for cell in created.cells
            if (cell.x, cell.y) not in filled and (cell.x, cell.y) != (0, 0) and not cell.safe_blank
        )
        if problems:
            _rollback_saved(auto, restored, max(undo_steps, len(normalized) * 4) + 8)
            rollback_verified = True
            raise PagesetError(
                "Grid 3 did not save what was reviewed, so the original grid was "
                "restored: " + "; ".join(problems) + "."
            )
    except Exception:
        if not rollback_verified:
            if restored():
                _restore_unsaved(auto, undo_steps)
            else:
                _rollback_saved(auto, restored, max(undo_steps, len(normalized) * 4) + 8)
        _leave_edit_mode(auto)
        raise
    _leave_edit_mode(auto)
    forget_last_edit()
    expected_symbols = sum(item.get("symbol", True) for item in normalized)
    return {
        "page": title,
        "parent": grid.name,
        "grid_set": Path(active.path).stem,
        "buttons": len(normalized),
        "checks": {
            "grid3_edit": "pass", "created_grid": "pass", "linked_grid": "pass",
            "content": "pass", "positions": "pass", "untouched_buttons": "pass",
            "save_completed": "pass",
            "symbols": "pass" if symbols == expected_symbols else "partial",
        },
        "warnings": ([
            f"Grid 3 could not choose a verified symbol for {expected_symbols - symbols} cell(s)."
        ] if symbols < expected_symbols else []),
    }
