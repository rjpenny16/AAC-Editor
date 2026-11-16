"""The local operation log (REL-025, roadmap A4).

Before this, the packaged app wrote no log anywhere and no operation had an
ID, a start time or a duration, so every intermittent failure was
unrepeatable and unexplainable. This is one JSON-lines file in the app's data
folder (next to ``settings.json``), rotated at :data:`KEEP` files of
:data:`MAX_BYTES` each.

Summary level is always on: one record per operation. Diagnostic mode, which
the user switches on in settings, adds one record per step and switches
itself off after :data:`DIAGNOSTIC_HOURS` hours or :data:`DIAGNOSTIC_BYTES`
bytes.

**What is never written, at any level:** button labels, spoken messages, page
or grid names, vocabulary, AI prompts or outputs, file names, paths, user or
client names, and free-text exception messages. :func:`_clean` enforces this
by construction: only allow-listed field names are kept, and string values
must look like identifiers (codes, kinds, versions). Where a record needs to
say "the same page as before", it uses :func:`ident`, a salted hash whose
salt lives only in memory for this run.

Logging must never affect an operation: every public function here swallows
its own failures. ``tests/test_oplog.py`` holds that, and the seeded-label
privacy test in ``tests/test_privacy_contract.py`` holds the "never written"
list.
"""

import contextlib
import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections.abc import Iterator
from typing import Optional

from .. import errors
from . import settings

MAX_BYTES = 1024 * 1024
KEEP = 5
DIAGNOSTIC_HOURS = 24
DIAGNOSTIC_BYTES = 50 * 1024 * 1024

# One per process: tells two copies apart in one log (REL-010).
INSTANCE = secrets.token_hex(2)
_SALT = secrets.token_bytes(16)
_port: Optional[int] = None
_lock = threading.RLock()
_local = threading.local()

# Field names a record may carry. Anything else is dropped.
_FIELDS = {
    "t", "op", "kind", "app", "outcome", "code", "ms", "counts", "undo_presses",
    "fallbacks", "instance", "port", "exc", "step", "name", "polls", "result",
    "foreground", "edit_mode", "page", "version", "status", "engine", "model",
    "packaged", "python", "platform", "window", "elevated", "steps", "attempt",
    "launch", "deadline_ms", "cancelled", "event",
}
# A string value must look like a code, a kind or a version: no spaces, no
# path separators, short. Labels with spaces, paths and sentences fail this.
_TOKEN = re.compile(r"[A-Za-z0-9_.:+\-]{0,64}")


def ident(value) -> str:
    """A salted hash of *value*, stable within this run and meaningless after.

    For correlating records about the same page without naming it.
    """
    digest = hashlib.sha256(_SALT + str(value).encode("utf-8", "replace")).hexdigest()
    return digest[:10]


def set_port(port: Optional[int]) -> None:
    global _port
    _port = port


def log_dir() -> str:
    return os.path.join(settings._data_dir(), "logs")


def log_path() -> str:
    return os.path.join(log_dir(), "operations.jsonl")


def _diagnostic_path() -> str:
    return os.path.join(log_dir(), "diagnostic.json")


def _clean_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(value, 3) if isinstance(value, float) else value
    if isinstance(value, str):
        return value if _TOKEN.fullmatch(value) else "?"
    if isinstance(value, dict):
        return {
            str(key): _clean_value(item)
            for key, item in value.items()
            if isinstance(key, str) and _TOKEN.fullmatch(key)
            and (item is None or isinstance(item, (int, float, bool)))
        }
    if isinstance(value, (list, tuple)):
        return [_clean_value(item) for item in list(value)[:20]]
    return "?"


def _clean(fields: dict) -> dict:
    return {key: _clean_value(value) for key, value in fields.items() if key in _FIELDS}


def _rotate(path: str) -> None:
    if not os.path.exists(path) or os.path.getsize(path) < MAX_BYTES:
        return
    for index in range(KEEP - 1, 0, -1):
        older = f"{path}.{index}"
        newer = f"{path}.{index - 1}" if index > 1 else path
        if os.path.exists(newer):
            os.replace(newer, older)


def _write(record: dict) -> None:
    with _lock:
        path = log_path()
        settings.ensure_private_dir(log_dir())
        _rotate(path)
        line = json.dumps(record, separators=(",", ":"), sort_keys=False) + "\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(line)
        if diagnostic_enabled():
            _count_diagnostic_bytes(len(line))


def record(**fields) -> None:
    """Append one record. Never raises."""
    try:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        base = {"t": f"{stamp}.{int(time.time() * 1000) % 1000:03d}Z",
                "instance": INSTANCE, "port": _port}
        _write({**base, **_clean(fields)})
    except Exception:  # noqa: S110 - logging must never break an operation
        pass


# ---------------------------------------------------------------------------
# diagnostic mode


