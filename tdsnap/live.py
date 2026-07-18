"""Edit the open TD Snap page set through Windows UI Automation.

The word model decides what to add; this module only performs the repeatable
TD Snap workflow.  It intentionally uses TD Snap's accessibility controls
before adding a vision model: those controls are faster, smaller, and expose
the current page, buttons, edit fields, and navigation directly.
"""

import argparse
import ctypes
import glob
import hashlib
import json
import os
import sqlite3
import statistics
import sys
import time
from collections import deque
from contextlib import closing
from ctypes import wintypes
from dataclasses import dataclass

from .builder import _normalize_items
from .errors import PagesetError

DEFAULT_PARENT = "Topics Menu Page"
TD_SNAP_APP = r"shell:AppsFolder\TobiiDynavox.Snap_626b2w651dr5w!App"
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
        deadline = time.monotonic() + 30
        while True:
            try:
                pattern.Invoke()
                return
            except Exception as exc:
                # UIA_E_ELEMENTNOTENABLED is transient while TD Snap processes images.
                if getattr(exc, "hresult", None) != -2147220992:
                    raise
                if time.monotonic() >= deadline:
                    raise PagesetError("TD Snap stayed busy while activating a control.") from exc
                time.sleep(0.15)
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
    _verify_process(window)
    return window


def _process_app_id(process_id):
    """Return the Windows package application ID for a process, if available."""
    if sys.platform != "win32" or not process_id:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    getter = getattr(kernel32, "GetApplicationUserModelId", None)
    if getter is None:
        return None
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    getter.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    getter.restype = wintypes.LONG
    process = kernel32.OpenProcess(0x1000, False, process_id)
    if not process:
        return None
    try:
        length = wintypes.UINT()
        if getter(process, ctypes.byref(length), None) != 122 or not length.value:
            return None
        application_id = ctypes.create_unicode_buffer(length.value)
        if getter(process, ctypes.byref(length), application_id) == 0:
            return application_id.value
    finally:
        kernel32.CloseHandle(process)
    return None


def _verify_process(window):
    expected = TD_SNAP_APP.removeprefix("shell:AppsFolder\\")
    actual = _process_app_id(getattr(window, "ProcessId", 0))
    if not actual:
        raise PagesetError("AAC Editor could not verify the TD Snap application process.")
    if actual.casefold() != expected.casefold():
        raise PagesetError("The detected window is not the installed TD Snap application.")


def launch():
    """Ask Windows to open TD Snap; do nothing when it is already ready."""
    if sys.platform != "win32":
        raise PagesetError("TD Snap can only be opened automatically on Windows.")
    if status(False).get("running"):
        return {"launched": False}
    try:
        os.startfile(TD_SNAP_APP)
    except OSError as exc:
        raise PagesetError(
            "TD Snap could not be opened automatically. Open it from Start, then try again."
        ) from exc
    return {"launched": True}


def _focus_window(window):
    """Keep raw grid clicks from landing on a window covering TD Snap."""
    try:
        window.SetFocus()
    except (AttributeError, OSError):
        raise PagesetError("TD Snap could not be brought to the foreground.")
    time.sleep(0.2)


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


def _page_name(window, group=None):
    """Return the user-facing current page title shown above the grid."""
    group = group or _page_group(window)
    page_rect = group.BoundingRectangle
    titles = []
    for control, _ in _walk(window, 4):
        rect = control.BoundingRectangle
        name = (control.Name or "").strip()
        if (
            control.ControlTypeName == "TextControl"
            and name
            and rect.bottom <= page_rect.top
            and rect.left >= page_rect.left
            and rect.right <= page_rect.right
        ):
            titles.append(control)
    return min(
        titles,
        key=lambda control: control.BoundingRectangle.top,
        default=group,
    ).Name


def _pageset_matches_visible_page(path, page, labels):
    try:
        with closing(sqlite3.connect(
            f"file:{path}?mode=ro", uri=True, timeout=1
        )) as conn:
            rows = conn.execute(
                "SELECT Id FROM Page WHERE PageType = 1 AND Title = ? COLLATE NOCASE",
                (page,),
            ).fetchall()
            if len(rows) != 1:
                return False
            if not labels:
                return True
            visible = {
                row[0].strip().casefold()
                for row in conn.execute(
                    "SELECT Button.Label FROM Button "
                    "JOIN ElementReference ON ElementReference.Id = Button.ElementReferenceId "
                    "WHERE ElementReference.PageId = ? AND Button.Label IS NOT NULL",
                    (rows[0][0],),
                )
                if row[0].strip()
            }
        return {label.strip().casefold() for label in labels if label.strip()} <= visible
    except (OSError, sqlite3.Error):
        return False


