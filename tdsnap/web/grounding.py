"""Optional web grounding for AI suggestions.

Small offline models don't know niche or current topics (e.g. Roblox
characters, a specific game's cast), so they hallucinate plausible-but-wrong
answers. When the user explicitly asks, we look up real reference facts about
the page title and hand them to the model as authoritative context, so it
names actual items instead of guessing.

Uses Wikipedia's keyless API — no account, no API key, and no third-party HTTP
dependency. Every failure is swallowed and grounds nothing: no internet, a
blocked host, or an unknown topic all fall back to ordinary ungrounded
generation. Set ``TDSNAP_WEB_GROUNDING=0`` to disable even explicitly requested
lookups (privacy / fully-offline installs).

The lookup used to take the first search result silently, which is the one
thing about this feature a user cannot argue with: "Mercury" the planet and
"Mercury" the element read identically in a page title, and a whole set of
suggestions can be quietly wrong because the wrong article won a search. So
``lookup`` names the article it used, offers the runners-up, and accepts both a
chosen title and a list of rejected ones — see the grounding note in ai.js.

Only the page title is ever sent. Nothing the user has composed, and nothing
read out of their page set, reaches this module: style samples, existing button
labels, and rejected suggestions all stay on the machine. ``lookup`` takes a
title and titles, and there is deliberately no parameter through which anything
else could arrive.
"""

import json
import os
import re
from collections.abc import Sequence
from typing import Optional
from urllib.parse import quote, urlencode
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
    request = Request(  # noqa: S310 - URL is built from the _API constant; scheme is fixed https
        f"{_API}?{urlencode(params)}",
        headers={"User-Agent": "tdsnap-editor", "Accept": "application/json"},
    )
    # URL is built from the _API constant; scheme is fixed https
    with urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Wikipedia response was too large.")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Wikipedia returned invalid JSON.")
    return data


def article_url(title: str) -> str:
    """The human-readable Wikipedia URL for *title*, for the UI to show."""
    return "https://en.wikipedia.org/wiki/" + quote(
        str(title or "").strip().replace(" ", "_"), safe=""
    )


def _search_titles(query: str, limit: int = 5) -> list[str]:
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


def _empty() -> dict:
    return {"used": False, "text": "", "title": "", "url": "", "alternatives": []}


def lookup(
    category: str,
    max_chars: int = 1600,
    *,
    requested: bool = False,
    title: Optional[str] = None,
    exclude: Sequence[str] = (),
) -> dict:
    """Look up reference facts for *category* and say which article they came from.

    Returns ``{used, text, title, url, alternatives}``. ``used`` is False for
    every miss — disabled, offline, blocked, unknown topic — and the caller then
    generates exactly as it would have with grounding switched off.

    *title* pins the article (the user picked it from a previous answer's
    alternatives); *exclude* drops articles they rejected. Candidates are tried
    in order rather than only the first, so rejecting the one that won the
    search leaves something usable behind instead of silently grounding nothing.
    """
    category = str(category or "").strip()
    if not enabled(requested) or len(category) < 2:
        return _empty()
    rejected = {str(name or "").strip().casefold() for name in exclude}
    rejected.discard("")
    try:
        candidates = [
            found for found in _search_titles(category)
            if found.casefold() not in rejected
        ]
        chosen = str(title or "").strip()
        if chosen:
            # An explicitly chosen article leads; it is still only a Wikipedia
            # title, so the request shape is unchanged.
            candidates = [chosen] + [
                found for found in candidates if found.casefold() != chosen.casefold()
            ]
        for candidate in candidates[:3]:
            extract = _extract(candidate)
            if not extract:
                continue
            alternatives = [
                other for other in candidates if other != candidate
            ][:4]
            related = ", ".join(alternatives)
            text = f"Wikipedia — {candidate}:\n{extract}"
            if related:
                text += f"\nRelated articles: {related}"
            return {
                "used": True,
                "text": _TAG.sub("", text)[:max_chars].strip(),
                "title": candidate,
                "url": article_url(candidate),
                "alternatives": alternatives,
            }
    except Exception:
        # Offline, blocked, rate-limited, or unknown topic: ground nothing.
        return _empty()
    return _empty()


def reference_text(
    category: str, max_chars: int = 1600, *, requested: bool = False
) -> str:
    """Return authoritative reference facts for *category*, or "" on any miss."""
    return lookup(category, max_chars, requested=requested)["text"]
