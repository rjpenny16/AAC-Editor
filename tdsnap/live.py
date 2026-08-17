"""Edit the open TD Snap page set through Windows UI Automation.

The word model decides what to add; this module only performs the repeatable
TD Snap workflow.  It intentionally uses TD Snap's accessibility controls
before adding a vision model: those controls are faster, smaller, and expose
the current page, buttons, edit fields, and navigation directly.

Three kinds of edit share one spine (``apply_page_edits``): adding buttons to
empty cells, changing an existing button's label or spoken message, and
removing one. Change and remove are destructive in a way adding never was, so
they carry two extra obligations, both enforced here rather than in the UI:

1. **Only a plain speaking button is ever rewritten.** Navigation, actions,
   and anything whose stored command sequence this app does not recognize stay
   locked. The accessibility tree cannot tell these apart — a page-link button
   and a speaking button look identical — so eligibility is read from the page
   set's own database (see the prior-content section below).
2. **Prior content is captured before anything is touched, and the edit is
   refused outright when it cannot be read.** Rollback for an additive edit
   could restore prior *shape*; a destructive one has to restore prior
   *content*, and it cannot do that from a snapshot it never took.
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
from contextlib import closing, suppress
from ctypes import wintypes
from dataclasses import dataclass

from . import colors, templates, uia
from .builder import MAX_LABEL_LENGTH, MAX_MESSAGE_LENGTH, _normalize_items
from .errors import PagesetError

DEFAULT_PARENT = "Topics Menu Page"
TD_SNAP_APP = r"shell:AppsFolder\TobiiDynavox.Snap_626b2w651dr5w!App"
_EXCLUDED_GROUPS = {"Message Bar", "Tool Bar"}

# Why a button is not eligible for a change or a removal, in the words the
# preview shows on hover and focus. Only a button whose whole job is to speak
# its own message is ever rewritten: navigation, actions, and anything whose
# command sequence this app does not recognize stay locked, because getting
# them wrong breaks how someone moves around their own vocabulary.
LOCK_REASONS = {
    "navigate": "This button opens another page, so AAC Editor leaves it alone.",
    "action": "This button runs a TD Snap action, so AAC Editor leaves it alone.",
    "unknown": "AAC Editor doesn't recognize what this button does, so it leaves it alone.",
    "unreadable": "AAC Editor couldn't read what this button holds today.",
}


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
    return uia.automation(
        "Direct TD Snap editing is available on Windows only.",
        "Windows automation is not installed. Reinstall the app or run "
        "'pip install uiautomation'.",
    )


# See tdsnap/uia.py's module docstring for why each of these shares its
# implementation with grid3.py's helper of the same name, and why the
# retry/tolerance/depth chosen there is correct for TD Snap too.
_walk = uia.walk
_clusters = uia.clusters
_wait_for = uia.wait_for


def _activate(control):
    return uia.activate(
        control,
        missing_message="TD Snap changed while the edit was running.",
        busy_message="TD Snap stayed busy while activating a control.",
    )


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


def _window(auto):
    window = auto.WindowControl(searchDepth=1, Name="TD Snap")
    if not window.Exists(1):
        raise PagesetError("Open TD Snap before using direct editing.")
    _verify_process(window)
    return window


_process_app_id = uia.process_app_user_model_id


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
        os.startfile(TD_SNAP_APP)  # noqa: S606 - launches the fixed TD Snap package AppUserModelId
    except OSError as exc:
        raise PagesetError(
            "TD Snap could not be opened automatically. Open it from Start, then try again."
        ) from exc
    return {"launched": True}


def _focus_window(window):
    """Keep raw grid clicks from landing on a window covering TD Snap."""
    try:
        window.SetFocus()
    except (AttributeError, OSError) as exc:
        raise PagesetError("TD Snap could not be brought to the foreground.") from exc
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
                queue.append((destination, [*route, edge]))
    return []


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


# ---------------------------------------------------------------------------
# Prior content: what a button holds before a destructive edit
#
# Every operation before change and remove was additive, so a rollback could
# mean "undo until the page matches its pre-edit fingerprint" — the fingerprint
# carries each button's name and position, and only an add could move either.
# Rewriting a spoken message changes neither, so that same rollback would stop
# on its first check and report the page restored while the message stayed
# wrong. Destructive edits therefore capture prior *content* first, and refuse
# to run at all when that capture fails.
#
# The page set's own database is where this is readable. The alternative —
# opening TD Snap's button editor on every cell in turn before the edit starts
# — is slower, and would have to touch the very buttons it is trying to leave
# alone. It is also the only place the command sequence behind a button is
# visible: the accessibility tree shows a page-link button and a speaking
# button identically.

_SPEAK_COMMAND_TYPE = "3"


def _column(row, name, default=None):
    """Read an optional column, tolerating older page-set schema revisions."""
    return row[name] if name in row.keys() else default  # noqa: SIM118 - sqlite3.Row


def _command_kind(commands, command_flags, page_links):
    """Classify one stored button. Only ``'speak'`` may ever be rewritten."""
    if page_links or command_flags == templates.COMMAND_FLAGS_NAVIGATE:
        return "navigate"
    try:
        parsed = json.loads(commands or "")
    except (TypeError, ValueError):
        return "unknown"
    values = parsed.get("$values") if isinstance(parsed, dict) else None
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        return "action"
    if str(values[0].get("$type")) != _SPEAK_COMMAND_TYPE:
        return "action"
    return "speak" if command_flags == templates.COMMAND_FLAGS_SPEAK else "action"


def _stored_page_content(page):
    """Prior label, message, border, and command kind for the buttons on *page*.

    Keyed by casefolded label, because that is the only key the live control
    tree and the stored page set reliably agree on: UI Automation exposes a
    button's name, while matching by grid coordinate would mean re-deriving
    the layout through the same guesswork the preview already does. A label
    that appears twice on the page is dropped rather than guessed at, which
    locks those buttons out of destructive editing instead of risking editing
    the wrong one.

    Returns ``None`` when the page set or the page cannot be identified, which
    makes the caller refuse a destructive edit rather than run one it could
    not undo.
    """
    title = str(page or "").strip()
    path = _active_pageset_path(title)
    if not path or not title:
        return None
    try:
        with closing(sqlite3.connect(
            f"file:{path}?mode=ro", uri=True, timeout=2
        )) as conn:
            conn.row_factory = sqlite3.Row
            pages = conn.execute(
                "SELECT Id FROM Page WHERE PageType = 1 AND Title = ? COLLATE NOCASE",
                (title,),
            ).fetchall()
            if len(pages) != 1:
                return None
            rows = conn.execute(
                "SELECT button.*, commands.SerializedCommands AS SerializedCommands, "
                "(SELECT COUNT(*) FROM ButtonPageLink link "
                " WHERE link.ButtonId = button.Id) AS PageLinks "
                "FROM Button button "
                "JOIN ElementReference ref ON ref.Id = button.ElementReferenceId "
                "LEFT JOIN CommandSequence commands ON commands.ButtonId = button.Id "
                "WHERE ref.PageId = ?",
                (pages[0]["Id"],),
            ).fetchall()
    except (OSError, sqlite3.Error):
        return None

    content = {}
    ambiguous = set()
    for row in rows:
        label = (_column(row, "Label") or "").strip()
        if not label:
            continue
        key = label.casefold()
        if key in content:
            ambiguous.add(key)
            continue
        border = _column(row, "BorderColor")
        message = (_column(row, "Message") or "").strip()
        content[key] = {
            "label": label,
            "message": message or None,
            "border_color": border,
            "function": _function_for_border(border),
            "symbol": bool(
                _column(row, "LibrarySymbolId") or _column(row, "PageSetImageId")
            ),
            "kind": _command_kind(
                _column(row, "SerializedCommands"),
                _column(row, "CommandFlags"),
                _column(row, "PageLinks", 0),
            ),
        }
    for key in ambiguous:
        content.pop(key, None)
    return content


def _function_for_border(border_color):
    """Name the communicative function a stored border color stands for."""
    if border_color is None:
        return None
    stored = colors.hex_from_argb(border_color).casefold()
    for name, value in colors.FUNCTION_BORDER_COLORS.items():
        if value.casefold() == stored:
            return name
    return None


def _describe_buttons(page, buttons):
    """Annotate visible buttons with what each holds and whether it is editable.

    A page whose stored content cannot be read still lists every button; they
    are simply all locked, so adding buttons keeps working exactly as before
    on a page set AAC Editor cannot fully identify.
    """
    content = _stored_page_content(page)
    described = []
    for button in buttons:
        stored = (content or {}).get(button["label"].strip().casefold())
        kind = stored["kind"] if stored else "unreadable"
        described.append({
            **button,
            "message": stored["message"] if stored else None,
            "function": stored["function"] if stored else None,
            "symbol": stored["symbol"] if stored else False,
            "editable": kind == "speak",
            "locked_reason": None if kind == "speak" else LOCK_REASONS[kind],
        })
    return described, content is not None


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
            # Bound now, not on call: _wait_for consumes this within the same
            # iteration today, but binding keeps it correct if that changes.
            lambda before=before: _fingerprint(_page_group(window)) != before,
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
            lambda destination=destination: _page_name(window).casefold()
            == destination.casefold(),
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
    except PagesetError as exc:
        if _fingerprint(_page_group(window)) != before:
            _undo_if_needed(window)
        else:
            auto.SendKeys("{Esc}", waitTime=0.1)
        raise PagesetError(
            "TD Snap's empty-cell action could not be selected."
        ) from exc


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


def _named_slots(window):
    """Map every named grid button to its slot, re-measuring the live grid."""
    group = _page_group(window)
    grid = _grid(group)
    return {
        _control_slot(grid, control): control
        for control in group.GetChildren()
        if control.ControlTypeName == "ButtonControl"
        and (control.Name or "").strip()
    }


def _spoken_message(window, control):
    """Read one button's spoken message out of TD Snap's own editor."""
    _activate(control)
    _expand_editor(window)
    message_box = _find(window, automation_id="MessageBox", control_type="EditControl")
    value = None if message_box is None else _value(message_box)
    _collapse_editor(window)
    return message_box is not None, value


def _verify_page_state(window, expected=(), removed=(), untouched=None):
    """Verify every reviewed cell, and that nothing else on the page moved.

    *expected* is the ``{slot, label, message}`` each added or changed button
    must now carry, *removed* the slots that must now be empty, and
    *untouched* the label every other cell held before the edit and must
    still hold. That last check is what makes a destructive edit reviewable:
    "these three cells changed" is only a promise if the other cells are
    checked too.
    """
    _collapse_editor(window)
    by_slot = _named_slots(window)
    for item in expected:
        control = by_slot.get(item["slot"])
        if control is None or (control.Name or "").strip() != item["label"]:
            raise PagesetError(
                f"TD Snap did not verify {item['label']!r} in its reviewed cell."
            )
        # `None` means "no message was requested"; "" means "clear it and go
        # back to speaking the label", which is a real request and is checked
        # like any other.
        if item["message"] is not None:
            found, value = _spoken_message(window, control)
            if not found or (value or "") != item["message"]:
                raise PagesetError(
                    f"TD Snap did not verify the spoken message for {item['label']!r}."
                )
    for slot in removed:
        control = by_slot.get(slot)
        if control is not None:
            raise PagesetError(
                f"TD Snap did not verify the removal of "
                f"{(control.Name or '').strip()!r}; it is still on the page."
            )
    for slot, label in (untouched or {}).items():
        control = by_slot.get(slot)
        if control is None or (control.Name or "").strip() != label:
            raise PagesetError(
                f"TD Snap changed {label!r}, which this edit was not meant to touch. "
                "Inspect the page before making another edit."
            )


def _content_restored(window, content):
    """True when every touched cell holds the content it held before the edit.

    A read that fails part-way counts as "not restored yet" rather than
    propagating: mid-rollback TD Snap is repainting, and letting a transient
    read error out of here would replace the caller's specific "inspect the
    page before making another edit" with whichever control happened to be
    missing at that instant.
    """
    if not content:
        return True
    try:
        by_slot = _named_slots(window)
        for slot, prior in content.items():
            control = by_slot.get(slot)
            if control is None or (control.Name or "").strip() != prior["label"]:
                return False
            found, value = _spoken_message(window, control)
            if not found or (value or None) != prior["message"]:
                return False
    except PagesetError:
        return False
    return True


def _restore_page_state(window, baseline, content=None, maximum=0):
    """Undo until the page matches its reviewed shape *and* its prior content.

    Shape alone was a complete check while every operation was additive (see
    the prior-content section above for why it stopped being one). *content*
    maps a slot to the ``{label, message}`` it held before the edit and is
    read back through TD Snap's own editor rather than the page-set file, so
    a restoration is confirmed against what TD Snap is showing right now.
    """
    _enter_edit_mode(window)

    def restored():
        return (
            _fingerprint(_page_group(window)) == baseline
            and _content_restored(window, content)
        )

    for _ in range(maximum + 1):
        if restored():
            return
        undo = _find(window, automation_id="UndoButton", control_type="ButtonControl")
        if undo is None or not getattr(undo, "IsEnabled", False):
            break
        _activate(undo)
        time.sleep(0.12)
    if not restored():
        raise PagesetError(
            "TD Snap could not verify restoration of the reviewed page. "
            "Inspect the page before making another edit."
        )


def _restore_page_fingerprint(window, baseline, maximum):
    """Undo an additive edit, where prior shape is the whole of prior state."""
    _restore_page_state(window, baseline, None, maximum)


def _rollback_new_page(auto, window, parent, parent_baseline, page_baseline, maximum):
    """Restore both a provisional child page and its parent link."""
    with suppress(AttributeError, OSError):
        auto.SendKeys("{Esc}", waitTime=0.05)
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


def _filled_label_field(window, expected):
    """The button-editor label box when it already holds *expected*.

    This is how a change or a removal proves it is acting on the button it
    reviewed. Clicking a cell selects whatever is actually there, and the
    button fingerprint is unchanged by a mere selection, so the field's own
    value is the only evidence available that the right cell opened — the
    same reasoning as ``_empty_label_field``, from the other direction.
    """
    wanted = expected.strip().casefold()
    for control, _ in _walk(window, 12):
        if (
            control.ControlTypeName == "EditControl"
            and control.AutomationId == "TextBox"
            and control.IsEnabled
            and (_value(control) or "").strip().casefold() == wanted
        ):
            return control
    return None


def _select_button(auto, window, cell, label):
    """Open TD Snap's button editor on the existing button in *cell*."""
    x, y = _physical_point(window, cell.x, cell.y)
    auto.Click(x, y, waitTime=0.2)
    return _wait_for(
        lambda: _filled_label_field(window, label),
        f"TD Snap did not open its button editor on {label!r}.",
        timeout=6,
    )


