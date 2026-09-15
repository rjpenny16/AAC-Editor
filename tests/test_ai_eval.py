"""The AI eval set, run against the real built-in model.

Prompt edits used to be guesswork: change a sentence, run it by hand a few
times, decide it felt better. This runs a fixed set of category prompts through
the real engine, scores each answer against the rules the prompt already states
(see ``tests/ai_eval.py``), and records the pass rate so a prompt change has a
number attached to it.

Opt-in, because it downloads a model and runs ~20 generations on CPU:

    TDSNAP_AI_SMOKE=1 python -m pytest tests/test_ai_eval.py

Environment:
    TDSNAP_AI_EVAL_FLOOR   minimum pass rate before the run fails (default 0.3)
    TDSNAP_AI_EVAL_LIMIT   run only the first N cases (default: all)
    TDSNAP_AI_EVAL_REPORT  where to write the JSON report

**The floor is a tripwire, not a quality bar.** CI runs the smallest model the
project supports (0.5B) to keep the job cheap, and a small model gets a fair
number of these wrong; what the floor catches is a prompt edit or a parsing
change that makes the answers *much* worse. The number to watch is the recorded
pass rate, compared against the previous release, not the distance to the floor.
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

DEFAULT_FLOOR = 0.3
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
    summary["model"] = smoke_localai.choice_for(smoke_localai.active_key()).name
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

    floor = _floor()
    assert summary["pass_rate"] >= floor, (
        f"pass rate {summary['pass_rate']:.0%} is below the {floor:.0%} floor; "
        f"see {REPORT}"
    )
