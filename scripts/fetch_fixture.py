"""Download the real TD Snap page set used by the integration tests.

The file is Tobii Dynavox's "Motor Plan 40 High Contrast" page set
(SchemaVersion 4.13), shipped as an example in the open-source obf-node
converter. It is proprietary Tobii content, so it is never committed to this
repository — this script fetches it into the gitignored fixtures directory.

Usage:  python scripts/fetch_fixture.py
"""

import hashlib
import pathlib
import sys
import urllib.request

URL = "https://raw.githubusercontent.com/willwade/obf-node/master/examples/example.sps"
DEST = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "example.sps"

# Guards against a silently truncated download; update if obf-node updates
# its example file (the tests will tell you: SQLite magic check fails fast).
MIN_BYTES = 10_000_000
SQLITE_MAGIC = b"SQLite format 3\x00"


def main() -> int:
    if DEST.exists() and DEST.stat().st_size >= MIN_BYTES:
        print(f"Already present: {DEST} ({DEST.stat().st_size:,} bytes)")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL} ...")
    with urllib.request.urlopen(URL) as response:
        data = response.read()
    if not data.startswith(SQLITE_MAGIC) or len(data) < MIN_BYTES:
        print("Downloaded file doesn't look like a TD Snap page set; aborting.",
              file=sys.stderr)
        return 1
    DEST.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"Wrote {DEST} ({len(data):,} bytes, sha256={digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
