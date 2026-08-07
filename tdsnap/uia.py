"""Shared Windows UI Automation helpers behind TD Snap and Grid 3 editing.

``tdsnap/live.py`` (TD Snap) and ``tdsnap/grid3.py`` (Grid 3) each drove the
same ``uiautomation`` control tree independently, and by the time this module
was extracted twelve identically-named functions existed in both files —
three of them had already diverged in behaviour. Each divergence below was
resolved deliberately, not by keeping whichever file happened to be older:

- **``walk()``**: ``max_depth=10`` and a ``try``/``except`` around
  ``GetChildren()``. 10 is a strict superset of TD Snap's old default of 9 —
  raising it cannot change which match a breadth-first ``_find()`` returns
  for anything already reachable at depth 9 (BFS visits shallower nodes
  first regardless of the depth cutoff); it can only make deeper matches
  reachable, and Grid 3's WPF visual tree already needed that extra level.
  The ``try``/``except`` (from ``grid3.py``) guards a real race — a control
  disappearing mid-walk while Edit Mode repaints — and is a strict safety
  addition for TD Snap too, which never hit it only because nothing had
  triggered the race yet.
- **``clusters()``**: ``tolerance=8``. TD Snap's tolerance was measured
  against its own button grid; ``grid3.py``'s tighter 6 was never explained
  in a comment or commit, and Grid 3's cells are typically larger and better
  separated, so the looser tolerance is strictly safer there too — it can
  only merge points that are genuinely close together. ``statistics.mean``
  and the hand-rolled ``sum(group) / len(group)`` it replaces compute the
  same value for a non-empty group (every group here always has at least one
  element); ``statistics.mean`` is kept for the clearer intent.
- **``activate()``**: retries ``Invoke()`` for 30s against the transient
  ``UIA_E_ELEMENTNOTENABLED`` HRESULT (TD Snap's rationale: a control can be
  briefly disabled while TD Snap finishes rendering an image), then falls
  back to ``SelectionItemPattern``, then a raw ``Click()``. The retry only
  ever fires for that one specific HRESULT — every other exception still
  raises immediately — so carrying it over to Grid 3 can only help, never
  introduce a new failure mode.
- **``wait_for()``**: the shared default timeout is 8s, matching Grid 3's
  original default rather than TD Snap's 6s. Widening a timeout can only
  make a genuine failure take longer to report, never mask one, so the more
  patient value was kept. Grid 3's ``ignore=`` of transient
  ``OSError``/``BadZipFile``/``KeyError`` while polling a grid-set package
  mid-edit is *not* a divergence to resolve away — it is a genuine per-product
  difference (TD Snap's callbacks only ever touch the live control tree, never
  a file on disk) — so it stays a caller-supplied parameter instead of a
  hard-coded default.

Three of the twelve names are **not** merged here, and that is itself a
deliberate choice, not an oversight:

- **``window()``**: TD Snap is a single well-known UWP window found by name;
  Grid 3's window title varies with whichever grid set is open and is found
  by enumerating native windows for a title prefix. Different discovery
  strategies, not accidental drift.
- **``verify_process()``**: TD Snap is verified by its packaged
  ApplicationUserModelId; Grid 3 by its installed ``.exe`` path — different
  Windows identity mechanisms for a UWP app versus a traditional desktop one.
  The shared ``ctypes`` plumbing each strategy is built on
  (``process_app_user_model_id()`` / ``process_image_path()``) lives here;
  the choice of which one to call, and what "expected" means, stays in each
  product module.
- **``fingerprint()`` / ``grid()``**: TD Snap's fingerprint and grid geometry
  come from measuring the live control tree (no other source of truth
  exists once a page is open); Grid 3's fingerprint hashes the grid set's
  on-disk XML and its geometry comes from parsing that XML directly. These
  are different concepts that happen to share a name, not the same
  operation implemented twice.
"""

import ctypes
import statistics
import sys
import time
from ctypes import wintypes

from .errors import PagesetError

# ---------------------------------------------------------------------------
# uiautomation setup