def _change_button(auto, window, cell, current, label=None, message=None):
    """Rewrite the label and/or spoken message of one existing button.

    ``label``/``message`` of ``None`` mean "leave this as it is"; an empty
    message means "go back to speaking the label".
    """
    field = _select_button(auto, window, cell, current)
    if label and label != current:
        _set_value(field, label)
        _wait_for(
            lambda: _find(_page_group(window), name=label, control_type="ButtonControl"),
            f"TD Snap did not save the new label {label!r}.",
        )
    if message is None:
        return
    name = label or current
    _expand_editor(window)
    message_box = _find(window, automation_id="MessageBox", control_type="EditControl")
    if message_box is None:
        raise PagesetError(f"TD Snap did not expose the spoken-message field for {name!r}.")
    _set_value(message_box, message)
    _wait_for(
        lambda: (_value(message_box) or "") == message,
        f"TD Snap did not save the spoken message for {name!r}.",
    )
    _collapse_editor(window)


# TD Snap's editing panel is the surface most likely to be renamed by a product
# update, so the delete action is discovered rather than pinned to one id: by
# automation id first, then by the names the action is known to carry. A wrong
# guess must never silently do nothing, so failing to find it refuses the
# removal by name instead of continuing — the same line this project holds for
# Grid 3, where a feature stops at whatever the app does not expose.
_DELETE_AUTOMATION_IDS = ("DeleteButton", "DeleteElementButton", "RemoveButton")
_DELETE_NAMES = {"delete", "delete button", "remove", "remove button", "delete cell"}
_CONFIRM_NAMES = ("Delete", "Remove", "Yes", "OK")
_ACTIONABLE = {"ButtonControl", "ListItemControl", "MenuItemControl"}