def _active_pageset_path(visible_page=None, visible_labels=()):
    """Return the page-set database selected in TD Snap's user settings."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    settings_files = glob.glob(os.path.join(
        local, "Packages", "TobiiDynavox.Snap_*", "LocalState",
        "Users", "*", "Settings.ssf",
    ))
    candidates = []
    for settings_path in settings_files:
        try:
            with closing(sqlite3.connect(
                f"file:{settings_path}?mode=ro", uri=True, timeout=1
            )) as conn:
                row = conn.execute(
                    "SELECT PageSetGuid FROM UserSettings LIMIT 1"
                ).fetchone()
            if not row or not row[0]:
                continue
            pageset_path = os.path.join(
                os.path.dirname(settings_path), f"{row[0]}.sps"
            )
            if os.path.isfile(pageset_path):
                candidates.append(pageset_path)
        except (OSError, sqlite3.Error):
            continue
    candidates = list(dict.fromkeys(
        os.path.realpath(path) for path in candidates
    ))
    if len(candidates) == 1:
        return candidates[0]
    if not visible_page:
        return None
    matches = [
        path for path in candidates
        if _pageset_matches_visible_page(path, visible_page, visible_labels)
    ]
    return matches[0] if len(matches) == 1 else None


def _active_pageset_pages(visible_page=None, visible_labels=()):
    """Read every vocabulary-page title from the page set open in TD Snap."""
    pageset_path = _active_pageset_path(visible_page, visible_labels)
    if not pageset_path:
        return []
    try:
        with closing(sqlite3.connect(
            f"file:{pageset_path}?mode=ro", uri=True, timeout=1
        )) as conn:
            rows = conn.execute(
                "SELECT COALESCE(NULLIF(Title, ''), 'Page ' || Id) "
                "FROM Page WHERE PageType = 1 ORDER BY Title COLLATE NOCASE"
            ).fetchall()
        return list(dict.fromkeys(row[0] for row in rows))
    except (OSError, sqlite3.Error):
        return []


def _page_route(start, target, visible_labels=()):
    """Find button presses from *start* to *target* in the active page set."""
    pageset_path = _active_pageset_path(start, visible_labels)
    if not pageset_path:
        return None
    try:
        with closing(sqlite3.connect(
            f"file:{pageset_path}?mode=ro", uri=True, timeout=1
        )) as conn:
            rows = conn.execute(
                "SELECT source.Title, source.PageType, button.Label, target.Title "
                "FROM ButtonPageLink link "
                "JOIN Button button ON button.Id = link.ButtonId "
                "JOIN ElementReference ref ON ref.Id = button.ElementReferenceId "
                "JOIN Page source ON source.Id = ref.PageId "
                "JOIN Page target ON target.UniqueId = link.PageUniqueId "
                "WHERE target.PageType = 1 AND source.Title IS NOT NULL "
                "AND button.Label IS NOT NULL AND target.Title IS NOT NULL"
            ).fetchall()
    except (OSError, sqlite3.Error):
        return None

    graph = {}
    toolbar = []
    for source, page_type, button, destination in rows:
        edge = (button, destination, page_type != 1)
        (toolbar if page_type != 1 else graph.setdefault(source.casefold(), [])).append(edge)
    queue = deque([(start, [])])
    seen = {start.casefold()}
    while queue:
        page, route = queue.popleft()
        if page.casefold() == target.casefold():
            return route
        for edge in graph.get(page.casefold(), []) + toolbar:
            destination = edge[1]
            if destination.casefold() not in seen:
                seen.add(destination.casefold())
                queue.append((destination, route + [edge]))
    return []


def _clusters(values, tolerance=8):
    groups = []
    for value in sorted(values):
        if not groups or value - statistics.mean(groups[-1]) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return tuple(round(statistics.mean(group)) for group in groups)


def _stored_sparse_grid(group, buttons, width, height):
    """Use saved placements when visible buttons do not expose the whole grid."""
    pageset_path = _active_pageset_path()
    title = (getattr(group, "Name", "") or "").strip()
    if not pageset_path or not title:
        return None
    try:
        with closing(sqlite3.connect(pageset_path)) as connection:
            layouts = connection.execute(
                """
                SELECT pl.Id, COALESCE(p.GridDimension, pl.PageLayoutSetting)
                FROM Page p JOIN PageLayout pl ON pl.PageId = p.Id
                WHERE p.Title = ? ORDER BY pl.Id
                """,
                (title,),
            ).fetchall()
            candidates = []
            for layout_id, setting in layouts:
                cols, rows = (int(value) for value in setting.split(",")[:2])
                placements = dict(connection.execute(
                    """
                    SELECT lower(b.Label), ep.GridPosition
                    FROM Button b
                    JOIN ElementReference er ON er.Id = b.ElementReferenceId
                    JOIN ElementPlacement ep ON ep.ElementReferenceId = er.Id
                    WHERE ep.PageLayoutId = ? AND ep.Visible = 1
                    """,
                    (layout_id,),
                ))
                observed = []
                for button in buttons:
                    position = placements.get((button.Name or "").casefold())
                    if not position:
                        continue
                    column, row = (int(value) for value in position.split(",")[:2])
                    rect = button.BoundingRectangle
                    observed.append(((rect.left + rect.right) // 2,
                                     (rect.top + rect.bottom) // 2, column, row))
                if observed:
                    candidates.append((cols, rows, observed))
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return None

    if not candidates:
        return None

    def fit(candidate):
        _, _, observed = candidate

        def measured_step(center_index, position_index):
            values = []
            for index, first in enumerate(observed):
                for second in observed[index + 1:]:
                    difference = second[position_index] - first[position_index]
                    if difference:
                        values.append(abs(
                            (second[center_index] - first[center_index]) / difference
                        ))
            return statistics.median(values) if values else None

        x_step = measured_step(0, 2) or width + 13
        y_step = measured_step(1, 3) or height + (x_step - width)
        first_x = statistics.median([x - column * x_step for x, _, column, _ in observed])
        first_y = statistics.median([y - row * y_step for _, y, _, row in observed])
        error = sum(
            abs(x - (first_x + column * x_step))
            + abs(y - (first_y + row * y_step))
            for x, y, column, row in observed
        )
        return len(buttons) - len(observed), error, x_step, y_step, first_x, first_y

    cols, rows, observed = min(candidates, key=lambda candidate: fit(candidate)[:2])
    _, _, x_step, y_step, first_x, first_y = fit((cols, rows, observed))
    return Grid(
        tuple(round(first_x + index * x_step) for index in range(cols)),
        tuple(round(first_y + index * y_step) for index in range(rows)),
        width,
        height,
    )


def _stored_empty_grid(group):
    """Infer clickable cell centers for a new page with no UIA buttons yet."""
    pageset_path = _active_pageset_path()
    title = (getattr(group, "Name", "") or "").strip()
    if not pageset_path or not title:
        return None
    try:
        with closing(sqlite3.connect(
            f"file:{pageset_path}?mode=ro", uri=True, timeout=1
        )) as connection:
            settings = connection.execute(
                """
                SELECT COALESCE(p.GridDimension, pl.PageLayoutSetting)
                FROM Page p JOIN PageLayout pl ON pl.PageId = p.Id
                WHERE p.Title = ?
                """,
                (title,),
            ).fetchall()
        dimensions = {
            tuple(int(value) for value in setting.split(",")[:2])
            for setting, in settings if setting
        }
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return None
    if len(dimensions) != 1:
        return None
    cols, rows = dimensions.pop()
    if cols < 1 or rows < 1:
        return None
    bounds = group.BoundingRectangle
    x_step = (bounds.right - bounds.left) / cols
    y_step = (bounds.bottom - bounds.top) / rows
    return Grid(
        tuple(round(bounds.left + (index + 0.5) * x_step) for index in range(cols)),
        tuple(round(bounds.top + (index + 0.5) * y_step) for index in range(rows)),
        round(x_step),
        round(y_step),
    )


def _grid(group):
    buttons = [
        child for child in group.GetChildren()
        if child.ControlTypeName == "ButtonControl"
        and child.BoundingRectangle.right > child.BoundingRectangle.left
    ]
    if not buttons:
        stored = _stored_empty_grid(group)
        if stored:
            return stored
        raise PagesetError("TD Snap's button grid could not be measured.")
    rects = [button.BoundingRectangle for button in buttons]
    widths = [rect.right - rect.left for rect in rects]
    heights = [rect.bottom - rect.top for rect in rects]
    width = round(statistics.median(widths))
    height = round(statistics.median(heights))
    stored = _stored_sparse_grid(group, buttons, width, height)
    if stored:
        return stored
    xs = _clusters([
        (rect.left + rect.right) // 2
        for rect in rects if rect.right - rect.left <= width * 1.5
    ])
    ys = _clusters([
        (rect.top + rect.bottom) // 2
        for rect in rects if rect.bottom - rect.top <= height * 1.5
    ])
    x_step = (
        statistics.median([b - a for a, b in zip(xs, xs[1:])])
        if len(xs) > 1 else None
    )
    y_step = (
        statistics.median([b - a for a, b in zip(ys, ys[1:])])
        if len(ys) > 1 else None
    )
    if x_step is None:
        x_step = y_step * width / height if y_step else width * 1.1
    if y_step is None:
        y_step = x_step * height / width if x_step else height * 1.1

    def fill_gaps(centers, step):
        filled = []
        for center in centers:
            if filled:
                missing = round((center - filled[-1]) / step) - 1
                if missing > 0:
                    previous = filled[-1]
                    filled.extend(
                        round(previous + step * index)
                        for index in range(1, missing + 1)
                    )
            filled.append(center)
        return tuple(filled)

    xs = fill_gaps(xs, x_step)
    ys = fill_gaps(ys, y_step)

    def complete_axis(centers, start, size, cell_size, step):
        if len(centers) > 1:
            return centers
        gap = max(0, step - cell_size)
        count = max(2, round((size + gap) / step))
        span = (count - 1) * step + cell_size
        first = start + (size - span) / 2 + cell_size / 2
        if centers:
            nearest = round((centers[0] - first) / step)
            first += centers[0] - (first + nearest * step)
        return tuple(round(first + index * step) for index in range(count))

    bounds = group.BoundingRectangle
    xs = complete_axis(xs, bounds.left, bounds.right - bounds.left, width, x_step)
    ys = complete_axis(ys, bounds.top, bounds.bottom - bounds.top, height, y_step)
    return Grid(xs, ys, width, height)


def _fingerprint(group):
    return tuple(
        sorted(
            (child.Name, child.BoundingRectangle.left, child.BoundingRectangle.top)
            for child in group.GetChildren()
            if child.ControlTypeName == "ButtonControl"
        )
    )


def _fingerprint_token(group):
    """Stable, opaque token used to reject edits against a changed page."""
    payload = json.dumps(_fingerprint(group), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _page_layout(group, grid):
    """Return visible buttons mapped to zero-based grid slots."""
    buttons = []
    for child in group.GetChildren():
        rect = child.BoundingRectangle
        label = (child.Name or "").strip()
        if (
            child.ControlTypeName != "ButtonControl"
            or not label
            or rect.right <= rect.left
            or rect.bottom <= rect.top
        ):
            continue
        center_x = (rect.left + rect.right) // 2
        center_y = (rect.top + rect.bottom) // 2
        column = min(range(len(grid.xs)), key=lambda i: abs(grid.xs[i] - center_x))
        row = min(range(len(grid.ys)), key=lambda i: abs(grid.ys[i] - center_y))
        if abs(grid.xs[column] - center_x) > grid.cell_width or abs(grid.ys[row] - center_y) > grid.cell_height:
            continue
        buttons.append({
            "slot": row * len(grid.xs) + column,
            "label": label,
        })
    return sorted(buttons, key=lambda item: item["slot"])


def _named_page_buttons(group):
    """Return unique visible grid-button names in reading order."""
    buttons = []
    seen = set()
    for child in group.GetChildren():
        rect = child.BoundingRectangle
        name = (child.Name or "").strip()
        if (
            child.ControlTypeName != "ButtonControl"
            or not name
            or len(name) > 80
            or rect.right <= rect.left
            or rect.bottom <= rect.top
            or name.casefold() in seen
        ):
            continue
        seen.add(name.casefold())
        buttons.append((rect.top, rect.left, name))
    return [name for _, _, name in sorted(buttons)]


def _first_empty(grid, rectangles):
    for y in grid.ys:
        for x in grid.xs:
            if not any(
                rect.left <= x <= rect.right and rect.top <= y <= rect.bottom
                for rect in rectangles
            ):
                return Cell(x, y, grid.cell_width, grid.cell_height)
    return None


def _cell_at(grid, slot):
    """Translate a zero-based preview slot into TD Snap grid coordinates."""
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        return None
    total = len(grid.xs) * len(grid.ys)
    if slot < 0 or slot >= total:
        return None
    row, column = divmod(slot, len(grid.xs))
    return Cell(
        grid.xs[column], grid.ys[row], grid.cell_width, grid.cell_height
    )


def _anchored_grid(template, button, slot):
    """Place a known grid shape around the first button on a sparse page."""
    row, column = divmod(int(slot), len(template.xs))
    rect = button.BoundingRectangle
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    x_step = statistics.median([
        right - left for left, right in zip(template.xs, template.xs[1:])
    ])
    y_step = statistics.median([
        bottom - top for top, bottom in zip(template.ys, template.ys[1:])
    ])
    first_x = center_x - column * x_step
    first_y = center_y - row * y_step
    return Grid(
        tuple(round(first_x + index * x_step) for index in range(len(template.xs))),
        tuple(round(first_y + index * y_step) for index in range(len(template.ys))),
        rect.right - rect.left,
        rect.bottom - rect.top,
    )


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
        empty = _first_empty(grid, [
            button.BoundingRectangle for button in buttons if (button.Name or "").strip()
        ])
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


def _editor_toggle(window, group):
    window_rect = window.BoundingRectangle
    group_rect = group.BoundingRectangle
    candidates = []
    for control, _ in _walk(window, 5):
        rect = control.BoundingRectangle
        if (
            control.ControlTypeName == "ButtonControl"
            and not control.AutomationId
            and 35 <= rect.right - rect.left <= 75
            and 35 <= rect.bottom - rect.top <= 75
            and rect.left <= window_rect.left + 140
            and abs((rect.top + rect.bottom) // 2 - group_rect.bottom) <= 65
        ):
            candidates.append(control)
    if not candidates:
        raise PagesetError("TD Snap's editing panel toggle could not be found.")
    return min(candidates, key=lambda c: c.BoundingRectangle.left)


def _collapse_editor(window):
    group = _page_group(window)
    window_rect = window.BoundingRectangle
    group_rect = group.BoundingRectangle
    if group_rect.bottom >= window_rect.bottom - 100:
        return
    old_bottom = group_rect.bottom
    _activate(_editor_toggle(window, group))
    _wait_for(
        lambda: _page_group(window).BoundingRectangle.bottom > old_bottom + 100,
        "TD Snap's editing panel did not collapse.",
    )


def _expand_editor(window):
    group = _page_group(window)
    window_rect = window.BoundingRectangle
    group_rect = group.BoundingRectangle
    if group_rect.bottom < window_rect.bottom - 100:
        return
    old_bottom = group_rect.bottom
    _activate(_editor_toggle(window, group))
    _wait_for(
        lambda: _page_group(window).BoundingRectangle.bottom < old_bottom - 100,
        "TD Snap's editing panel did not open.",
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


def _open_page_button(window, button, page_name):
    """Open a page link using TD Snap's accessibility action."""
    before = _page_name(window)
    _activate(button)
    return _wait_for(
        lambda: (
            _page_name(window)
            if _page_name(window).casefold() != before.casefold() else None
        ),
        f"TD Snap did not open {page_name!r} after activating its button.",
        timeout=10,
    )


