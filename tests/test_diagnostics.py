"""Support-report tests, centred on what the report must never contain.

The report exists so a user can paste it into a public issue without reading
it first. That promise is only as good as the redaction, so most of these
tests feed realistic page-set content through the collectors and assert it
does not survive.
"""

import pytest

from tdsnap.errors import PagesetError
from tdsnap.web import diagnostics, server


@pytest.fixture
def client():
    return server.app.test_client()


# Values a real user would recognise as theirs, planted in the status dicts
# the collectors read from.
PRIVATE_PAGE = "Ryan's Snack Words"
PRIVATE_GRIDSET = "Client 4 Communication"
PRIVATE_USER = "rpenny"


def fake_live_status(*_args, **_kwargs):
    return {
        "available": True,
        "running": True,
        "unlocked": True,
        "page": PRIVATE_PAGE,
        "pages": [PRIVATE_PAGE, "Topics Menu Page"],
        "grid": {"cols": 8, "rows": 5},
    }


def fake_grid3_status(*_args, **_kwargs):
    return {
        "available": True,
        "installed": True,
        "running": True,
        "unlocked": True,
        "elevated": True,
        "needs_elevation": False,
        "version": "3.0.93",
        "grid_set": PRIVATE_GRIDSET,
        "page": PRIVATE_PAGE,
        "user": PRIVATE_USER,
        "grid": {"cols": 12, "rows": 7},
    }


@pytest.fixture
def running_apps(monkeypatch):
    monkeypatch.setattr(diagnostics.live, "status", fake_live_status)
    monkeypatch.setattr(diagnostics.grid3, "status", fake_grid3_status)
    monkeypatch.setattr(diagnostics.grid3, "has_ui_access", lambda: True)
    monkeypatch.setattr(diagnostics.ollama, "status", lambda host: {"reachable": False})


def test_report_omits_page_set_content(running_apps):
    """The whole point: nothing the user would call theirs comes back."""
    text = diagnostics.as_text(diagnostics.report())
    for secret in (PRIVATE_PAGE, PRIVATE_GRIDSET, PRIVATE_USER, "Topics Menu Page"):
        assert secret not in text


def test_report_keeps_the_facts_a_maintainer_needs(running_apps):
    data = diagnostics.report()
    assert data["tdsnap"]["running"] is True
    assert data["tdsnap"]["grid"] == "8x5"
    assert data["grid3"]["version"] == "3.0.93"
    assert data["grid3"]["grid"] == "12x7"
    assert data["grid3"]["ui_access"] is True
    assert data["app"]["version"]


def test_grid_size_reported_as_shape_only(running_apps):
    """Dimensions describe the page's shape; they carry no vocabulary."""
    data = diagnostics.report()
    assert "cols" not in str(data["tdsnap"]["grid"])
    assert data["tdsnap"]["grid"] == "8x5"


def test_unknown_grid_when_not_running(monkeypatch):
    monkeypatch.setattr(diagnostics.live, "status", lambda *a, **k: {"available": False})
    assert "grid" not in diagnostics.report()["tdsnap"]


def test_probe_failure_is_reported_not_raised(monkeypatch):
    """A broken probe is itself the diagnostic; it must not sink the report."""
    def explode(*_args, **_kwargs):
        raise PagesetError("TD Snap isn't running.")

    monkeypatch.setattr(diagnostics.live, "status", explode)
    monkeypatch.setattr(diagnostics.grid3, "status", explode)
    data = diagnostics.report()
    assert "PagesetError" in data["tdsnap"]["probe_failed"]
    assert "PagesetError" in data["grid3"]["probe_failed"]


def test_ollama_probe_failure_is_not_fatal(monkeypatch):
    def explode(_host):
        raise OSError("connection refused")

    monkeypatch.setattr(diagnostics.ollama, "status", explode)
    assert diagnostics.report()["ai"]["ollama_reachable"] is False


def test_window_mode_tracks_the_host(running_apps):
    assert diagnostics.report(native=True)["app"]["window"] == "native"
    assert diagnostics.report(native=False)["app"]["window"] == "browser"


def test_grounding_flag_follows_the_environment(monkeypatch, running_apps):
    monkeypatch.setenv("TDSNAP_WEB_GROUNDING", "0")
    assert diagnostics.report()["app"]["grounding_allowed"] is False
    monkeypatch.setenv("TDSNAP_WEB_GROUNDING", "1")
    assert diagnostics.report()["app"]["grounding_allowed"] is True


def test_as_text_renders_booleans_readably():
    text = diagnostics.as_text({"app": {"packaged": True, "running": False, "missing": None}})
    assert "packaged: yes" in text
    assert "running: no" in text
    assert "missing: unknown" in text


def test_as_text_states_the_redaction_promise():
    text = diagnostics.as_text(diagnostics.report())
    assert "No page-set content" in text


def test_endpoint_returns_report_and_text(client, running_apps):
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["report"]["app"]["version"]
    assert payload["text"].startswith("AAC Editor support report")
    assert PRIVATE_PAGE not in payload["text"]


def test_endpoint_needs_no_token(client, running_apps):
    """Read-only and content-free, so it stays reachable when things are broken."""
    assert client.get("/api/diagnostics").status_code == 200
