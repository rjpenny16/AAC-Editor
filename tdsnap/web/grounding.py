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
import threading
import time
import unicodedata
from collections.abc import Sequence
from html import unescape
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

_API = "https://en.wikipedia.org/w/api.php"
_TIMEOUT = 6
_TAG = re.compile(r"<[^>]+>")
MAX_REFERENCE_CHARS = 4800
MAX_ARTICLE_CHARS = 100_000
_response_cache = {}
_cache_lock = threading.Lock()
_CACHE_SECONDS = 300
# Everyday page names are not encyclopedia titles. In particular, Wikipedia's
# search maps "farm animals" to the novel Animal Farm. Resolve these ordinary
# topic phrases explicitly before running the same vetted article lookup.
_TOPIC_TITLES = {
    "farm animals": "Livestock",
    "farm animal": "Livestock",
}


def wikipedia_title(value: str) -> str:
    """Accept a title or an exact English Wikipedia URL; never fetch arbitrary URLs."""
    value = str(value or "").strip()
    if not value:
        return ""
    if "://" not in value:
        if value.startswith("//"):
            raise ValueError("Enter an English Wikipedia article title or https link.")
        title = value
    else:
        parts = urlsplit(value)
        if (parts.scheme != "https" or parts.hostname not in {
            "en.wikipedia.org", "en.m.wikipedia.org",
        } or parts.username or parts.password or parts.port not in (None, 443)):
            raise ValueError("Use an https link to an English Wikipedia article, "
                             "or paste reference text from another page.")
        if parts.path.startswith("/wiki/"):
            title = unquote(parts.path[6:]).replace("_", " ")
        elif parts.path == "/w/index.php":
            title = parse_qs(parts.query).get("title", [""])[0]
        else:
            title = ""
    namespace = title.partition(":")[0].strip().casefold()
    if (not title.strip() or len(title) > 200 or namespace in {
        "special", "talk", "user", "user talk", "wikipedia", "wikipedia talk",
        "file", "file talk", "media", "mediawiki", "template", "template talk",
        "help", "category", "category talk", "portal", "draft", "module", "book",
    }):
        raise ValueError("Enter a Wikipedia article title, rather than a special page.")
    return title.strip()


