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
import ctypes
import webbrowser
from types import SimpleNamespace

import pytest

from tdsnap.errors import PagesetError
from tdsnap.web import server
from tdsnap.web import desktop


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


def test_index_explains_both_local_ai_setup_options(client):
    page = client.get("/").get_data(as_text=True)
    assert "Recommended: use the built-in model" in page
    assert "ollama pull llama3.2" in page
    assert "Check connection" in page
    assert "Drop your" not in page
    assert "TD Snap exported file" in page
    assert "Create a page in a separate edited copy" in page
    assert "sends only this page title to Wikipedia" in page
    assert "Drag buttons to the exact cells" in page


def test_foreign_hosts_are_rejected(client):
    """DNS rebinding shows up as a non-loopback Host header — refuse it."""
    for evil in ("evil.example", "evil.example:8765", "127.0.0.1.evil.example"):
        response = client.get("/api/config", headers={"Host": evil})
        assert response.status_code == 403, evil

    for good in ("127.0.0.1:8765", "localhost:8765", "localhost", "[::1]:8765"):
        response = client.get("/api/health", headers={"Host": good})
        assert response.status_code == 200, good


def test_browser_security_headers_prevent_framing(client):
    response = client.get("/")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_rejected_upload_leaves_no_session_dir(client):
    response = client.post(
        "/api/pageset",
        data={"file": (io.BytesIO(b"not a database"), "bogus.sps")},
        headers=token_headers(),
    )
    assert response.status_code == 400
    assert os.listdir(server._SESSION_ROOT) == []
    assert server._sessions == {}


def test_config_hands_the_token_to_same_origin_pages(client):
    data = client.get("/api/config").get_json()
    assert data["token"] == server.API_TOKEN
    assert data["native"] is False


def test_grid3_read_apis_and_elevated_mutation_security(client, monkeypatch):
    monkeypatch.setattr(
        server.grid3, "status",
        lambda include_layout=False: {
            "installed": True, "running": True, "elevated": True,
            "page": "Home", "layout_requested": include_layout,
        },
    )
    monkeypatch.setattr(
        server.grid3, "inspect_page",
        lambda: {"page": "Home", "fingerprint": "grid-fingerprint"},
    )
    monkeypatch.setattr(
        server.grid3, "probe_accessibility",
        lambda: {"supported": True, "checks": {"undo_without_save": "pass"}},
    )
    calls = []
    monkeypatch.setattr(
        server.grid3, "add_to_existing_page",
        lambda items, fingerprint: calls.append((items, fingerprint)) or {
            "page": "Home", "buttons": len(items), "checks": {"grid3_edit": "pass"}
        },
    )

    assert client.get("/api/grid3/status?layout=1").get_json()["layout_requested"] is True
    assert client.get("/api/grid3/page-layout").get_json()["fingerprint"] == "grid-fingerprint"
    assert client.post("/api/grid3/probe").status_code == 403
    probe = client.post(
        "/api/grid3/probe",
        headers={**token_headers(), "X-AAC-Editor": "grid3"},
    )
    assert probe.get_json()["checks"]["undo_without_save"] == "pass"

    payload = {
        "operation": "add_to_existing_page",
        "items": [{"label": "new", "slot": 1}],
        "fingerprint": "grid-fingerprint",
    }
    assert client.post("/api/grid3/edit-plan", json=payload).status_code == 403
    assert client.post(
        "/api/grid3/edit-plan", json=payload, headers=token_headers()
    ).status_code == 400
    response = client.post(
        "/api/grid3/edit-plan", json=payload,
        headers={**token_headers(), "X-AAC-Editor": "grid3"},
    )
    assert response.status_code == 200
    assert response.get_json()["checks"]["grid3_edit"] == "pass"
    assert calls == [([{"label": "new", "slot": 1}], "grid-fingerprint")]


def test_grid3_elevation_restart_uses_runas_and_closes_only_after_success(monkeypatch):
    calls = []
    destroyed = []
    shell = SimpleNamespace(
        ShellExecuteW=lambda *args: calls.append(args) or 42,
    )
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(shell32=shell), raising=False)
    monkeypatch.setattr(
        desktop.threading, "Timer",
        lambda _delay, callback: SimpleNamespace(start=callback),
    )
    api = desktop.NativeApi(8765)
    api.window = SimpleNamespace(destroy=lambda: destroyed.append(True))

    result = api.restart_elevated_for_grid3()

    assert result == {"ok": True, "restarting": True}
    assert calls[0][1] == "runas"
    assert "--replace-instance" in calls[0][3]
    assert "--grid3" in calls[0][3]
    assert destroyed == [True]


