"""Optional Ollama backend for word/phrase suggestions.

If the user already runs Ollama, the app uses it automatically — it's often
faster than the built-in engine and lets power users pick any model. The
editor works fully without it; failures return empty results plus a
human-readable message instead of raising.
"""

import ipaddress
import json
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from . import prompts

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"
MAX_HOST_LENGTH = 2048
MAX_RESPONSE_BYTES = 2_000_000


def normalize_host(host: str) -> str:
    """Return a safe Ollama origin, rejecting paths, credentials, and odd schemes."""
    if not isinstance(host, str) or not host.strip() or len(host) > MAX_HOST_LENGTH:
        raise ValueError("Enter a valid Ollama address.")
    try:
        parts = urlsplit(host.strip())
        port = parts.port
    except ValueError as exc:
        raise ValueError("Enter a valid Ollama address.") from exc
    if (
        parts.scheme.lower() not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "The Ollama address must be an http(s) origin without a path, "
            "credentials, query, or fragment."
        )
    hostname = parts.hostname.lower()
    if any(ord(character) < 33 for character in hostname):
        raise ValueError("Enter a valid Ollama address.")
    try:
        loopback = hostname == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if not loopback:
        raise ValueError(
            "The Ollama address must use localhost or a loopback IP address."
        )
    if port == 0:
        raise ValueError("Enter a valid Ollama port.")
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parts.scheme.lower(), netloc, "", "", ""))


def _request_bytes(request: Request, timeout: int) -> Tuple[int, bytes]:
    """Open a bounded HTTP response and return its status and body."""
    try:
        response = urlopen(request, timeout=timeout)
    except URLError as exc:
        # HTTPError has a status-bearing response body; other URL errors do not.
        if not hasattr(exc, "code"):
            raise
        response = exc
    try:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        status_code = getattr(response, "status", None) or response.getcode()
    finally:
        response.close()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Ollama response was too large.")
    return int(status_code), raw


def status(host: str = DEFAULT_HOST) -> Dict:
    """Return ``{reachable, models, message}`` for the Ollama server at *host*."""
    try:
        host = normalize_host(host)
        request = Request(
            f"{host}/api/tags",
            headers={"Accept": "application/json"},
        )
        status_code, raw = _request_bytes(request, 5)
        if status_code != 200:
            return {
                "reachable": False,
                "models": [],
                "message": f"Ollama answered with status {status_code}.",
            }
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Ollama returned invalid JSON.")
        installed = payload.get("models", [])
        if not isinstance(installed, list):
            raise ValueError("Ollama returned invalid model data.")
    except (URLError, OSError, TimeoutError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "reachable": False,
            "models": [],
            "message": f"Could not connect to Ollama at {host}: {exc.__class__.__name__}",
        }
    models = [
        m["name"][:200] for m in installed
        if isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"]
    ]
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
    existing: Optional[Sequence[str]] = None,
    reference: Optional[str] = None,
) -> Tuple[List, Optional[str]]:
    """Return ``(words, error)``; on any failure words is [] and error explains."""
    try:
        host = normalize_host(host)
        count = max(1, min(int(count), 60))
    except (TypeError, ValueError) as exc:
        return [], str(exc)
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompts.build_prompt(
                category, count, kind, function, existing, reference
            )}
        ],
        "stream": False,
        "format": prompts.response_schema(kind),
        "options": {"num_predict": 800, "temperature": 0.7},
    }
    try:
        request = Request(
            f"{host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        status_code, raw = _request_bytes(request, 120)
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        return [], f"Could not reach Ollama at {host}: {exc.__class__.__name__}"

    if status_code != 200:
        detail = raw[:200].decode("utf-8", errors="replace")
        return [], f"Ollama error {status_code}: {detail}"

    try:
        response_payload = json.loads(raw.decode("utf-8"))
        content = response_payload.get("message", {}).get("content", "")
    except (json.JSONDecodeError, UnicodeError, AttributeError):
        return [], "Ollama returned something that wasn't valid JSON."
    words = prompts.parse_items(content, count, kind)
    if words is None:
        return [], "Ollama returned something that wasn't valid JSON."
    return words, None
