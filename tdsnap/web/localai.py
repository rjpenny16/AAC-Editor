"""Built-in AI backend: llama.cpp running a small open-source model.

Nothing here is required for the editor to work — it powers the optional
word/phrase suggestions without asking the user to install anything. The
model file is not shipped in the download (it's ~1 GB); the app offers a
one-time download on first use, stores it in the per-user data directory,
and runs it fully offline afterwards.

Default model: Qwen2.5-1.5B-Instruct (Apache-2.0), quantized to Q4_K_M GGUF.
Override with the TDSNAP_MODEL_URL / TDSNAP_MODEL_FILE environment variables
(useful for smaller models on weak machines, or for tests).
"""

import os
import shutil
import threading
import urllib.request
from typing import List, Optional, Tuple

from . import prompts

MODEL_NAME = "Qwen2.5 1.5B Instruct"
MODEL_LICENSE = "Apache-2.0"
MODEL_URL = os.environ.get(
    "TDSNAP_MODEL_URL",
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-1.5b-instruct-q4_k_m.gguf",
)
MODEL_FILE = os.environ.get("TDSNAP_MODEL_FILE", "qwen2.5-1.5b-instruct-q4_k_m.gguf")
MODEL_SIZE_HINT = "about 1 GB"

_download = {"status": "idle", "done": 0, "total": 0, "error": None}
_download_lock = threading.Lock()
_llm = None
_llm_lock = threading.Lock()


def _models_dir() -> str:
    """Per-user data dir: %LOCALAPPDATA% on Windows, XDG data home elsewhere."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get(
            "XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share")
        )
    path = os.path.join(base, "tdsnap-editor", "models")
    os.makedirs(path, exist_ok=True)
    return path


def model_path() -> str:
    return os.path.join(_models_dir(), MODEL_FILE)


def engine_available() -> bool:
    """True when llama-cpp-python is importable (bundled in the packaged app)."""
    try:
        import llama_cpp  # noqa: F401

        return True
    except Exception:
        return False


def is_downloaded() -> bool:
    return os.path.exists(model_path())


def download_state() -> dict:
    with _download_lock:
        return dict(_download)


# The Q4_K_M file is ~1 GB; require headroom so the download can't fill the
# disk and fail (or break the user's machine) at 99%.
REQUIRED_FREE_BYTES = 2 * 1024**3


def _free_disk_bytes() -> int:
    try:
        return shutil.disk_usage(_models_dir()).free
    except OSError:
        return REQUIRED_FREE_BYTES  # can't tell; let the download try


def start_download() -> dict:
    """Kick off the one-time model download in a background thread."""
    with _download_lock:
        if _download["status"] == "downloading" or is_downloaded():
            return dict(_download)
        free = _free_disk_bytes()
        if free < REQUIRED_FREE_BYTES:
            _download.update(
                status="error", done=0, total=0,
                error=f"Not enough free disk space: the model needs about "
                      f"2 GB free, but only {free / 1e9:.1f} GB is available. "
                      "Free some space and try again.",
            )
            return dict(_download)
        _download.update(status="downloading", done=0, total=0, error=None)

    def work():
        part = model_path() + ".part"
        try:
            request = urllib.request.Request(
                MODEL_URL, headers={"User-Agent": "tdsnap-editor"}
            )
            with urllib.request.urlopen(request) as response:
                total = int(response.headers.get("Content-Length") or 0)
                with _download_lock:
                    _download["total"] = total
                with open(part, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 512)
                        if not chunk:
                            break
                        handle.write(chunk)
                        with _download_lock:
                            _download["done"] += len(chunk)
            os.replace(part, model_path())
            with _download_lock:
                _download["status"] = "ready"
        except Exception as exc:  # network errors surface in the UI
            try:
                os.remove(part)
            except OSError:
                pass
            with _download_lock:
                _download.update(status="error", error=str(exc))

    threading.Thread(target=work, daemon=True).start()
    return download_state()


def _load_llm():
    global _llm
    with _llm_lock:
        if _llm is None:
            from llama_cpp import Llama

            _llm = Llama(
                model_path=model_path(),
                n_ctx=2048,
                n_threads=max(2, (os.cpu_count() or 4) - 1),
                verbose=False,
            )
        return _llm


def generate_words(
    category: str,
    count: int = 10,
    kind: str = "words",
    function: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """Return ``(words, error)`` from the built-in model."""
    if not engine_available():
        return [], "The built-in AI engine isn't available in this install."
    if not is_downloaded():
        return [], "The AI model hasn't been downloaded yet."
    count = max(1, min(int(count), 60))
    prompt = prompts.build_prompt(category, count, kind, function)
    try:
        llm = _load_llm()
        with _llm_lock:
            result = llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={
                    "type": "json_object",
                    "schema": prompts.WORDS_SCHEMA,
                },
                max_tokens=800,
                temperature=0.7,
            )
        content = result["choices"][0]["message"]["content"]
    except Exception as exc:
        return [], f"The built-in model failed: {exc}"
    words = prompts.parse_items(content or "", count)
    if words is None:
        return [], "The built-in model returned something that wasn't valid JSON."
    return words, None