def test_grid3_uac_cancellation_keeps_original_window(monkeypatch):
    destroyed = []
    shell = SimpleNamespace(ShellExecuteW=lambda *_args: 5)
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(shell32=shell), raising=False)
    api = desktop.NativeApi(8765)
    api.window = SimpleNamespace(destroy=lambda: destroyed.append(True))

    result = api.restart_elevated_for_grid3()

    assert result["ok"] is False
    assert "cancelled" in result["error"]
    assert destroyed == []


def test_frozen_browser_launch_clears_bundled_dll_directory(monkeypatch):
    directories = []
    opened = []
    kernel32 = SimpleNamespace(
        SetDllDirectoryW=lambda path: directories.append(path) or True,
    )
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server.sys, "frozen", True, raising=False)
    monkeypatch.setattr(server.sys, "_MEIPASS", r"C:\\AACEditor\\_internal", raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel32, raising=False)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)

    assert server._open_browser("http://127.0.0.1:8765") is True
    assert directories == [None, r"C:\\AACEditor\\_internal"]
    assert opened == ["http://127.0.0.1:8765"]


def test_posts_without_the_token_are_rejected(client, seeded_source):
    with open(seeded_source, "rb") as handle:
        payload = io.BytesIO(handle.read())
    response = client.post("/api/pageset", data={"file": (payload, "test.sps")})
    assert response.status_code == 403


def test_ai_status_requires_token_and_rejects_invalid_hosts(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        server.ollama,
        "status",
        lambda host: calls.append(host) or {
            "reachable": False, "models": [], "message": "off",
        },
    )
    assert client.get("/api/ai/status?host=http://localhost:11434").status_code == 403
    assert calls == []

    response = client.get(
        "/api/ai/status?host=http://localhost:11434/path",
        headers=token_headers(),
    )
    assert response.status_code == 400
    assert calls == []

    response = client.get(
        "/api/ai/status?host=http://169.254.169.254",
        headers=token_headers(),
    )
    assert response.status_code == 400
    assert calls == []

    response = client.get(
        "/api/ai/status?host=http://localhost:11434/",
        headers=token_headers(),
    )
    assert response.status_code == 200
    assert calls == ["http://localhost:11434"]


def test_bad_json_boundaries_return_json_errors(client):
    response = client.post(
        "/api/pageset/missing/page",
        json={"title": "x", "items": [], "parent_page_id": "bad"},
        headers=token_headers(),
    )
    assert response.status_code == 400
    assert response.is_json

    response = client.post(
        "/api/ai/words",
        json={"category": "Snacks", "count": "many"},
        headers=token_headers(),
    )
    assert response.status_code == 400
    assert response.is_json

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


def test_parent_capacity_counts_spanning_buttons(tmp_path):
    source = tmp_path / "capacity.sqlite"
    conn = sqlite3.connect(str(source))
    conn.executescript(
        """
        CREATE TABLE PageSetProperties (GridDimension TEXT);
        CREATE TABLE PageLayout (
            Id INTEGER PRIMARY KEY, PageId INTEGER, PageLayoutSetting TEXT
        );
        CREATE TABLE ElementPlacement (
            PageLayoutId INTEGER, GridPosition TEXT, GridSpan TEXT, Visible INTEGER
        );
        INSERT INTO PageSetProperties VALUES ('3,2');
        INSERT INTO PageLayout VALUES (1, 7, '3,2,True,0');
        INSERT INTO ElementPlacement VALUES (1, '0,0', '2,1', 1);
        """
    )
    conn.commit()
    conn.close()
    assert server._free_cells(str(source), 7) == 4


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


def test_cleanup_sessions_removes_registered_copies(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_SESSION_ROOT", str(tmp_path))
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "original").write_bytes(b"private page set")
    monkeypatch.setattr(server, "_sessions", {
        "session": {"dir": str(session_dir), "filename": "private.sps"},
    })

    server.cleanup_sessions()

    assert server._sessions == {}
    assert not session_dir.exists()