def _navigate_to_parent(window, parent):
    _exit_edit_mode(window)
    current = _page_name(window)
    if current.casefold() == parent.casefold():
        return parent
    route = _page_route(current, parent, _named_page_buttons(_page_group(window)))
    if not route:
        raise PagesetError(
            f"TD Snap has no page-link route from {current!r} to {parent!r}. "
            "Open that page in TD Snap and the live preview will follow it."
        )
    toolbar = _find(window, name="Tool Bar", control_type="GroupControl")
    for button_name, destination, from_toolbar in route:
        container = toolbar if from_toolbar else _page_group(window)
        button = _find(container, name=button_name, control_type="ButtonControl")
        if button is None:
            raise PagesetError(
                f"TD Snap's route to {parent!r} uses {button_name!r}, but that "
                "button is not visible on the current grid."
            )
        if from_toolbar:
            _activate(button)
        else:
            _open_page_button(window, button, destination)
        _wait_for(
            lambda: _page_name(window).casefold() == destination.casefold(),
            f"TD Snap did not open {destination!r} while navigating to {parent!r}.",
            timeout=10,
        )
    return parent


def _undo_if_needed(window):
    undo = _find(window, automation_id="UndoButton", control_type="ButtonControl")
    if undo and undo.IsEnabled:
        _activate(undo)


