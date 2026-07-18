"""Optional web grounding for AI suggestions.

Small offline models don't know niche or current topics (e.g. Roblox
characters, a specific game's cast), so they hallucinate plausible-but-wrong
answers. When the user explicitly asks, we look up real reference facts about
the page title and hand them to the model as authoritative context, so it
names actual items instead of guessing.

Uses Wikipedia's keyless API — no account, no API key, and no third-party HTTP
dependency. Every failure is swallowed and returns ``""``: no internet, a
blocked host, or an unknown topic all fall back to ordinary ungrounded
generation. Set ``TDSNAP_WEB_GROUNDING=0`` to disable even explicitly requested
lookups (privacy / fully-offline installs).
"""

import json
import os
import re
from typing import List
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_API = "https://en.wikipedia.org/w/api.php"
_TIMEOUT = 6
_TAG = re.compile(r"<[^>]+>")


def enabled(requested: bool = False) -> bool:
    """True only for an explicit request that policy has not disabled."""
    allowed = os.environ.get("TDSNAP_WEB_GROUNDING", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
    return requested is True and allowed


def _get(params: dict) -> dict:
    params = {"format": "json", "formatversion": "2", **params}
    request = Request(
        f"{_API}?{urlencode(params)}",
        headers={"User-Agent": "tdsnap-editor", "Accept": "application/json"},
    )
    with urlopen(request, timeout=_TIMEOUT) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Wikipedia response was too large.")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Wikipedia returned invalid JSON.")
    return data


def _search_titles(query: str, limit: int = 3) -> List[str]:
    data = _get({
        "action": "query", "list": "search",
        "srsearch": query, "srlimit": limit,
    })
    results = data.get("query", {}).get("search", [])
    # Prefer "List of ... characters/items" articles: they enumerate members,
    # which is exactly what a "<subject> characters" page wants.
    titles = [r["title"] for r in results if r.get("title")]
    titles.sort(key=lambda t: 0 if t.lower().startswith("list of") else 1)
    return titles


def _extract(title: str, chars: int = 1500) -> str:
    data = _get({
        "action": "query", "prop": "extracts",
        "explaintext": "1", "exchars": chars, "titles": title,
    })
    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return ""
    return str(pages[0].get("extract", "")).strip()


def reference_text(
    category: str, max_chars: int = 1600, *, requested: bool = False
) -> str:
    """Return authoritative reference facts for *category*, or "" on any miss."""
    category = str(category or "").strip()
    if not enabled(requested) or len(category) < 2:
        return ""
    try:
        titles = _search_titles(category)
        if not titles:
            return ""
        extract = _extract(titles[0])
        if not extract:
            return ""
        related = ", ".join(titles[1:])
        text = f"Wikipedia — {titles[0]}:\n{extract}"
        if related:
            text += f"\nRelated articles: {related}"
        return _TAG.sub("", text)[:max_chars].strip()
    except Exception:
        # Offline, blocked, rate-limited, or unknown topic: ground nothing.
        return ""