class _ArticleText(HTMLParser):
    """Keep article prose, headings, lists and table cells, without navigation."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.skipped = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())
        skip = tag in {"script", "style", "sup"} or bool(classes & {
            "navbox", "infobox", "reflist", "reference", "mw-editsection",
            "metadata", "toc", "noprint", "sidebar", "hatnote",
            "mw-references-wrap", "references",
        })
        if tag in {"br", "hr", "img", "meta", "link", "input", "wbr"}:
            if not self.skipped and tag == "br":
                self.parts.append("\n")
            return
        self.stack.append((tag, skip))
        self.skipped += int(skip)
        if not self.skipped and tag in {"p", "li", "tr", "h2", "h3", "h4", "h5"}:
            self.parts.append("\n")
        if not self.skipped and tag in {"h2", "h3", "h4", "h5"}:
            self.parts.append("== ")
        if not self.skipped and tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                self.skipped -= sum(int(skip) for _, skip in self.stack[index:])
                del self.stack[index:]
                break
        if not self.skipped and tag in {"h2", "h3", "h4", "h5"}:
            self.parts.append(" ==")
        if not self.skipped and tag in {"p", "li", "tr", "h2", "h3", "h4", "h5"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(data)


def select_passages(text: str, query: str, max_chars: int = MAX_REFERENCE_CHARS) -> str:
    """Rank local passages, including sections far beyond the introduction.

    The private request may influence passage selection here, never web search.
    Preserve article order inside equally ranked sections and keep headings with
    their children, so a name is not separated from the group it belongs to.
    """
    terms = {word.casefold().rstrip("s") for word in re.findall(r"\w+", query)
             if len(word) > 2 and word.casefold() not in {
                 "the", "and", "only", "from", "with", "want", "words", "page",
             }}
    passages = []
    heading = ""
    entity_query = bool(re.search(r"\b(characters?|cast|people|presidents?)\b", query, re.I))
    for line in text[:MAX_ARTICLE_CHARS].splitlines():
        line = " ".join(line.split()).strip(" |")
        if not line:
            continue
        if line.startswith("=="):
            heading = line.strip("= ")
            if heading.casefold() in {"references", "external links", "notes", "sources",
                                      "bibliography", "further reading"}:
                break
            continue
        if not _appropriate(line):
            continue
        # Bound individual paragraphs; a long introduction must not crowd out lists.
        for start in range(0, len(line), 700):
            chunk = line[start:start + 700]
            tokens = {word.casefold().rstrip("s") for word in re.findall(r"\w+", chunk)}
            headings = {word.casefold().rstrip("s") for word in re.findall(r"\w+", heading)}
            score = len(terms & tokens) + 2 * len(terms & headings)
            if "|" in line or heading.casefold() in {"types", "species", "cast", "characters"}:
                score += 3
            if entity_query and heading:
                score += 2
                chunk = chunk[:350]
            passages.append((score, len(passages), heading, chunk))
    chosen = []
    used = 0
    ranked = sorted(passages, key=lambda p: (-p[0], p[1]))
    # Cover more than one character/section before consuming its biography.
    if entity_query:
        seen_headings = set()
        first, rest = [], []
        for passage in ranked:
            heading = passage[2]
            if heading in seen_headings:
                rest.append(passage)
            else:
                first.append(passage)
                seen_headings.add(heading)
        ranked = first + rest
    for _, index, heading, chunk in ranked:
        passage = f"{heading}: {chunk}" if heading and heading != chunk else chunk
        if used + len(passage) + 1 > max_chars:
            continue
        chosen.append((index, passage))
        used += len(passage) + 1
    return "\n".join(passage for _, passage in sorted(chosen))[:max_chars]
# Filter external reference material, never the vocabulary a person types.
# Whole words avoid rejecting innocent names such as Essex or Scunthorpe.
_EXPLICIT = re.compile(
    r"\b(?:sex(?:ual\w*|ting)?|porn\w*|eroti\w*|hentai|hentais|"
    r"fetish\w*|masturbat\w*|orgasm\w*|genital\w*|penis|penises|"
    r"vagin\w*|vulva\w*|testicl\w*|intercourse|nudit\w*|nude\w*|"
    r"prostitut\w*|brothel\w*|incest\w*|rape|raped|rapist\w*|"
    r"bdsm|bondage|striptease|fuck\w*|cock|cocks|dick|dicks|pussy|"
    r"blowjob\w*|cumshot\w*|semen|ejaculat\w*|onlyfans|nsfw|"
    r"adult[\s-]+(?:film\w*|entertainment|content|video\w*))\b",
    re.IGNORECASE,
)


def _appropriate(text: str) -> bool:
    plain = unicodedata.normalize("NFKC", unescape(_TAG.sub("", str(text))))
    return not _EXPLICIT.search(plain)


def enabled(requested: bool = False) -> bool:
    """True only for an explicit request that policy has not disabled."""
    allowed = os.environ.get("TDSNAP_WEB_GROUNDING", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
    return requested is True and allowed


def _get(params: dict) -> dict:
    params = {"format": "json", "formatversion": "2", **params}
    # Re-asking, rejecting suggestions, or changing local instructions does
    # not need another eleven Wikipedia requests. Bound both TTL and entries.
    # The transport is part of the key so replacement transports stay isolated.
    key = (urlopen, urlencode(params))
    with _cache_lock:
        cached = _response_cache.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
            return cached[1]
    request = Request(  # noqa: S310 - URL is built from the _API constant; scheme is fixed https
        f"{_API}?{urlencode(params)}",
        headers={"User-Agent": "AAC-Editor/1.0 (https://github.com/rjpenny16/AAC-Editor)",
                 "Accept": "application/json"},
    )
    # URL is built from the _API constant; scheme is fixed https
    with urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Wikipedia response was too large.")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Wikipedia returned invalid JSON.")
    with _cache_lock:
        if len(_response_cache) >= 64:
            _response_cache.pop(next(iter(_response_cache)))
        _response_cache[key] = (time.monotonic(), data)
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
    titles = [
        r["title"] for r in results
        if r.get("title") and _appropriate(r["title"] + " " + r.get("snippet", ""))
    ]
    # Subject overlap comes before a list bonus: an unrelated list must not
    # displace the article about the actual requested franchise/activity.
    terms = set(re.findall(r"\w+", query.casefold())) - {"list", "of", "the"}
    types = {"characters", "foods", "places", "animals", "people", "items"}
    subject = terms - types
    def rank(title):
        words = set(re.findall(r"\w+", title.casefold()))
        overlap = len(subject & words) / max(1, len(subject))
        return (overlap, len(terms & words),
                int(bool(terms & types) and title.casefold().startswith("list of")))
    titles.sort(key=rank, reverse=True)
    return titles


def _extract(title: str, chars: int = MAX_ARTICLE_CHARS) -> str:
    data = _get({
        "action": "query", "prop": "extracts|categories", "cllimit": "max",
        "explaintext": "1", "redirects": "1", "titles": title,
    })
    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return ""
    page = pages[0]
    extract = str(page.get("extract", "")).strip()
    metadata = " ".join(str(c.get("title", "")) for c in page.get("categories", []))
    if not _appropriate(f"{page.get('title', title)} {metadata}"):
        return ""
    if "Category:Disambiguation pages" in metadata or "may refer to:" in extract[:300]:
        return ""
    # TextExtracts omits tables and lists. The rendered article includes the
    # very character names / foods / objects we need, so retain that structure.
    parsed = _get({"action": "parse", "page": title, "prop": "text", "redirects": "1"})
    html = parsed.get("parse", {}).get("text", "")
    if isinstance(html, dict):
        html = html.get("*", "")
    if html:
        reader = _ArticleText()
        reader.feed(html)
        extract = "".join(reader.parts)
    # A passing mention in a large general article must not discard all its
    # useful sections. Explicit source metadata still rejects the whole article.
    return "\n".join(line for line in extract[:chars].splitlines()
                     if _appropriate(line)).strip()


def _empty() -> dict:
    return {"used": False, "text": "", "title": "", "url": "", "alternatives": []}


def choose_reference(source: dict, description: str) -> dict:
    """Use local instructions to disambiguate already fetched candidates.

    For example, "the planet" can favor Mercury (planet) over Mercury
    (element). The description is never a Wikipedia search argument.
    """
    negative_terms = {word.casefold().rstrip("s") for word in re.findall(
        r"\b(?:not|avoid|exclude)\s+(?:the\s+)?(\w+)", description, re.I,
    )}
    terms = {word.casefold().rstrip("s") for word in re.findall(r"\w+", description)
             if len(word) > 2 and word.casefold() not in {
                 "the", "and", "only", "from", "with", "want", "words", "please",
             }} - negative_terms
    candidates = source.get("candidates", [])
    if not terms or not candidates:
        return source
    def rank(candidate):
        title_words = {word.casefold().rstrip("s")
                       for word in re.findall(r"\w+", candidate["title"])}
        body_words = {word.casefold().rstrip("s")
                      for word in re.findall(r"\w+", candidate["text"])}
        return (3 * len(terms & title_words) + len(terms & body_words)
                - 3 * len(negative_terms & title_words))
    selected = max(candidates, key=rank)
    return {**source, **selected, "alternatives": [
        candidate["title"] for candidate in candidates
        if candidate["title"] != selected["title"]
    ]}


def lookup(
    category: str,
    max_chars: int = MAX_REFERENCE_CHARS,
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
    if not enabled(requested) or len(category) < 2 or not _appropriate(category):
        return _empty()
    rejected = {str(name or "").strip().casefold() for name in exclude}
    rejected.discard("")
    try:
        chosen = str(title or "").strip()
        # An exact article works even when Wikipedia search is unavailable.
        candidates = [] if chosen else [
            found for found in _search_titles(category)
            if found.casefold() not in rejected
        ]
        canonical = _TOPIC_TITLES.get(category.casefold())
        if not chosen and canonical and canonical.casefold() not in rejected:
            candidates = [canonical, *(found for found in candidates if found != canonical)]
        if chosen and chosen.casefold() not in rejected and _appropriate(chosen):
            # An explicitly chosen article leads; it is still only a Wikipedia
            # title, so the request shape is unchanged.
            candidates = [chosen] + [
                found for found in candidates if found.casefold() != chosen.casefold()
            ]
        vetted = []
        for candidate in dict.fromkeys(candidates[:5]):
            if not _appropriate(candidate):
                continue
            try:
                extract = _extract(candidate)
            except Exception:  # noqa: S112 - omit unverified external reference material
                # An unverified alternative must never reach the UI or model.
                continue
            if not extract:
                continue
            vetted.append((candidate, extract))
            if len(vetted) >= 3:
                break
        if vetted:
            candidate, extract = vetted[0]
            alternatives = [other for other, _ in vetted[1:]]
            result = {
                "used": True,
                # Source identity is metadata, not evidence. Otherwise the
                # model can "verify" invented names against related titles.
                "text": (_TAG.sub("", extract) if max_chars >= MAX_ARTICLE_CHARS
                         else select_passages(_TAG.sub("", extract), category, max_chars)),
                "title": candidate,
                "url": article_url(candidate),
                "alternatives": alternatives,
            }
            if max_chars >= MAX_ARTICLE_CHARS and not chosen:
                # These remain on the server for local disambiguation. The
                # browser receives only the identity of the selected source.
                result["candidates"] = [
                    {"title": name, "text": _TAG.sub("", text), "url": article_url(name)}
                    for name, text in vetted
                ]
            return result
    except Exception:
        # Offline, blocked, rate-limited, or unknown topic: ground nothing.
        return _empty()
    return _empty()


def reference_text(
    category: str, max_chars: int = 1600, *, requested: bool = False
) -> str:
    """Return authoritative reference facts for *category*, or "" on any miss."""
    return lookup(category, max_chars, requested=requested)["text"]