def _window_dpi(window):
    if sys.platform != "win32":
        return 96
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    getter = getattr(user32, "GetDpiForWindow", None)
    handle = getattr(window, "NativeWindowHandle", 0)
    if not getter or not handle:
        return 96
    getter.argtypes = [wintypes.HWND]
    getter.restype = wintypes.UINT
    return getter(handle) or 96


def _client_origin(window):
    if sys.platform != "win32" or not getattr(window, "NativeWindowHandle", 0):
        return None
    point = wintypes.POINT()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if not user32.ClientToScreen(window.NativeWindowHandle, ctypes.byref(point)):
        return None
    return point.x, point.y


def _physical_point(window, x, y):
    """Map TD Snap's client-relative logical grid point to screen pixels."""
    origin = _client_origin(window)
    if origin is None:
        return round(x), round(y)
    scale = _window_dpi(window) / 96
    return (
        round(origin[0] + (x - origin[0]) * scale),
        round(origin[1] + (y - origin[1]) * scale),
    )


def _click_empty_icon(auto, window, cell, x_offset, y_offset, expected_text):
    before = _fingerprint(_page_group(window))
    x, y = _physical_point(
        window,
        cell.x + cell.width * x_offset,
        cell.y + cell.height * y_offset,
    )
    auto.Click(x, y, waitTime=0.2)
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
        raise PagesetError("TD Snap's empty-cell action could not be selected.")


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