def _delete_action(window):
    """TD Snap's delete-the-selected-button control, however it exposes it."""
    controls = [control for control, _ in _walk(window, 12) if control.IsEnabled]
    for control in controls:
        if (control.AutomationId or "") in _DELETE_AUTOMATION_IDS:
            return control
    for control in controls:
        rect = control.BoundingRectangle
        if (
            control.ControlTypeName in _ACTIONABLE
            and (control.Name or "").strip().casefold() in _DELETE_NAMES
            and rect.right > rect.left
            and rect.bottom > rect.top
        ):
            return control
    return None


def _confirm_removal(window, label):
    """Answer TD Snap's confirmation prompt, if it showed one.

    Only consulted while the button is still on the page. Activating a stray
    dialog control when no dialog opened would be a click into whatever the
    editing panel happens to be showing, which is exactly the class of blind
    action this module exists to avoid.
    """
    gone = _find(_page_group(window), name=label, control_type="ButtonControl") is None
    if gone:
        return
    confirm = _find(window, automation_id="PrimaryButton", control_type="ButtonControl")
    for name in _CONFIRM_NAMES:
        if confirm is not None:
            break
        confirm = _find(window, name=name, control_type="ButtonControl")
    if confirm is not None:
        _activate(confirm)


def _remove_button(auto, window, cell, label):
    """Delete one existing button through TD Snap's own editing controls."""
    _select_button(auto, window, cell, label)
    _expand_editor(window)
    action = _delete_action(window)
    if action is None:
        raise PagesetError(
            f"TD Snap did not expose a way to delete {label!r} through its "
            "accessibility controls, so the button was left alone."
        )
    _activate(action)
    _confirm_removal(window, label)
    _wait_for(
        lambda: _find(
            _page_group(window), name=label, control_type="ButtonControl"
        ) is None,
        f"TD Snap did not remove the {label!r} button.",
    )


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
            pages = [DEFAULT_PARENT, *detected]
        result["pages"] = list(dict.fromkeys([result["page"], *pages]))
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
    page_name = _page_name(window, group)
    described, content_readable = _describe_buttons(page_name, buttons)
    return {
        "page": page_name,
        "grid": {"cols": len(grid.xs), "rows": len(grid.ys)},
        "buttons": described,
        "content_readable": content_readable,
        "free_slots": [
            slot for slot in range(len(grid.xs) * len(grid.ys))
            if slot not in {button["slot"] for button in buttons}
        ],
        "fingerprint": _fingerprint_token(group),
    }


