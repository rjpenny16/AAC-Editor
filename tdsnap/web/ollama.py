"""Optional word-list suggestions from a local Ollama server.

Ported from the retired Tkinter app. Everything here is best-effort: the
editor works fully without Ollama, so failures return empty results plus a
human-readable message instead of raising.
"""

import json
from typing import Dict, List, Optional, Tuple

import requests

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"

_WORDS_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
}

_PROMPT = """Generate exactly {count} common, practical items for the category "{category}"
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


def status(host: str = DEFAULT_HOST) -> Dict:
    """Return ``{reachable, models, message}`` for the Ollama server at *host*."""
    try:
        response = requests.get(f"{host}/api/tags", timeout=5)
    except requests.exceptions.RequestException as exc:
        return {
            "reachable": False,
            "models": [],
            "message": f"Could not connect to Ollama at {host}: {exc.__class__.__name__}",
        }
    if response.status_code != 200:
        return {
            "reachable": False,
            "models": [],
            "message": f"Ollama answered with status {response.status_code}.",
        }
    models = [m.get("name", "unknown") for m in response.json().get("models", [])]
    message = (
        "Connected." if models
        else "Connected, but no models installed (try: ollama pull llama3.2)."
    )
    return {"reachable": True, "models": models, "message": message}


def generate_words(
    category: str,
    count: int = 10,
    host: str = DEFAULT_HOST,
    model: str = DEFAULT_MODEL,
    kind: str = "words",
    function: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """Return ``(words, error)``; on any failure words is [] and error explains.

    ``kind='phrases'`` asks for quick-fire sentences instead of single words;
    ``function`` narrows phrases to one communicative function ('question',
    'comment', 'positive', 'negative', 'personal').
    """
    count = max(1, min(int(count), 60))
    if kind == "phrases":
        prompt = _PHRASE_PROMPT.format(
            count=count,
            category=category,
            function_line=_FUNCTION_LINES.get(function or "", ""),
        )
    else:
        prompt = _PROMPT.format(count=count, category=category)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": _WORDS_SCHEMA,
        "options": {"num_predict": 800, "temperature": 0.7},
    }
    try:
        response = requests.post(
            f"{host}/api/chat",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    except requests.exceptions.RequestException as exc:
        return [], f"Could not reach Ollama at {host}: {exc.__class__.__name__}"

    if response.status_code != 200:
        return [], f"Ollama error {response.status_code}: {response.text[:200]}"

    content = response.json().get("message", {}).get("content", "")
    try:
        items = json.loads(content).get("items", [])
    except (json.JSONDecodeError, AttributeError):
        return [], "Ollama returned something that wasn't valid JSON."
    if not isinstance(items, list):
        return [], "Ollama's response had no word list."

    words = [str(item).strip() for item in items if str(item).strip()]
    return words[:count], None
