"""Prompts, output schema, and answer cleaning shared by every AI backend.

Two halves, and the second one is why this module is not just strings.

*Asking* is ``build_prompt``: one prompt per kind of answer, plus the
"steer away from, and towards" block a request carries.

*Receiving* is ``parse_items``. A small model told to return bare labels will
still hand back ``"1. Harry Potter"``, ``"**Hermione**"``, ``"Ron Weasley -
Harry's best friend"``, the page title restated, and the same name twice.
Every one of those becomes a button in somebody's communication system, so
none of them is a thing to ask the user to notice and delete. They are
cleaned, and what cannot be cleaned is dropped: a suggestion the app is not
confident in is worth less than the second it takes to ask again.
"""

import json
import re
from collections.abc import Sequence
from typing import Optional

WORDS_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
}

PHRASE_FUNCTIONS = ("question", "comment", "positive", "negative", "personal")
PHRASES_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "function": {"type": "string", "enum": list(PHRASE_FUNCTIONS)},
                },
                "required": ["label", "function"],
            },
        }
    },
    "required": ["items"],
}

_WORDS_PROMPT = """Generate exactly {count} useful AAC button labels for a page titled
"{category}".
{request_line}{existing_line}{reference_line}
Requirements:
- First infer the user's intended subject and type of answer from the entire title
- If the title names a type (characters, foods, places, actions, feelings, etc.),
  every item must be an example of exactly that type, not merely related vocabulary
- If the title is broad, choose common concrete words a person would most likely
  want to say about that topic; do not return synonyms or descriptions of the title
- If the category asks for people or characters, return only their names; never
  return places, objects, actions, creatures, traits, or other related words
- For a named real or fictional work, use accurate, well-known names from that work
- Keep each label simple and clear (usually 1-3 words, never more than four)
- Write the button text and nothing else: no numbering, bullets, quotation
  marks, markdown, and no explanation of what the item is
- Never repeat the page title back as an item
- Silently check that every candidate matches the inferred intent before answering

Example: for "Harry Potter characters", valid items include "Harry Potter" and
"Hermione Granger"; "magic", "Hogwarts", and "wand" are invalid.

Provide exactly {count} items in a JSON object with an "items" array.

Example format:
{{"items": ["item1", "item2", "item3"]}}"""

# Quick-fire phrases for topic pages, optionally narrowed to one
# communicative function (the color-coding convention on topic pages).
_PHRASE_PROMPT = """Generate exactly {count} ready-to-speak phrases about the topic "{category}"
for an AAC (Augmentative and Alternative Communication) user's topic page.
{function_line}
{request_line}{existing_line}{reference_line}
Requirements:
- Infer what people commonly discuss, ask, like, dislike, and personally share
  about this topic; make every phrase specific and useful rather than generic
- Complete, natural speech someone would actually use in conversation
- Short enough to fit on a communication button (4-10 words)
- Varied — no two phrases should say the same thing
- Unless one function is required above, use a balanced mix of all five functions
- Assign each phrase exactly one function based on its actual meaning:
  question = a genuine question ending in ?
  comment = a neutral fact or observation
  positive = liking, enjoyment, praise, agreement, or wanting more
  negative = dislike, complaint, refusal, disagreement, or wanting to stop
  personal = information about the user's own life, experience, or preferences
- A statement must never be assigned the question function
- Write the spoken phrase and nothing else: no numbering, bullets, quotation
  marks, markdown, and no explanation of what the phrase is for

Provide exactly {count} phrases in a JSON object with an "items" array. Each item
must contain its spoken "label" and its "function".

Example format:
{{"items": [{{"label": "What happens next?", "function": "question"}},
{{"label": "I love this part", "function": "positive"}}]}}"""

_FUNCTION_LINES = {
    function: f'Every phrase and every "function" value must be "{function}".\n'
    for function in PHRASE_FUNCTIONS
}

