"""Real-model smoke test for the built-in AI engine.

Runs actual generations through llama.cpp against a small real GGUF — the exact
code path the packaged app uses. Needs network + llama-cpp-python, so it only
runs when explicitly requested:

    TDSNAP_AI_SMOKE=1 python -m pytest tests/test_ai_smoke.py

The model download itself lives in ``conftest.smoke_localai``, shared with the
eval set in ``test_ai_eval.py`` so CI fetches it once.

CI runs it in the release workflow and the soft-fail integration job.
"""

import os

import pytest

from tdsnap.web import prompts

pytestmark = pytest.mark.skipif(
    os.environ.get("TDSNAP_AI_SMOKE") != "1",
    reason="set TDSNAP_AI_SMOKE=1 to run the real-model smoke test",
)


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


def test_steering_reaches_a_real_generation(smoke_localai):
    """Rejections, examples, and style samples are accepted end to end.

    Whether a 0.5B model *obeys* a negative constraint is not something to
    assert on — that is what the eval set's pass rate is for. What must hold is
    that the extra prompt material does not break parsing or generation.
    """
    words, error = smoke_localai.generate_words(
        "Snacks",
        count=5,
        existing=["Crackers"],
        avoid=["Kale", "Spinach"],
        like=["Chips"],
        style=["I want more", "All done"],
    )
    assert error is None
    assert all(isinstance(word, str) and word.strip() for word in words)
