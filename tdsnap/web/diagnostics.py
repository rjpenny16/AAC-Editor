"""A copy-and-paste environment summary for bug reports.

Deliberately excludes every piece of page-set content. No page titles, button
labels, spoken messages, grid-set names, file paths, or user names ever reach
this report — only environment facts a maintainer needs to reproduce a
problem: versions, capability flags, and grid dimensions.

That exclusion is the whole point. ``SECURITY.md`` asks people not to attach
real page sets or AAC vocabulary to an issue, so the report the app offers
them has to be safe to paste in full without reading it first.

Nothing here leaves the machine: the only request made is the same loopback
probe the AI panel already performs against a local Ollama server.
"""

import os
import platform
import sys
from typing import Optional

from .. import __version__, grid3, live
from ..errors import PagesetError
from . import localai, ollama, oplog

# How many recent operation records a report carries.
RECENT_OPERATIONS = 30

# Keys worth reporting from live.status() / grid3.status(). Everything else
# those functions return is user content and is dropped: TD Snap's "page" and
# "pages", Grid 3's "grid_set", "page", and "user".
_LIVE_KEYS = ("available", "running", "unlocked", "error", "version")
_GRID3_KEYS = (
    "available", "installed", "running", "unlocked", "elevated",
    "needs_elevation", "version", "compatibility_warning", "error",
)


def _grid_size(status: dict) -> str:
    """Return "cols x rows" for the open page — a shape, not its content."""
    grid = status.get("grid")
    if isinstance(grid, dict) and grid.get("cols") and grid.get("rows"):
        return f"{grid['cols']}x{grid['rows']}"
    return "unknown"


def _picked(status: dict, keys) -> dict:
    return {key: status[key] for key in keys if key in status}


def _tdsnap() -> dict:
    """TD Snap capability facts. ``include_pages=False`` keeps vocabulary out."""
    try:
        status = live.status(False)
    except (PagesetError, OSError, RuntimeError) as exc:
        # The class, never the message: a message can name a page.
        return {"probe_failed": type(exc).__name__}
    report = _picked(status, _LIVE_KEYS)
    if "error" in report:
        report["error"] = "present"
    if status.get("running"):
        report["grid"] = _grid_size(status)
    return report


def _grid3() -> dict:
    try:
        status = grid3.status()
    except (PagesetError, OSError, RuntimeError) as exc:
        return {"probe_failed": type(exc).__name__}
    report = _picked(status, _GRID3_KEYS)
    if "error" in report:
        report["error"] = "present"
    if status.get("running"):
        report["grid"] = _grid_size(status)
    try:
        report["ui_access"] = grid3.has_ui_access()
    except (OSError, RuntimeError):
        report["ui_access"] = "unknown"
    return report


def _ai() -> dict:
    # Which model, not just whether one is present: a support report that says
    # "downloaded" without naming it cannot explain why one machine's
    # suggestions are better than another's.
    active = localai.choice_for(localai.active_key())
    memory = localai.total_memory_bytes()
    report = {
        "engine_available": localai.engine_available(),
        "model_downloaded": localai.is_downloaded(active.key),
        "model": active.name,
        "models_downloaded": localai.downloaded_keys(),
        "memory_gb": round(memory / localai.GIB, 1) if memory else "unknown",
    }
    report["launch"] = localai.launch_mode()
    try:
        report["ollama_reachable"] = bool(ollama.status(ollama.DEFAULT_HOST).get("reachable"))
    except (ValueError, OSError, RuntimeError):
        report["ollama_reachable"] = False
    return report


def _operation_line(item: dict) -> str:
    """One log record as one line: codes and numbers only (see oplog)."""
    keys = ("op", "kind", "app", "outcome", "code", "ms", "undo_presses", "fallbacks",
            "exc", "status", "instance", "port")
    parts = [f"{key}={item[key]}" for key in keys if item.get(key) not in (None, "", [])]
    if item.get("counts"):
        parts.append("counts=" + ",".join(f"{k}:{v}" for k, v in item["counts"].items()))
    return f"{item.get('t', '?')} " + " ".join(parts)


def _operations() -> dict:
    records = oplog.recent(RECENT_OPERATIONS)
    section = {"diagnostic_mode": oplog.diagnostic_status()["enabled"],
               "instance": oplog.INSTANCE}
    for index, item in enumerate(records, 1):
        section[f"{index:02d}"] = _operation_line(item)
    failed = oplog.last_failed()
    if failed and section["diagnostic_mode"]:
        for index, step in enumerate(oplog.steps_for(failed["op"]), 1):
            fields = " ".join(f"{k}={v}" for k, v in step.items()
                              if k not in ("t", "op", "kind", "instance", "port"))
            section[f"step_{index:03d}"] = f"op={failed['op']} {fields}"
    return section


def live_report() -> dict:
    """The facts that need the automation thread: TD Snap and Grid 3 probes."""
    return {"tdsnap": _tdsnap(), "grid3": _grid3()}


def _app(native: bool = False) -> dict:
    return {
        "version": __version__,
        "packaged": bool(getattr(sys, "frozen", False)),
        "window": "native" if native else "browser",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "grounding_allowed": os.environ.get(
            "TDSNAP_WEB_GROUNDING", "1"
        ).strip().lower() not in ("0", "false", "no", "off"),
    }


def report(native: bool = False, live_facts: Optional[dict] = None) -> dict:
    """Collect the full environment report as structured data.

    *live_facts* is :func:`live_report` run on the automation thread by the
    caller; without it the probes run here (the CLI and tests).
    """
    facts = live_facts if live_facts is not None else live_report()
    return {
        "app": _app(native),
        "tdsnap": facts.get("tdsnap", {}),
        "grid3": facts.get("grid3", {}),
        "ai": _ai(),
        "operations": _operations(),
    }


def _render_value(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "unknown"
    return str(value)


def as_text(data: dict) -> str:
    """Render *data* as the plain text a user pastes into an issue."""
    lines = ["AAC Editor support report", ""]
    for section, values in data.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"  {key}: {_render_value(value)}")
        lines.append("")
    lines.append("No page-set content, button labels, page names or file names are included.")
    return "\n".join(lines)