def _normalize_changes(changes):
    """Bound and shape ``[{slot, label?, message?}]`` change requests.

    ``label`` or ``message`` of ``None`` means "leave that as it is"; an empty
    message means "go back to speaking the label". A change that asks for
    neither is rejected rather than quietly doing nothing, because a review
    step that names a change which never happens is worse than an error.
    """
    normalized = []
    seen = set()
    for change in changes or ():
        if not isinstance(change, dict):
            raise PagesetError("Each change must be a {slot, label, message} object.")
        slot = change.get("slot")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise PagesetError("Each changed button needs a non-negative cell number.")
        if slot in seen:
            raise PagesetError("The same button cannot be changed twice in one edit.")
        seen.add(slot)
        label = change.get("label")
        if label is not None:
            if not isinstance(label, str):
                raise PagesetError("Each changed button label must be text.")
            label = label.strip()
            if not label:
                raise PagesetError("A changed button still needs a label.")
            if len(label) > MAX_LABEL_LENGTH:
                raise PagesetError(
                    f"Button label {label!r} is too long "
                    f"(maximum {MAX_LABEL_LENGTH} characters)."
                )
        message = change.get("message")
        if message is not None:
            if not isinstance(message, str):
                raise PagesetError("Each changed spoken message must be text.")
            message = message.strip()
            if len(message) > MAX_MESSAGE_LENGTH:
                raise PagesetError(
                    "A changed spoken message is too long "
                    f"(maximum {MAX_MESSAGE_LENGTH} characters)."
                )
        if label is None and message is None:
            raise PagesetError("A change must set a new label or a new spoken message.")
        normalized.append({"slot": slot, "label": label, "message": message})
    return normalized


