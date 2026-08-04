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

from .. import __version__, grid3, live
from ..errors import PagesetError
from . import localai, ollama

# Keys worth reporting from live.status() / grid3.status(). Everything else
# those functions return is user content and is dropped: TD Snap's "page" and
# "pages", Grid 3's "grid_set", "page", and "user".
_LIVE_KEYS = ("available", "running", "unlocked", "error")
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
        return {"probe_failed": f"{type(exc).__name__}: {exc}"}
    report = _picked(status, _LIVE_KEYS)
    if status.get("running"):
        report["grid"] = _grid_size(status)
    return report


def _grid3() -> dict:
    try:
        status = grid3.status()
    except (PagesetError, OSError, RuntimeError) as exc:
        return {"probe_failed": f"{type(exc).__name__}: {exc}"}
    report = _picked(status, _GRID3_KEYS)
    if status.get("running"):
        report["grid"] = _grid_size(status)
    try:
        report["ui_access"] = grid3.has_ui_access()
    except (OSError, RuntimeError):
        report["ui_access"] = "unknown"
    return report


def _ai() -> dict:
    report = {
        "engine_available": localai.engine_available(),
        "model_downloaded": localai.is_downloaded(),
        "model": localai.MODEL_NAME,
    }
    try:
        report["ollama_reachable"] = bool(ollama.status(ollama.DEFAULT_HOST).get("reachable"))
    except (ValueError, OSError, RuntimeError):
        report["ollama_reachable"] = False
    return report


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


def report(native: bool = False) -> dict:
    """Collect the full environment report as structured data."""
    return {
        "app": _app(native),
        "tdsnap": _tdsnap(),
        "grid3": _grid3(),
        "ai": _ai(),
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
    lines.append("No page-set content, button labels, or file names are included.")
    return "\n".join(lines)
