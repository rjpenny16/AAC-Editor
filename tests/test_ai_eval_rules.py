"""The eval set's rules, checked without a model — runs on every CI run.

The real-model eval (``test_ai_eval.py``) only runs when someone opts in, and
its pass rate is only worth reading if the checks behind it are strict. A check
that accepts everything passes every release and says nothing, which is the
failure mode this file exists to catch: each rule is given an answer that must
pass and an answer that must fail.
"""

import pytest

from tests import ai_eval

CASES = ai_eval.load_cases()
BY_ID = {case["id"]: case for case in CASES}


def test_the_eval_set_is_the_size_the_roadmap_asked_for():
    assert len(CASES) >= 20
    assert len({case["id"] for case in CASES}) == len(CASES)
    # Both shapes of suggestion are covered; phrases exercise the classifier.
    kinds = {case["kind"] for case in CASES}
    assert kinds == {"words", "phrases"}


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_every_case_is_well_formed(case):
    assert case["category"].strip()
    assert case["kind"] in {"words", "phrases"}
    assert 1 <= case["count"] <= 60
    # Each case says why it is in the set, so a future reader can argue with
    # the rule rather than guessing at it.
    assert case["why"].strip()
    assert case["checks"], "a case with no checks passes trivially"
    if case.get("function"):
        from tdsnap.web import prompts

        assert case["function"] in prompts.PHRASE_FUNCTIONS


def test_a_good_answer_passes_and_the_named_failure_does_not():
    case = BY_ID["harry-potter-characters"]
    good = ["Harry Potter", "Hermione Granger", "Ron Weasley", "Rubeus Hagrid"]
    assert ai_eval.score(case, good)["passed"]

    # The exact failure the prompt calls out by name.
    bad = ai_eval.score(case, ["Harry Potter", "wand", "Hogwarts", "magic"])
    assert not bad["passed"]
    assert any("forbids" in failure for failure in bad["failures"])


def test_confident_nonsense_does_not_pass():
    """The check that makes the pass rate mean something.

    ``forbids`` alone accepts any answer that dodges the forbidden words —
    including eight capitalised words that have nothing to do with the
    category. ``expects_any`` asks the other question: did anything
    recognisable as a member of this type come back at all?
    """
    case = BY_ID["harry-potter-characters"]
    nonsense = ["Alpha Bravo", "Charlie Delta", "Echo Foxtrot", "Golf Hotel"]
    result = ai_eval.score(case, nonsense)
    assert not result["passed"]
    assert any("expects_any" in failure for failure in result["failures"])
    # One recognisable name out of four is enough: this asks whether the model
    # knows the subject, not whether it picked a particular answer.
    assert ai_eval.score(
        case, ["Alpha Bravo", "Charlie Delta", "Echo Foxtrot", "Hermione Granger"]
    )["passed"]


def test_every_word_case_asks_for_something_recognisable():
    for case in CASES:
        if case["kind"] == "words":
            assert case["checks"].get("expects_any"), case["id"]


def test_each_rule_catches_what_it_is_for():
    case = BY_ID["farm-animals"]
    assert ai_eval.score(case, ["Cow", "Pig", "Sheep", "Goat", "Horse"])["passed"]

    def failing(items):
        return " ".join(ai_eval.score(case, items)["failures"])

    assert "forbids" in failing(["Cow", "Pig", "Sheep", "Goat", "Tractor"])
    assert "expects_any" in failing(["Alpha", "Bravo", "Charlie", "Delta", "Echo"])
    assert "min_items" in failing(["Cow", "Pig"])
    assert "no_duplicates" in failing(["Cow", "Pig", "Sheep", "Goat", "cow"])
    assert "not_the_title" in failing(["Cow", "Pig", "Sheep", "Goat", "Farm animals"])
    assert "max_words" in failing(
        ["Cow", "Pig", "Sheep", "Goat", "A very large brown horse"]
    )
    # Word boundaries, not substrings: a rule stays as narrow as it reads.
    assert ai_eval.score(
        BY_ID["harry-potter-characters"],
        ["Wanda Maximoff", "Harry Potter", "Ron Weasley", "Hermione Granger"],
    )["passed"]


