"""AI-suggestion plumbing: prompts, model download, engine selection.

No real model or network is used — the download test uses a file:// URL and
the endpoint tests monkeypatch the backends.
"""

import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

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
    # phrase_function's own behavior is pinned in test_prompts.py against the
    # golden cases shared with tests/js/phrases.test.js.
    assert prompts.response_schema("phrases") is prompts.PHRASES_SCHEMA


def _choice(path, key="small", **overrides):
    """A registry entry pointing at a tiny local file:// 'model'."""
    fields = {
        "key": key,
        "name": f"Tiny {key}",
        "license": "test",
        "file": f"tiny-{key}.gguf",
        "repo": "",
        "revision": "",
        "url_override": path.as_uri(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
        "min_memory_bytes": 0,
        "size_hint": "tiny",
        "summary": "a test model",
    }
    fields.update(overrides)
    return localai.ModelChoice(**fields)


def _install(monkeypatch, *choices):
    monkeypatch.setattr(localai, "REGISTRY", tuple(choices))
    monkeypatch.setattr(localai, "DEFAULT_KEY", choices[0].key)
    localai._validations.clear()
    localai._download.update(
        status="idle", done=0, total=0, error=None, model=choices[0].key
    )


def _settle():
    for _ in range(100):
        if localai.download_state()["status"] in ("ready", "error"):
            break
        time.sleep(0.05)
    return localai.download_state()


@pytest.fixture
def isolated_model(tmp_path, monkeypatch):
    """Point the built-in engine at a temp dir + tiny file:// 'model'."""
    fake_model = tmp_path / "src" / "tiny.gguf"
    fake_model.parent.mkdir()
    fake_model.write_bytes(b"GGUF-fake-bytes" * 100)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    _install(monkeypatch, _choice(fake_model))
    return fake_model


def test_download_flow(isolated_model):
    assert not localai.is_downloaded()
    localai.start_download()
    state = _settle()
    assert state["status"] == "ready", state
    assert localai.is_downloaded()
    with open(localai.model_path(), "rb") as handle:
        assert handle.read() == isolated_model.read_bytes()
    # A second start is a no-op, not a re-download.
    assert localai.start_download()["status"] == "ready"


def test_download_rejects_wrong_hash(isolated_model, monkeypatch):
    _install(monkeypatch, _choice(isolated_model, sha256="0" * 64))
    localai.start_download()
    assert _settle()["status"] == "error"
    assert "integrity" in localai.download_state()["error"].lower()
    assert not localai.is_downloaded()


def test_generate_requires_download(isolated_model, monkeypatch):
    monkeypatch.setattr(localai, "engine_available", lambda: True)
    words, error = localai.generate_words("Snacks")
    assert words == [] and "hasn't been downloaded" in error


# --- more than one model, chosen by measurement --------------------------


def test_only_fully_pinned_models_are_ever_offered():
    """An entry missing its size or SHA-256 cannot be downloaded at all.

    The registry is allowed to name a model before its checksum has been
    confirmed against the publisher, so the plumbing can be built and reviewed
    ahead of the pin. What it must never do is *offer* one — an unverifiable
    download is exactly what the size/SHA-256/GGUF discipline exists to stop.
    """
    assert localai.SMALL.pinned
    assert all(choice.pinned for choice in localai.choices())
    assert not localai.LARGE.pinned
    assert localai.LARGE not in localai.choices()
    # The default is the small model, and it stays that way: a clinic laptop
    # has to be able to run whatever this build picks on its own.
    assert localai.choices()[0] is localai.SMALL


def test_memory_gate_is_measured_not_assumed(monkeypatch, tmp_path):
    fake = tmp_path / "tiny.gguf"
    fake.write_bytes(b"GGUFxx" * 50)
    small = _choice(fake, "small")
    big = _choice(fake, "big", file="tiny-big.gguf", min_memory_bytes=16 * localai.GIB)
    _install(monkeypatch, small, big)

    # The default is always offered — refusing it would leave a user with no
    # built-in suggestions at all.
    monkeypatch.setattr(localai, "total_memory_bytes", lambda: 0)
    assert localai.supported(small)[0] is True
    # A machine whose memory cannot be read is never offered anything bigger.
    ok, reason = localai.supported(big)
    assert ok is False and "couldn't be measured" in reason

    monkeypatch.setattr(localai, "total_memory_bytes", lambda: 8 * localai.GIB)
    ok, reason = localai.supported(big)
    assert ok is False and "8 GB" in reason and "16 GB" in reason

    monkeypatch.setattr(localai, "total_memory_bytes", lambda: 32 * localai.GIB)
    assert localai.supported(big) == (True, "")


def test_a_model_the_machine_cannot_run_is_not_downloaded(monkeypatch, tmp_path):
    fake = tmp_path / "src.gguf"
    fake.write_bytes(b"GGUFyy" * 50)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    big = _choice(fake, "big", file="tiny-big.gguf", min_memory_bytes=64 * localai.GIB)
    _install(monkeypatch, _choice(fake), big)
    monkeypatch.setattr(localai, "total_memory_bytes", lambda: 8 * localai.GIB)
    state = localai.start_download("big")
    assert state["status"] == "error" and "64 GB" in state["error"]
    assert not localai.is_downloaded("big")


def test_each_model_keeps_its_own_file_and_verification(monkeypatch, tmp_path):
    """Downloading a second model never disturbs the one already working."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    first = tmp_path / "first.gguf"
    first.write_bytes(b"GGUF-first" * 40)
    second = tmp_path / "second.gguf"
    second.write_bytes(b"GGUF-second" * 60)
    _install(monkeypatch, _choice(first, "small"), _choice(second, "big",
                                                           file="tiny-big.gguf"))
    assert localai.model_path("small") != localai.model_path("big")

    localai.start_download("small")
    assert _settle()["status"] == "ready"
    assert localai.downloaded_keys() == ["small"]
    # With only the small one on disk, that is what a generation would use,
    # even when the bigger one is preferred — choosing a model must never
    # break suggestions that were working.
    assert localai.active_key("big") == "small"

    localai._download.update(status="idle", done=0, total=0, error=None)
    localai.start_download("big")
    assert _settle()["status"] == "ready"
    assert localai.downloaded_keys() == ["small", "big"]
    assert localai.active_key("big") == "big"
    assert localai.is_downloaded("small")


def test_status_describes_every_choice(monkeypatch, tmp_path):
    fake = tmp_path / "tiny.gguf"
    fake.write_bytes(b"GGUFzz" * 50)
    big = _choice(fake, "big", file="tiny-big.gguf", min_memory_bytes=16 * localai.GIB)
    _install(monkeypatch, _choice(fake), big)
    monkeypatch.setattr(localai, "total_memory_bytes", lambda: 4 * localai.GIB)
    monkeypatch.setattr(localai, "engine_available", lambda: False)
    report = localai.status()
    assert [c["key"] for c in report["choices"]] == ["small", "big"]
    assert report["choices"][0]["supported"] is True
    assert report["choices"][1]["supported"] is False
    assert report["memory_measured"] is True
    assert report["model"]["name"] == "Tiny small"


def test_environment_override_replaces_the_registry(monkeypatch):
    monkeypatch.setenv("TDSNAP_MODEL_URL", "https://example.invalid/m.gguf")
    monkeypatch.setenv("TDSNAP_MODEL_FILE", "m.gguf")
    override = localai._environment_override()
    assert override is not None
    assert override.key == "custom" and override.file == "m.gguf"
    # Named after the file: this reaches the support report and the eval
    # report, where "set by an environment variable" names no model at all.
    assert "m.gguf" in override.name
    # No hash was supplied, so the file is checked for GGUF magic and nothing
    # more — that is the operator's call to make, and it is never memory-gated.
    assert override.sha256 is None and override.min_memory_bytes == 0


@pytest.fixture
def ai_client(monkeypatch):
    """A test client with both engines stubbed and no network anywhere."""
    from tdsnap.web.server import API_TOKEN, app

    monkeypatch.setattr(
        ollama, "status",
        lambda host=None: {"reachable": False, "models": [], "message": "off"},
    )
    monkeypatch.setattr(localai, "engine_available", lambda: False)
    monkeypatch.setattr(localai, "is_downloaded", lambda key=None: False)
    monkeypatch.setattr(localai, "active_key", lambda preferred=None: preferred or "small")
    return app.test_client(), {"X-TDSnap-Token": API_TOKEN}


@pytest.fixture
def recording_grounding(monkeypatch):
    """Record every grounding lookup instead of reaching Wikipedia."""
    calls = []

    def fake_lookup(category, max_chars=1600, *, requested=False, title=None, exclude=()):
        calls.append({
            "category": category, "requested": requested,
            "title": title, "exclude": list(exclude),
        })
        if not requested:
            return {"used": False, "text": "", "title": "", "url": "",
                    "alternatives": []}
        chosen = title or f"About {category}"
        return {
            "used": True,
            "text": f"REF:{chosen}",
            "title": chosen,
            "url": grounding.article_url(chosen),
            "alternatives": ["Another article"],
        }

    monkeypatch.setattr(grounding, "lookup", fake_lookup)
    return calls


def test_ai_endpoints(ai_client, recording_grounding, monkeypatch):
    client, headers = ai_client

    status = client.get("/api/ai/status", headers=headers).get_json()
    assert status["ollama"]["reachable"] is False
    assert status["local"]["engine_available"] is False
    assert status["local"]["model"]["license"] == "Apache-2.0"
    # Every offered model is described, so the panel can explain its choices.
    assert status["local"]["choices"]
    assert all(
        {"key", "name", "size", "downloaded", "supported"} <= set(choice)
        for choice in status["local"]["choices"]
    )

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
    monkeypatch.setattr(localai, "is_downloaded", lambda key=None: True)
    generated = {}

    def fake_generate(**kwargs):
        generated.update(kwargs)
        return ["Chips", "Apple"], None

    monkeypatch.setattr(localai, "generate_words", fake_generate)
    data = client.post("/api/ai/words", json={
        "category": "Snacks", "existing": ["Crackers", "Juice"],
    },
                       headers=headers).get_json()
    assert data["ok"] is True
    assert data["words"] == ["Chips", "Apple"] and data["engine"] == "local"
    assert generated["existing"] == ["Crackers", "Juice"]
    # Grounding is private by default and runs only after explicit opt-in.
    assert generated["reference"] == ""
    assert data["grounding"]["used"] is False
    assert recording_grounding == [
        {"category": "Snacks", "requested": False, "title": None, "exclude": []}
    ]

    data = client.post("/api/ai/words", json={
        "category": "Snacks", "grounding": True,
    }, headers=headers).get_json()
    assert generated["reference"] == "REF:About Snacks"
    assert recording_grounding[-1]["requested"] is True

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


def test_steering_reaches_the_model(ai_client, recording_grounding, monkeypatch):
    """Rejected, kept, and style labels all reach the prompt as themselves."""
    client, headers = ai_client
    monkeypatch.setattr(localai, "engine_available", lambda: True)
    monkeypatch.setattr(localai, "is_downloaded", lambda key=None: True)
    generated = {}

    def fake_generate(**kwargs):
        generated.update(kwargs)
        return ["Pretzel"], None

    monkeypatch.setattr(localai, "generate_words", fake_generate)
    data = client.post("/api/ai/words", json={
        "category": "Snacks",
        "existing": ["Crackers"],
        "avoid": ["Kale", "  "],
        "like": ["Chips"],
        "style": ["I want more", "All done"],
        "model_key": "small",
    }, headers=headers).get_json()
    assert data["ok"] is True
    assert generated["avoid"] == ["Kale"]  # blank entries dropped
    assert generated["like"] == ["Chips"]
    assert generated["style"] == ["I want more", "All done"]
    assert generated["model_key"] == "small"

    prompt = prompts.build_prompt(
        "Snacks", 5, existing=["Crackers"], avoid=["Kale"], like=["Chips"],
        style=["I want more"],
    )
    assert "rejected these suggestions" in prompt and "Kale" in prompt
    assert "more of the same kind" in prompt and "Chips" in prompt
    assert "writing style only" in prompt and "I want more" in prompt


def test_nothing_the_user_composed_reaches_wikipedia(ai_client, recording_grounding,
                                                     monkeypatch):
    """The grounding request carries the page title and nothing else.

    Style samples are read out of the user's own page set and rejected
    suggestions are their judgement about their own vocabulary. Both are local
    by construction; this pins that the one outbound request in the whole app
    never carries either, whatever else the request asked for.
    """
    client, headers = ai_client
    monkeypatch.setattr(localai, "engine_available", lambda: True)
    monkeypatch.setattr(localai, "is_downloaded", lambda key=None: True)
    monkeypatch.setattr(localai, "generate_words", lambda **kw: (["Chips"], None))

    client.post("/api/ai/words", json={
        "category": "Snacks",
        "grounding": True,
        "existing": ["Crackers"],
        "avoid": ["Kale"],
        "like": ["Chips"],
        "style": ["I want more", "All done"],
    }, headers=headers)

    assert len(recording_grounding) == 1
    call = recording_grounding[0]
    assert call["category"] == "Snacks"
    sent = json.dumps(call)
    for private in ("Crackers", "Kale", "Chips", "I want more", "All done"):
        assert private not in sent


def test_grounding_source_is_named_and_can_be_rejected(ai_client, recording_grounding,
                                                       monkeypatch):
    client, headers = ai_client
    monkeypatch.setattr(localai, "engine_available", lambda: True)
    monkeypatch.setattr(localai, "is_downloaded", lambda key=None: True)
    monkeypatch.setattr(localai, "generate_words", lambda **kw: (["Chips"], None))

    data = client.post("/api/ai/words", json={
        "category": "Mercury", "grounding": True,
    }, headers=headers).get_json()
    source = data["grounding"]
    assert source["used"] is True
    assert source["title"] == "About Mercury"
    assert source["url"].startswith("https://en.wikipedia.org/wiki/")
    assert source["alternatives"] == ["Another article"]
    # The text itself stays on the server: the browser is told which article
    # was used, not handed the article.
    assert "text" not in source

    # Rejecting it, and choosing another, both reach the lookup.
    client.post("/api/ai/words", json={
        "category": "Mercury", "grounding": True,
        "grounding_exclude": ["About Mercury"],
        "grounding_title": "Mercury (planet)",
    }, headers=headers)
    assert recording_grounding[-1]["title"] == "Mercury (planet)"
    assert recording_grounding[-1]["exclude"] == ["About Mercury"]


def test_a_failed_generation_still_names_its_source(ai_client, recording_grounding,
                                                    monkeypatch):
    client, headers = ai_client
    monkeypatch.setattr(localai, "engine_available", lambda: True)
    monkeypatch.setattr(localai, "is_downloaded", lambda key=None: True)
    monkeypatch.setattr(localai, "generate_words", lambda **kw: ([], "model broke"))
    response = client.post("/api/ai/words", json={
        "category": "Mercury", "grounding": True,
    }, headers=headers)
    assert response.status_code == 502
    assert response.get_json()["grounding"]["title"] == "About Mercury"


def test_steering_lists_are_bounded(ai_client, monkeypatch):
    client, headers = ai_client
    monkeypatch.setattr(localai, "engine_available", lambda: True)
    monkeypatch.setattr(localai, "is_downloaded", lambda key=None: True)
    monkeypatch.setattr(localai, "generate_words", lambda **kw: (["Chips"], None))
    for payload, expected in (
        ({"avoid": ["x"] * 61}, "avoid"),
        ({"like": ["x"] * 21}, "like"),
        ({"style": ["x"] * 41}, "style"),
        ({"avoid": "not a list"}, "avoid"),
        ({"style": ["x" * 121]}, "style"),
    ):
        response = client.post(
            "/api/ai/words", json={"category": "Snacks", **payload}, headers=headers
        )
        assert response.status_code == 400
        assert expected in response.get_json()["error"]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return json.dumps(self._payload).encode("utf-8")


def test_grounding_builds_reference(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        params = {
            key: values[0]
            for key, values in parse_qs(urlsplit(request.full_url).query).items()
        }
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

    monkeypatch.setattr(grounding, "urlopen", fake_urlopen)
    assert grounding.reference_text("Roblox characters") == ""
    assert calls == []

    text = grounding.reference_text("Roblox characters", requested=True)
    assert "List of Roblox characters" in text
    assert "Builderman" in text
    assert "<b>" not in text  # HTML stripped
    assert "Related articles: Roblox" in text
    assert len(calls) == 2


def test_grounding_is_best_effort(monkeypatch):
    # Network failure → no grounding, no raise.
    def boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(grounding, "urlopen", boom)
    assert grounding.reference_text("Anything", requested=True) == ""
    # Too-short titles are skipped without a request.
    assert grounding.reference_text("x", requested=True) == ""
    # An opt-out env var disables lookups entirely.
    monkeypatch.setenv("TDSNAP_WEB_GROUNDING", "0")
    assert not grounding.enabled()
    assert grounding.reference_text("Roblox characters", requested=True) == ""


def _wiki_stub(monkeypatch, extracts):
    """Answer Wikipedia's search with `extracts`' keys, in order."""
    titles = list(extracts)
    asked = []

    def fake_urlopen(request, timeout=None):
        params = {
            key: values[0]
            for key, values in parse_qs(urlsplit(request.full_url).query).items()
        }
        if params.get("list") == "search":
            return _FakeResponse(
                {"query": {"search": [{"title": title} for title in titles]}}
            )
        asked.append(params["titles"])
        return _FakeResponse(
            {"query": {"pages": [{"extract": extracts.get(params["titles"], "")}]}}
        )

    monkeypatch.setattr(grounding, "urlopen", fake_urlopen)
    return asked


def test_lookup_names_the_article_it_used(monkeypatch):
    asked = _wiki_stub(monkeypatch, {
        "Mercury (element)": "Mercury is a chemical element.",
        "Mercury (planet)": "Mercury is the smallest planet.",
    })
    source = grounding.lookup("Mercury", requested=True)
    assert source["used"] is True
    assert source["title"] == "Mercury (element)"
    assert source["url"] == "https://en.wikipedia.org/wiki/Mercury_%28element%29"
    assert source["alternatives"] == ["Mercury (planet)"]
    assert "chemical element" in source["text"]
    assert asked == ["Mercury (element)"]


def test_lookup_honours_a_rejection_and_a_choice(monkeypatch):
    extracts = {
        "Mercury (element)": "Mercury is a chemical element.",
        "Mercury (planet)": "Mercury is the smallest planet.",
    }
    _wiki_stub(monkeypatch, extracts)
    rejected = grounding.lookup(
        "Mercury", requested=True, exclude=["mercury (element)"]
    )
    assert rejected["title"] == "Mercury (planet)"
    assert "Mercury (element)" not in rejected["alternatives"]

    _wiki_stub(monkeypatch, extracts)
    chosen = grounding.lookup("Mercury", requested=True, title="Mercury (planet)")
    assert chosen["title"] == "Mercury (planet)"


def test_lookup_moves_past_an_article_with_no_text(monkeypatch):
    """A first result that has no extract used to ground nothing at all."""
    asked = _wiki_stub(monkeypatch, {
        "Mercury": "",
        "Mercury (planet)": "Mercury is the smallest planet.",
    })
    source = grounding.lookup("Mercury", requested=True)
    assert source["title"] == "Mercury (planet)"
    assert asked == ["Mercury", "Mercury (planet)"]


def test_lookup_is_empty_when_nothing_was_asked_for(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no lookup should happen")

    monkeypatch.setattr(grounding, "urlopen", boom)
    assert grounding.lookup("Mercury", requested=False) == {
        "used": False, "text": "", "title": "", "url": "", "alternatives": [],
    }


def test_ollama_host_is_loopback_only():
    assert ollama.normalize_host("http://localhost:11434/") == "http://localhost:11434"
    assert ollama.normalize_host("https://[::1]:11434") == "https://[::1]:11434"
    for host in (
        "http://169.254.169.254",
        "http://example.com",
        "http://localhost:11434/api/tags",
        "http://user:pass@localhost:11434",
    ):
        with pytest.raises(ValueError):
            ollama.normalize_host(host)


def test_download_refused_when_disk_is_full(isolated_model, monkeypatch):
    monkeypatch.setattr(localai, "_free_disk_bytes", lambda: 100)
    state = localai.start_download()
    assert state["status"] == "error"
    assert "disk space" in state["error"]
    # Clear the sticky error so later tests see a clean slate.
    localai._download.update(status="idle", done=0, total=0, error=None)


# --- the smoke test's transport/defect classifier -------------------------
#
# It decides whether a failed model download skips the build or fails it, so
# getting it wrong either hides a real defect or makes CI flaky.

@pytest.mark.parametrize("error", [
    "HTTP Error 429: Too Many Requests",
    "HTTP Error 503: Service Unavailable",
    "<urlopen error [Errno -3] Temporary failure in name resolution>",
    "The read operation timed out",
    "[Errno 104] Connection reset by peer",
    "Remote end closed connection without response",
])
def test_transport_failures_skip_the_smoke_test(error):
    from tests.conftest import TRANSPORT_FAILURE

    assert TRANSPORT_FAILURE.search(error), f"{error!r} should skip, not fail"


@pytest.mark.parametrize("error", [
    "The model download failed its integrity check.",
    "The model download has the wrong size.",
    "The download is not a GGUF model.",
    "HTTP Error 404: Not Found",
    "Not enough disk space for the model.",
])
def test_real_defects_still_fail_the_smoke_test(error):
    from tests.conftest import TRANSPORT_FAILURE

    assert not TRANSPORT_FAILURE.search(error), f"{error!r} must fail, not skip"


# --- the pin checker ------------------------------------------------------
#
# scripts/verify_model_pins.py is what makes "pin and verify" more than a
# number somebody typed once. These cover its comparison and its exit codes
# without touching the network.

def _pin_script(monkeypatch, tree, head="abc123def456789"):
    import scripts.verify_model_pins as verify

    def fake_get(url):
        if "/tree/" in url:
            return tree
        return {"sha": head}

    monkeypatch.setattr(verify, "_get", fake_get)
    return verify


def test_pin_checker_accepts_a_pin_the_publisher_agrees_with(monkeypatch, capsys):
    verify = _pin_script(monkeypatch, [
        {"path": localai.SMALL.file,
         "lfs": {"oid": localai.SMALL.sha256, "size": localai.SMALL.size}},
    ])
    assert verify.check(localai.SMALL, resolve=False) == "ok"
    assert "matches" in capsys.readouterr().out


def test_pin_checker_refuses_a_pin_the_publisher_disagrees_with(monkeypatch, capsys):
    verify = _pin_script(monkeypatch, [
        {"path": localai.SMALL.file, "lfs": {"oid": "0" * 64, "size": 123}},
    ])
    assert verify.check(localai.SMALL, resolve=False) == "mismatch"
    output = capsys.readouterr().out
    assert "sha256" in output and "size" in output


def test_pin_checker_reports_a_file_that_is_not_there(monkeypatch, capsys):
    verify = _pin_script(monkeypatch, [{"path": "something-else.gguf"}])
    assert verify.check(localai.SMALL, resolve=False) == "mismatch"
    assert "is not in" in capsys.readouterr().out


def test_pin_checker_prints_the_missing_pin_to_paste(monkeypatch, capsys):
    verify = _pin_script(monkeypatch, [
        {"path": localai.LARGE.file, "lfs": {"oid": "b" * 64, "size": 4_683_073_184}},
    ])
    # Without --resolve an unpinned entry is reported, not silently skipped.
    assert verify.check(localai.LARGE, resolve=False) == "unresolved"
    assert "no revision pinned" in capsys.readouterr().out

    assert verify.check(localai.LARGE, resolve=True) == "unresolved"
    printed = capsys.readouterr().out
    assert 'revision="abc123def456789"' in printed
    assert f'sha256="{"b" * 64}"' in printed
    assert "size=4_683_073_184" in printed


def test_pin_checker_separates_unreachable_from_wrong(monkeypatch):
    import scripts.verify_model_pins as verify

    def offline(url):
        raise OSError("offline")

    monkeypatch.setattr(verify, "_get", offline)
    # "I could not check" must never read as "I checked and it was fine".
    assert verify.check(localai.SMALL, resolve=False) == "unreachable"
    assert verify.main([]) == 2
