"""Which suggestion engine runs, and the sentence the panel shows about it.

The decision used to live in two places — the endpoint picked one engine while
the browser described a different state — so these pin the single copy. Pure
functions over the two status dictionaries the backends already return: no
network, no model, no Flask.
"""

import pytest

from tdsnap.web import engines

OFF = {"reachable": False, "models": [], "message": "off"}
RUNNING = {"reachable": True, "models": ["llama3.2"], "message": "ok"}
EMPTY = {"reachable": True, "models": [], "message": "no models"}

NO_ENGINE = {
    "engine_available": False, "downloaded": False,
    "download": {"status": "idle"}, "model": {"name": "Small", "size": "about 1 GB"},
}
NEEDS_DOWNLOAD = {**NO_ENGINE, "engine_available": True}
DOWNLOADING = {**NEEDS_DOWNLOAD, "download": {"status": "downloading"}}
READY = {**NEEDS_DOWNLOAD, "downloaded": True}


def test_auto_prefers_a_running_ollama_then_the_built_in_model():
    assert engines.choose(RUNNING, READY) == (engines.OLLAMA, "")
    assert engines.choose(OFF, READY) == (engines.LOCAL, "")
    # Reachable is not ready: a server with no models cannot generate.
    assert engines.choose(EMPTY, READY) == (engines.LOCAL, "")
    assert engines.choose(OFF, NEEDS_DOWNLOAD) == (None, "")


def test_a_choice_is_honoured_and_stood_in_for_rather_than_refused():
    assert engines.choose(RUNNING, READY, engines.LOCAL) == (engines.LOCAL, "")

    # Somebody who chose Ollama and forgot to start it is better served by
    # working suggestions plus a sentence saying which model wrote them.
    engine, note = engines.choose(OFF, READY, engines.OLLAMA)
    assert engine == engines.LOCAL
    assert "built-in model" in note

    engine, note = engines.choose(RUNNING, NEEDS_DOWNLOAD, engines.LOCAL)
    assert engine == engines.OLLAMA
    assert "Ollama" in note

    # Nothing to stand in with, and nothing invented.
    assert engines.choose(OFF, NEEDS_DOWNLOAD, engines.OLLAMA) == (None, "")


def test_an_unknown_preference_is_simply_not_a_preference():
    assert engines.choose(RUNNING, READY, "magic") == (engines.OLLAMA, "")
    assert engines.choose(RUNNING, READY, None) == (engines.OLLAMA, "")


@pytest.mark.parametrize(
    ("ollama_state", "local_state", "state", "action"),
    [
        (RUNNING, READY, engines.READY, ""),
        (OFF, READY, engines.READY, ""),
        (OFF, DOWNLOADING, engines.DOWNLOADING, ""),
        (OFF, NEEDS_DOWNLOAD, engines.SETUP, "download"),
        # Ollama running but empty: the next step is in Ollama, not here.
        (EMPTY, NO_ENGINE, engines.SETUP, "ollama"),
        # No engine of its own and nothing running: Ollama is the only route,
        # which is a fact to state rather than a setup to bury.
        (OFF, NO_ENGINE, engines.UNAVAILABLE, "ollama"),
    ],
)
def test_one_state_and_one_next_step(ollama_state, local_state, state, action):
    report = engines.readiness(ollama_state, local_state)
    assert report["state"] == state
    assert report["action"] == action
    assert report["ready"] is (state == engines.READY)
    # Every state says something; an empty panel is the bug this replaced.
    assert report["summary"] and report["detail"]


def test_a_download_in_flight_wins_over_offering_the_download_again():
    assert engines.readiness(OFF, DOWNLOADING)["can_download"] is False
    assert engines.readiness(OFF, NEEDS_DOWNLOAD)["can_download"] is True


def test_the_summary_names_the_model_that_would_actually_write():
    local = engines.readiness(OFF, READY)
    assert "Small" in local["summary"]

    named = engines.readiness(RUNNING, READY, ollama_model="llama3.2")
    assert "llama3.2" in named["summary"]

    # No model named is still a true sentence, not a blank one.
    unnamed = engines.readiness(RUNNING, READY)
    assert "Ollama" in unnamed["summary"]


def test_a_model_with_no_name_still_gets_a_true_sentence():
    """A status the app could not read fully must not print "the built-in
    model ()" at somebody."""
    nameless = {**READY, "model": {}}
    assert engines.describe(engines.LOCAL, nameless) == "the built-in model"
    assert engines.describe(None, nameless) == "no model"


def test_the_setup_sentence_names_the_download_size():
    report = engines.readiness(OFF, NEEDS_DOWNLOAD)
    assert "about 1 GB" in report["detail"]