def _normalize_removals(removals):
    """Bound and de-duplicate the slots a removal request names."""
    slots = []
    for slot in removals or ():
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise PagesetError("Each removed button needs a non-negative cell number.")
        if slot not in slots:
            slots.append(slot)
    return sorted(slots)


def _prior_content(page, changes, removals, by_slot):
    """Capture what every cell this edit will damage holds today.

    Refusing the whole edit when this cannot be read is the single most
    important rule on this path: without it, a failure part-way through a
    change or a removal has nothing to restore from.
    """
    touched = sorted({*removals, *(change["slot"] for change in changes)})
    if not touched:
        return {}
    content = _stored_page_content(page)
    if content is None:
        raise PagesetError(
            "AAC Editor couldn't read this page set's saved button content, so it "
            "won't change or remove anything here. Adding buttons still works."
        )
    prior = {}
    for slot in touched:
        label = by_slot.get(slot)
        if label is None:
            raise PagesetError(
                "One or more buttons in this edit are no longer where they were "
                "reviewed. Refresh the page layout and review the edit again."
            )
        stored = content.get(label.strip().casefold())
        if stored is None:
            raise PagesetError(
                f"AAC Editor couldn't read what {label!r} holds today, so it won't "
                "be changed or removed."
            )
        if stored["kind"] != "speak":
            raise PagesetError(f"{label!r} can't be edited. {LOCK_REASONS[stored['kind']]}")
        prior[slot] = stored
    return prior


