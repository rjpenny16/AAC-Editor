"""One running copy of AAC Editor per user (REL-010, roadmap C6).

There used to be no lock. A second launch probed port 8765 for one second;
if the running copy was slow to answer (hashing a model, in a long
automation call, Windows busy at login) the second launch decided the port
belonged to something else and started its own server on a random port. Two
copies then shared settings.json, the working-copy folder and the model
download, and "Clear all saved data" in one deleted the other's work.

Now a lock is taken before anything else: a named mutex on Windows, an
advisory lock on a file elsewhere. The running copy records its port beside
the lock, so a second launch can find it even on a non-default port, ask it
to show its window, and exit.
"""

import contextlib
import json
import os
import sys
import time
from typing import Optional

from . import settings

_held = None  # the OS object that holds the lock while this process runs


def _lock_dir() -> str:
    return settings._data_dir()


def _info_path() -> str:
    return os.path.join(_lock_dir(), "instance.json")


def _mutex_name() -> str:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    safe = "".join(ch for ch in user if ch.isalnum())[:40] or "user"
    return f"Local\\AACEditor-{safe}"


def _acquire_windows() -> Optional[object]:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateMutexW(None, True, _mutex_name())
    already_exists = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    if not handle:
        return None
    if already_exists:
        kernel32.CloseHandle(handle)
        return None
    return handle


def _acquire_posix() -> Optional[object]:
    import fcntl

    settings.ensure_private_dir(_lock_dir())
    handle = open(os.path.join(_lock_dir(), "instance.lock"), "a+")  # noqa: SIM115 - held for the process lifetime
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def acquire(wait: float = 0.0) -> bool:
    """Take the single-instance lock; True if this process now holds it.

    *wait* seconds are spent retrying, for a copy restarting itself (the
    administrator restart for Grid 3) while the old one exits.
    """
    global _held
    if _held is not None:
        return True
    deadline = time.monotonic() + wait
    while True:
        try:
            _held = _acquire_windows() if sys.platform == "win32" else _acquire_posix()
        except OSError:
            _held = None
        if _held is not None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


def record_port(port: int) -> None:
    """Say where this copy is listening, for the next launch to find it."""
    with contextlib.suppress(OSError):
        settings.ensure_private_dir(_lock_dir())
        with open(_info_path(), "w", encoding="utf-8") as handle:
            json.dump({"port": int(port), "pid": os.getpid()}, handle)


def running_port() -> Optional[int]:
    """The port the copy holding the lock recorded, if any."""
    try:
        with open(_info_path(), encoding="utf-8") as handle:
            port = json.load(handle).get("port")
    except (OSError, ValueError, AttributeError):
        return None
    return port if isinstance(port, int) and 0 < port < 65536 else None


def release() -> None:
    global _held
    held, _held = _held, None
    if held is None:
        return
    with contextlib.suppress(OSError, ValueError):
        os.remove(_info_path())
    if sys.platform == "win32":  # pragma: no cover - Windows only
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex(held)
        kernel32.CloseHandle(held)
    else:
        with contextlib.suppress(OSError):
            held.close()


def is_held() -> bool:
    return _held is not None
