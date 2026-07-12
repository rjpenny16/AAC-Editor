"""Web backend lifecycle and API-hardening tests.

Covers the pieces added for desktop-grade behavior: instance detection and
port fallback, the CSRF token guard on POSTs, the quit endpoint, stale
session cleanup, and the native open/save helpers used by the window mode.
No real HTTP server or pywebview is needed — Flask's test client and the
plain helper functions are enough.
"""

import io
import os
import socket
import sqlite3
import time

import pytest

from tdsnap.errors import PagesetError
from tdsnap.web import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setattr(server, "_sessions", {})
    os.makedirs(server._SESSION_ROOT)
    return server.app.test_client()


def token_headers():
    return {"X-TDSnap-Token": server.API_TOKEN}


def upload(client, source_path, filename="test.sps"):
    with open(source_path, "rb") as handle:
        payload = io.BytesIO(handle.read())
    return client.post(
        "/api/pageset",
        data={"file": (payload, filename)},
        headers=token_headers(),
    )


def test_health_identifies_the_app(client):
    data = client.get("/api/health").get_json()
    assert data["ok"] and data["app"] == server.APP_ID


def test_config_hands_the_token_to_same_origin_pages(client):
    data = client.get("/api/config").get_json()
    assert data["token"] == server.API_TOKEN
    assert data["native"] is False


def test_posts_without_the_token_are_rejected(client, seeded_source):
    with open(seeded_source, "rb") as handle:
        payload = io.BytesIO(handle.read())
    response = client.post("/api/pageset", data={"file": (payload, "test.sps")})
    assert response.status_code == 403

    response = client.post(
        "/api/pageset", headers={"X-TDSnap-Token": "wrong"}, data={}
    )
    assert response.status_code == 403


def test_focus_is_token_exempt_and_reports_a_handler(client, monkeypatch):
    assert client.post("/api/focus").get_json()["focused"] is False

    calls = []
    monkeypatch.setitem(server._runtime, "focus", lambda: calls.append(1))
    assert client.post("/api/focus").get_json()["focused"] is True
    assert calls == [1]


def test_upload_build_download_roundtrip(client, seeded_source, tmp_path):
    data = upload(client, seeded_source).get_json()
    assert data["ok"], data
    session_id = data["session_id"]
    parent = next(p for p in data["pages"] if p["title"] == "Home Page")

    built = client.post(
        f"/api/pageset/{session_id}/page",
        json={"title": "Snacks", "items": ["chips", "apple"],
              "parent_page_id": parent["id"]},
        headers=token_headers(),
    ).get_json()
    assert built["ok"] and built["buttons"] == 2

    response = client.get(f"/api/pageset/{session_id}/download")
    assert response.status_code == 200
    assert "test.edited.sps" in response.headers["Content-Disposition"]
    edited = tmp_path / "roundtrip.sps"
    edited.write_bytes(response.data)
    conn = sqlite3.connect(str(edited))
    titles = {row[0] for row in conn.execute("SELECT Title FROM Page")}
    conn.close()
    assert "Snacks" in titles


def test_open_path_and_save_current_as(client, seeded_source, tmp_path):
    before = open(seeded_source, "rb").read()
    data = server.open_path(seeded_source)
    assert data["ok"] and data["filename"] == "test.sps"
    assert open(seeded_source, "rb").read() == before  # source untouched

    assert server.edited_filename(data["session_id"]) == "test.edited.sps"

    dest = tmp_path / "saved.sps"
    server.save_current_as(data["session_id"], str(dest))
    conn = sqlite3.connect(str(dest))
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_open_path_rejects_missing_files(client, tmp_path):
    with pytest.raises(PagesetError):
        server.open_path(str(tmp_path / "nope.sps"))


def test_open_path_rejects_non_pagesets(client, tmp_path):
    bogus = tmp_path / "bogus.sps"
    bogus.write_bytes(b"not a database")
    with pytest.raises(PagesetError):
        server.open_path(str(bogus))


def test_quit_stops_the_server(client, monkeypatch):
    assert client.post("/api/quit", headers=token_headers()).status_code == 400

    calls = []
    monkeypatch.setitem(server._runtime, "shutdown", lambda: calls.append(1))
    assert client.post("/api/quit", headers=token_headers()).get_json()["ok"]
    deadline = time.time() + 3
    while not calls and time.time() < deadline:
        time.sleep(0.05)
    assert calls == [1]


def test_pick_port_prefers_free_falls_back_when_busy():
    free = server.pick_port(0)  # any free port works for the busy setup
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        busy_port = blocker.getsockname()[1]
        picked = server.pick_port(busy_port)
        assert picked != busy_port
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        open_port = probe.getsockname()[1]
    assert server.pick_port(open_port) == open_port
    assert free  # OS gave us something


def test_instance_running_is_false_on_a_dead_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert server.instance_running(port) is False


def test_cleanup_stale_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_SESSION_ROOT", str(tmp_path))
    stale = tmp_path / "old-session"
    fresh = tmp_path / "new-session"
    stale.mkdir()
    fresh.mkdir()
    old = time.time() - 2 * server.SESSION_MAX_AGE
    os.utime(stale, (old, old))

    server.cleanup_stale_sessions()
    assert not stale.exists()
    assert fresh.exists()
