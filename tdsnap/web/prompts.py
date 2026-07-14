"""Prompts and output schema shared by every AI backend (Ollama, built-in)."""

import json
import re
from typing import Optional, Sequence

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
{existing_line}{reference_line}
Requirements:
- First infer the user's intended subject and type of answer from the entire title
- If the title names a type (characters, foods, places, actions, feelings, etc.),
  every item must be an example of exactly that type, not merely related vocabulary
- If the title is broad, choose common concrete words a person would most likely
  want to say about that topic; do not return synonyms or descriptions of the title
- If the category asks for people or characters, return only their names; never
  return places, objects, actions, creatures, traits, or other related words
- For a named real or fictional work, use accurate, well-known names from that work
- Keep each label simple and clear (usually 1-3 words)
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
{existing_line}{reference_line}
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
    text = str(label or "").strip().replace("’", "'")
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


def build_prompt(
    category: str,
    count: int,
    kind: str = "words",
    function: Optional[str] = None,
    existing: Optional[Sequence[str]] = None,
    reference: Optional[str] = None,
) -> str:
    """Return the prompt for *count* words or quick-fire phrases."""
    existing_line = ""
    if existing:
        existing_line = (
            "The page already contains these buttons: "
            f"{json.dumps(list(existing), ensure_ascii=False)}\n"
            "Suggest only new items; do not repeat or rephrase existing buttons."
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
            existing_line=existing_line,
            reference_line=reference_line,
        )
    return _WORDS_PROMPT.format(
        count=count, category=category,
        existing_line=existing_line, reference_line=reference_line,
    )


def response_schema(kind: str):
    return PHRASES_SCHEMA if kind == "phrases" else WORDS_SCHEMA


def parse_items(content: str, count: int, kind: str = "words"):
    """Parse a backend's JSON reply into clean suggestions (or None)."""
    try:
        items = json.loads(content).get("items", [])
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(items, list):
        return None
    if kind == "phrases":
        phrases = []
        for item in items:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            function = item.get("function")
            if not label or function not in PHRASE_FUNCTIONS:
                continue
            phrases.append({
                "label": label,
                "function": phrase_function(label, function),
            })
        return phrases[:count]
    return [str(item).strip() for item in items if str(item).strip()][:count]