_QUESTION = re.compile(
    r"^(?:who|what|when|where|why|how|which|whose|is|are|am|was|were|"
    r"do|does|did|can|could|would|will|should|may|have|has)\b", re.I,
)
_NEGATIVE = re.compile(
    r"\b(?:no|not|never|don't|doesn't|didn't|can't|cannot|won't|hate|dislike|"
    r"stop|bad|boring|scary|wrong|upset|angry|sad|too loud|too busy)\b", re.I,
)
_OWNERSHIP = re.compile(r"\b(?:my|mine|our|ours)\b", re.I)
_PERSONAL = re.compile(
    r"^i\s+(?:am|was|have|had|went|saw|read|live|remember|tried|visited|"
    r"played|watched|ate)\b", re.I,
)
_POSITIVE = re.compile(
    r"\b(?:love|like|enjoy|favorite|great|good|fun|awesome|amazing|excited|"
    r"happy|delicious|beautiful|cool|yes|agree|please|want|best)\b", re.I,
)


def phrase_function(label: str, suggested: Optional[str] = None) -> str:
    """Correct high-confidence phrase types before TD Snap row placement."""
    # curly apostrophe is normalized deliberately
    text = str(label or "").strip().replace("’", "'")  # noqa: RUF001
    if text.endswith("?") or _QUESTION.search(text):
        return "question"
    if _NEGATIVE.search(text):
        return "negative"
    if _OWNERSHIP.search(text):
        return "personal"
    if _POSITIVE.search(text):
        return "positive"
    if _PERSONAL.search(text):
        return "personal"
    return suggested if suggested in PHRASE_FUNCTIONS and suggested != "question" else "comment"


