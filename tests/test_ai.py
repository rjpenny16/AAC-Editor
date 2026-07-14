"""AI-suggestion plumbing: prompts, model download, engine selection.

No real model or network is used — the download test uses a file:// URL and
the endpoint tests monkeypatch the backends.
"""

import time

import pytest

from tdsnap.web import grounding, localai, ollama, prompts


def test_build_prompt_variants():
    words = prompts.build_prompt("Snacks", 5, "words", existing=["Chips", "Apple"])
    assert "5" in words and "Snacks" in words and "1-3 words" in words
    assert "Chips" in words and "do not repeat" in words

    characters = prompts.build_prompt("Harry Potter characters", 12)
    assert "return only their names" in characters
    assert '"magic", "Hogwarts", and "wand" are invalid' in characters

    broad = prompts.build_prompt("School", 8)
    assert "infer the user's intended subject and type" in broad
    assert "If the title is broad" in broad

    phrases = prompts.build_prompt("Lunch", 4, "phrases")
    assert "ready-to-speak phrases" in phrases
    assert "statement must never be assigned the question function" in phrases

    question = prompts.build_prompt("Lunch", 4, "phrases", "question")
    assert 'must be "question"' in question
    assert 'must be "question"' not in phrases

    # Reference facts, when supplied, become an authoritative block; absent,
    # the prompt is unchanged.
    grounded = prompts.build_prompt(
        "Roblox characters", 6, reference="Wikipedia — Roblox: Builderman is a mascot."
    )
    assert "Reference facts" in grounded and "Builderman" in grounded
    assert "Reference facts" not in prompts.build_prompt("Roblox characters", 6)


def test_parse_items():
    assert prompts.parse_items('{"items": ["a", " b ", ""]}', 10) == ["a", "b"]
    assert prompts.parse_items('{"items": ["a", "b", "c"]}', 2) == ["a", "b"]
    assert prompts.parse_items("not json", 5) is None
    assert prompts.parse_items('{"items": "nope"}', 5) is None
    content = '{"items": [{"label": "Why?", "function": "comment"},' \
              '{"label": "The story has magic", "function": "question"},' \
              '{"label": "I love this", "function": "personal"},' \
              '{"label": "Wrong", "function": "blue"}]}'
    assert prompts.parse_items(content, 5, "phrases") == [
        {"label": "Why?", "function": "question"},
        {"label": "The story has magic", "function": "comment"},
        {"label": "I love this", "function": "positive"},
    ]
    assert prompts.phrase_function("I do not like spiders", "positive") == "negative"
    assert prompts.phrase_function("I read it with Mom", "comment") == "personal"
    assert prompts.phrase_function("I am excited", "personal") == "positive"
    assert prompts.phrase_function("My favorite is Chipotle", "positive") == "personal"
    assert prompts.response_schema("phrases") is prompts.PHRASES_SCHEMA


@pytest.fixture
def isolated_model(tmp_path, monkeypatch):
    """Point the built-in engine at a temp dir + tiny file:// 'model'."""
    fake_model = tmp_path / "src" / "tiny.gguf"
    fake_model.parent.mkdir()
    fake_model.write_bytes(b"GGUF-fake-bytes" * 100)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    monkeypatch.setattr(localai, "MODEL_URL", fake_model.as_uri())
    monkeypatch.setattr(localai, "MODEL_FILE", "tiny.gguf")
    localai._download.update(status="idle", done=0, total=0, error=None)
    return fake_model


def test_download_flow(isolated_model):
    assert not localai.is_downloaded()
    localai.start_download()
    for _ in range(100):
        if localai.download_state()["status"] in ("ready", "error"):
            break
        time.sleep(0.05)
    state = localai.download_state()
    assert state["status"] == "ready", state
    assert localai.is_downloaded()
    with open(localai.model_path(), "rb") as handle:
        assert handle.read() == isolated_model.read_bytes()
    # A second start is a no-op, not a re-download.
    assert localai.start_download()["status"] == "ready"


def test_generate_requires_download(isolated_model, monkeypatch):
    monkeypatch.setattr(localai, "engine_available", lambda: True)
    words, error = localai.generate_words("Snacks")
    assert words == [] and "hasn't been downloaded" in error


