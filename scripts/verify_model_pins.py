"""Confirm every built-in model pin against the publisher, and complete a new one.

``tdsnap/web/localai.py`` pins each downloadable model to a repository, an
immutable commit, an exact byte size, and a SHA-256, and refuses a download
that does not match all of them. That discipline is only worth anything if the
pinned values are the publisher's real ones — a pin nobody ever checked is a
number, not a guarantee.

This asks Hugging Face's metadata API what the file at that exact revision
actually is. It never downloads the model itself: LFS metadata carries the size
and the SHA-256, so verifying a 4.7 GB pin costs one small JSON request.

    python scripts/verify_model_pins.py            # check the pins that exist
    python scripts/verify_model_pins.py --resolve  # also print missing ones

``--resolve`` is how an entry that is declared but not yet offered gets its pin:
it resolves the repository's current head commit and prints the ``revision``,
``size`` and ``sha256`` lines to paste into the registry. Until those are
pasted in, ``ModelChoice.pinned`` is False and the app will not offer or
download that model at all.

Exit codes: 0 all pins verified · 1 a pin disagrees with the publisher ·
2 the publisher could not be reached (no network, rate limit, unknown repo).
"""

import json
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

API = "https://huggingface.co/api/models"
TIMEOUT = 30


def _get(url: str):
    request = urllib.request.Request(  # noqa: S310 - URL is built from the API constant
        url, headers={"User-Agent": "tdsnap-editor-pin-check",
                      "Accept": "application/json"}
    )
    # URL is built from the API constant; the scheme is fixed https
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        return json.loads(response.read(8_000_000).decode("utf-8"))


def head_revision(repo: str) -> str:
    return str(_get(f"{API}/{repo}").get("sha") or "")


def file_metadata(repo: str, revision: str, filename: str) -> dict:
    """The publisher's own record of one file at one commit."""
    for entry in _get(f"{API}/{repo}/tree/{revision}"):
        if entry.get("path") == filename:
            lfs = entry.get("lfs") or {}
            return {
                # LFS stores the SHA-256 as the object id; a non-LFS file has
                # only a git blob sha, which is not the same thing and must not
                # be mistaken for one.
                "sha256": str(lfs.get("oid") or "") if lfs else "",
                "size": int(lfs.get("size") or entry.get("size") or 0),
            }
    raise LookupError(f"{filename!r} is not in {repo} at {revision[:12]}")


def check(choice, resolve: bool) -> str:
    """Return "ok", "mismatch", "unresolved", or "unreachable" for one entry."""
    if not choice.repo:
        print(f"  -- {choice.key:6} {choice.name}: not a published pin, skipped")
        return "ok"
    revision = choice.revision
    try:
        if not revision:
            if not resolve:
                print(
                    f"  ?? {choice.key:6} {choice.name}: no revision pinned "
                    "(run with --resolve)"
                )
                return "unresolved"
            revision = head_revision(choice.repo)
        actual = file_metadata(choice.repo, revision, choice.file)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        print(f"  !! {choice.key:6} {choice.name}: could not reach the publisher: {exc}")
        return "unreachable"
    except LookupError as exc:
        print(f"  XX {choice.key:6} {choice.name}: {exc}")
        return "mismatch"

    if not choice.pinned:
        print(f"  ++ {choice.key:6} {choice.name}: paste these into the registry")
        print(f'         revision="{revision}",')
        print(f'         sha256="{actual["sha256"]}",')
        print(f"         size={actual['size']:_},")
        return "unresolved"

    problems = []
    if actual["sha256"] and actual["sha256"].lower() != choice.sha256.lower():
        problems.append(f"sha256 {choice.sha256} != published {actual['sha256']}")
    if actual["size"] and actual["size"] != choice.size:
        problems.append(f"size {choice.size:_} != published {actual['size']:_}")
    if problems:
        print(f"  XX {choice.key:6} {choice.name}: " + "; ".join(problems))
        return "mismatch"
    print(f"  ok {choice.key:6} {choice.name}: matches {choice.repo}@{revision[:12]}")
    return "ok"


def main(argv) -> int:
    # Imported here so the script runs from a checkout without the package
    # installed, and so the path fiddling stays out of the module body.
    sys.path.insert(0, str(ROOT))
    from tdsnap.web import localai

    resolve = "--resolve" in argv
    print("Verifying built-in model pins against their publishers:")
    outcomes = [check(choice, resolve) for choice in localai.CHOICES]
    if "mismatch" in outcomes:
        print("\na pin disagrees with the publisher; do not ship it", file=sys.stderr)
        return 1
    if "unreachable" in outcomes:
        print("\ncould not verify every pin", file=sys.stderr)
        return 2
    unresolved = outcomes.count("unresolved")
    if unresolved:
        print(f"\n{unresolved} entry(s) still need a pin before they are offered")
    else:
        print("\nevery pin matches its publisher")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
