"""Real-model smoke test for the built-in AI engine.

Downloads a small GGUF (Qwen2.5 0.5B, ~400 MB) and runs actual generations
through llama.cpp — proving the exact code path the packaged app uses. Needs
network + llama-cpp-python, so it only runs when explicitly requested:

    TDSNAP_AI_SMOKE=1 python -m pytest tests/test_ai_smoke.py

CI runs it in the release workflow and the soft-fail integration job.
"""

import importlib
import os
import re
import time

import pytest

from tdsnap.web import prompts

pytestmark = pytest.mark.skipif(
    os.environ.get("TDSNAP_AI_SMOKE") != "1",
    reason="set TDSNAP_AI_SMOKE=1 to run the real-model smoke test",
)

# Fetching ~400 MB from a third-party CDN fails for reasons that say nothing
# about this code: rate limits, 5xx, DNS, a dropped connection. Those skip.
# Anything else — above all a failed integrity check, a wrong size, or a file
# that is not GGUF — is a real defect in the download path and must fail.
TRANSPORT_FAILURE = re.compile(
    r"HTTP Error (?:429|5\d\d)"
    r"|timed out|timeout"
    r"|name resolution|nodename nor servname|getaddrinfo"
    r"|[Cc]onnection (?:reset|refused|aborted)"
    r"|Remote end closed"
    r"|URLError",
)


@pytest.fixture(scope="module")
def smoke_localai(tmp_path_factory):
    pytest.importorskip("llama_cpp")
    tmp = tmp_path_factory.mktemp("model-home")
    os.environ["XDG_DATA_HOME"] = str(tmp)
    os.environ["LOCALAPPDATA"] = str(tmp)
    os.environ["TDSNAP_MODEL_URL"] = (
        "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/"
        "qwen2.5-0.5b-instruct-q4_k_m.gguf"
    )
    os.environ["TDSNAP_MODEL_FILE"] = "qwen2.5-0.5b-instruct-q4_k_m.gguf"

    from tdsnap.web import localai

    importlib.reload(localai)  # pick up the env overrides
    localai.start_download()
    deadline = time.time() + 600
    while time.time() < deadline:
        state = localai.download_state()
        if state["status"] in ("ready", "error"):
            break
        time.sleep(2)
    final = localai.download_state()
    if final["status"] != "ready":
        error = str(final.get("error") or "")
        if TRANSPORT_FAILURE.search(error):
            pytest.skip(f"could not fetch the model from the CDN: {error}")
        pytest.fail(f"model download failed: {final}")
    return localai


def test_generate_words_with_real_model(smoke_localai):
    words, error = smoke_localai.generate_words("Snacks", count=6)
    assert error is None
    assert 1 <= len(words) <= 6
    assert all(isinstance(word, str) and word for word in words)


def test_generate_phrases_with_real_model(smoke_localai):
    """The classifier is applied to what the model actually said.

    This used to assert every phrase came back tagged ``question`` when
    ``function="question"`` was requested — which the pipeline deliberately does
    not promise. ``prompts.phrase_function`` exists to *overrule* a claimed
    function that the text does not support, and its last line never passes a
    claimed "question" through unchecked. Ask a 1.5B model for four questions
    about swimming and one "Let's go swimming" is a perfectly ordinary answer;
    it is correctly downgraded, and the old assertion then failed on the
    classifier doing its job.

    So what is checked here is the promise the code makes: every phrase is
    labelled, carries a known function, and carries the function the classifier
    derives from its own text. That still fails loudly if the classifier stops
    being applied to real model output — the regression this test is for —
    without depending on which phrasing the model happened to pick.
    """
    phrases, error = smoke_localai.generate_words(
        "Swimming", count=4, kind="phrases", function="question"
    )
    assert error is None
    assert 1 <= len(phrases) <= 4
    assert all(item["label"].strip() for item in phrases)
    assert all(item["function"] in prompts.PHRASE_FUNCTIONS for item in phrases)
    assert all(
        item["function"] == prompts.phrase_function(item["label"], "question")
        for item in phrases
    )
    # A claimed question that does not read as one is never left tagged as one.
    assert all(
        item["function"] == "question"
        for item in phrases
        if item["label"].strip().endswith("?")
    )
