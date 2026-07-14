"""Optional web grounding for AI suggestions.

Small offline models don't know niche or current topics (e.g. Roblox
characters, a specific game's cast), so they hallucinate plausible-but-wrong
answers. Before generating, we look up real reference facts about the page
title and hand them to the model as authoritative context, so it names actual
items instead of guessing.

Uses Wikipedia's keyless API — no account, no API key, no extra dependency
(``requests`` is already used by the Ollama backend). Every failure is
swallowed and returns ``""``: no internet, a blocked host, or an unknown topic
all fall back to ordinary ungrounded generation. Set ``TDSNAP_WEB_GROUNDING=0``
to disable network lookups entirely (privacy / fully-offline installs).
"""

import os
import re
from typing import List

import requests

_API = "https://en.wikipedia.org/w/api.php"
_TIMEOUT = 6
_TAG = re.compile(r"<[^>]+>")


def enabled() -> bool:
    return os.environ.get("TDSNAP_WEB_GROUNDING", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _get(params: dict) -> dict:
    params = {"format": "json", "formatversion": "2", **params}
    response = requests.get(
        _API, params=params,
        headers={"User-Agent": "tdsnap-editor"}, timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


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


def reference_text(category: str, max_chars: int = 1600) -> str:
    """Return authoritative reference facts for *category*, or "" on any miss."""
    category = str(category or "").strip()
    if not enabled() or len(category) < 2:
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
