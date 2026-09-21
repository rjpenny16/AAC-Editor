"""What a model actually returns, and what is allowed to become a button.

The prompt asks for bare labels. A 1.5B model running on a clinic laptop still
answers with ``"1. Harry Potter"``, ``"**Hermione**"``, ``"Ron Weasley - his
best friend"``, the page title echoed back, and the same name twice. Every one
of those used to arrive as a planned button for somebody to notice and delete.

These pin the cleaning that stops them. Asking is not the same as enforcing,
so each rule the prompt states has a case here that would fail without it.
"""

import pytest

from tdsnap.web import prompts


def clean(items, count=10, **kwargs):
    return prompts.clean_items(items, count, **kwargs)


# ---------- the shapes a model wraps an answer in ----------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1. Harry Potter", "Harry Potter"),
        ("2) Hermione Granger", "Hermione Granger"),
        ("- Ron Weasley", "Ron Weasley"),
        ("• Luna Lovegood", "Luna Lovegood"),
        ('"Draco Malfoy"', "Draco Malfoy"),
        ("**Neville**", "Neville"),
        ("`Hagrid`", "Hagrid"),
        ("“Dobby”", "Dobby"),
        ("Ron Weasley - his best friend", "Ron Weasley"),
        ("Hedwig (an owl)", "Hedwig"),
        ("Snape: the potions master", "Snape"),
        ("  Ginny   Weasley  ", "Ginny Weasley"),
        ("Fred Weasley.", "Fred Weasley"),
    ],
)
def test_a_label_is_cleaned_down_to_the_button_text(raw, expected):
    assert clean([raw]) == [expected]


def test_a_hyphenated_word_is_not_an_explanation():
    """The rule is "space dash space", so a real hyphen survives."""
    assert clean(["ice-cream", "well-done"]) == ["ice-cream", "well-done"]


def test_a_phrase_keeps_its_own_punctuation():
    """A dash inside spoken text is the user's sentence, not a gloss."""
    items = [
        {"label": "1. What happens next?", "function": "question"},
        {"label": "I want more - please", "function": "positive"},
    ]
    assert clean(items, kind="phrases") == [
        {"label": "What happens next?", "function": "question"},
        {"label": "I want more - please", "function": "positive"},
    ]


# ---------- what is dropped rather than cleaned ----------

def test_the_page_title_echoed_back_is_not_a_suggestion():
    assert clean(["Farm animals", "Cow", "farm  animals!"], category="Farm animals") \
        == ["Cow"]


def test_a_repeat_is_a_repeat_whatever_its_case_or_punctuation():
    assert clean(["Mom's", "Moms", "MOM'S", "Dad"]) == ["Mom's", "Dad"]
    assert clean(["Ice Cream", "ice-cream", "Cake"]) == ["Ice Cream", "Cake"]


def test_what_is_already_on_the_page_never_comes_back_as_a_suggestion():
    """Filtered here, not in the browser: filtering after the fact is how a
    request for ten suggestions quietly becomes four."""
    assert clean(["Chips", "Apple"], exclude=["chips"]) == ["Apple"]


def test_a_sentence_is_not_a_word_button():
    long_one = "a label so long it could never fit on a button"
    assert clean(["Popcorn", long_one]) == ["Popcorn"]
    # A phrase gets the room a phrase needs, and no more.
    phrases = [
        {"label": "I really do not like this one bit at all", "function": "negative"},
        {"label": " ".join(["word"] * 20), "function": "comment"},
    ]
    assert [item["label"] for item in clean(phrases, kind="phrases")] == [
        "I really do not like this one bit at all"
    ]


def test_items_with_no_content_are_dropped():
    assert clean(["", "   ", "---", "***", "Chips"]) == ["Chips"]


def test_a_phrase_without_a_usable_function_is_dropped():
    items = [
        {"label": "I love this", "function": "blue"},
        {"label": "no function at all"},
        "a bare string",
        {"label": "What next?", "function": "question"},
    ]
    assert clean(items, kind="phrases") == [
        {"label": "What next?", "function": "question"}
    ]


def test_the_classifier_still_overrules_what_the_model_claimed():
    items = [{"label": "The story has magic", "function": "question"}]
    assert clean(items, kind="phrases") == [
        {"label": "The story has magic", "function": "comment"}
    ]


def test_cleaning_is_safe_to_run_twice():
    """Two rounds of suggestions merge back through it."""
    once = clean(["1. Chips", "Chips", "Apple"])
    assert clean([*once, "apple", "2. Juice"]) == ["Chips", "Apple", "Juice"]


def test_count_is_a_ceiling_on_what_survives_cleaning_not_on_what_arrived():
    # Three arrive, two survive, and the cap does not cut the survivors short.
    assert clean(["1. Chips", "Chips", "Apple"], count=2) == ["Chips", "Apple"]


# ---------- the reply the JSON arrived in ----------

def test_a_reply_wrapped_in_prose_or_fences_is_still_an_answer():
    """Small models ignore a response schema often enough that a hard failure
    here reads to the user as "the model is broken"."""
    assert prompts.parse_items(
        'Here you go:\n```json\n{"items": ["Chips"]}\n```', 5
    ) == ["Chips"]
    assert prompts.parse_items('Sure! {"items": ["Chips"]} Hope that helps.', 5) \
        == ["Chips"]
    # A bare array is the other shape they reach for.
    assert prompts.parse_items('["Chips", "Apple"]', 5) == ["Chips", "Apple"]


def test_something_that_is_not_an_answer_is_still_reported_as_one():
    """None and [] mean different things to the caller: "the model broke" and
    "the model returned nothing I could use" are different sentences."""
    assert prompts.parse_items("not json at all", 5) is None
    assert prompts.parse_items('{"items": "nope"}', 5) is None
    assert prompts.parse_items('{"items": []}', 5) == []
    assert prompts.parse_items('{"items": ["Snacks"]}', 5, category="Snacks") == []


# ---------- asking for enough of them ----------

def test_the_ask_is_inflated_because_cleaning_drops_things():
    assert prompts.overask(10) > 10
    assert prompts.overask(1) >= 4
    # Never past what the engines themselves accept.
    assert prompts.overask(60) == 60
    assert prompts.overask(40) <= 60


def test_the_token_budget_grows_with_the_request():
    """A flat budget truncated a long request mid-JSON, and a truncated reply
    is not partially useful — it fails to parse."""
    assert prompts.token_budget(40) > prompts.token_budget(10)
    assert prompts.token_budget(40, "phrases") > prompts.token_budget(40, "words")
    assert prompts.token_budget(60, "phrases") <= 2048


def test_what_this_round_already_produced_is_its_own_prompt_line():
    """Not "already on the page" and not "rejected" — those are both untrue,
    and a model told something untrue drifts."""
    prompt = prompts.build_prompt("Snacks", 5, already=["Chips"])
    assert "already returned these" in prompt and "Chips" in prompt
    assert "rejected" not in prompt
    assert "already returned" not in prompts.build_prompt("Snacks", 5)
