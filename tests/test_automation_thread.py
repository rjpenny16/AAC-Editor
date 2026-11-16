"""TD Snap and Grid 3 automation runs on one thread, and never blocks the poll.

UI Automation is COM underneath: a thread has to be initialized before it
uses it, and a control must be used on the thread that found it. The web
server answers every request on a new thread, so each automation call is
handed to one long-lived thread instead. These tests pin that down without
Windows — the calls are plain functions.
"""

import os
import threading

import pytest

from tdsnap.errors import PagesetError
from tdsnap.uia import AutomationThread
from tdsnap.web import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setattr(server, "_sessions", {})
    os.makedirs(server._SESSION_ROOT)
    return server.app.test_client()


def token_headers(**extra):
    return {"X-TDSnap-Token": server.API_TOKEN, **extra}


def test_every_call_runs_on_the_same_initialized_thread():
    initialized = []
    worker = AutomationThread(initialize=lambda: initialized.append(threading.get_ident()))
    seen = set()

    def call():
        seen.add(threading.get_ident())
        return "done"

    results = []
    callers = [
        threading.Thread(target=lambda: results.append(worker.run(call))) for _ in range(5)
    ]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join()

    assert results == ["done"] * 5
    assert len(seen) == 1
    assert initialized == list(seen)
    assert threading.get_ident() not in seen


def test_an_error_is_raised_in_the_caller_and_the_thread_keeps_working():
    worker = AutomationThread(initialize=lambda: None)

    def fail():
        raise PagesetError("TD Snap changed while the edit was running.")

    with pytest.raises(PagesetError, match="changed while the edit"):
        worker.run(fail)
    assert worker.run(lambda: 42) == 42


def test_a_failed_startup_is_reported_rather_than_hanging():
    def broken():
        raise OSError("CoInitializeEx failed")

    worker = AutomationThread(initialize=broken)
    with pytest.raises(PagesetError, match="Windows automation could not start"):
        worker.run(lambda: "never")


def test_a_call_from_the_automation_thread_itself_does_not_deadlock():
    worker = AutomationThread(initialize=lambda: None)
    assert worker.run(lambda: worker.run(lambda: "nested")) == "nested"


def test_live_endpoints_run_on_the_automation_thread(client, monkeypatch):
    threads = []

    def status(include_pages=True):
        threads.append(threading.current_thread().name)
        return {"available": True, "running": False, "unlocked": True, "page": None, "grid": None}

    monkeypatch.setattr(server.live, "status", status)
    assert client.get("/api/tdsnap/status", headers=token_headers()).get_json()["ok"]
    assert threads == ["aac-editor-automation"]


def test_the_background_poll_never_waits_behind_an_edit(client, monkeypatch):
    # A poll that queued behind a running edit held the user's next request
    # up in turn, until one ran past the browser's deadline.
    def status(include_pages=True):
        raise AssertionError("the poll must not touch TD Snap while it is busy")

    monkeypatch.setattr(server.live, "status", status)
    with server._LIVE_LOCK:
        data = client.get(
            "/api/tdsnap/status", headers=token_headers(**{"X-TDSnap-Brief": "1"})
        ).get_json()
    assert data == {"ok": True, "busy": True}


def test_an_unexpected_failure_is_json_the_browser_can_show(client, monkeypatch):
    def status(include_pages=True):
        raise RuntimeError("(-2147220991, 'An event was unable to invoke any of the subscribers')")

    monkeypatch.setattr(server.live, "status", status)
    response = client.get("/api/tdsnap/status", headers=token_headers())
    assert response.status_code == 500
    data = response.get_json()
    assert data["ok"] is False
    assert "Something unexpected went wrong" in data["error"]
    assert "unable to invoke" in data["error"]


def test_an_unknown_api_path_is_json_too(client):
    response = client.get("/api/does-not-exist", headers=token_headers())
    assert response.status_code == 404
    assert response.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# Deadlines and cancellation (REL-011, roadmap C5)


def test_a_call_past_its_deadline_is_abandoned_and_told_to_stop():
    from tdsnap import uia

    worker = AutomationThread(initialize=lambda: None)
    release = threading.Event()
    pressed_after_deadline = []

    def hangs_then_continues():
        release.wait(5)  # stuck inside the AAC app
        try:
            uia.check_cancelled()  # the next wait or input
        except uia.Cancelled:
            return "stopped"
        pressed_after_deadline.append(True)
        return "pressed"

    with pytest.raises(PagesetError) as caught:
        worker.run(hangs_then_continues, deadline=0.1)
    assert caught.value.code == "AUTOMATION_DEADLINE"

    # Nothing is queued behind a call that is still stuck.
    with pytest.raises(PagesetError, match="still not responding"):
        worker.run(lambda: "next", deadline=1)

    release.set()
    deadline = threading.Event()
    deadline.wait(0.3)
    assert pressed_after_deadline == []
    # Once it has stopped, the thread takes work again.
    assert worker.run(lambda: "next", deadline=1) == "next"


def test_a_write_past_its_deadline_is_unknown_and_locks_live_editing(client, monkeypatch):
    from tdsnap import live

    monkeypatch.setattr(server, "WRITE_DEADLINE_SECONDS", 0.1)
    monkeypatch.setattr(server, "_AUTOMATION", AutomationThread(initialize=lambda: None))
    monkeypatch.setitem(server._live_lock_state, "op", None)
    release = threading.Event()

    def hangs(*_args, **_kwargs):
        release.wait(5)
        return {"outcome": "verified"}

    monkeypatch.setattr(live, "apply_page_edits", hangs)
    monkeypatch.setattr(live, "last_edit", lambda: None)
    body = {"operation": "edit_page", "page": "Eating", "fingerprint": "f",
            "items": [{"label": "apple", "slot": 0}]}
    headers = token_headers(**{"X-TDSnap-Editor": "1"})
    first = client.post("/api/tdsnap/edit-plan", json=body, headers=headers).get_json()
    assert first["code"] == "AUTOMATION_DEADLINE" and first["outcome"] == "unknown"

    release.set()
    threading.Event().wait(0.3)
    second = client.post("/api/tdsnap/edit-plan", json=body, headers=headers).get_json()
    assert second["code"] == "LIVE_LOCKED"

    assert client.post("/api/live/reconnect", headers=headers).get_json()["ok"]
    monkeypatch.setattr(live, "apply_page_edits", lambda *a, **k: {"outcome": "verified"})
    third = client.post("/api/tdsnap/edit-plan", json=body, headers=headers).get_json()
    assert third["ok"] is True
