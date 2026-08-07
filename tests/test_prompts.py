"""Tests for tdsnap/web/prompts.py, including the phrase classifier's golden cases.

tests/fixtures/phrase_function_cases.json is the single source of truth for
`phrase_function`'s expected behavior — this file and tests/js/phrases.test.js
both run every case against their own implementation, so a change to one
regex set without the other fails CI instead of shipping a silent disagreement
(see phrases.js's module docstring and ROADMAP.md's Phase 3).
"""

import json
import pathlib

import pytest

from tdsnap.web import prompts

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PHRASE_CASES = json.loads((FIXTURES / "phrase_function_cases.json").read_text(encoding="utf-8"))


def test_golden_fixture_is_not_empty():
    assert len(PHRASE_CASES) > 0


@pytest.mark.parametrize(
    "case", PHRASE_CASES, ids=[case["label"] or "<empty>" for case in PHRASE_CASES]
)
def test_phrase_function_matches_the_shared_golden_cases(case):
    assert prompts.phrase_function(case["label"], case.get("suggested")) == case["expected"]
