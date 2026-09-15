"""Scoring for the AI eval set — the rules, without a model attached.

``tests/fixtures/ai_eval_set.json`` is a fixed set of category prompts and the
things the prompt in ``tdsnap/web/prompts.py`` already promises about the
answer: *"Harry Potter characters"* must not come back holding *"wand"*, a word
button is one to three words, a phrase carries the function its own text
supports. Until now those promises were prose. This turns each of them into a
check that either passes or does not.

Two test files use it, and the split is deliberate:

* ``test_ai_eval_rules.py`` runs the scorer against made-up answers, offline,
  on every CI run. It is what stops a rule from quietly going soft — a check
  that accepts everything passes every release and means nothing.
* ``test_ai_eval.py`` runs the same rules against the real built-in model when
  ``TDSNAP_AI_SMOKE=1`` is set, and records the pass rate.

Nothing here imports the model, the network, or the app's write path, so a
rule can be argued about and changed without a GPU or a Windows box.
"""

import json
import pathlib
import re

from tdsnap.web import prompts

EVAL_SET = pathlib.Path(__file__).parent / "fixtures" / "ai_eval_set.json"

# Checks a case may ask for. Adding one means adding it here and in CHECKS.
KNOWN_CHECKS = {
    "forbids",       # none of these words may appear in any item
    "expects_any",   # at least one item is a recognisable member of the type
    "max_words",     # every item is at most this many words
    "min_items",     # at least this many usable items came back
    "no_duplicates", # no item repeats another, case-insensitively
    "not_the_title", # no item is just the category restated
    "looks_like_names",  # every item reads as a proper name
    "functions_match",   # each phrase carries the function its text supports
    "ends_questions",    # a phrase tagged question ends in a question mark
}


def load_cases() -> list:
    cases = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    for case in cases:
        unknown = set(case.get("checks", {})) - KNOWN_CHECKS
        if unknown:
            raise ValueError(f"{case['id']}: unknown checks {sorted(unknown)}")
    return cases


def _labels(items) -> list:
    """The spoken text of each item, whichever shape the engine returned."""
    out = []
    for item in items:
        label = item.get("label", "") if isinstance(item, dict) else item
        label = str(label or "").strip()
        if label:
            out.append(label)
    return out


def _check_forbids(case, items, forbidden) -> str:
    """The type-matching rule: related vocabulary is not an example of a type."""
    for label in _labels(items):
        folded = label.casefold()
        for word in forbidden:
            # Word-boundary rather than substring, so "wand" does not fire on
            # "Wanda" and a rule stays as narrow as it reads.
            if re.search(rf"\b{re.escape(str(word).casefold())}\b", folded):
                return f"{label!r} contains the forbidden word {word!r}"
    return ""


def _check_expects_any(case, items, expected) -> str:
    """Does the model know this category at all?

    ``forbids`` catches the drift the prompt warns about — "wand" for a
    characters page — but on its own it passes any answer that avoids the
    forbidden words, including confident nonsense. This is the other half: at
    least one item has to be something a person would recognise as a member of
    the type. Deliberately generous — one hit out of eight is enough — because
    it is checking for knowledge of the subject, not for a particular answer.
    """
    haystack = " | ".join(label.casefold() for label in _labels(items))
    for word in expected:
        if re.search(rf"\b{re.escape(str(word).casefold())}\b", haystack):
            return ""
    return "nothing recognisable as an example of this category came back"


def _check_max_words(case, items, limit) -> str:
    for label in _labels(items):
        if len(label.split()) > limit:
            return f"{label!r} is longer than {limit} words"
    return ""


def _check_min_items(case, items, minimum) -> str:
    found = len(_labels(items))
    return "" if found >= minimum else f"only {found} usable items, wanted {minimum}"


def _check_no_duplicates(case, items, _value) -> str:
    seen = set()
    for label in _labels(items):
        folded = label.casefold()
        if folded in seen:
            return f"{label!r} appears more than once"
        seen.add(folded)
    return ""


def _check_not_the_title(case, items, _value) -> str:
    title = str(case["category"]).casefold().strip()
    for label in _labels(items):
        if label.casefold().strip() == title:
            return f"{label!r} just restates the page title"
    return ""


# A curly apostrophe is ordinary in a name, so it is allowed alongside the
# straight one. Both are written as escapes: the literal characters are
# indistinguishable on sight, which is exactly what ruff's RUF001 is for.
_NAME = re.compile(
    r"^[A-Z\u00C0-\u024F][\w\u0027\u2019.\-]*"
    r"(?:\s+[\w\u0027\u2019.\-]+)*$"
)


def _check_looks_like_names(case, items, _value) -> str:
    """"Return only their names" — so an item starts like a name, not a noun."""
    for label in _labels(items):
        if not _NAME.match(label):
            return f"{label!r} does not read as a name"
    return ""


def _check_functions_match(case, items, _value) -> str:
    """Every phrase carries the function its own text supports.

    This is the promise ``prompts.phrase_function`` makes, not the one the
    model makes: a model may claim any function it likes and the classifier
    overrules it. What must hold is that the classifier was applied.
    """
    for item in items:
        if not isinstance(item, dict):
            return f"{item!r} is not a phrase object"
        function = item.get("function")
        if function not in prompts.PHRASE_FUNCTIONS:
            return f"{item.get('label')!r} carries the unknown function {function!r}"
        derived = prompts.phrase_function(item["label"], function)
        if function != derived:
            return (
                f"{item['label']!r} is tagged {function!r} but reads as {derived!r}"
            )
    return ""


def _check_ends_questions(case, items, _value) -> str:
    for item in items:
        if (
            isinstance(item, dict)
            and item.get("function") == "question"
            and not str(item.get("label", "")).strip().endswith("?")
        ):
            return f"{item.get('label')!r} is tagged a question but is not one"
    return ""


CHECKS = {
    "forbids": _check_forbids,
    "expects_any": _check_expects_any,
    "max_words": _check_max_words,
    "min_items": _check_min_items,
    "no_duplicates": _check_no_duplicates,
    "not_the_title": _check_not_the_title,
    "looks_like_names": _check_looks_like_names,
    "functions_match": _check_functions_match,
    "ends_questions": _check_ends_questions,
}


def score(case: dict, items) -> dict:
    """Run *case*'s checks over *items*.

    Returns ``{id, passed, failures}``. Every failing check is reported, not
    just the first, because "which rule did this release lose?" is the whole
    reason to keep the number.
    """
    failures = []
    for name, value in case.get("checks", {}).items():
        reason = CHECKS[name](case, items, value)
        if reason:
            failures.append(f"{name}: {reason}")
    return {"id": case["id"], "passed": not failures, "failures": failures}


def summarize(results) -> dict:
    results = list(results)
    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        # Rounded, and 0.0 for an empty run rather than a division by zero: an
        # eval that ran nothing has not proved anything.
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "results": results,
    }
