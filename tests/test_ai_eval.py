"""The AI eval set, run against the real built-in model.

Prompt edits used to be guesswork: change a sentence, run it by hand a few
times, decide it felt better. This runs a fixed set of category prompts through
the real engine, scores each answer against the rules the prompt already states
(see ``tests/ai_eval.py``), and records the pass rate so a prompt change has a
number attached to it.

Opt-in, because it downloads a model and runs ~20 generations on CPU:

    TDSNAP_AI_SMOKE=1 python -m pytest tests/test_ai_eval.py

Environment:
    TDSNAP_AI_EVAL_FLOOR   fail below this pass rate (default 0: record only)
    TDSNAP_AI_EVAL_LIMIT   run only the first N cases (default: all)
    TDSNAP_AI_EVAL_REPORT  where to write the JSON report

**This records; it does not gate.** The first CI run settled an argument the
first draft of this file got wrong. It asserted a 0.3 pass rate, which was a
guess — the exact thing the eval exists to replace — and CI measured 0.15 on the
model it runs. That model is Qwen2.5 **0.5B**, the cheapest one that exercises
the real code path, and at that size it mostly echoes the page title back:
*"farm animals"* for Farm animals, *"Hogwarts"* for Harry Potter characters. The
shipped default is three times its size. So a pass rate here is a number to
compare against the previous release, not a verdict on what a user gets, and
gating on it would mean a red build on a known baseline plus whatever
temperature 0.7 adds on twenty cases.

What does gate, on every build: ``test_ai_eval_rules.py`` proves the checks are
strict, and ``test_ai_smoke.py`` fails outright if generation or parsing breaks.
A collapse cannot pass through those unnoticed, which is what a floor here would
otherwise have been for.

Set ``TDSNAP_AI_EVAL_FLOOR`` to gate deliberately — against a known model, on a
release build — rather than by default.
"""

import json
import os
import pathlib

import pytest

from tests import ai_eval

pytestmark = pytest.mark.skipif(
    os.environ.get("TDSNAP_AI_SMOKE") != "1",
    reason="set TDSNAP_AI_SMOKE=1 to run the real-model eval set",
)

# 0 means "record, do not gate" — see the module docstring.
DEFAULT_FLOOR = 0.0
REPORT = pathlib.Path(
    os.environ.get("TDSNAP_AI_EVAL_REPORT")
    or pathlib.Path(__file__).resolve().parent.parent / "ai-eval-report.json"
)


def _cases():
    cases = ai_eval.load_cases()
    limit = os.environ.get("TDSNAP_AI_EVAL_LIMIT", "").strip()
    return cases[: int(limit)] if limit.isdigit() and int(limit) > 0 else cases


def _floor() -> float:
    try:
        return float(os.environ.get("TDSNAP_AI_EVAL_FLOOR", DEFAULT_FLOOR))
    except ValueError:
        return DEFAULT_FLOOR


def test_eval_set_pass_rate(smoke_localai, record_property):
    results = []
    for case in _cases():
        items, error = smoke_localai.generate_words(
            case["category"],
            count=case["count"],
            kind=case["kind"],
            function=case.get("function"),
        )
        if error:
            # A generation that failed outright is a failed case, named as
            # such: an eval that skipped its hard prompts is not an eval.
            results.append({
                "id": case["id"], "passed": False,
                "failures": [f"generation failed: {error}"],
            })
            continue
        result = ai_eval.score(case, items)
        result["items"] = items
        results.append(result)

    summary = ai_eval.summarize(results)
    active = smoke_localai.choice_for(smoke_localai.active_key())
    summary["model"] = active.name
    summary["model_file"] = active.file
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    record_property("ai_eval_pass_rate", summary["pass_rate"])
    print(
        f"\nAI eval: {summary['passed']}/{summary['total']} passed "
        f"({summary['pass_rate']:.0%}) on {summary['model']} — report at {REPORT}"
    )
    for result in results:
        if not result["passed"]:
            print(f"  FAIL {result['id']}: {'; '.join(result['failures'])}")

    # An eval that scored nothing has not measured anything, and must not be
    # read as a clean run — that is the one unambiguous failure here.
    assert summary["total"] == len(_cases()), (
        f"only {summary['total']} of {len(_cases())} cases produced a result"
    )

    floor = _floor()
    if floor > 0:
        assert summary["pass_rate"] >= floor, (
            f"pass rate {summary['pass_rate']:.0%} is below the {floor:.0%} floor; "
            f"see {REPORT}"
        )
