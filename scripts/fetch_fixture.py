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

URL = (
    "https://raw.githubusercontent.com/willwade/obf-node/"
    "e514e16a9b1ab481ee22790d2437b6a3db18cd93/examples/example.sps"
)
DEST = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "example.sps"

EXPECTED_SHA256 = "f1fa9133fbeb1d29094f31a44309366bdeb77ab6ed8f6cef7bb18afa6b47e17b"
SQLITE_MAGIC = b"SQLite format 3\x00"


def main() -> int:
    if DEST.exists() and hashlib.sha256(DEST.read_bytes()).hexdigest() == EXPECTED_SHA256:
        print(f"Already present: {DEST} ({DEST.stat().st_size:,} bytes)")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL} ...")
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if not data.startswith(SQLITE_MAGIC) or digest != EXPECTED_SHA256:
        print("Downloaded fixture failed its SQLite/header checksum; aborting.",
              file=sys.stderr)
        return 1
    DEST.write_bytes(data)
    print(f"Wrote {DEST} ({len(data):,} bytes, sha256={digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