def test_name_shaped_answers_are_distinguished_from_nouns():
    case = BY_ID["us-presidents"]
    assert ai_eval.score(case, ["Abraham Lincoln", "John Adams", "James Monroe",
                                "Grover Cleveland"])["passed"]
    assert "looks_like_names" in " ".join(
        ai_eval.score(case, ["Abraham Lincoln", "the white house is big",
                             "John Adams", "James Monroe"])["failures"]
    )


def test_phrase_cases_check_the_classifier_was_applied():
    case = BY_ID["swimming-phrases"]
    good = [
        {"label": "Can we swim now?", "function": "question"},
        {"label": "I love the water", "function": "positive"},
        {"label": "The pool is cold", "function": "comment"},
    ]
    assert ai_eval.score(case, good)["passed"]

    # A statement claiming to be a question: the exact thing the prompt and
    # phrase_function both refuse.
    mislabelled = ai_eval.score(case, [
        {"label": "The pool is cold", "function": "question"},
        {"label": "Can we swim now?", "function": "question"},
        {"label": "I love the water", "function": "positive"},
    ])
    assert not mislabelled["passed"]
    assert any("functions_match" in f for f in mislabelled["failures"])

    # An unknown function is a failure, not a crash.
    unknown = ai_eval.score(case, [{"label": "Nice day", "function": "cheerful"}])
    assert not unknown["passed"]


def test_every_failing_check_is_reported_not_just_the_first():
    case = BY_ID["farm-animals"]
    result = ai_eval.score(case, ["Tractor", "Tractor"])
    assert len(result["failures"]) >= 3
    assert not result["passed"]


def test_summarize_counts_what_ran():
    summary = ai_eval.summarize([
        {"id": "a", "passed": True, "failures": []},
        {"id": "b", "passed": False, "failures": ["forbids: nope"]},
    ])
    assert summary["total"] == 2 and summary["passed"] == 1
    assert summary["pass_rate"] == 0.5
    # An eval that ran nothing has not proved anything, and must not read as
    # a perfect score.
    assert ai_eval.summarize([])["pass_rate"] == 0.0


def test_an_unknown_check_is_refused_rather_than_ignored(tmp_path, monkeypatch):
    """A typo in the eval set must fail loudly, not silently skip a rule."""
    import json

    bogus = tmp_path / "eval.json"
    bogus.write_text(json.dumps([
        {"id": "x", "category": "c", "kind": "words", "count": 1,
         "why": "w", "checks": {"forbidz": ["a"]}}
    ]), encoding="utf-8")
    monkeypatch.setattr(ai_eval, "EVAL_SET", bogus)
    with pytest.raises(ValueError, match="forbidz"):
        ai_eval.load_cases()


def test_the_job_summary_reports_what_ran():
    """A missing or unreadable report must never read as a clean run."""
    import scripts.ai_eval_summary as summary

    rendered = summary.render({
        "model": "Tiny", "total": 2, "passed": 1, "failed": 1, "pass_rate": 0.5,
        "results": [
            {"id": "a", "passed": True, "failures": []},
            {"id": "b", "passed": False, "failures": ["forbids: 'wand'"]},
        ],
    })
    assert "1/2 passed (50%)" in rendered
    assert "| b | forbids: 'wand' |" in rendered
    assert "Tiny" in rendered

    clean = summary.render({
        "model": "Tiny", "total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0,
        "results": [{"id": "a", "passed": True, "failures": []}],
    })
    assert "Every case passed." in clean


def test_a_missing_report_says_so(tmp_path, capsys):
    import scripts.ai_eval_summary as summary

    assert summary.main([str(tmp_path / "nope.json")]) == 0
    assert "no report" in capsys.readouterr().out
