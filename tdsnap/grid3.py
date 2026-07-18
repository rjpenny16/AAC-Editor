"""Read and edit the grid currently open in Grid 3 on Windows.

Grid-set packages are read only here.  Grid 3 performs every mutation and save
so its sync identity and versioning remain intact.
"""

from __future__ import annotations

import ctypes
import glob
import hashlib
import os
import sys
import time
import zipfile
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional
from xml.etree import ElementTree as ET

from .builder import _normalize_items
from .errors import PagesetError
from .live import _desktop_unlocked, _focus_window


GRID3_EXE = os.path.join(
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
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


@dataclass(frozen=True)
class Grid3Style:
    key: str = "Default"
    background: Optional[str] = None
    border: Optional[str] = None
    foreground: Optional[str] = None


@dataclass(frozen=True)
class Grid3Cell:
    x: int
    y: int
    column_span: int
    row_span: int
    label: str
    image: Optional[str]
    commands: tuple[str, ...]
    content_type: Optional[str]
    content_subtype: Optional[str]
    style: Grid3Style
    message: Optional[str]
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
    background: Optional[str]

    def cell_at(self, x: int, y: int) -> Optional[Grid3Cell]:
        return next((cell for cell in self.cells if cell.x == x and cell.y == y), None)

    def cell_for_slot(self, slot: int) -> Optional[Grid3Cell]:
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
    if sys.platform != "win32":
        raise PagesetError("Live Grid 3 editing is available on Windows only.")
    try:
        import uiautomation as auto
    except ImportError as exc:
        raise PagesetError(
            "Windows automation is not installed. Reinstall AAC Editor."
        ) from exc
    auto.SetGlobalSearchTimeout(2)
    return auto


def _walk(root, max_depth=10):
    queue = [(root, 0)]
    while queue:
        control, depth = queue.pop(0)
        yield control, depth
        if depth < max_depth:
            try:
                queue.extend((child, depth + 1) for child in control.GetChildren())
            except Exception:
                continue


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

    @callback_type
    def collect(handle, _parameter):
        length = user32.GetWindowTextLengthW(handle)
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


def _process_path(process_id: int) -> Optional[str]:
    if sys.platform != "win32" or not process_id:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    process = kernel32.OpenProcess(0x1000, False, process_id)
    if not process:
        return None
    try:
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
            return path.value
    finally:
        kernel32.CloseHandle(process)
    return None


def _verify_process(window) -> None:
    actual = _process_path(getattr(window, "ProcessId", 0))
    expected = os.path.realpath(_grid3_exe())
    if not actual:
        raise PagesetError("AAC Editor could not verify the Grid 3 process executable.")
    if os.path.normcase(os.path.realpath(actual)) != os.path.normcase(expected):
        raise PagesetError("The detected window is not the installed Grid 3 application.")


def _file_version(path: str) -> Optional[str]:
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
        raise PagesetError("Protected .gridsetx files (including WordPower) are not supported.")
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


def _text(node: Optional[ET.Element], path: str) -> Optional[str]:
    if node is None:
        return None
    found = node.find(path)
    if found is None:
        return None
    value = "".join(found.itertext()).strip()
    return value or None


def _rich_text(node: Optional[ET.Element], path: str = ".") -> Optional[str]:
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


def _css_color(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if len(value) == 9 and value.startswith("#"):
        return value[:7]
    return value if len(value) in {4, 7} and value.startswith("#") else None


class Grid3Package:
    def __init__(self, path: str):
        if path.lower().endswith(".gridsetx"):
            raise PagesetError("Protected .gridsetx files are not supported.")
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
            return ET.fromstring(self._bytes(name))
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

    def _styles(self) -> Dict[str, Grid3Style]:
        root = self._xml("Settings0/Styles/styles.xml")
        raw = {node.get("Key", ""): node for node in root.findall("./Styles/Style")}
        cache: Dict[str, Grid3Style] = {}

        def resolve(key: str, seen=()) -> Grid3Style:
            if key in cache:
                return cache[key]
            if key in seen:
                return Grid3Style(key=key)
            node = raw.get(key)
            if node is None:
                return Grid3Style(key=key)
            parent_key = _text(node, "BasedOnStyle")
            parent = resolve(parent_key, seen + (key,)) if parent_key else Grid3Style()
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
    except Exception:
        pass
    return None


def _clusters(values: Iterable[int], tolerance=6) -> tuple[int, ...]:
    groups: list[list[int]] = []
    for value in sorted(values):
        if not groups or value - round(sum(groups[-1]) / len(groups[-1])) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return tuple(round(sum(group) / len(group)) for group in groups)


def _live_cells(
    window, grid: Grid3Grid,
    expected: Optional[Dict[tuple[int, int], _LiveCell]] = None,
) -> Dict[tuple[int, int], _LiveCell]:
    """Return accessible controls mapped to XML coordinates, or fail closed."""
    if expected is not None:
        by_rect = {}
        for control, _ in _walk(window, 9):
            rect = _rect(control)
            if getattr(control, "ControlTypeName", "") in _CELL_TYPES and rect:
                by_rect.setdefault((rect.left, rect.top, rect.right, rect.bottom), control)
        return {
            position: _LiveCell(control, item.rect)
            for position, item in expected.items()
            if (control := by_rect.get((
                item.rect.left, item.rect.top, item.rect.right, item.rect.bottom,
            )))
        }
    labels = {cell.label.casefold() for cell in grid.cells if cell.label}
    if not labels:
        raise PagesetError(
            "Grid 3 exposed no named existing cell that AAC Editor could use to verify the layout."
        )
    best = None
    for container, _ in _walk(window, 9):
        try:
            children = [child for child in container.GetChildren() if _rect(child)]
        except Exception:
            continue
        children = [
            child for child in children
            if child.ControlTypeName in _CELL_TYPES and _rect(child)
        ]
        if len(children) < min(4, len(grid.cells)) or len(children) > len(grid.cells) * 2:
            continue
        xs = _clusters(_rect(child).left for child in children)
        ys = _clusters(_rect(child).top for child in children)
        if len(xs) != grid.cols or len(ys) != grid.rows:
            continue
        matched = sum(1 for child in children if (child.Name or "").strip().casefold() in labels)
        required = min(3, len(labels))
        if matched < required:
            continue
        score = (matched, -abs(len(children) - len(grid.cells)))
        if best is None or score > best[0]:
            best = (score, children, xs, ys)
    if best is None:
        raise PagesetError(
            "Grid 3 did not expose a verifiable accessible cell grid. "
            "AAC Editor will not use unverified screen coordinates."
        )
    _, children, xs, ys = best
    mapped: Dict[tuple[int, int], _LiveCell] = {}
    for child in children:
        rect = _rect(child)
        x = min(range(len(xs)), key=lambda index: abs(xs[index] - rect.left))
        y = min(range(len(ys)), key=lambda index: abs(ys[index] - rect.top))
        existing = mapped.get((x, y))
        if existing is None or (
            (rect.right - rect.left) * (rect.bottom - rect.top)
            > (existing.rect.right - existing.rect.left)
            * (existing.rect.bottom - existing.rect.top)
        ):
            mapped[(x, y)] = _LiveCell(child, rect)
    return mapped


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


def inspect_page() -> dict:
    if not is_elevated():
        raise PagesetError("Restart AAC Editor with administrator access for Grid 3.")
    auto, window, active, grid = _active_context()
    live = _live_cells(window, grid)
    live_rects = [item.rect for item in live.values()]
    grid_left = min(rect.left for rect in live_rects)
    grid_top = min(rect.top for rect in live_rects)
    grid_right = max(rect.right for rect in live_rects)
    grid_bottom = max(rect.bottom for rect in live_rects)
    grid_width = max(1, grid_right - grid_left)
    grid_height = max(1, grid_bottom - grid_top)
    cells = []
    free_slots = []
    for cell in grid.cells:
        control = live.get((cell.x, cell.y))
        rect = control.rect if control else None
        slot = cell.y * grid.cols + cell.x
        if cell.safe_blank and control:
            free_slots.append(slot)
        cells.append({
            "slot": slot, "x": cell.x, "y": cell.y,
            "column_span": cell.column_span, "row_span": cell.row_span,
            "label": cell.label, "occupied": not cell.safe_blank,
            "safe_blank": bool(cell.safe_blank and control),
            "image": bool(cell.image), "style": {
                "key": cell.style.key, "background": cell.style.background,
                "border": cell.style.border, "foreground": cell.style.foreground,
            },
            "rect": ({
                "left": (rect.left - grid_left) / grid_width,
                "top": (rect.top - grid_top) / grid_height,
                "width": (rect.right - rect.left) / grid_width,
                "height": (rect.bottom - rect.top) / grid_height,
            } if rect else None),
        })
    return {
        "supported": True,
        "grid_set": Path(active.path).stem,
        "page": grid.name,
        "grid": {"cols": grid.cols, "rows": grid.rows},
        "background": grid.background,
        "preview_aspect": grid_width / grid_height,
        "buttons": [
            {"slot": cell["slot"], "label": cell["label"], "existing": True}
            for cell in cells if cell["occupied"]
        ],
        "cells": cells,
        "free_slots": free_slots,
        "fingerprint": _fingerprint(active),
    }


def _send(auto, keys: str, wait=0.35) -> None:
    auto.SendKeys(keys, waitTime=wait)


def _find_named(window, name: str, control_type=None):
    wanted = name.casefold()
    for control, _ in _walk(window, 12):
        if (control.Name or "").strip().casefold() == wanted and (
            control_type is None or control.ControlTypeName == control_type
        ):
            return control
    return None


def _require_normal_mode(window) -> None:
    if _find_named(window, "Finish Editing"):
        raise PagesetError("Finish the existing Grid 3 Edit Mode session, then reconnect.")


def _wait_for_edit_mode(window) -> None:
    _wait_for(
        lambda: _find_named(window, "Finish Editing"),
        "Grid 3 did not enter a verifiable Edit Mode after F11.",
    )


def _activate(control) -> None:
    if control is None:
        raise PagesetError("Grid 3's editor controls changed during the edit.")
    getter = getattr(control, "GetInvokePattern", None)
    pattern = getter() if getter else None
    if pattern:
        pattern.Invoke()
    else:
        control.Click(simulateMove=False)


def _wait_for(callback, message, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = callback()
        except (OSError, zipfile.BadZipFile, KeyError):
            value = None
        if value:
            return value
        time.sleep(0.15)
    raise PagesetError(message)


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


def _fresh_grid(active: ActiveGrid3) -> Grid3Grid:
    with Grid3Package(active.path) as package:
        return package.grid(active.grid_name)


def _undo(auto, steps: int) -> None:
    for _ in range(steps):
        _send(auto, "{Ctrl}z", wait=0.08)


def _send_text(auto, value: str) -> None:
    """Type literal user text without treating braces as automation keys."""
    auto.SendKeys(value, interval=0.01, waitTime=0.15, charMode=True)


def _restore_unsaved(auto, window, maximum: int) -> None:
    """Undo only until Grid 3 reports the originally clean document again."""
    for _ in range(maximum + 3):
        if not (window.Name or "").rstrip().endswith("*"):
            return
        _send(auto, "{Ctrl}z", wait=0.12)
    raise PagesetError("Grid 3 could not restore the clean pre-edit state.")


def _rollback_saved(auto, window, active, baseline, maximum: int) -> None:
    """Undo and save one history step at a time, stopping exactly at baseline."""
    for _ in range(maximum):
        _send(auto, "{Ctrl}z", wait=0.1)
        _send(auto, "{Ctrl}s", wait=0.35)
        _wait_for(
            lambda: not (window.Name or "").rstrip().endswith("*"),
            "Grid 3 did not finish saving the rollback.", timeout=4,
        )
        try:
            if _semantic(_fresh_grid(active)) == baseline:
                return
        except (OSError, zipfile.BadZipFile, PagesetError):
            pass
    raise PagesetError("Grid 3 could not restore the verified pre-edit content.")


def _set_message(window, message: str) -> None:
    toggle = _find_named(window, "Same as cell label")
    if toggle:
        _activate(toggle)
    edits = [control for control, _ in _walk(window, 12)
             if control.ControlTypeName == "EditControl" and _rect(control)]
    if not edits:
        raise PagesetError("Grid 3's separate spoken-text field was not accessible.")
    field = min(edits, key=lambda control: _rect(control).left)
    setter = getattr(field, "GetValuePattern", lambda: None)()
    if setter:
        setter.SetValue(message)
    else:
        _activate(field)
        auto = _automation()
        _send(auto, "{Ctrl}a", wait=0.05)
        _send_text(auto, message)


def _try_symbol(window, label: str) -> bool:
    find_picture = _find_named(window, "Find Picture", "ButtonControl")
    if not find_picture:
        return False
    try:
        _activate(find_picture)
        exact = _wait_for(
            lambda: _find_named(window, label),
            "", timeout=3,
        )
        if exact:
            _activate(exact)
            ok = _find_named(window, "OK", "ButtonControl")
            if ok:
                _activate(ok)
            return True
    except PagesetError:
        pass
    cancel = _find_named(window, "Cancel", "ButtonControl")
    if cancel:
        _activate(cancel)
    return False


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
    _require_normal_mode(window)
    normal_live = _live_cells(window, grid)
    _focus_window(window)
    _send(auto, "{F11}")
    try:
        _wait_for_edit_mode(window)
        live = _live_cells(window, _fresh_grid(active), normal_live)
        target = live.get((blank.x, blank.y))
        if target is None:
            raise PagesetError("The compatibility check could not access the safe empty cell.")
        _activate(target.control)
        _send(auto, "{Ctrl}w")
        undo_steps += 1
        _wait_for(
            lambda: _find_named(window, "Write"),
            "Grid 3 did not expose the provisional Write command.",
        )
        change_label = _wait_for(
            lambda: _find_named(window, "Change Label", "ButtonControl"),
            "Grid 3's Change Label control was not accessible.",
        )
        _activate(change_label)
        _send_text(auto, probe_label)
        _send(auto, "{Enter}")
        undo_steps += 1
        _wait_for(
            lambda: (window.Name or "").rstrip().endswith("*"),
            "Grid 3 did not report the provisional compatibility edit.",
        )
        _restore_unsaved(auto, window, undo_steps)
        _wait_for(
            lambda: _semantic(_fresh_grid(active)) == baseline,
            "The compatibility check could not verify the unchanged grid-set file.",
        )
        if _fingerprint(active) != before:
            raise PagesetError("The Grid 3 file changed during the compatibility check.")
    except Exception:
        _restore_unsaved(auto, window, undo_steps)
        _send(auto, "{F11}")
        raise
    _send(auto, "{F11}")
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


def add_to_existing_page(items, fingerprint=None) -> dict:
    normalized = _normalize_items(items)
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
    baseline = _semantic(grid)
    existing = {cell.label.casefold() for cell in grid.cells if cell.label}
    duplicates = [item["label"] for item in normalized if item["label"].casefold() in existing]
    if duplicates:
        raise PagesetError("Already on this grid: " + ", ".join(duplicates) + ".")
    planned = [item["label"].casefold() for item in normalized]
    if len(set(planned)) != len(planned):
        raise PagesetError("The reviewed Grid 3 vocabulary contains duplicate labels.")
    slots = [item.get("slot") for item in normalized]
    if any(slot is None for slot in slots) or len(set(slots)) != len(slots):
        raise PagesetError("Review and place every new cell in a different empty space.")
    targets = [grid.cell_for_slot(slot) for slot in slots]
    if any(cell is None or not cell.safe_blank for cell in targets):
        raise PagesetError("One or more selected Grid 3 cells are not safe empty cells.")

    _require_normal_mode(window)
    normal_live = _live_cells(window, grid)
    _focus_window(window)
    _send(auto, "{F11}")
    undo_steps = 0
    symbols = 0
    rollback_verified = False
    try:
        _wait_for_edit_mode(window)
        reopened = _active_from_title(window.Name or "")
        if (reopened.path, reopened.grid_name) != (active.path, active.grid_name):
            raise PagesetError("Grid 3 changed grids while entering Edit Mode.")
        edit_grid = _fresh_grid(active)
        live = _live_cells(window, edit_grid, normal_live)
        for item, cell in zip(normalized, targets):
            target = live.get((cell.x, cell.y))
            if target is None:
                raise PagesetError("A selected empty cell was not accessible in Grid 3 Edit Mode.")
            _activate(target.control)
            _send(auto, "{Ctrl}w")
            undo_steps += 1
            change_label = _wait_for(
                lambda: _find_named(window, "Change Label", "ButtonControl"),
                "Grid 3's Change Label control was not accessible.",
            )
            _activate(change_label)
            _send_text(auto, item["label"])
            _send(auto, "{Enter}")
            undo_steps += 1
            if item["message"]:
                _set_message(window, item["message"])
                undo_steps += 1
            if item.get("symbol", True) and _try_symbol(window, item["label"]):
                symbols += 1
                undo_steps += 1
        _send(auto, "{Ctrl}s", wait=0.6)
        updated = _wait_for(
            lambda: (
                fresh if _semantic(fresh := _fresh_grid(active)) != baseline else None
            ),
            "Grid 3 did not save the requested cells.", timeout=12,
        )
        after = _semantic(updated)
        target_positions = {(cell.x, cell.y) for cell in targets}
        baseline_cells = baseline["cells"]
        after_cells = after["cells"]
        unchanged = all(
            after_cells.get(position) == value
            for position, value in baseline_cells.items()
            if position not in target_positions
        ) and after["grid"] == baseline["grid"]
        verified = all(
            (fresh := updated.cell_at(cell.x, cell.y)) is not None
            and fresh.label == item["label"]
            and "Action.InsertText" in fresh.commands
            and fresh.message == (item["message"] or item["label"])
            and fresh.style == cell.style
            for item, cell in zip(normalized, targets)
        )
        if not unchanged or not verified:
            _rollback_saved(
                auto, window, active, baseline,
                max(undo_steps, len(normalized) * 4) + 8,
            )
            rollback_verified = True
            raise PagesetError("Grid 3 did not verify the edit; the original grid was restored.")
    except Exception:
        if not rollback_verified:
            if _semantic(_fresh_grid(active)) == baseline:
                _restore_unsaved(auto, window, undo_steps)
            else:
                _rollback_saved(
                    auto, window, active, baseline,
                    max(undo_steps, len(normalized) * 4) + 8,
                )
        _send(auto, "{F11}")
        raise
    _send(auto, "{F11}")
    expected_symbols = sum(item.get("symbol", True) for item in normalized)
    return {
        "page": grid.name,
        "grid_set": Path(active.path).stem,
        "buttons": len(normalized),
        "checks": {
            "grid3_edit": "pass", "target_grid": "pass", "content": "pass",
            "positions": "pass", "style_preserved": "pass", "save_completed": "pass",
            "symbols": "pass" if symbols == expected_symbols else "partial",
        },
        "warnings": ([
            f"Grid 3 could not choose a verified symbol for {expected_symbols - symbols} cell(s)."
        ] if symbols < expected_symbols else []),
    }