def _diagnostic_state() -> dict:
    try:
        with open(_diagnostic_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def diagnostic_enabled() -> bool:
    state = _diagnostic_state()
    since = state.get("since")
    if not isinstance(since, (int, float)):
        return False
    if time.time() - since > DIAGNOSTIC_HOURS * 3600:
        return False
    return int(state.get("bytes", 0)) < DIAGNOSTIC_BYTES


def diagnostic_status() -> dict:
    state = _diagnostic_state()
    on = diagnostic_enabled()
    since = state.get("since") if on else None
    return {
        "enabled": on,
        "since": since,
        "until": since + DIAGNOSTIC_HOURS * 3600 if since else None,
        "bytes": int(state.get("bytes", 0)) if on else 0,
        "limit_bytes": DIAGNOSTIC_BYTES,
    }


def set_diagnostic(enabled: bool) -> dict:
    """Switch diagnostic mode on (for 24 hours) or off. Never raises."""
    try:
        with _lock:
            if enabled:
                settings.ensure_private_dir(log_dir())
                with open(_diagnostic_path(), "w", encoding="utf-8") as handle:
                    json.dump({"since": time.time(), "bytes": 0}, handle)
            else:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(_diagnostic_path())
        record(kind="diagnostic", event="on" if enabled else "off")
    except Exception:  # noqa: S110
        pass
    return diagnostic_status()


def _count_diagnostic_bytes(count: int) -> None:
    state = _diagnostic_state()
    if "since" not in state:
        return
    state["bytes"] = int(state.get("bytes", 0)) + count
    with open(_diagnostic_path(), "w", encoding="utf-8") as handle:
        json.dump(state, handle)


# ---------------------------------------------------------------------------
# operations


class Operation:
    """One user-visible operation: an ID, a kind, a duration and an outcome.

    Live modules reach the operation running on their thread through
    :func:`current` and add to it (:meth:`fallback`, :meth:`count`,
    :meth:`undo`, :meth:`step`) without it being passed around.
    """

    def __init__(self, kind: str, app: Optional[str] = None):
        self.id = secrets.token_hex(2)
        self.kind = kind
        self.app = app
        self.started = time.monotonic()
        self.outcome: Optional[str] = None
        self.code: Optional[str] = None
        self.exc: Optional[str] = None
        self.counts: dict = {}
        self.fallbacks: list = []
        self.undo_presses = 0
        self.steps = 0
        self.extra: dict = {}
        self.finished = False

    # -- what live code adds while it runs --------------------------------
    def fallback(self, code: str) -> None:
        if code not in self.fallbacks:
            self.fallbacks.append(code)

    def count(self, name: str, amount: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + amount

    def undo(self) -> None:
        self.undo_presses += 1

    def step(self, name: str, **fields) -> None:
        self.steps += 1
        if diagnostic_enabled():
            record(op=self.id, kind="step", step=self.steps, name=name, **fields)

    def fail(self, error: BaseException) -> None:
        self.outcome = errors.outcome_of(error)
        self.code = errors.code_of(error)
        self.exc = type(error).__name__

    def finish(self, outcome: Optional[str] = None, code: Optional[str] = None, **extra) -> None:
        if self.finished:
            return
        self.finished = True
        if outcome:
            self.outcome = outcome
        if code:
            self.code = code
        record(
            op=self.id, kind=self.kind, app=self.app, outcome=self.outcome or "ok",
            code=self.code, ms=int((time.monotonic() - self.started) * 1000),
            counts=self.counts or None, undo_presses=self.undo_presses or None,
            fallbacks=self.fallbacks or None, exc=self.exc, steps=self.steps or None,
            **{**self.extra, **extra},
        )


def current() -> Optional[Operation]:
    """The operation running on this thread, if any."""
    stack = getattr(_local, "stack", None)
    return stack[-1] if stack else None


@contextlib.contextmanager
def bound(op: Optional[Operation]) -> Iterator[Optional[Operation]]:
    """Make *op* the current operation on this thread for the block."""
    stack = getattr(_local, "stack", None)
    if stack is None:
        stack = _local.stack = []
    stack.append(op)
    try:
        yield op
    finally:
        stack.pop()


@contextlib.contextmanager
def operation(kind: str, app: Optional[str] = None) -> Iterator[Operation]:
    """Time and record the block as one operation. Re-raises what it catches."""
    op = Operation(kind, app)
    with bound(op):
        try:
            yield op
        except BaseException as exc:
            op.fail(exc)
            op.finish()
            raise
    op.finish()


def fallback(code: str) -> None:
    """Note on the current operation that a fallback path was taken."""
    with contextlib.suppress(Exception):
        op = current()
        if op is not None:
            op.fallback(code)


def step(name: str, **fields) -> None:
    """Note a step on the current operation (written in diagnostic mode)."""
    with contextlib.suppress(Exception):
        op = current()
        if op is not None:
            op.step(name, **fields)


def note_undo() -> None:
    with contextlib.suppress(Exception):
        op = current()
        if op is not None:
            op.undo()


def count(name: str, amount: int = 1) -> None:
    with contextlib.suppress(Exception):
        op = current()
        if op is not None:
            op.count(name, amount)


# ---------------------------------------------------------------------------
# reading and clearing


def _files_newest_first() -> list:
    path = log_path()
    return [p for p in [path, *(f"{path}.{i}" for i in range(1, KEEP))] if os.path.exists(p)]


def recent(limit: int = 50, *, include_steps: bool = False) -> list:
    """The last *limit* records, oldest first. Never raises."""
    out: list = []
    try:
        for path in _files_newest_first():
            with open(path, encoding="utf-8") as handle:
                lines = handle.readlines()
            for line in reversed(lines):
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if not include_steps and item.get("kind") == "step":
                    continue
                out.append(item)
                if len(out) >= limit:
                    return list(reversed(out))
    except OSError:
        pass
    return list(reversed(out))


def steps_for(op_id: str) -> list:
    """Every step record of operation *op_id*, oldest first."""
    return [item for item in recent(2000, include_steps=True)
            if item.get("op") == op_id and item.get("kind") == "step"]


def last_failed() -> Optional[dict]:
    for item in reversed(recent(200)):
        failed = item.get("outcome") not in (None, "ok", errors.VERIFIED, errors.REFUSED) \
            or item.get("code") not in (None, "REFUSED")
        if failed and item.get("op"):
            return item
    return None


def clear() -> None:
    """Delete the log and diagnostic state (part of "Clear all saved data")."""
    with _lock:
        for path in [*_files_newest_first(), _diagnostic_path()]:
            with contextlib.suppress(FileNotFoundError):
                os.remove(path)