def _value(control):
    getter = getattr(control, "GetValuePattern", None)
    pattern = getter() if getter else None
    return pattern.Value if pattern else None


def _control_slot(grid, control):
    rect = control.BoundingRectangle
    center_x = (rect.left + rect.right) // 2
    center_y = (rect.top + rect.bottom) // 2
    column = min(range(len(grid.xs)), key=lambda index: abs(grid.xs[index] - center_x))
    row = min(range(len(grid.ys)), key=lambda index: abs(grid.ys[index] - center_y))
    if (
        abs(grid.xs[column] - center_x) > grid.cell_width
        or abs(grid.ys[row] - center_y) > grid.cell_height
    ):
        return None
    return row * len(grid.xs) + column


def _verify_added_buttons(window, items):
    """Verify exact slots, labels, and requested spoken messages in Edit mode."""
    _collapse_editor(window)
    group = _page_group(window)
    grid = _grid(group)
    by_slot = {
        _control_slot(grid, control): control
        for control in group.GetChildren()
        if control.ControlTypeName == "ButtonControl"
        and (control.Name or "").strip()
    }
    for item in items:
        control = by_slot.get(item["slot"])
        if control is None or (control.Name or "").strip() != item["label"]:
            raise PagesetError(
                f"TD Snap did not verify {item['label']!r} in its reviewed cell."
            )
        if item["message"]:
            _activate(control)
            _expand_editor(window)
            message_box = _find(
                window, automation_id="MessageBox", control_type="EditControl"
            )
            if message_box is None or _value(message_box) != item["message"]:
                raise PagesetError(
                    f"TD Snap did not verify the spoken message for {item['label']!r}."
                )
            _collapse_editor(window)


def _restore_page_fingerprint(window, baseline, maximum):
    """Undo until the visible page matches the reviewed pre-edit baseline."""
    _enter_edit_mode(window)
    for _ in range(maximum + 1):
        if _fingerprint(_page_group(window)) == baseline:
            return
        undo = _find(window, automation_id="UndoButton", control_type="ButtonControl")
        if undo is None or not getattr(undo, "IsEnabled", False):
            break
        _activate(undo)
        time.sleep(0.12)
    if _fingerprint(_page_group(window)) != baseline:
        raise PagesetError(
            "TD Snap could not verify restoration of the reviewed page. "
            "Inspect the page before making another edit."
        )


def _rollback_new_page(auto, window, parent, parent_baseline, page_baseline, maximum):
    """Restore both a provisional child page and its parent link."""
    try:
        auto.SendKeys("{Esc}", waitTime=0.05)
    except (AttributeError, OSError):
        pass
    current = _page_name(window)
    if current.casefold() != parent.casefold():
        if page_baseline is not None:
            _restore_page_fingerprint(window, page_baseline, maximum)
        _exit_edit_mode(window)
        back = _find(window, automation_id="BackButton", control_type="ButtonControl")
        if back is None:
            raise PagesetError(
                "TD Snap could not return to the parent while restoring the new page. "
                "Inspect the page set before making another edit."
            )
        _activate(back)
        _wait_for(
            lambda: _page_name(window).casefold() == parent.casefold(),
            "TD Snap could not return to the parent while restoring the new page.",
            timeout=10,
        )
    _restore_page_fingerprint(window, parent_baseline, maximum)


def _create_page_link(auto, window, title, cell):
    parent_page = _page_name(window)
    choice = _click_empty_icon(
        auto, window, cell,
        float(os.environ.get("TDSNAP_LINK_ICON_X", "0.39")),
        float(os.environ.get("TDSNAP_LINK_ICON_Y", "-0.33")),
        "Link to new page",
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
        lambda: (
            True if _page_name(window).casefold() != parent_page.casefold() else
            _find(_page_group(window), name=title, control_type="ButtonControl")
        ),
        "TD Snap did not create the new page link.",
        timeout=10,
    )
    if _page_name(window).casefold() == parent_page.casefold():
        _exit_edit_mode(window)
        link = _find(_page_group(window), name=title, control_type="ButtonControl")
        _open_page_button(window, link, title)
        _enter_edit_mode(window)
    _wait_for(
        lambda: _page_name(window).casefold() != parent_page.casefold(),
        "TD Snap did not open the newly created page.",
        timeout=10,
    )


def _search_results(window, web=False):
    result_type = "MyTdxWebImage" if web else "SymbolLibrarySearchResult"
    return [
        control for control, _ in _walk(window, 8)
        if control.ControlTypeName == "ListItemControl"
        and result_type in (control.Name or "")
        and control.BoundingRectangle.right > control.BoundingRectangle.left
    ]


