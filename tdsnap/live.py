"""Edit the open TD Snap page set through Windows UI Automation.

The word model decides what to add; this module only performs the repeatable
TD Snap workflow.  It intentionally uses TD Snap's accessibility controls
before adding a vision model: those controls are faster, smaller, and expose
the current page, buttons, edit fields, and navigation directly.
"""

import argparse
import ctypes
import json
import os
import statistics
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

from .builder import _normalize_items
from .errors import PagesetError

DEFAULT_PARENT = "Topics Menu Page"
_EXCLUDED_GROUPS = {"Message Bar", "Tool Bar"}


@dataclass(frozen=True)
class Grid:
    xs: tuple
    ys: tuple
    cell_width: int
    cell_height: int


@dataclass(frozen=True)
class Cell:
    x: int
    y: int
    width: int
    height: int


def _desktop_unlocked() -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.GetUserObjectInformationW.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetUserObjectInformationW.restype = wintypes.BOOL
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    desktop = user32.OpenInputDesktop(0, False, 0x0100)
    if not desktop:
        return False
    try:
        needed = ctypes.c_ulong()
        buffer = ctypes.create_unicode_buffer(256)
        if not user32.GetUserObjectInformationW(
            desktop, 2, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)
        ):
            return False
        if buffer.value.casefold() != "default":
            return False
    finally:
        user32.CloseDesktop(desktop)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    foreground = user32.GetForegroundWindow()
    if not foreground:
        return True
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    process = kernel32.OpenProcess(0x1000, False, process_id.value)
    if not process:
        return True
    try:
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if not kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(length)):
            return True
        return os.path.basename(path.value).casefold() not in {"lockapp.exe", "logonui.exe"}
    finally:
        kernel32.CloseHandle(process)


def _automation():
    if sys.platform != "win32":
        raise PagesetError("Direct TD Snap editing is available on Windows only.")
    try:
        import uiautomation as auto
    except ImportError as exc:
        raise PagesetError(
            "Windows automation is not installed. Reinstall the app or run "
            "'pip install uiautomation'."
        ) from exc
    auto.SetGlobalSearchTimeout(2)
    return auto


def _walk(root, max_depth=9):
    queue = [(root, 0)]
    while queue:
        control, depth = queue.pop(0)
        yield control, depth
        if depth < max_depth:
            queue.extend((child, depth + 1) for child in control.GetChildren())


def _matches(control, *, name=None, automation_id=None, control_type=None):
    return (
        (name is None or (control.Name or "").casefold() == name.casefold())
        and (automation_id is None or control.AutomationId == automation_id)
        and (control_type is None or control.ControlTypeName == control_type)
    )


def _find(root, **criteria):
    for control, _ in _walk(root):
        if _matches(control, **criteria):
            return control
    return None


def _find_text(root, text):
    wanted = text.casefold()
    matches = []
    for control, _ in _walk(root):
        rect = control.BoundingRectangle
        if (
            wanted in (control.Name or "").casefold()
            and rect.right > rect.left
            and rect.bottom > rect.top
        ):
            matches.append(control)
    interactive = {"ButtonControl", "ListItemControl", "EditControl"}
    return next((c for c in matches if c.ControlTypeName in interactive), None) or (
        matches[0] if matches else None
    )


def _activate(control):
    if control is None:
        raise PagesetError("TD Snap changed while the edit was running.")
    getter = getattr(control, "GetInvokePattern", None)
    pattern = getter() if getter else None
    if pattern:
        pattern.Invoke()
        return
    getter = getattr(control, "GetSelectionItemPattern", None)
    pattern = getter() if getter else None
    if pattern:
        pattern.Select()
        return
    control.Click(simulateMove=False)


