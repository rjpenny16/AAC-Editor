"""Prompts and output schema shared by every AI backend (Ollama, built-in)."""

from typing import Optional

WORDS_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
}

_WORDS_PROMPT = """Generate exactly {count} common, practical items for the category "{category}"
for an AAC (Augmentative and Alternative Communication) app.

Requirements:
- Items should be commonly known and used
- Keep items simple and clear (1-3 words each)
- For places, use well-known brand names or common place types
- For food, use popular dishes or restaurants
- Make items practical for everyday communication
- Use simple, everyday language

Provide exactly {count} items in a JSON object with an "items" array.

Example format:
{{"items": ["item1", "item2", "item3"]}}"""

# Quick-fire phrases for topic pages, optionally narrowed to one
# communicative function (the color-coding convention on topic pages).
_PHRASE_PROMPT = """Generate exactly {count} ready-to-speak phrases about the topic "{category}"
for an AAC (Augmentative and Alternative Communication) user's topic page.
{function_line}
Requirements:
- Complete, natural sentences someone would actually say in conversation
- Short enough to fit on a communication button (4-10 words)
- First person, everyday language, no quotation marks
- Varied — no two phrases should say the same thing

Provide exactly {count} phrases in a JSON object with an "items" array.

Example format:
{{"items": ["phrase one", "phrase two"]}}"""

_FUNCTION_LINES = {
    "question": "Every phrase must be a QUESTION the user would ask about the topic.\n",
    "comment": "Every phrase must be a general COMMENT or observation about the topic.\n",
    "positive": "Every phrase must be a POSITIVE comment (liking, enjoying, praising).\n",
    "negative": "Every phrase must be a NEGATIVE comment (disliking, complaining, refusing).\n",
    "personal": "Every phrase must be a PERSONAL statement about the user's own life or preferences.\n",
}


def build_prompt(
    category: str, count: int, kind: str = "words", function: Optional[str] = None
) -> str:
    """Return the prompt for *count* words or quick-fire phrases."""
    if kind == "phrases":
        return _PHRASE_PROMPT.format(
            count=count,
            category=category,
            function_line=_FUNCTION_LINES.get(function or "", ""),
        )
    return _WORDS_PROMPT.format(count=count, category=category)


def parse_items(content: str, count: int):
    """Parse a backend's JSON reply into a clean list of strings (or None)."""
    import json

    try:
        items = json.loads(content).get("items", [])
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(items, list):
        return None
    words = [str(item).strip() for item in items if str(item).strip()]
    return words[:count]