def _choose_symbol(window, label):
    """Choose the first relevant TD Snap symbol, falling back to web search."""
    try:
        content = _find(window, name="Content", control_type="ListItemControl")
        if content:
            content.Click(simulateMove=False)
        opener = _find(
            window, automation_id="OpenSymbolSearchButton",
            control_type="ButtonControl",
        )
        _activate(opener)
        search = _wait_for(
            lambda: next((
                control for control, _ in _walk(window, 8)
                if control.ControlTypeName == "EditControl"
                and control.BoundingRectangle.right > control.BoundingRectangle.left
                and "search" in (control.Name or "").casefold()
            ), None),
            "TD Snap did not open symbol search.",
        )
        _set_value(search, label)
        query = _find(window, automation_id="QueryButton", control_type="ButtonControl")
        _activate(query)
        try:
            results = _wait_for(
                lambda: _search_results(window),
                "No built-in symbols matched.", timeout=4,
            )
        except PagesetError:
            web = _find(window, name="Web", control_type="ListItemControl")
            if web:
                _activate(web)
                _activate(query)
            results = _wait_for(
                lambda: _search_results(window, web=True),
                "No symbol or web image matched.", timeout=6,
            )
        _activate(results[0])
        done = _find(window, automation_id="PrimaryButton", control_type="ButtonControl")
        _activate(done)
        _wait_for(
            lambda: _find(window, automation_id="PrimaryButton",
                          control_type="ButtonControl") is None,
            "TD Snap did not close symbol search.", timeout=60,
        )
        return True
    except PagesetError:
        cancel = _find(
            window, automation_id="SecondaryButton", control_type="ButtonControl"
        )
        if cancel:
            _activate(cancel)
        return False


def _closest_color_item(window, border_color):
    target = border_color & 0xFFFFFF
    target_rgb = ((target >> 16) & 255, (target >> 8) & 255, target & 255)
    choices = []
    for control, _ in _walk(window, 12):
        name = (control.Name or "").strip()
        if control.ControlTypeName != "ListItemControl" or not name.startswith("argb: #"):
            continue
        try:
            rgb = int(name[-6:], 16)
        except ValueError:
            continue
        channels = ((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255)
        distance = sum((a - b) ** 2 for a, b in zip(target_rgb, channels))
        choices.append((distance, control))
    return min(choices, key=lambda choice: choice[0])[1] if choices else None


def _apply_border(window, border_color):
    """Apply the nearest TD Snap palette color and a medium topic border."""
    if border_color is None:
        return False
    try:
        style = _find(window, name="Style", control_type="ListItemControl")
        style.Click(simulateMove=False)
        border_heading = _wait_for(
            lambda: _find(window, name="Button Border", control_type="TextControl"),
            "TD Snap did not open button style.",
        )
        color_labels = [
            control for control, _ in _walk(window, 9)
            if control.ControlTypeName == "TextControl"
            and control.Name == "Color"
            and control.BoundingRectangle.top > border_heading.BoundingRectangle.top
        ]
        color_row = min(color_labels, key=lambda c: c.BoundingRectangle.top)
        _activate(color_row.GetParentControl())
        choice = _wait_for(
            lambda: _closest_color_item(window, border_color),
            "TD Snap's border colors were unavailable.",
        )
        scroll = getattr(choice, "GetScrollItemPattern", lambda: None)()
        if scroll:
            scroll.ScrollIntoView()
        _activate(choice)
        if _find(window, name="Border Color", control_type="TextControl"):
            _activate(_find(window, automation_id="PART_BackButton",
                            control_type="ButtonControl"))

        thickness = _find(window, name="Thickness", control_type="TextControl")
        _activate(thickness.GetParentControl())
        medium = _wait_for(
            lambda: _find(window, automation_id="MediumItem",
                          control_type="ListItemControl"),
            "TD Snap's border thickness choices were unavailable.",
        )
        _activate(medium)
        if _find(window, name="Border Thickness", control_type="TextControl"):
            _activate(_find(window, automation_id="PART_BackButton",
                            control_type="ButtonControl"))
        return True
    except (PagesetError, AttributeError):
        back = _find(window, automation_id="PART_BackButton",
                     control_type="ButtonControl")
        if back:
            _activate(back)
        return False


def _empty_label_field(window):
    """The button-editor label box when it is open and not yet filled.

    Clicking an empty cell either creates a new button (truly-empty grid) or
    selects a pre-placed blank button (template pages fill every cell with a
    blank placeholder). Both open TD Snap's label field *empty*. Requiring the
    field to be empty also skips the field still showing the previous button's
    label between adds, so we never relabel the button we just made.
    """
    for control, _ in _walk(window, 12):
        if (
            control.ControlTypeName == "EditControl"
            and control.AutomationId == "TextBox"
            and control.IsEnabled
        ):
            getter = getattr(control, "GetValuePattern", None)
            pattern = getter() if getter else None
            if pattern is None or not (pattern.Value or "").strip():
                return control
    return None


def _add_button(auto, window, cell, label, message=None,
                border_color=None, use_symbol=False):
    before = _fingerprint(_page_group(window))
    x, y = _physical_point(
        window,
        cell.x + cell.width * float(os.environ.get("TDSNAP_ADD_ICON_X", "0")),
        cell.y + cell.height * float(os.environ.get("TDSNAP_ADD_ICON_Y", "0")),
    )
    auto.Click(x, y, waitTime=0.2)
    opened = False
    try:
        # An empty label field appearing — not a change in the button
        # fingerprint — is the signal the cell is ready. Clicking a blank
        # placeholder button on a template page opens the editor without adding
        # a button, so the old fingerprint check wrongly reported failure and
        # left the cell blank.
        textbox = _wait_for(
            lambda: _empty_label_field(window),
            "TD Snap did not open a button in the empty cell.",
            timeout=6,
        )
        opened = True
        _set_value(textbox, label)
        _wait_for(
            lambda: _find(_page_group(window), name=label, control_type="ButtonControl"),
            f"TD Snap did not save the {label!r} button.",
        )
        symbol_applied = False
        border_applied = border_color is None
        if message:
            _expand_editor(window)
            message_box = _find(
                window, automation_id="MessageBox", control_type="EditControl"
            )
            if message_box is None:
                raise PagesetError(
                    f"TD Snap did not expose the spoken-message field for {label!r}."
                )
            _set_value(message_box, message)
            _wait_for(
                lambda: _value(message_box) == message,
                f"TD Snap did not save the spoken message for {label!r}.",
            )
        if border_color is not None or use_symbol:
            try:
                _expand_editor(window)
                if use_symbol:
                    symbol_applied = _choose_symbol(window, label)
                border_applied = _apply_border(window, border_color)
            except PagesetError:
                pass
        return {"symbol": symbol_applied, "border": border_applied}
    except PagesetError:
        if opened or _fingerprint(_page_group(window)) != before:
            _undo_if_needed(window)
        raise


def status(include_pages=True):
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
        page=_page_name(window, group),
        grid={"cols": len(grid.xs), "rows": len(grid.ys)},
    )
    if include_pages:
        pages = _active_pageset_pages(result["page"], _named_page_buttons(group))
        if not pages:
            detected = _named_page_buttons(group) if group.Name == DEFAULT_PARENT else []
            pages = [DEFAULT_PARENT] + detected
        result["pages"] = list(dict.fromkeys([result["page"]] + pages))
    return result