def _wait_for(callback, message, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = callback()
        if value:
            return value
        time.sleep(0.15)
    raise PagesetError(message)


def _window(auto):
    window = auto.WindowControl(searchDepth=1, Name="TD Snap")
    if not window.Exists(1):
        raise PagesetError("Open TD Snap before using direct editing.")
    return window


def _page_group(window):
    candidates = []
    for control, _ in _walk(window, 5):
        rect = control.BoundingRectangle
        if (
            control.ControlTypeName == "GroupControl"
            and control.Name not in _EXCLUDED_GROUPS
            and rect.right - rect.left > 400
        ):
            candidates.append(control)
    if not candidates:
        raise PagesetError("TD Snap's current page could not be identified.")
    return max(candidates, key=lambda c: c.BoundingRectangle.right - c.BoundingRectangle.left)


def _clusters(values, tolerance=8):
    groups = []
    for value in sorted(values):
        if not groups or value - statistics.mean(groups[-1]) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return tuple(round(statistics.mean(group)) for group in groups)


def _grid(group):
    buttons = [
        child for child in group.GetChildren()
        if child.ControlTypeName == "ButtonControl"
        and child.BoundingRectangle.right > child.BoundingRectangle.left
    ]
    if not buttons:
        raise PagesetError("TD Snap's button grid could not be measured.")
    rects = [button.BoundingRectangle for button in buttons]
    xs = _clusters([(rect.left + rect.right) // 2 for rect in rects])
    ys = _clusters([(rect.top + rect.bottom) // 2 for rect in rects])
    if len(xs) < 2 or len(ys) < 2:
        raise PagesetError("TD Snap's button grid is too sparse to measure safely.")
    widths = [rect.right - rect.left for rect in rects]
    heights = [rect.bottom - rect.top for rect in rects]
    return Grid(xs, ys, round(statistics.median(widths)), round(statistics.median(heights)))


def _fingerprint(group):
    return tuple(
        sorted(
            (child.Name, child.BoundingRectangle.left, child.BoundingRectangle.top)
            for child in group.GetChildren()
            if child.ControlTypeName == "ButtonControl"
        )
    )


def _first_empty(grid, rectangles):
    for y in grid.ys:
        for x in grid.xs:
            if not any(
                rect.left <= x <= rect.right and rect.top <= y <= rect.bottom
                for rect in rectangles
            ):
                return Cell(x, y, grid.cell_width, grid.cell_height)
    return None


def _empty_cell(window, grid, allow_scroll=True):
    seen = set()
    while True:
        group = _page_group(window)
        fingerprint = _fingerprint(group)
        if fingerprint in seen:
            raise PagesetError("TD Snap's page grid looped without finding an empty cell.")
        seen.add(fingerprint)
        buttons = [
            child for child in group.GetChildren()
            if child.ControlTypeName == "ButtonControl"
        ]
        empty = _first_empty(grid, [button.BoundingRectangle for button in buttons])
        if empty:
            return empty
        if not allow_scroll:
            raise PagesetError("The new TD Snap page has no empty cells.")
        down = [
            button for button in buttons
            if not button.Name
            and (button.BoundingRectangle.top + button.BoundingRectangle.bottom) // 2
            >= max(grid.ys) - 8
        ]
        if not down:
            raise PagesetError("The parent page is full; no link button will fit.")
        before = fingerprint
        _activate(max(down, key=lambda c: c.BoundingRectangle.left))
        _wait_for(
            lambda: _fingerprint(_page_group(window)) != before,
            "TD Snap did not move to the next grid screen.",
        )


def _collapse_editor(window):
    group = _page_group(window)
    window_rect = window.BoundingRectangle
    group_rect = group.BoundingRectangle
    if group_rect.bottom >= window_rect.bottom - 100:
        return
    candidates = []
    for control, _ in _walk(window, 5):
        rect = control.BoundingRectangle
        if (
            control.ControlTypeName == "ButtonControl"
            and not control.AutomationId
            and 35 <= rect.right - rect.left <= 70
            and 35 <= rect.bottom - rect.top <= 70
            and rect.left <= window_rect.left + 20
            and abs(rect.top - group_rect.bottom) <= 8
        ):
            candidates.append(control)
    if not candidates:
        raise PagesetError("TD Snap's editing panel could not be collapsed.")
    old_bottom = group_rect.bottom
    _activate(candidates[0])
    _wait_for(
        lambda: _page_group(window).BoundingRectangle.bottom > old_bottom + 100,
        "TD Snap's editing panel did not collapse.",
    )


def _exit_edit_mode(window):
    done = _find(window, automation_id="DoneButton", control_type="ButtonControl")
    if done:
        _activate(done)
        _wait_for(
            lambda: _find(window, automation_id="settings_button", control_type="ButtonControl"),
            "TD Snap did not leave edit mode.",
        )


def _enter_edit_mode(window):
    if _find(window, automation_id="DoneButton", control_type="ButtonControl"):
        return
    _activate(_find(window, automation_id="settings_button", control_type="ButtonControl"))
    _wait_for(
        lambda: _find(window, automation_id="DoneButton", control_type="ButtonControl"),
        "TD Snap did not enter edit mode.",
    )


def _navigate_to_parent(window, parent):
    _exit_edit_mode(window)
    if _page_group(window).Name == parent:
        return
    if parent != DEFAULT_PARENT:
        raise PagesetError(
            f"Open {parent!r} in TD Snap first. Automatic navigation currently supports "
            f"{DEFAULT_PARENT!r}."
        )
    toolbar = _find(window, name="Tool Bar", control_type="GroupControl")
    topic_button = _find(toolbar, name="Topics", control_type="ButtonControl")
    _activate(topic_button)
    _wait_for(
        lambda: _page_group(window).Name == parent,
        f"TD Snap did not open {parent!r}.",
    )


def _undo_if_needed(window):
    undo = _find(window, automation_id="UndoButton", control_type="ButtonControl")
    if undo and undo.IsEnabled:
        _activate(undo)


def _click_empty_icon(auto, window, cell, x_offset, y_offset, expected_text):
    before = _fingerprint(_page_group(window))
    auto.Click(
        round(cell.x + cell.width * x_offset),
        round(cell.y + cell.height * y_offset),
        waitTime=0.2,
    )
    try:
        return _wait_for(
            lambda: _find_text(window, expected_text),
            f"TD Snap did not show {expected_text!r}.",
            timeout=2,
        )
    except PagesetError:
        if _fingerprint(_page_group(window)) != before:
            _undo_if_needed(window)
        else:
            auto.SendKeys("{Esc}", waitTime=0.1)
        raise PagesetError(
            "TD Snap's empty-cell controls moved. No edit was kept. Set the "
            "TDSNAP_LINK_ICON_X/Y or TDSNAP_ADD_ICON_X/Y calibration values "
            "or update the bundled skill."
        )


def _set_value(control, value):
    candidates = [control] + [
        child for child, _ in _walk(control, 3)
        if child is not control and child.ControlTypeName == "EditControl"
    ]
    for candidate in candidates:
        pattern = candidate.GetValuePattern()
        if pattern:
            pattern.SetValue(value)
            return
    raise PagesetError("TD Snap's text field is not editable through accessibility.")


def _create_page_link(auto, window, title, cell):
    x_offset = float(os.environ.get("TDSNAP_LINK_ICON_X", "0.39"))
    y_offset = float(os.environ.get("TDSNAP_LINK_ICON_Y", "-0.33"))
    choice = _click_empty_icon(
        auto, window, cell, x_offset, y_offset, "Link to new page"
    )
    _activate(choice)
    create = _wait_for(
        lambda: _find(window, name="Create", control_type="ButtonControl"),
        "TD Snap did not open the New Page dialog.",
    )
    edits = [
        control for control, _ in _walk(window)
        if control.ControlTypeName == "EditControl"
        and control.BoundingRectangle.right > control.BoundingRectangle.left
    ]
    if not edits:
        raise PagesetError("TD Snap's New Page name field was not found.")
    named = [e for e in edits if "name" in (e.Name + e.AutomationId).casefold()]
    _set_value((named or edits)[0], title)
    _activate(create)
    _wait_for(
        lambda: _page_group(window).Name == title,
        "TD Snap did not open the newly created page.",
        timeout=10,
    )


def _add_button(auto, window, cell, text):
    x_offset = float(os.environ.get("TDSNAP_ADD_ICON_X", "0"))
    y_offset = float(os.environ.get("TDSNAP_ADD_ICON_Y", "0"))
    label = _click_empty_icon(auto, window, cell, x_offset, y_offset, "Label")
    edits = [
        control for control, _ in _walk(window)
        if control.ControlTypeName == "EditControl"
        and control.BoundingRectangle.right > control.BoundingRectangle.left
    ]
    textbox = next((e for e in edits if e.AutomationId == "TextBox"), None)
    if textbox is None:
        textbox = label.GetParentControl().GetParentControl()
        if textbox.ControlTypeName != "EditControl":
            raise PagesetError("TD Snap's button label field was not found.")
    _set_value(textbox, text)
    _wait_for(
        lambda: _find(_page_group(window), name=text, control_type="ButtonControl"),
        f"TD Snap did not save the {text!r} button.",
    )


def status():
    result = {
        "available": sys.platform == "win32",
        "running": False,
        "unlocked": _desktop_unlocked(),
        "page": None,
        "grid": None,
    }
    if not result["available"]:
        return result
    try:
        auto = _automation()
        window = _window(auto)
        group = _page_group(window)
        grid = _grid(group)
    except PagesetError as exc:
        result["error"] = str(exc)
        return result
    result.update(
        running=True,
        page=group.Name,
        grid={"cols": len(grid.xs), "rows": len(grid.ys)},
    )
    return result


def add_topic_page(title, items, parent=DEFAULT_PARENT):
    title = str(title or "").strip()
    normalized = _normalize_items(items)
    if not title:
        raise PagesetError("Give the new page a title.")
    if not normalized:
        raise PagesetError("Add at least one word or phrase.")
    if not _desktop_unlocked():
        raise PagesetError("Unlock Windows before editing TD Snap directly.")

    auto = _automation()
    window = _window(auto)
    _navigate_to_parent(window, parent)
    _enter_edit_mode(window)
    _collapse_editor(window)
    grid = _grid(_page_group(window))
    if len(normalized) > len(grid.xs) * len(grid.ys):
        raise PagesetError("The words do not fit on one TD Snap grid screen.")

    parent_cell = _empty_cell(window, grid)
    _create_page_link(auto, window, title, parent_cell)
    for item in normalized:
        _collapse_editor(window)
        cell = _empty_cell(window, grid, allow_scroll=False)
        # The first live version speaks the displayed text. Preserve full
        # phrases even when the export editor supplied a shorter label.
        _add_button(auto, window, cell, item["message"] or item["label"])

    _exit_edit_mode(window)
    _activate(_find(window, automation_id="BackButton", control_type="ButtonControl"))
    _wait_for(
        lambda: _page_group(window).Name == parent,
        "The page was created, but TD Snap did not return to its parent.",
    )
    link = _find(_page_group(window), name=title, control_type="ButtonControl")
    if not link:
        raise PagesetError("The new page exists, but its parent link was not visible.")
    _activate(link)
    _wait_for(
        lambda: _page_group(window).Name == title,
        "The new parent button did not open the new page.",
    )
    return {
        "page": title,
        "parent": parent,
        "buttons": len(normalized),
        "checks": {
            "td_snap_edit": "pass",
            "navigation": "pass",
            "content": "pass",
        },
        "warnings": [warning for warning in [
            "Live editing currently uses the spoken phrase as the visible label."
            if any(item["message"] for item in normalized) else None,
            "Live editing does not yet apply communicative-function border colors."
            if any(item["border_color"] is not None for item in normalized) else None,
        ] if warning],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Edit the open TD Snap page set locally.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    add = commands.add_parser("add")
    add.add_argument("--title", required=True)
    add.add_argument("--item", action="append", required=True)
    add.add_argument("--parent", default=DEFAULT_PARENT)
    add.add_argument("--yes", action="store_true", help="confirm the live TD Snap edit")
    args = parser.parse_args(argv)
    if args.command == "status":
        output = status()
    else:
        if not args.yes:
            parser.error("add changes the open TD Snap page set; pass --yes to confirm")
        output = add_topic_page(args.title, args.item, args.parent)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