def automation(platform_message: str, missing_message: str):
    """Import and configure ``uiautomation``, or raise a product-specific error.

    *platform_message* is raised outside Windows; *missing_message* is raised
    when the ``uiautomation`` package itself is not importable (it ships with
    the packaged app, so this should only happen in an unusual install).
    """
    if sys.platform != "win32":
        raise PagesetError(platform_message)
    try:
        import uiautomation as auto
    except ImportError as exc:
        raise PagesetError(missing_message) from exc
    auto.SetGlobalSearchTimeout(2)
    return auto


# ---------------------------------------------------------------------------
# control-tree walking

WALK_MAX_DEPTH = 10


def walk(root, max_depth=WALK_MAX_DEPTH):
    """Breadth-first walk of *root*'s control tree, yielding ``(control, depth)``.

    A control that vanishes mid-walk (``GetChildren()`` raising) is skipped
    rather than propagated — Edit Mode in either product can repaint while a
    walk is in progress.
    """
    queue = [(root, 0)]
    while queue:
        control, depth = queue.pop(0)
        yield control, depth
        if depth < max_depth:
            try:
                queue.extend((child, depth + 1) for child in control.GetChildren())
            except Exception:  # noqa: S112 - a control that vanished mid-walk is expected; skip it
                continue


# ---------------------------------------------------------------------------
# coordinate clustering

CLUSTER_TOLERANCE = 8


def clusters(values, tolerance=CLUSTER_TOLERANCE):
    """Group nearby coordinate *values* into their rounded mean centers."""
    groups = []
    for value in sorted(values):
        if not groups or value - statistics.mean(groups[-1]) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return tuple(round(statistics.mean(group)) for group in groups)


# ---------------------------------------------------------------------------
# activating a control

ACTIVATE_RETRY_SECONDS = 30
# UIA_E_ELEMENTNOTENABLED: transient while the target app is still rendering
# (e.g. an image or symbol loading), not a real failure.
_UIA_E_ELEMENTNOTENABLED = -2147220992


def activate(
    control,
    *,
    missing_message="The control changed while the edit was running.",
    busy_message="The control stayed busy too long to activate.",
) -> None:
    """Invoke *control* the most direct way its automation pattern allows.

    *missing_message* and *busy_message* let each product name itself in the
    two errors this can raise; the activation logic itself is identical.
    """
    if control is None:
        raise PagesetError(missing_message)
    getter = getattr(control, "GetInvokePattern", None)
    pattern = getter() if getter else None
    if pattern:
        deadline = time.monotonic() + ACTIVATE_RETRY_SECONDS
        while True:
            try:
                pattern.Invoke()
                return
            except Exception as exc:
                if getattr(exc, "hresult", None) != _UIA_E_ELEMENTNOTENABLED:
                    raise
                if time.monotonic() >= deadline:
                    raise PagesetError(busy_message) from exc
                time.sleep(0.15)
    getter = getattr(control, "GetSelectionItemPattern", None)
    pattern = getter() if getter else None
    if pattern:
        pattern.Select()
        return
    control.Click(simulateMove=False)


# ---------------------------------------------------------------------------
# polling

WAIT_DEFAULT_TIMEOUT = 8


def wait_for(callback, message, timeout=WAIT_DEFAULT_TIMEOUT, ignore=()):
    """Poll *callback* until truthy, or raise ``PagesetError(message)``.

    *ignore* names exception types that count as "not yet" instead of a hard
    failure — see the module docstring for why this is a caller-supplied
    parameter rather than a hard-coded default.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = callback()
        except ignore:
            value = None
        if value:
            return value
        time.sleep(0.15)
    raise PagesetError(message)


# ---------------------------------------------------------------------------
# process identity

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_app_user_model_id(process_id: int):
    """UWP/MSIX package application ID for *process_id*, if available."""
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
    process = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
    )
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


def process_image_path(process_id: int):
    """Full executable path for *process_id*, if available."""
    if sys.platform != "win32" or not process_id:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    process = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
    )
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
