"""Evaluate an actual offered model, including strict source-specific cases.

Run from a checkout with the AI extra installed. Unlike the cheap CI smoke
model, this uses the pinned models users can actually select.
Downloads require --download; references are fixed local fixtures, so live
Wikipedia changes cannot change the expected results.
"""

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["small", "qwen3", "large"], default="qwen3")
    parser.add_argument("--case", action="append", default=[], help="Case ID; repeat to select several")
    parser.add_argument("--download", action="store_true", help="Allow a verified model download")
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--floor", type=float, default=1.0, help="Required pass rate for selected cases")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from tdsnap.web import grounding, localai, prompts
    from tests import ai_eval

    cases = [case for case in ai_eval.load_cases() if not args.case or case["id"] in args.case]
    unknown = set(args.case) - {case["id"] for case in cases}
    if unknown or not cases:
        parser.error(f"Unknown or empty case selection: {sorted(unknown)}")
    if not localai.engine_available():
        parser.error("Install the AI extra (llama-cpp-python) to evaluate real output.")
    choice = localai.choice_for(args.model)
    if choice.key != args.model:
        parser.error("Clear TDSNAP_MODEL_* overrides to evaluate an offered model.")
    if not localai.is_downloaded(args.model):
        if not args.download:
            parser.error("Model is not installed; use --download to allow its verified download.")
        localai.start_download(args.model)
        deadline = time.monotonic() + 900
        while localai.download_state()["status"] == "downloading" and time.monotonic() < deadline:
            time.sleep(1)
        if not localai.is_downloaded(args.model):
            parser.error(f"Model download did not finish: {localai.download_state()}")
    results = []
    for case in cases:
        started = time.monotonic()
        reference = grounding.select_passages(
            case.get("reference", ""), f"{case['category']} {case.get('request', '')}"
        )
        items, error = localai.generate_words(
            case["category"], count=prompts.overask(case["count"]), kind=case["kind"],
            function=case.get("function"), reference=reference,
            request=case.get("request"), model_key=args.model,
        )
        items = prompts.clean_items(
            items, case["count"], case["kind"], case["category"],
            reference=reference, function=case.get("function"),
        )
        result = ai_eval.score(case, items)
        if error:
            result["passed"] = False
            result["failures"].append(error)
        result.update(items=items, seconds=round(time.monotonic() - started, 2))
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    report = {**ai_eval.summarize(results), "model": choice.name,
              "revision": choice.revision, "floor": args.floor}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{report['passed']}/{report['total']} cases passed; report: {args.report}")
    return int(report["pass_rate"] < args.floor)


if __name__ == "__main__":
    sys.exit(main())