def _listing(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _constraint_lines(
    existing: Optional[Sequence[str]],
    avoid: Optional[Sequence[str]],
    like: Optional[Sequence[str]],
    style: Optional[Sequence[str]],
    already: Optional[Sequence[str]] = None,
) -> str:
    """The "what to steer away from, and towards" block of the prompt.

    Separate lines rather than one merged list, because they do not mean the
    same thing to a model. A button that is already on the page is a fact
    about the page; a rejected suggestion is a judgement the user made; a kept
    one is the direction they want more of; something this round already
    produced is neither, only used up; and style samples are about *how* to
    write, never *what* to write. Collapsing them (e.g. feeding rejections
    in as "already on the page") tells the model something untrue and shows up
    as suggestions drifting towards vocabulary that is not there.
    """
    lines = []
    if existing:
        lines.append(
            "The page already contains these buttons: "
            f"{_listing(existing)}\n"
            "Suggest only new items; do not repeat or rephrase existing buttons."
        )
    if avoid:
        lines.append(
            "The user rejected these suggestions: "
            f"{_listing(avoid)}\n"
            "Never suggest them again, and avoid close variants of them."
        )
    if like:
        lines.append(
            "The user kept these and asked for more of the same kind: "
            f"{_listing(like)}\n"
            "Match what those have in common, without repeating them."
        )
    if already:
        lines.append(
            "You already returned these for this request: "
            f"{_listing(already)}\n"
            "They were kept; return different ones now rather than repeating them."
        )
    if style:
        lines.append(
            "For writing style only, here is how buttons are already worded in "
            f"this page set: {_listing(style)}\n"
            "Match their length, capitalization, and register. They are examples "
            "of style, not of subject matter: never reuse their wording or let "
            "them change what the items are about."
        )
    return "\n".join(lines)


def build_prompt(
    category: str,
    count: int,
    kind: str = "words",
    function: Optional[str] = None,
    existing: Optional[Sequence[str]] = None,
    reference: Optional[str] = None,
    avoid: Optional[Sequence[str]] = None,
    like: Optional[Sequence[str]] = None,
    style: Optional[Sequence[str]] = None,
    already: Optional[Sequence[str]] = None,
    request: Optional[str] = None,
) -> str:
    """Return the prompt for *count* words or quick-fire phrases."""
    existing_line = _constraint_lines(existing, avoid, like, style, already)
    # The user's own description of what they want. It decides the subject,
    # but the format rules below still hold, so cleaning and parsing keep working.
    request_line = ""
    if request and request.strip():
        request_line = (
            "The user described what they want, in their own words:\n"
            '"""\n' + request.strip() + '\n"""\n'
            "Follow this description; where it is more specific than the title, "
            "it decides what the items are. The format requirements below still apply.\n"
        )
    # Authoritative facts looked up for this title (see grounding.py). Kept
    # blank when absent so offline generation reads exactly as before.
    reference_line = "\n"
    if reference and reference.strip():
        reference_line = (
            "\nReference facts (authoritative — every item must be consistent "
            "with this; use only names that appear here and never invent ones "
            'that contradict it):\n"""\n' + reference.strip() + '\n"""\n'
        )
    if kind == "phrases":
        return _PHRASE_PROMPT.format(
            count=count,
            category=category,
            function_line=_FUNCTION_LINES.get(function or "", ""),
            request_line=request_line,
            existing_line=existing_line,
            reference_line=reference_line,
        )
    return _WORDS_PROMPT.format(
        count=count, category=category, request_line=request_line,
        existing_line=existing_line, reference_line=reference_line,
    )


def response_schema(kind: str):
    return PHRASES_SCHEMA if kind == "phrases" else WORDS_SCHEMA


def overask(count: int, limit: int = 60) -> int:
    """How many items to request in order to end up with *count* usable ones.

    Cleaning below throws things away — a repeat, the page title echoed back,
    a label that is really a sentence — so asking for exactly what the user
    wants reliably delivers fewer. Asking for half again costs a few tokens
    and is the difference between "Added 10" and "Added 6".
    """
    wanted = max(1, int(count))
    return max(1, min(int(limit), wanted + max(3, round(wanted * 0.5))))


def token_budget(count: int, kind: str = "words") -> int:
    """Room for *count* items to come back whole.

    A flat budget truncated a long request mid-JSON, and a truncated reply is
    not partially useful: it fails to parse and the user is told the model
    returned nothing.
    """
    per_item = 48 if kind == "phrases" else 24
    return int(min(2048, 256 + max(1, int(count)) * per_item))


# ---------- cleaning what a model actually returns ----------

# "usually 1-3 words" for a label, "4-10" for a phrase. These are the outer
# bounds at which an item stops being a button somebody could read at a
# glance, not the target — the prompt asks for the target.
MAX_WORD_WORDS = 4
MAX_PHRASE_WORDS = 14

# "1.", "1)", "- ", "* ", "• ", "2 -" at the start of a line.
_LIST_MARKER = re.compile(
    r"^(?:[-*\u2022\u2013\u2014]+|\(?\d{1,3}[.):]|\d{1,3}\s*[-\u2013\u2014])\s+"
)
# Matched wrappers a model adds when it is "quoting" the answer to itself.
_WRAPPERS = {
    '"': '"', "'": "'", "`": "`", "*": "*",
    "\u201c": "\u201d", "\u2018": "\u2019",  # curly quotes, written as escapes
}
# Trailing list punctuation. "?" and "!" are deliberately absent: they carry
# meaning on a communication button, and "?" is how a question is recognised.
_TRAILING_JUNK = re.compile(r"[\s,;:.\u2026\-\u2013\u2014]+$")
_PARENTHETICAL = re.compile(r"\s*[(\[][^)\]]*[)\]]\s*$")
# "Ron Weasley - his best friend" and "Snape: the potions master". A dash needs
# spaces around it to count, so the hyphen in "ice-cream" is left alone; a
# colon does not, because that is how a model writes a gloss.
_EXPLANATION = re.compile(r"(?:\s+[-\u2013\u2014]|\s*:)\s+.*$")
_HAS_CONTENT = re.compile(r"\w")
_APOSTROPHE = re.compile(r"[\u0027\u2019]")  # straight and curly, as escapes
_PUNCTUATION = re.compile(r"[^\w\s]+")
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _unwrap(label: str) -> str:
    """Strip matched quotes, backticks, and markdown emphasis, repeatedly."""
    while len(label) >= 2 and _WRAPPERS.get(label[0]) == label[-1]:
        label = label[1:-1].strip()
    return label


def _clean(raw, kind: str = "words") -> str:
    """One item's text, as it would have to read on a button."""
    label = " ".join(str(raw or "").split())
    label = _LIST_MARKER.sub("", label, count=1)
    label = _unwrap(label)
    if kind != "phrases":
        # A word button is a label, so an explanation of the label is not part
        # of it: "Ron Weasley - Harry's best friend" is the name plus noise.
        # A phrase keeps its own punctuation; a dash inside spoken text is the
        # user's sentence, not a gloss.
        label = _PARENTHETICAL.sub("", label)
        label = _EXPLANATION.sub("", label)
        label = _unwrap(label.strip())
    return _TRAILING_JUNK.sub("", label).strip()


def normalized(label) -> str:
    """A comparison key: case, punctuation, and spacing folded away.

    "Mom's" and "Moms", "Ice Cream" and "ice-cream" are one suggestion each,
    and offering both is the same as offering a duplicate. An apostrophe
    closes up and everything else opens out, which is what makes those two
    pairs match without also merging genuinely different words.
    """
    text = _APOSTROPHE.sub("", str(label or ""))
    return " ".join(_PUNCTUATION.sub(" ", text).casefold().split())


def _usable(label: str, kind: str) -> bool:
    if not label or not _HAS_CONTENT.search(label):
        return False
    limit = MAX_PHRASE_WORDS if kind == "phrases" else MAX_WORD_WORDS
    return len(label.split()) <= limit


def clean_items(
    items: Sequence,
    count: int,
    kind: str = "words",
    category: str = "",
    exclude: Sequence[str] = (),
) -> list:
    """Return at most *count* usable suggestions from whatever came back.

    Everything the prompt asks for is enforced here as well as asked for,
    because asking is not a guarantee: numbering and quoting are stripped, the
    page title echoed back is dropped, over-long items are dropped, and both
    repeats within the answer and anything in *exclude* (what is on the page,
    and what the user already rejected) go too.

    Safe to run twice — two rounds of suggestions merge through it.
    """
    blocked = {key for key in (normalized(name) for name in exclude) if key}
    title = normalized(category)
    phrases = kind == "phrases"
    seen: set = set()
    cleaned: list = []
    for item in items:
        function = None
        if isinstance(item, dict):
            raw = item.get("label", "")
            function = item.get("function")
            if phrases and function not in PHRASE_FUNCTIONS:
                continue
        elif phrases:
            # A phrase needs its communicative function; a bare string has none
            # and guessing one would put it on the wrong topic-page row.
            continue
        else:
            raw = item
        label = _clean(raw, kind)
        if not _usable(label, kind):
            continue
        key = normalized(label)
        if not key or key in seen or key in blocked or key == title:
            continue
        seen.add(key)
        cleaned.append(
            {"label": label, "function": phrase_function(label, function)}
            if phrases else label
        )
        if len(cleaned) >= count:
            break
    return cleaned


def _json_candidates(text: str):
    """The reply itself, then the shapes a model wraps it in."""
    yield text
    for block in _FENCE.findall(text):
        yield block.strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if 0 <= start < end:
            yield text[start:end + 1]


def parse_items(
    content: str,
    count: int,
    kind: str = "words",
    category: str = "",
    exclude: Sequence[str] = (),
):
    """Parse a backend's JSON reply into clean suggestions (or None).

    None means the reply was not an answer at all. An empty list means it was
    an answer with nothing usable in it, which the caller reports differently
    — "the model returned nothing I could use" is not "the model broke".
    """
    text = str(content or "").strip()
    items = None
    for candidate in _json_candidates(text):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            found = data.get("items")
        elif isinstance(data, list):
            found = data
        else:
            continue
        if isinstance(found, list):
            items = found
            break
    if items is None:
        return None
    return clean_items(items, count, kind, category, exclude)