def inspect_page(page=None):
    """Inspect a visible/detected page without entering Edit mode."""
    if not _desktop_unlocked():
        raise PagesetError("Unlock Windows before inspecting TD Snap.")
    auto = _automation()
    window = _window(auto)
    requested = str(page or "").strip()
    if requested and _page_name(window).casefold() != requested.casefold():
        _navigate_to_parent(window, requested)
    group = _page_group(window)
    grid = _grid(group)
    buttons = _page_layout(group, grid)
    return {
        "page": _page_name(window, group),
        "grid": {"cols": len(grid.xs), "rows": len(grid.ys)},
        "buttons": buttons,
        "free_slots": [
            slot for slot in range(len(grid.xs) * len(grid.ys))
            if slot not in {button["slot"] for button in buttons}
        ],
        "fingerprint": _fingerprint_token(group),
    }


def add_to_existing_page(page, items, fingerprint=None):
    """Add reviewed buttons to empty cells on an existing TD Snap page."""
    normalized = _normalize_items(items)
    if not normalized:
        raise PagesetError("Add at least one word or phrase.")
    if not _desktop_unlocked():
        raise PagesetError("Unlock Windows before editing TD Snap directly.")

    auto = _automation()
    window = _window(auto)
    _focus_window(window)
    requested = str(page or "").strip()
    if not requested:
        raise PagesetError("Choose an existing TD Snap page.")
    if not fingerprint:
        raise PagesetError(
            "The TD Snap review fingerprint is required. Refresh the layout and review again."
        )
    if _page_name(window).casefold() != requested.casefold():
        _navigate_to_parent(window, requested)
    group = _page_group(window)
    if _fingerprint_token(group) != fingerprint:
        raise PagesetError(
            "The target page changed after preview. Refresh the layout and review the edit again."
        )
    baseline = _fingerprint(group)
    grid = _grid(group)
    existing = _page_layout(group, grid)
    occupied = {button["slot"] for button in existing}
    labels = {button["label"].strip().casefold() for button in existing if button["label"]}
    duplicates = [item["label"] for item in normalized if item["label"].casefold() in labels]
    if duplicates:
        raise PagesetError(
            "Already on this page: " + ", ".join(duplicates) + ". Remove or rename duplicates before submitting."
        )
    requested_slots = [item.get("slot") for item in normalized]
    if any(slot is None for slot in requested_slots):
        raise PagesetError("Review and place every new button in an empty cell before submitting.")
    if len(set(requested_slots)) != len(requested_slots):
        raise PagesetError("Two new buttons cannot use the same cell.")
    if any(not isinstance(slot, int) or slot in occupied or _cell_at(grid, slot) is None for slot in requested_slots):
        raise PagesetError("One or more selected cells are no longer empty. Refresh the page layout.")

    _enter_edit_mode(window)
    symbols = 0
    styled = 0
    try:
        for item in normalized:
            _collapse_editor(window)
            edit_grid = _grid(_page_group(window))
            result = _add_button(
                auto, window, _cell_at(edit_grid, item["slot"]), item["label"],
                item["message"], item["border_color"], item.get("symbol", True),
            )
            symbols += int(result["symbol"])
            styled += int(result["border"] and item["border_color"] is not None)
        _verify_added_buttons(window, normalized)
        _exit_edit_mode(window)
        final_group = _page_group(window)
        final_grid = _grid(final_group)
        final_slots = {
            button["slot"]: button["label"] for button in _page_layout(final_group, final_grid)
        }
        missing = [
            item["label"] for item in normalized
            if final_slots.get(item["slot"]) != item["label"]
        ]
        if missing:
            raise PagesetError(
                "TD Snap did not verify the added button(s) in their reviewed cells: "
                + ", ".join(missing)
            )
    except Exception as exc:
        try:
            _restore_page_fingerprint(window, baseline, len(normalized) * 6 + 8)
        except PagesetError as rollback_error:
            raise PagesetError(f"{exc} {rollback_error}") from exc
        raise PagesetError(f"{exc} The original page was restored.") from exc
    finally:
        _exit_edit_mode(window)

    expected_symbols = sum(item.get("symbol", True) for item in normalized)
    expected_styles = sum(item["border_color"] is not None for item in normalized)
    return {
        "page": _page_name(window, final_group),
        "buttons": len(normalized),
        "checks": {
            "td_snap_edit": "pass",
            "target_page": "pass",
            "content": "pass",
            "positions": "pass",
            "symbols": "pass" if symbols == expected_symbols else "partial",
            "topic_format": "pass" if styled == expected_styles else "partial",
        },
        "warnings": [warning for warning in [
            f"TD Snap could not find a symbol for {expected_symbols - symbols} button(s)."
            if symbols < expected_symbols else None,
            "Some topic border colors could not be applied automatically."
            if styled < expected_styles else None,
        ] if warning],
    }


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
    _focus_window(window)
    parent = str(parent or DEFAULT_PARENT).strip()
    actual_parent = _navigate_to_parent(window, parent)
    parent_group = _page_group(window)
    known_pages = _active_pageset_pages(
        actual_parent, _named_page_buttons(parent_group)
    )
    if title.casefold() in {page.casefold() for page in known_pages} or _find(
        parent_group, name=title, control_type="ButtonControl"
    ):
        raise PagesetError(
            f"A TD Snap page or parent link named {title!r} already exists."
        )

    # Find parent capacity before opening any creation dialog. This may move to
    # another grid screen; the rollback baseline is captured after that move.
    _empty_cell(window, _grid(parent_group))
    parent_group = _page_group(window)
    parent_baseline = _fingerprint(parent_group)
    page_baseline = None
    symbols = 0
    styled = 0
    placed = []
    try:
        _enter_edit_mode(window)
        _collapse_editor(window)
        parent_cell = _empty_cell(window, _grid(_page_group(window)))
        _create_page_link(auto, window, title, parent_cell)

        _collapse_editor(window)
        child_group = _page_group(window)
        page_baseline = _fingerprint(child_group)
        new_grid = _grid(child_group)
        occupied = {
            button["slot"] for button in _page_layout(child_group, new_grid)
        }
        available = [
            slot for slot in range(len(new_grid.xs) * len(new_grid.ys))
            if slot not in occupied
        ]
        if len(normalized) > len(available):
            raise PagesetError("The words do not fit in the new TD Snap page's empty cells.")

        unused = set(available)
        for item in normalized:
            requested = item.get("slot")
            slot = requested if isinstance(requested, int) and requested in unused else min(unused)
            unused.remove(slot)
            placed_item = dict(item, slot=slot)
            placed.append(placed_item)
            _collapse_editor(window)
            active_grid = _grid(_page_group(window))
            result = _add_button(
                auto, window, _cell_at(active_grid, slot), item["label"],
                item["message"], item["border_color"], item.get("symbol", True),
            )
            symbols += int(result["symbol"])
            styled += int(result["border"] and item["border_color"] is not None)

        _verify_added_buttons(window, placed)
        _exit_edit_mode(window)
        final_group = _page_group(window)
        final_grid = _grid(final_group)
        final_slots = {
            button["slot"]: button["label"]
            for button in _page_layout(final_group, final_grid)
        }
        if any(final_slots.get(item["slot"]) != item["label"] for item in placed):
            raise PagesetError("TD Snap did not verify the new page's reviewed content.")

        back = _find(window, automation_id="BackButton", control_type="ButtonControl")
        if back is None:
            raise PagesetError("The new page was created, but its Back button was unavailable.")
        _activate(back)
        _wait_for(
            lambda: _page_name(window).casefold() == actual_parent.casefold(),
            "The page was created, but TD Snap did not return to its parent.",
        )
        link = _find(_page_group(window), name=title, control_type="ButtonControl")
        if not link:
            raise PagesetError("The new page exists, but its parent link was not visible.")
        link_symbol = False
        try:
            _enter_edit_mode(window)
            link = _find(_page_group(window), name=title, control_type="ButtonControl")
            _activate(link)
            _expand_editor(window)
            link_symbol = _choose_symbol(window, title)
        except PagesetError:
            pass
        finally:
            _exit_edit_mode(window)
        link = _find(_page_group(window), name=title, control_type="ButtonControl")
        _open_page_button(window, link, title)
    except Exception as exc:
        try:
            _rollback_new_page(
                auto, window, actual_parent, parent_baseline, page_baseline,
                len(normalized) * 6 + 12,
            )
        except PagesetError as rollback_error:
            raise PagesetError(f"{exc} {rollback_error}") from exc
        raise PagesetError(f"{exc} The provisional page and parent link were restored.") from exc
    finally:
        _exit_edit_mode(window)

    total_symbols = symbols + int(link_symbol)
    expected_symbols = len(normalized) + 1
    return {
        "page": title,
        "parent": parent,
        "buttons": len(normalized),
        "checks": {
            "td_snap_edit": "pass",
            "navigation": "pass",
            "content": "pass",
            "symbols": "pass" if total_symbols == expected_symbols else "partial",
            "topic_format": "pass" if styled == sum(
                item["border_color"] is not None for item in normalized
            ) else "partial",
        },
        "warnings": [warning for warning in [
            f"TD Snap could not find a symbol for {expected_symbols - total_symbols} button(s)."
            if total_symbols < expected_symbols else None,
            "Some topic border colors could not be applied automatically."
            if styled < sum(item["border_color"] is not None for item in normalized) else None,
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