def test_ai_endpoints(monkeypatch, tmp_path):
    from tdsnap.web.server import API_TOKEN, app

    monkeypatch.setattr(
        ollama, "status",
        lambda host=None: {"reachable": False, "models": [], "message": "off"},
    )
    monkeypatch.setattr(localai, "engine_available", lambda: False)
    monkeypatch.setattr(localai, "is_downloaded", lambda: False)
    # Never touch the network from a unit test; grounding is exercised separately.
    monkeypatch.setattr(grounding, "reference_text", lambda category: "REF:" + category)

    client = app.test_client()
    headers = {"X-TDSnap-Token": API_TOKEN}

    status = client.get("/api/ai/status").get_json()
    assert status["ollama"]["reachable"] is False
    assert status["local"]["engine_available"] is False
    assert status["local"]["model"]["license"] == "Apache-2.0"

    # No engine ready → clear, actionable error.
    response = client.post("/api/ai/words", json={"category": "Snacks"},
                           headers=headers)
    assert response.status_code == 400
    assert "No AI engine is ready" in response.get_json()["error"]

    # Download refused when the engine isn't installed.
    response = client.post("/api/ai/download", headers=headers)
    assert response.status_code == 400

    # With the engine "installed" and model "downloaded", words flow through.
    monkeypatch.setattr(localai, "engine_available", lambda: True)
    monkeypatch.setattr(localai, "is_downloaded", lambda: True)
    generated = {}

    def fake_generate(**kwargs):
        generated.update(kwargs)
        return ["Chips", "Apple"], None

    monkeypatch.setattr(localai, "generate_words", fake_generate)
    data = client.post("/api/ai/words", json={
        "category": "Snacks", "existing": ["Crackers", "Juice"],
    },
                       headers=headers).get_json()
    assert data == {"ok": True, "words": ["Chips", "Apple"], "engine": "local"}
    assert generated["existing"] == ["Crackers", "Juice"]
    # Grounding facts for the title are threaded into the backend call.
    assert generated["reference"] == "REF:Snacks"

    # A reachable Ollama takes precedence.
    monkeypatch.setattr(
        ollama, "status",
        lambda host=None: {"reachable": True, "models": ["m"], "message": "ok"},
    )
    monkeypatch.setattr(
        ollama, "generate_words", lambda **kw: (["Juice"], None)
    )
    data = client.post("/api/ai/words", json={"category": "Snacks"},
                       headers=headers).get_json()
    assert data["engine"] == "ollama" and data["words"] == ["Juice"]

    # ... but an Ollama server with no models falls back to the built-in
    # engine instead of failing with "model not found".
    monkeypatch.setattr(
        ollama, "status",
        lambda host=None: {"reachable": True, "models": [], "message": "empty"},
    )
    data = client.post("/api/ai/words", json={"category": "Snacks"},
                       headers=headers).get_json()
    assert data["engine"] == "local" and data["words"] == ["Chips", "Apple"]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_grounding_builds_reference(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        if params.get("list") == "search":
            return _FakeResponse({"query": {"search": [
                {"title": "Roblox"},
                {"title": "List of Roblox characters"},
            ]}})
        # extracts request — must target the "List of" article (preferred).
        assert params["titles"] == "List of Roblox characters"
        return _FakeResponse({"query": {"pages": [
            {"extract": "Builderman, Noob, and Guest are notable <b>avatars</b>."}
        ]}})

    monkeypatch.setattr(grounding.requests, "get", fake_get)
    text = grounding.reference_text("Roblox characters")
    assert "List of Roblox characters" in text
    assert "Builderman" in text
    assert "<b>" not in text  # HTML stripped
    assert "Related articles: Roblox" in text
    assert len(calls) == 2


def test_grounding_is_best_effort(monkeypatch):
    # Network failure → no grounding, no raise.
    def boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(grounding.requests, "get", boom)
    assert grounding.reference_text("Anything") == ""
    # Too-short titles are skipped without a request.
    assert grounding.reference_text("x") == ""
    # An opt-out env var disables lookups entirely.
    monkeypatch.setenv("TDSNAP_WEB_GROUNDING", "0")
    assert not grounding.enabled()
    assert grounding.reference_text("Roblox characters") == ""


def test_download_refused_when_disk_is_full(isolated_model, monkeypatch):
    monkeypatch.setattr(localai, "_free_disk_bytes", lambda: 100)
    state = localai.start_download()
    assert state["status"] == "error"
    assert "disk space" in state["error"]
    # Clear the sticky error so later tests see a clean slate.
    localai._download.update(status="idle", done=0, total=0, error=None)
