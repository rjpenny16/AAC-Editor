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


def test_the_built_in_model_is_the_default_and_ollama_is_never_used_unasked():
    """REL-028: a reachable but slow or half-set-up Ollama used to win over a
    working built-in model, and people without Ollama saw its errors."""
    assert engines.choose(RUNNING, READY) == (engines.LOCAL, "")
    assert engines.choose(OFF, READY) == (engines.LOCAL, "")
    assert engines.choose(EMPTY, READY) == (engines.LOCAL, "")
    # Not even as a stand-in: Ollama is only for people who chose it.
    assert engines.choose(RUNNING, NEEDS_DOWNLOAD) == (None, "")
    assert engines.choose(RUNNING, NEEDS_DOWNLOAD, engines.LOCAL) == (None, "")
    assert engines.choose(OFF, NEEDS_DOWNLOAD) == (None, "")


def test_a_choice_of_ollama_is_honoured_and_stood_in_for_rather_than_refused():
    assert engines.choose(RUNNING, READY, engines.OLLAMA) == (engines.OLLAMA, "")
    # Reachable is not ready: a server with no models cannot generate.
    assert engines.choose(EMPTY, READY, engines.OLLAMA)[0] == engines.LOCAL

    # Somebody who chose Ollama and forgot to start it is better served by
    # working suggestions plus a sentence saying which model wrote them.
    engine, note = engines.choose(OFF, READY, engines.OLLAMA)
    assert engine == engines.LOCAL
    assert "built-in model" in note

    # Nothing to stand in with, and nothing invented.
    assert engines.choose(OFF, NEEDS_DOWNLOAD, engines.OLLAMA) == (None, "")


def test_an_unknown_preference_is_simply_not_a_preference():
    assert engines.choose(RUNNING, READY, "magic") == (engines.LOCAL, "")
    assert engines.choose(RUNNING, READY, None) == (engines.LOCAL, "")


def test_ollama_is_probed_only_when_chosen():
    assert engines.wants_ollama(engines.OLLAMA) is True
    assert not engines.wants_ollama(None)
    assert not engines.wants_ollama(engines.LOCAL)


@pytest.mark.parametrize(
    ("ollama_state", "local_state", "preferred", "state", "action"),
    [
        (RUNNING, READY, None, engines.READY, ""),
        (OFF, READY, None, engines.READY, ""),
        (OFF, DOWNLOADING, None, engines.DOWNLOADING, ""),
        (OFF, NEEDS_DOWNLOAD, None, engines.SETUP, "download"),
        # No built-in engine and Ollama not chosen: nothing about Ollama.
        (EMPTY, NO_ENGINE, None, engines.UNAVAILABLE, ""),
        (OFF, NO_ENGINE, None, engines.UNAVAILABLE, ""),
        # Chose Ollama, running but empty: the next step is in Ollama.
        (EMPTY, NO_ENGINE, engines.OLLAMA, engines.SETUP, "ollama"),
        # Chose Ollama and it is off: say so, and how to get back.
        (OFF, NO_ENGINE, engines.OLLAMA, engines.UNAVAILABLE, "ollama"),
    ],
)
def test_one_state_and_one_next_step(ollama_state, local_state, preferred, state, action):
    report = engines.readiness(ollama_state, local_state, preferred)
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

    named = engines.readiness(RUNNING, READY, engines.OLLAMA, ollama_model="llama3.2")
    assert "llama3.2" in named["summary"]

    # No model named is still a true sentence, not a blank one.
    unnamed = engines.readiness(RUNNING, READY, engines.OLLAMA)
    assert "Ollama" in unnamed["summary"]


def test_nobody_who_did_not_choose_ollama_is_told_about_it():
    for ollama_state in (OFF, EMPTY, RUNNING, engines.NOT_CHECKED):
        for local_state in (NO_ENGINE, NEEDS_DOWNLOAD, DOWNLOADING, READY):
            report = engines.readiness(ollama_state, local_state)
            text = " ".join(str(report[key]) for key in ("summary", "detail", "note"))
            assert "Ollama" not in text
            assert report["action"] != "ollama"


def test_the_status_names_the_launch_mode():
    """REL-028: launch.bat and the installed app could have different engines
    and nothing on screen said which was running."""
    source = engines.readiness(OFF, NO_ENGINE, launch_mode=engines.SOURCE)
    assert source["launch_mode"] == engines.SOURCE
    assert "launch.bat" in source["detail"]
    installed = engines.readiness(OFF, READY, launch_mode=engines.INSTALLED)
    assert installed["launch_mode"] == engines.INSTALLED
    assert "installed app" in installed["detail"]
    assert "launch.bat" in engines.readiness(
        OFF, READY, launch_mode=engines.SOURCE)["detail"]


def test_a_model_with_no_name_still_gets_a_true_sentence():
    """A status the app could not read fully must not print "the built-in
    model ()" at somebody."""
    nameless = {**READY, "model": {}}
    assert engines.describe(engines.LOCAL, nameless) == "the built-in model"
    assert engines.describe(None, nameless) == "no model"


def test_the_setup_sentence_names_the_download_size():
    report = engines.readiness(OFF, NEEDS_DOWNLOAD)
    assert "about 1 GB" in report["detail"]
