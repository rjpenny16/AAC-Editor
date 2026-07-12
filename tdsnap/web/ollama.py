"""Optional Ollama backend for word/phrase suggestions.

If the user already runs Ollama, the app uses it automatically — it's often
faster than the built-in engine and lets power users pick any model. The
editor works fully without it; failures return empty results plus a
human-readable message instead of raising.
"""

from typing import Dict, List, Optional, Tuple

import requests

from . import prompts

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"


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
    """Return ``(words, error)``; on any failure words is [] and error explains."""
    count = max(1, min(int(count), 60))
    payload = {
        "model": model,
        "messages": [
            {"role": "user",
             "content": prompts.build_prompt(category, count, kind, function)}
        ],
        "stream": False,
        "format": prompts.WORDS_SCHEMA,
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
    words = prompts.parse_items(content, count)
    if words is None:
        return [], "Ollama returned something that wasn't valid JSON."
    return words, None
