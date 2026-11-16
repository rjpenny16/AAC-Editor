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

import contextlib
import ctypes
import os
import queue
import statistics
import sys
import threading
import time
from ctypes import wintypes

from .errors import PagesetError

# ---------------------------------------------------------------------------
# the one thread that drives TD Snap and Grid 3


def _initialize_com():
    """Set up COM for UI Automation on the calling thread.

    ``uiautomation`` is COM underneath, and its documentation is explicit: a
    thread that uses it must initialize it first, and a control found on one
    thread must not be used from another. The web server answers each request
    on a fresh, short-lived thread and did neither, so an automation call
    worked or failed depending on which thread happened to create the shared
    COM object and whether that thread still existed. Returns the initializer,
    which must stay referenced for as long as the thread runs.
    """
    if sys.platform != "win32":
        return None
    try:
        import uiautomation as auto
    except ImportError:
        return None
    return auto.UIAutomationInitializerInThread()


class AutomationThread:
    """Run every TD Snap and Grid 3 automation call on one long-lived thread.

    One thread means COM is initialized once, in the apartment every control
    is then created and used in, and it means two calls can never drive the
    same app at once. Callers block until their call finishes, and an
    exception raised by the call is raised again in the caller.
    """

    def __init__(self, initialize=_initialize_com):
        self._initialize = initialize
        self._jobs = queue.SimpleQueue()
        self._thread = None
        self._start_lock = threading.Lock()

    def _loop(self):
        initializer = None
        try:
            initializer = self._initialize()
        except Exception as exc:  # reported to every caller rather than lost
            startup_error = exc
        else:
            startup_error = None
        while True:
            call, outcome, done = self._jobs.get()
            try:
                if startup_error is not None:
                    raise PagesetError(
                        "Windows automation could not start. Restart AAC Editor and try again."
                    ) from startup_error
                outcome["result"] = call()
            except BaseException as exc:  # handed back to the waiting caller
                outcome["error"] = exc
            finally:
                done.set()
        del initializer  # pragma: no cover - the loop never exits

    def _ensure_started(self):
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._loop, name="aac-editor-automation", daemon=True
                )
                self._thread.start()

    def run(self, call):
        """Run *call* on the automation thread and return what it returns."""
        if threading.current_thread() is self._thread:
            return call()
        self._ensure_started()
        outcome = {}
        done = threading.Event()
        self._jobs.put((call, outcome, done))
        done.wait()
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("result")


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
# Every wait gets at least this many polls, however short its timeout: a
# 2 s wait on a slow PC used to get one or two tree walks (REL-017).
WAIT_MIN_POLLS = 3

# What a UI Automation read raises when the element went away between being
# found and being read: COMError from comtypes on Windows, OSError otherwise.
try:  # pragma: no cover - Windows only
    from _ctypes import COMError as _COMError

    VANISHED = (OSError, _COMError)
except ImportError:  # pragma: no cover - non-Windows interpreters
    VANISHED = (OSError,)


def wait_for(callback, message, timeout=WAIT_DEFAULT_TIMEOUT, ignore=(),
             min_polls=WAIT_MIN_POLLS):
    """Poll *callback* until truthy, or raise ``PagesetError(message)``.

    REL-017, roadmap C2:

    - an element that vanishes during a read (the AAC app repainted) counts
      as "not yet" and is polled again, instead of failing the operation;
    - there is always one poll after the deadline has passed, so a value that
      arrived during the last sleep is not missed;
    - the wait lasts at least *timeout* seconds **and** *min_polls* polls.

    *ignore* names further exception types that count as "not yet"; see the
    module docstring for why that is a caller-supplied parameter.
    """
    started = time.monotonic()
    deadline = started + timeout
    polls = 0
    tolerated = (*VANISHED, *tuple(ignore or ()))
    while True:
        polls += 1
        try:
            value = callback()
        except tolerated:
            value = None
        if value:
            _note_wait(started, polls, "ok")
            return value
        if time.monotonic() >= deadline and polls >= min_polls:
            break
        time.sleep(0.15)
    _note_wait(started, polls, "timeout")
    raise PagesetError(message)


def _note_wait(started: float, polls: int, result: str) -> None:
    """A step record for diagnostic mode: how long a wait took and how many
    polls it got. That is the evidence for or against REL-017."""
    try:
        from .web import oplog

        oplog.step("wait", polls=polls, ms=int((time.monotonic() - started) * 1000),
                   result=result)
    except Exception:  # noqa: S110 - logging must never change what a wait does
        pass


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