def apply_page_edits(page, items=(), changes=(), removals=(), fingerprint=None):
    """Add, change, and remove reviewed buttons on one existing TD Snap page.

    One spine for all three so that a single review, fingerprint guard,
    edit-mode session, and rollback covers the whole edit rather than three
    partly-overlapping ones. Removals run first (they free the cells an add
    may have been placed in), then changes, then additions.
    """
    normalized = _normalize_items(items)
    changes = _normalize_changes(changes)
    removals = _normalize_removals(removals)
    if set(removals) & {change["slot"] for change in changes}:
        raise PagesetError("A button can't be changed and removed in the same edit.")
    if not (normalized or changes or removals):
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
    by_slot = {button["slot"]: button["label"] for button in existing}
    prior = _prior_content(requested, changes, removals, by_slot)

    # What the page will read as once this edit lands, used to catch a rename
    # or an addition that would leave two buttons sharing one label.
    remaining = {
        slot: label for slot, label in by_slot.items() if slot not in removals
    }
    for change in changes:
        if change["label"]:
            remaining[change["slot"]] = change["label"]
    labels = [
        label.strip().casefold() for label in remaining.values() if label.strip()
    ]
    repeated = sorted({label for label in labels if labels.count(label) > 1})
    if repeated:
        raise PagesetError(
            "Two buttons on this page would end up with the same label: "
            + ", ".join(repeated) + "."
        )
    duplicates = [item["label"] for item in normalized if item["label"].casefold() in labels]
    if duplicates:
        raise PagesetError(
            "Already on this page: " + ", ".join(duplicates) + ". Remove or rename duplicates before submitting."
        )
    occupied = set(by_slot) - set(removals)
    requested_slots = [item.get("slot") for item in normalized]
    if any(slot is None for slot in requested_slots):
        raise PagesetError("Review and place every new button in an empty cell before submitting.")
    if len(set(requested_slots)) != len(requested_slots):
        raise PagesetError("Two new buttons cannot use the same cell.")
    if any(not isinstance(slot, int) or slot in occupied or _cell_at(grid, slot) is None for slot in requested_slots):
        raise PagesetError("One or more selected cells are no longer empty. Refresh the page layout.")

    expected = [
        {"slot": item["slot"], "label": item["label"], "message": item["message"]}
        for item in normalized
    ] + [
        {
            "slot": change["slot"],
            "label": change["label"] or prior[change["slot"]]["label"],
            "message": (
                prior[change["slot"]]["message"]
                if change["message"] is None else change["message"]
            ),
        }
        for change in changes
    ]
    touched = set(requested_slots) | set(removals) | {c["slot"] for c in changes}
    untouched = {slot: label for slot, label in by_slot.items() if slot not in touched}
    # A removed cell an addition then fills is verified by that addition, not
    # by "this cell is empty" — removing a typo and typing the correction into
    # the same space is the most ordinary use of this whole feature.
    filled = {item["slot"] for item in expected}
    emptied = [slot for slot in removals if slot not in filled]
    restore_content = {
        slot: {"label": entry["label"], "message": entry["message"]}
        for slot, entry in prior.items()
    }

    _enter_edit_mode(window)
    symbols = 0
    styled = 0
    try:
        for slot in removals:
            _collapse_editor(window)
            edit_grid = _grid(_page_group(window))
            _remove_button(auto, window, _cell_at(edit_grid, slot), prior[slot]["label"])
        for change in changes:
            _collapse_editor(window)
            edit_grid = _grid(_page_group(window))
            _change_button(
                auto, window, _cell_at(edit_grid, change["slot"]),
                prior[change["slot"]]["label"], change["label"], change["message"],
            )
        for item in normalized:
            _collapse_editor(window)
            edit_grid = _grid(_page_group(window))
            result = _add_button(
                auto, window, _cell_at(edit_grid, item["slot"]), item["label"],
                item["message"], item["border_color"], item.get("symbol", True),
            )
            symbols += int(result["symbol"])
            styled += int(result["border"] and item["border_color"] is not None)
        _verify_page_state(window, expected, emptied, untouched)
        _exit_edit_mode(window)
        final_group = _page_group(window)
        final_grid = _grid(final_group)
        final_slots = {
            button["slot"]: button["label"] for button in _page_layout(final_group, final_grid)
        }
        missing = [
            item["label"] for item in expected
            if final_slots.get(item["slot"]) != item["label"]
        ]
        if missing:
            raise PagesetError(
                "TD Snap did not verify the edited button(s) in their reviewed cells: "
                + ", ".join(missing)
            )
        left_behind = [final_slots[slot] for slot in emptied if slot in final_slots]
        if left_behind:
            raise PagesetError(
                "TD Snap did not verify the removal of: " + ", ".join(left_behind)
            )
    except Exception as exc:
        steps = len(normalized) + len(changes) + len(removals)
        try:
            _restore_page_state(window, baseline, restore_content, steps * 6 + 8)
        except PagesetError as rollback_error:
            raise PagesetError(f"{exc} {rollback_error}") from exc
        raise PagesetError(f"{exc} The original page was restored.") from exc
    finally:
        _exit_edit_mode(window)

    expected_symbols = sum(item.get("symbol", True) for item in normalized)
    expected_styles = sum(item["border_color"] is not None for item in normalized)
    checks = {
        "td_snap_edit": "pass",
        "target_page": "pass",
        "content": "pass",
        "positions": "pass",
        "symbols": "pass" if symbols == expected_symbols else "partial",
        "topic_format": "pass" if styled == expected_styles else "partial",
    }
    if changes:
        checks["changed_content"] = "pass"
    if removals:
        checks["removed_buttons"] = "pass"
    if changes or removals:
        checks["untouched_buttons"] = "pass"
    return {
        "page": _page_name(window, final_group),
        "buttons": len(normalized),
        "changed": len(changes),
        "removed": len(removals),
        "checks": checks,
        "warnings": [warning for warning in [
            f"TD Snap could not find a symbol for {expected_symbols - symbols} button(s)."
            if symbols < expected_symbols else None,
            "Some topic border colors could not be applied automatically."
            if styled < expected_styles else None,
        ] if warning],
    }


def add_to_existing_page(page, items, fingerprint=None):
    """Add reviewed buttons to empty cells on an existing TD Snap page."""
    return apply_page_edits(page, items, fingerprint=fingerprint)


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

        _verify_page_state(window, placed)
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
