"""Opt-in local settings: remembered preferences and an in-progress draft.

Nothing here is written until the user does something that implies a save —
changing a preference, or the draft autosave that runs while a page is being
composed. A fresh install therefore creates no file at all, matching the
model download's "nothing until asked" behavior in ``localai.py``.

Stored at ``settings.json`` in the same per-user data directory
``localai.py``'s model downloader already uses, so there is exactly one
"AAC Editor keeps files here" location to document and to clear.

A corrupt file (bad JSON, wrong shape, or implausibly large) is renamed aside
with a timestamp suffix rather than deleted or trusted — recoverable for a
curious user, but never allowed to block startup. This mirrors how a rejected
page-set upload leaves no session behind in ``server.py``.
"""

import contextlib
import json
import os
import tempfile
import threading
import time
from typing import Optional

SETTINGS_VERSION = 1
# Preferences and a draft item list are both small JSON; this is generous
# headroom while still catching a runaway or hand-edited file early.
MAX_SETTINGS_BYTES = 2 * 1024 * 1024

_lock = threading.Lock()


def _data_dir() -> str:
    """Per-user data dir: %LOCALAPPDATA% on Windows, XDG data home elsewhere.

    Same root as ``localai._models_dir()`` — deliberately, so there is one
    directory to name in the Settings disclosure and in "Clear all saved
    data", not two.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get(
            "XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share")
        )
    return os.path.join(base, "tdsnap-editor")


def settings_path() -> str:
    return os.path.join(_data_dir(), "settings.json")


def _empty() -> dict:
    return {
        "version": SETTINGS_VERSION,
        "preferences": {},
        "draft": None,
        "templates": [],
    }


def _quarantine(path: str) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    with contextlib.suppress(OSError):
        os.replace(path, f"{path}.corrupt-{stamp}")


def load() -> dict:
    """Return the stored settings, or the empty default if none exist yet.

    Never raises: a missing, corrupt, oversized, or malformed file is treated
    as "no settings yet" rather than surfaced to the caller.
    """
    path = settings_path()
    with _lock:
        try:
            if os.path.getsize(path) > MAX_SETTINGS_BYTES:
                _quarantine(path)
                return _empty()
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return _empty()
        except (OSError, ValueError):
            _quarantine(path)
            return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("preferences"), dict):
        _quarantine(path)
        return _empty()
    draft = data.get("draft")
    templates = data.get("templates")
    return {
        "version": SETTINGS_VERSION,
        "preferences": data["preferences"],
        "draft": draft if isinstance(draft, dict) else None,
        # A file written before templates existed simply has none, rather than
        # being treated as corrupt — the whole point of quarantining a bad file
        # is that a merely *older* one is not bad.
        "templates": templates if isinstance(templates, list) else [],
    }


def save(preferences: dict, draft: Optional[dict], templates: Optional[list] = None) -> None:
    """Atomically write *preferences*, *draft*, and *templates*.

    This is the only function that creates the file — a fresh install writes
    nothing until a caller reaches this. Temp-then-``os.replace`` mirrors
    ``Pageset.save_as``, so a crash mid-write leaves the previous file intact
    rather than a half-written one.

    ``templates=None`` keeps whatever is already stored. A saved template is
    work the user did deliberately and expects to find later, so a caller that
    does not mention templates — the draft autosave, every few seconds — must
    not be able to erase them. Passing ``[]`` is how they are actually cleared.
    """
    if templates is None:
        templates = load()["templates"]
    payload = {
        "version": SETTINGS_VERSION,
        "preferences": preferences,
        "draft": draft,
        "templates": templates,
    }
    encoded = json.dumps(payload, indent=2)
    directory = _data_dir()
    os.makedirs(directory, exist_ok=True)
    with _lock:
        handle, temp_path = tempfile.mkstemp(prefix=".settings-", dir=directory)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
                temp_file.write(encoded)
            os.replace(temp_path, settings_path())
        finally:
            with contextlib.suppress(OSError):
                os.remove(temp_path)


def clear() -> None:
    """Delete the settings file — the "Clear all saved data" action."""
    with _lock, contextlib.suppress(OSError):
        os.remove(settings_path())
