"""Enforce per-module coverage floors on the code that writes to a page set.

A single global percentage lets the safety-critical modules hide behind
well-tested helpers, and it can only ever be as high as the least testable
file. Most of this package's uncovered lines are in the Windows UI Automation
modules, which cannot run on a Linux CI box at all — so the global number says
very little about whether `builder`, `validate`, `schema`, or `templates` are
actually exercised.

Those four decide what lands in someone's communication device. They get their
own floors, checked here.

Usage:
    coverage run -m pytest && python scripts/check_coverage.py
"""

import json
import subprocess
import sys

# Floors, not targets. Raise them as coverage improves; never lower one to make
# a build pass.
FLOORS = {
    "tdsnap/builder.py": 90,
    "tdsnap/validate.py": 82,
    "tdsnap/templates.py": 88,
    "tdsnap/schema.py": 85,
    "tdsnap/pageset.py": 82,
    "tdsnap/colors.py": 85,
    "tdsnap/web/diagnostics.py": 90,
}


def main() -> int:
    try:
        report = json.loads(
            subprocess.run(
                [sys.executable, "-m", "coverage", "json", "-o", "-"],
                capture_output=True, text=True, check=True,
            ).stdout
        )
    except subprocess.CalledProcessError as exc:
        print(f"could not read coverage data: {exc.stderr.strip()}", file=sys.stderr)
        return 2

    files = report.get("files", {})
    failures, missing = [], []
    for path, floor in sorted(FLOORS.items()):
        entry = files.get(path) or files.get(path.replace("/", "\\"))
        if entry is None:
            missing.append(path)
            continue
        percent = entry["summary"]["percent_covered"]
        status = "ok " if percent >= floor else "LOW"
        print(f"  {status} {path:34} {percent:5.1f}%  (floor {floor}%)")
        if percent < floor:
            failures.append(f"{path}: {percent:.1f}% is below its {floor}% floor")

    if missing:
        print(f"\nnot measured: {', '.join(missing)}", file=sys.stderr)
        return 2
    if failures:
        print("\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print("\nevery write-path module clears its floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
