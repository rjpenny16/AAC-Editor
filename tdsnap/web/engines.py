"""Which suggestion engine runs, and one sentence saying so.

Two engines sit behind one button — a model the app downloads once, and an
Ollama server the user may already run — and until now every caller worked out
for itself which of them was usable. The endpoint picked one way, the browser
described the state another way, and the two drifted: the panel could say
"Ollama is connected, but no model is installed" while the request quietly ran
the built-in model instead.

So the decision lives here, once, and the status endpoint and the generate
endpoint both ask it. Everything in this module is pure: it takes the two
status dictionaries those backends already return and returns a decision plus
the words to put on screen. No network, no model, no Flask.

The sentences are part of the contract, not decoration. "No AI model is ready
yet. Follow the built-in setup below, or use the Ollama instructions." asked a
speech therapist to work out which of two setups they were in; the ones here
name the single next thing to do.
"""

from typing import Optional

AUTO = "auto"
OLLAMA = "ollama"
LOCAL = "local"
ENGINES = (OLLAMA, LOCAL)

# What the panel shows. One of these, never a combination.
READY = "ready"
DOWNLOADING = "downloading"
SETUP = "setup"
UNAVAILABLE = "unavailable"


def _ollama_ready(state: dict) -> bool:
    """Reachable is not enough: a server with no models cannot generate."""
    return bool(state.get("reachable") and state.get("models"))


def _local_ready(state: dict) -> bool:
    return bool(state.get("engine_available") and state.get("downloaded"))


def _downloading(local_state: dict) -> bool:
    download = local_state.get("download") or {}
    return download.get("status") == "downloading"


def choose(
    ollama_state: dict,
    local_state: dict,
    preferred: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """``(engine, note)`` — which engine will run, and why it is not the one
    that was asked for.

    A preference is honoured when it can run and quietly stood in for when it
    cannot: somebody who chose Ollama and forgot to start it is better served
    by working suggestions plus a sentence saying which model wrote them than
    by an error telling them what they already know. ``engine`` is None when
    neither can run, and ``note`` is empty whenever nothing surprising
    happened.
    """
    wanted = preferred if preferred in ENGINES else AUTO
    ready = {OLLAMA: _ollama_ready(ollama_state), LOCAL: _local_ready(local_state)}
    # Ollama first by default: somebody running it has already chosen a model,
    # and it is usually the faster of the two.
    order = [wanted, *(engine for engine in ENGINES if engine != wanted)] \
        if wanted in ENGINES else list(ENGINES)
    for engine in order:
        if ready[engine]:
            if wanted in ENGINES and engine != wanted:
                return engine, _fallback_note(wanted, engine)
            return engine, ""
    return None, ""


def _fallback_note(wanted: str, used: str) -> str:
    if used == LOCAL:
        return (
            "Ollama wasn't reachable, so these came from the built-in model "
            "on this computer."
        )
    return "The built-in model isn't ready, so these came from your Ollama server."


def describe(engine: Optional[str], local_state: dict, ollama_model: str = "") -> str:
    """Name the model that would actually write the suggestions."""
    if engine == OLLAMA:
        named = str(ollama_model or "").strip()
        return f"your Ollama model ({named})" if named else "your Ollama server"
    if engine == LOCAL:
        model = local_state.get("model") or {}
        name = str(model.get("name") or "").strip()
        return f"the built-in model ({name})" if name else "the built-in model"
    return "no model"


def readiness(
    ollama_state: dict,
    local_state: dict,
    preferred: Optional[str] = None,
    ollama_model: str = "",
) -> dict:
    """Everything the panel needs to render one state, in one read.

    ``state`` is what to show, ``summary`` is what to say, and ``action`` is
    the single next thing the person can do about it. The browser renders
    this; it does not re-derive it.
    """
    engine, note = choose(ollama_state, local_state, preferred)
    model = local_state.get("model") or {}
    size = str(model.get("size") or "about 1 GB")
    can_download = bool(
        local_state.get("engine_available") and not local_state.get("downloaded")
    )
    if engine:
        return {
            "ready": True,
            "engine": engine,
            "state": READY,
            "summary": f"Ready — suggestions come from {describe(engine, local_state, ollama_model)}.",
            "detail": "Nothing you write leaves this computer.",
            "action": "",
            "note": note,
            "can_download": can_download,
        }
    if _downloading(local_state):
        return {
            "ready": False,
            "engine": None,
            "state": DOWNLOADING,
            "summary": "Setting up suggestions…",
            "detail": "You can keep adding words while this finishes.",
            "action": "",
            "note": "",
            "can_download": False,
        }
    if can_download:
        return {
            "ready": False,
            "engine": None,
            "state": SETUP,
            "summary": "Suggestions need a one-time setup.",
            "detail": (
                f"AAC Editor downloads a free suggestion model once ({size}) and "
                "then works offline. It is one button — there is nothing to "
                "install or sign up for."
            ),
            "action": "download",
            "note": "",
            "can_download": True,
        }
    if ollama_state.get("reachable"):
        return {
            "ready": False,
            "engine": None,
            "state": SETUP,
            "summary": "Ollama is running, but it has no model installed.",
            "detail": (
                "Install one in Ollama — for example run “ollama pull llama3.2” "
                "— then choose Check again."
            ),
            "action": "ollama",
            "note": "",
            "can_download": False,
        }
    return {
        "ready": False,
        "engine": None,
        "state": UNAVAILABLE,
        "summary": "Suggestions aren't available in this installation.",
        "detail": (
            "This copy of AAC Editor was built without the suggestion model. "
            "Suggestions need Ollama running on this computer instead. "
            "Everything else in AAC Editor works exactly as it does with them."
        ),
        "action": "ollama",
        "note": "",
        "can_download": False,
    }
