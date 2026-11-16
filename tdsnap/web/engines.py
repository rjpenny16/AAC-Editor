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

# How this copy was started. The installer bundles the built-in engine; a
# source checkout started from launch.bat or launch.sh has it only if the AI
# extra installed (REL-028). The panel says which, so the two are not
# mistaken for each other.
INSTALLED = "installed"
SOURCE = "source"

# Stands in for an Ollama status that was deliberately not fetched: Ollama is
# only probed when somebody chose it, so nobody who did not ask for Ollama
# waits on its probe or sees its errors (REL-028).
NOT_CHECKED = {"reachable": False, "models": [], "message": "not checked", "checked": False}

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

    The built-in model is the default, and the only engine used unless
    somebody chose Ollama in the suggestion settings (REL-028): an Ollama
    that is reachable but slow or half-configured used to be preferred over a
    working built-in model, and anybody without Ollama saw its connection
    errors. A choice of Ollama is honoured when it can run and stood in for
    by the built-in model when it cannot, with a sentence saying so.
    ``engine`` is None when nothing can run, and ``note`` is empty whenever
    nothing surprising happened.
    """
    wanted = preferred if preferred in ENGINES else AUTO
    ready = {OLLAMA: _ollama_ready(ollama_state), LOCAL: _local_ready(local_state)}
    order = [OLLAMA, LOCAL] if wanted == OLLAMA else [LOCAL]
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


def wants_ollama(preferred: Optional[str]) -> bool:
    """Whether Ollama should be probed at all for this preference."""
    return preferred == OLLAMA


def _started(launch_mode: str) -> str:
    if launch_mode == SOURCE:
        return "AAC Editor was started from launch.bat or launch.sh."
    return "AAC Editor is running as the installed app."


def readiness(
    ollama_state: dict,
    local_state: dict,
    preferred: Optional[str] = None,
    ollama_model: str = "",
    launch_mode: str = INSTALLED,
) -> dict:
    """Everything the panel needs to render one state, in one read.

    ``state`` is what to show, ``summary`` is what to say, and ``action`` is
    the single next thing the person can do about it. The browser renders
    this; it does not re-derive it. ``launch_mode`` and ``engine`` are
    reported so the panel and the support report can say which copy is
    running with which engine.
    """
    engine, note = choose(ollama_state, local_state, preferred)
    chose_ollama = wants_ollama(preferred)
    started = _started(launch_mode)
    model = local_state.get("model") or {}
    size = str(model.get("size") or "about 1 GB")
    can_download = bool(
        local_state.get("engine_available") and not local_state.get("downloaded")
    )
    if engine:
        return {
            "ready": True,
            "engine": engine,
            "launch_mode": launch_mode,
            "state": READY,
            "summary": f"Ready — suggestions come from {describe(engine, local_state, ollama_model)}.",
            "detail": f"Nothing you write leaves this computer. {started}",
            "action": "",
            "note": note,
            "can_download": can_download,
        }
    if _downloading(local_state):
        return {
            "ready": False,
            "engine": None,
            "launch_mode": launch_mode,
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
            "launch_mode": launch_mode,
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
    if chose_ollama and ollama_state.get("reachable"):
        return {
            "ready": False,
            "engine": None,
            "launch_mode": launch_mode,
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
    if chose_ollama:
        return {
            "ready": False,
            "engine": None,
            "launch_mode": launch_mode,
            "state": UNAVAILABLE,
            "summary": "Your Ollama server isn't answering.",
            "detail": (
                "You chose Ollama in the suggestion settings. Start Ollama and "
                "choose Check again, or switch back to the built-in model. "
                "Everything else in AAC Editor works without suggestions."
            ),
            "action": "ollama",
            "note": "",
            "can_download": False,
        }
    if launch_mode == SOURCE:
        detail = (
            "Suggestions are not included when AAC Editor is started from "
            "launch.bat or launch.sh without the AI extra. Use the installed "
            "app, or run launch.bat again once the AI extra can install. "
            "Everything else in AAC Editor works exactly as it does with them."
        )
    else:
        detail = (
            "This copy of AAC Editor was built without the suggestion model. "
            "Everything else in AAC Editor works exactly as it does with them."
        )
    return {
        "ready": False,
        "engine": None,
        "launch_mode": launch_mode,
        "state": UNAVAILABLE,
        "summary": "Suggestions aren't included in this copy of AAC Editor.",
        "detail": detail,
        "action": "",
        "note": "",
        "can_download": False,
    }
