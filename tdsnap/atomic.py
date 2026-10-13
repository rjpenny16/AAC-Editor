"""Durable atomic file writes.

``os.replace`` alone keeps a reader from ever seeing a half-written file, but
it does not survive a crash or power loss: the rename can reach the disk while
the data blocks do not, leaving a zero-length file under the final name. For
the settings, drafts, and exported page sets this app writes, that is the
worst outcome, so every write goes through here: write to a temp file beside
the destination, flush it to disk, rename it into place, then flush the
directory entry.
"""

import contextlib
import os
import shutil
import tempfile
from typing import Union


def _fsync_directory(directory: str) -> None:
    """Flush a directory entry; a no-op where the platform cannot open one."""
    if os.name == "nt":
        return
    with contextlib.suppress(OSError):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def replace_durably(temporary: str, dest_path: str) -> None:
    """Flush *temporary* to disk, then rename it over *dest_path*."""
    with open(temporary, "rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, dest_path)
    _fsync_directory(os.path.dirname(os.path.abspath(dest_path)))


def atomic_write(
    dest_path: str,
    data: Union[bytes, str],
    *,
    prefix: str = ".atomic-",
    suffix: str = "",
    encoding: str = "utf-8",
) -> None:
    """Write *data* to *dest_path* so it is either fully there or untouched."""
    directory = os.path.dirname(os.path.abspath(dest_path)) or os.curdir
    descriptor, temporary = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=directory)
    try:
        if isinstance(data, str):
            with os.fdopen(descriptor, "w", encoding=encoding, newline="") as handle:
                handle.write(data)
        else:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
        replace_durably(temporary, dest_path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(temporary)


def atomic_copy(
    source_path: str, dest_path: str, *, prefix: str = ".atomic-", suffix: str = ""
) -> None:
    """Copy *source_path* over *dest_path* with the same all-or-nothing guarantee."""
    directory = os.path.dirname(os.path.abspath(dest_path)) or os.curdir
    descriptor, temporary = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=directory)
    os.close(descriptor)
    try:
        shutil.copyfile(source_path, temporary)
        replace_durably(temporary, dest_path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(temporary)
