"""Real-model smoke test for the built-in AI engine.

Downloads a small GGUF (Qwen2.5 0.5B, ~400 MB) and runs actual generations
through llama.cpp — proving the exact code path the packaged app uses. Needs
network + llama-cpp-python, so it only runs when explicitly requested:

    TDSNAP_AI_SMOKE=1 python -m pytest tests/test_ai_smoke.py

CI runs it in the release workflow and the soft-fail integration job.
"""

import importlib
import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("TDSNAP_AI_SMOKE") != "1",
    reason="set TDSNAP_AI_SMOKE=1 to run the real-model smoke test",
)


@pytest.fixture(scope="module")
def smoke_localai(tmp_path_factory):
    pytest.importorskip("llama_cpp")
    tmp = tmp_path_factory.mktemp("model-home")
    os.environ["XDG_DATA_HOME"] = str(tmp)
    os.environ["LOCALAPPDATA"] = str(tmp)
    os.environ["TDSNAP_MODEL_URL"] = (
        "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/"
        "qwen2.5-0.5b-instruct-q4_k_m.gguf"
    )
    os.environ["TDSNAP_MODEL_FILE"] = "qwen2.5-0.5b-instruct-q4_k_m.gguf"

    from tdsnap.web import localai

    importlib.reload(localai)  # pick up the env overrides
    localai.start_download()
    deadline = time.time() + 600
    while time.time() < deadline:
        state = localai.download_state()
        if state["status"] in ("ready", "error"):
            break
        time.sleep(2)
    assert localai.download_state()["status"] == "ready", localai.download_state()
    return localai


def test_generate_words_with_real_model(smoke_localai):
    words, error = smoke_localai.generate_words("Snacks", count=6)
    assert error is None
    assert 1 <= len(words) <= 6
    assert all(isinstance(word, str) and word for word in words)


def test_generate_phrases_with_real_model(smoke_localai):
    phrases, error = smoke_localai.generate_words(
        "Swimming", count=4, kind="phrases", function="question"
    )
    assert error is None
    assert 1 <= len(phrases) <= 4