# ---------------------------------------------------------------------------
# Foreground (REL-005, roadmap C1)
#
# Raw input (a mouse click at screen coordinates, a drag, a key press) goes
# to whichever window is in front. TD Snap's path used to call SetFocus once
# per edit and ignore the result; Grid 3's checked the foreground *process*
# before every key. Both now go through require_foreground before every raw
# input. Windows may refuse to hand the foreground to a background process;
# nothing here tries to force it. A minimised window is restored, one
# ordinary focus request is made, and if the AAC app is still not in front
# the step is refused and the person is asked to click it.

_GA_ROOT = 2
_SW_RESTORE = 9


def _user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    return user32


def foreground_state(window) -> tuple:
    """``(window_in_front, process_in_front)`` for *window*; both True off Windows."""
    if sys.platform != "win32":
        return True, True
    handle = getattr(window, "NativeWindowHandle", 0)
    if not handle:
        return False, False
    user32 = _user32()
    foreground = user32.GetForegroundWindow()
    if not foreground:
        return False, False
    root = user32.GetAncestor(foreground, _GA_ROOT) or foreground
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
    same_window = int(root or 0) == int(handle) or int(foreground) == int(handle)
    return same_window, process_id.value == getattr(window, "ProcessId", -1)


def require_foreground(window, app_name: str, *, same_process_ok: bool = False) -> None:
    """Refuse a raw input unless *window* is the window in front.

    *same_process_ok* accepts any window of the same process: Grid 3 drives
    its own Create Cell dialogs by keyboard, so for Grid 3 the check stays
    per process until session T3-1 shows those dialogs' window identity.
    """
    window_ok, process_ok = foreground_state(window)
    if window_ok or (same_process_ok and process_ok):
        return
    handle = getattr(window, "NativeWindowHandle", 0)
    if sys.platform == "win32" and handle:
        user32 = _user32()
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, _SW_RESTORE)
            time.sleep(0.3)
    with contextlib.suppress(Exception):
        window.SetFocus()
        time.sleep(0.2)
    window_ok, process_ok = foreground_state(window)
    if window_ok or (same_process_ok and process_ok):
        return
    raise PagesetError(
        f"{app_name} is not the window in front, so AAC Editor sent nothing to it. "
        f"Click on {app_name} to bring it to the front, then try again.",
        code="NOT_FOREGROUND",
    )


# ---------------------------------------------------------------------------
# Integrity level (REL-023)
#
# Windows silently drops input sent to a process running at a higher
# integrity level (an elevated app) from a lower one. That used to show up
# only as timeouts such as "TD Snap did not open a button in the empty cell".

_TOKEN_QUERY = 0x0008
_TOKEN_INTEGRITY_LEVEL = 25


def process_integrity_level(process_id: int):
    """The mandatory integrity RID of *process_id* (e.g. 0x2000 medium,
    0x3000 high), or None when it cannot be read or off Windows."""
    if sys.platform != "win32" or not process_id:
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        advapi32.OpenProcessToken.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi32.GetTokenInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD)]
        advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
        process = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
        if not process:
            return None
        try:
            token = wintypes.HANDLE()
            if not advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)):
                return None
            try:
                size = wintypes.DWORD()
                advapi32.GetTokenInformation(
                    token, _TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(size))
                buffer = ctypes.create_string_buffer(size.value)
                if not advapi32.GetTokenInformation(
                        token, _TOKEN_INTEGRITY_LEVEL, buffer, size, ctypes.byref(size)):
                    return None
                sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
                count = advapi32.GetSidSubAuthorityCount(sid)[0]
                return int(advapi32.GetSidSubAuthority(sid, count - 1)[0])
            finally:
                kernel32.CloseHandle(token)
        finally:
            kernel32.CloseHandle(process)
    except (OSError, AttributeError, ValueError):
        return None


def require_not_more_elevated(window, app_name: str) -> None:
    """Refuse, at connect, when the AAC app runs above this app's integrity."""
    theirs = process_integrity_level(getattr(window, "ProcessId", 0))
    ours = process_integrity_level(os.getpid())
    if theirs is not None and ours is not None and theirs > ours:
        raise PagesetError(
            f"{app_name} is running as administrator and AAC Editor is not, so Windows "
            f"would silently drop every click AAC Editor sends it. Close {app_name} and "
            "start it normally (not with Run as administrator), then try again.",
            code="ELEVATION_MISMATCH",
        )
