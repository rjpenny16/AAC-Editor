"""One running copy per user (REL-010, roadmap C6).

The audit confirmed the mechanism on Linux: with the first copy made
unresponsive, a second launch started its own server on a random port and
both shared one session folder and one settings file. These pin that a
second launch now never starts a server while the lock is held.
"""

import sys

import pytest

from tdsnap.web import instance, server


@pytest.fixture(autouse=True)
def _no_lock_held(monkeypatch):
    monkeypatch.setattr(instance, "_held", None)
    yield
    instance.release()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX advisory lock")
def test_only_one_holder_at_a_time():
    first = instance._acquire_posix()
    assert first is not None
    assert instance._acquire_posix() is None
    first.close()
    second = instance._acquire_posix()
    assert second is not None
    second.close()


def test_the_running_copy_records_where_it_listens():
    assert instance.acquire()
    instance.record_port(44909)
    assert instance.running_port() == 44909
    instance.release()
    assert instance.running_port() is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX advisory lock")
def test_a_second_launch_never_starts_a_server_while_the_first_holds_the_lock(monkeypatch, capsys):
    other_process = instance._acquire_posix()  # the first copy, unresponsive
    instance.record_port(44909)
    try:
        started = []
        monkeypatch.setattr(server, "make_server", lambda port: started.append(port))
        asked = []
        monkeypatch.setattr(server.localhttp, "loopback_json",
                            lambda request, timeout: asked.append(request.full_url) or {})
        monkeypatch.setattr(server.time, "sleep", lambda _s: None)
        server.run(port=8765, open_browser=False)
        assert started == []
        # It looked for the first copy where that copy said it was listening.
        assert asked and all(url.startswith("http://127.0.0.1:44909/") for url in asked)
        assert "not answering" in capsys.readouterr().out
    finally:
        other_process.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX advisory lock")
def test_a_second_launch_brings_a_responsive_first_copy_forward(monkeypatch, capsys):
    other_process = instance._acquire_posix()
    instance.record_port(8765)
    try:
        monkeypatch.setattr(server, "make_server", lambda port: pytest.fail("second server"))
        monkeypatch.setattr(server.localhttp, "loopback_json",
                            lambda request, timeout: {"ok": True, "focused": True})
        server.run(port=8765, open_browser=False)
        assert "brought its window to the front" in capsys.readouterr().out
    finally:
        other_process.close()


def test_a_restarting_copy_waits_for_the_old_one(monkeypatch):
    attempts = iter([None, None, object()])
    monkeypatch.setattr(instance, "_acquire_posix", lambda: next(attempts))
    monkeypatch.setattr(instance, "_acquire_windows", lambda: next(attempts))
    monkeypatch.setattr(instance.time, "sleep", lambda _s: None)
    assert instance.acquire(wait=20) is True
    monkeypatch.setattr(instance, "_held", None)
