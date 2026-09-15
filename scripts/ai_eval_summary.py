"""Render the AI eval run's report as Markdown for a CI job summary.

``tests/test_ai_eval.py`` writes ``ai-eval-report.json``; this turns it into
the few lines a reviewer actually reads on the build page — the pass rate, and
which cases failed and why.

Usage:  python scripts/ai_eval_summary.py [report.json]

A missing report is said out loud rather than printed as a pass: the eval
downloads a model from a third-party CDN, and a run that never happened must
not read like a run that succeeded.
"""

import json
import pathlib
import sys

DEFAULT = pathlib.Path(__file__).resolve().parent.parent / "ai-eval-report.json"


def render(report: dict) -> str:
    lines = [
        f"### AI eval — {report.get('model', 'unknown model')}",
        "",
        f"**{report['passed']}/{report['total']} passed "
        f"({report['pass_rate']:.0%})**",
        "",
    ]
    failed = [result for result in report.get("results", []) if not result["passed"]]
    if failed:
        lines += ["| case | why |", "| --- | --- |"]
        lines += [
            f"| {result['id']} | {'; '.join(result['failures'])} |"
            for result in failed
        ]
    else:
        lines.append("Every case passed.")
    return "\n".join(lines) + "\n"


def main(argv) -> int:
    path = pathlib.Path(argv[0]) if argv else DEFAULT
    if not path.exists():
        print(
            "The AI eval produced no report — the run was skipped or the model "
            "could not be fetched."
        )
        return 0
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        print(render(report), end="")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"The AI eval report could not be read: {exc}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
