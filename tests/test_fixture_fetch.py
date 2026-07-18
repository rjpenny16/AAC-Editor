import io
import re

from scripts import fetch_fixture


def test_real_fixture_is_commit_and_checksum_pinned():
    assert re.search(r"/[0-9a-f]{40}/examples/example\.sps$", fetch_fixture.URL)
    assert re.fullmatch(r"[0-9a-f]{64}", fetch_fixture.EXPECTED_SHA256)


def test_real_fixture_rejects_wrong_checksum(tmp_path, monkeypatch):
    destination = tmp_path / "example.sps"
    monkeypatch.setattr(fetch_fixture, "DEST", destination)
    monkeypatch.setattr(
        fetch_fixture.urllib.request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(fetch_fixture.SQLITE_MAGIC + b"wrong"),
    )

    assert fetch_fixture.main() == 1
    assert not destination.exists()
