"""Built-in AI backend: llama.cpp running a small open-source model.

Nothing here is required for the editor to work — it powers the optional
word/phrase suggestions without asking the user to install anything. No model
file is shipped in the download (the smallest is ~1 GB); the app offers a
one-time download on first use, stores it in the per-user data directory, and
runs it fully offline afterwards.

Default model: Qwen2.5-1.5B-Instruct (Apache-2.0), quantized to Q4_K_M GGUF.
It stays the default forever: a clinic laptop has to be able to run this, and
the download size matters to families on metered connections.

**More than one model, chosen by measurement.** A machine with the memory to
spare can run something better at niche topics, so the registry below holds
several pinned choices and ``supported`` gates each one on *measured* installed
memory — never on a guess, and never on an assumption when the measurement
fails: a machine whose RAM cannot be read is offered the default and nothing
larger.

**Pin and verify, per choice.** Every registry entry carries an immutable URL,
an exact byte size, and a SHA-256, and every download is checked against all
three plus the GGUF magic before it is moved into place. An entry missing any
of those is not a choice the app will offer — see ``pinned`` and
``scripts/verify_model_pins.py``, which confirms a pin against the publisher.

Override with the TDSNAP_MODEL_URL / TDSNAP_MODEL_FILE environment variables
(useful for smaller models on weak machines, or for tests); an override
replaces the registry with the single model it names.
"""

import contextlib
import hashlib
import os
import shutil
import threading
import urllib.request
from collections.abc import Sequence
from typing import NamedTuple, Optional

from . import prompts

GIB = 1024**3


class ModelChoice(NamedTuple):
    """One downloadable model, pinned hard enough to verify what arrives.

    ``repo`` and ``revision`` are the publisher and the immutable commit the
    file is taken from; ``url`` is derived from them so a pin cannot name one
    revision and fetch another. ``url_override`` exists for the environment
    override and for tests, which point at a local file.
    """

    key: str
    name: str
    license: str
    file: str
    repo: str
    revision: str
    sha256: Optional[str]
    size: Optional[int]
    min_memory_bytes: int
    size_hint: str
    summary: str
    url_override: str = ""

    @property
    def url(self) -> str:
        if self.url_override:
            return self.url_override
        if not (self.repo and self.revision and self.file):
            return ""
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.file}"

    @property
    def pinned(self) -> bool:
        """True when this entry can be verified, and so is safe to offer."""
        return bool(self.url and self.file and self.sha256 and self.size)

    @property
    def required_free_bytes(self) -> int:
        """Disk the download needs: the file, plus room not to fill the disk."""
        return max(2 * GIB, (self.size or 0) + GIB)


SMALL = ModelChoice(
    key="small",
    name="Qwen2.5 1.5B Instruct",
    license="Apache-2.0",
    file="qwen2.5-1.5b-instruct-q4_k_m.gguf",
    repo="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
    revision="91cad51170dc346986eccefdc2dd33a9da36ead9",
    sha256="6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
    size=1_117_320_736,
    min_memory_bytes=4 * GIB,
    size_hint="about 1 GB",
    summary="Runs on a clinic laptop. The right choice on a small machine.",
)

# Declared, deliberately not yet offered. Everything around it is built and
# tested — the memory gate, the per-choice download, verification and storage,
# and the picker — but the entry is missing its exact size and SHA-256, and an
# unpinned entry is one this app will not download. `pinned` is False, so it
# does not reach the UI at all: a user sees today's single built-in model, and
# the choice appears the moment the pin is filled in, with no other change.
# Run `python scripts/verify_model_pins.py --resolve` on a machine that can
# reach the publisher to print the values to paste here.
LARGE = ModelChoice(
    key="large",
    name="Qwen2.5 7B Instruct",
    license="Apache-2.0",
    file="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    repo="bartowski/Qwen2.5-7B-Instruct-GGUF",
    revision="",
    sha256=None,
    size=None,
    min_memory_bytes=16 * GIB,
    size_hint="about 4.7 GB",
    summary="Better on niche topics. Wants a desktop-class machine.",
)

CHOICES = (SMALL, LARGE)


def _environment_override() -> Optional[ModelChoice]:
    """A single model named by the environment, replacing the registry.

    Whoever sets these has said exactly which file to fetch, so it is offered
    with whatever verification they supplied — the GGUF magic always, the size
    and hash when given — and never gated on memory.
    """
    url = os.environ.get("TDSNAP_MODEL_URL", "").strip()
    file = os.environ.get("TDSNAP_MODEL_FILE", "").strip()
    if not url and not file:
        return None
    size = os.environ.get("TDSNAP_MODEL_SIZE", "").strip()
    chosen_file = file or SMALL.file
    return ModelChoice(
        key="custom",
        # Named after the file, not after the variable that set it: this name
        # reaches the support report and the eval report, where "the model set
        # by an environment variable" says nothing about which model ran.
        name=f"Custom model ({chosen_file})",
        license="as supplied",
        file=chosen_file,
        repo="",
        revision="",
        url_override=url or SMALL.url,
        sha256=os.environ.get("TDSNAP_MODEL_SHA256") or None,
        size=int(size) if size.isdigit() else None,
        min_memory_bytes=0,
        size_hint="as supplied",
        summary="Set by this installation's environment.",
    )


def _registry() -> tuple[ModelChoice, ...]:
    override = _environment_override()
    if override is not None:
        return (override,)
    return tuple(choice for choice in CHOICES if choice.pinned)


# Read once: the environment does not change under a running app, and the smoke
# test reloads this module after setting it.
REGISTRY = _registry()
DEFAULT_KEY = REGISTRY[0].key

# Headroom the disk check falls back on when free space cannot be read. Each
# choice states its own requirement; this is only the floor, so a download can
# never fill the disk and fail (or break the user's machine) at 99%.
REQUIRED_FREE_BYTES = REGISTRY[0].required_free_bytes

_download = {"status": "idle", "done": 0, "total": 0, "error": None, "model": DEFAULT_KEY}
_download_lock = threading.Lock()
_llm = None
_llm_path = None
_llm_lock = threading.Lock()
_validations: dict = {}
_validation_lock = threading.Lock()


def choices() -> tuple[ModelChoice, ...]:
    """Every model this build is willing to download, default first."""
    return REGISTRY


def choice_for(key: Optional[str] = None) -> ModelChoice:
    """The registry entry for *key*, falling back to the default."""
    for choice in REGISTRY:
        if choice.key == key:
            return choice
    return REGISTRY[0]


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


def model_path(key: Optional[str] = None) -> str:
    """Where *key*'s file lives. Each choice keeps its own file, so downloading
    a second model never destroys the one that already worked."""
    return os.path.join(_models_dir(), choice_for(key).file)


def total_memory_bytes() -> int:
    """Installed physical memory, or 0 when it cannot be measured.

    0 is not "assume plenty": every caller treats an unmeasured machine as one
    that gets the default model and nothing larger.
    """
    if os.name == "nt":
        return _windows_memory_bytes()
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, ValueError, OSError):
        return 0


def _windows_memory_bytes() -> int:
    try:
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
    except Exception:
        return 0
    return 0


def supported(choice: ModelChoice, memory: Optional[int] = None) -> tuple[bool, str]:
    """``(ok, reason)`` for running *choice* on this machine.

    The default choice is always offered — refusing it would leave a user with
    no built-in suggestions at all, and it is the one sized for a weak machine.
    Anything larger has to clear a measured bar.
    """
    if choice.key == REGISTRY[0].key or choice.min_memory_bytes <= 0:
        return True, ""
    measured = total_memory_bytes() if memory is None else memory
    if measured <= 0:
        return False, (
            "This computer's memory couldn't be measured, so only the "
            "recommended model is offered."
        )
    if measured < choice.min_memory_bytes:
        return False, (
            f"This computer has about {measured / GIB:.0f} GB of memory; "
            f"{choice.name} needs about {choice.min_memory_bytes / GIB:.0f} GB."
        )
    return True, ""


def engine_available() -> bool:
    """True when llama-cpp-python is importable (bundled in the packaged app)."""
    try:
        import llama_cpp  # noqa: F401

        return True
    except Exception:
        return False


def _validation_error(key: Optional[str] = None) -> Optional[str]:
    """Return why a model is unsafe to load, caching the expensive hash check."""
    choice = choice_for(key)
    path = model_path(choice.key)
    try:
        stat = os.stat(path)
    except OSError:
        return "The AI model hasn't been downloaded yet."
    signature = (path, stat.st_size, stat.st_mtime_ns, choice.sha256, choice.size)
    with _validation_lock:
        cached = _validations.get(choice.key)
        if cached and cached[0] == signature:
            return cached[1]
    error = None
    if choice.size is not None and stat.st_size != choice.size:
        error = "The downloaded model has the wrong size."
    else:
        digest = hashlib.sha256() if choice.sha256 else None
        try:
            with open(path, "rb") as handle:
                magic = handle.read(4)
                if magic != b"GGUF":
                    error = "The downloaded file is not a GGUF model."
                elif digest:
                    digest.update(magic)
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
        except OSError as exc:
            error = f"The downloaded model could not be read: {exc}"
        if digest and error is None and digest.hexdigest().lower() != choice.sha256.lower():
            error = "The downloaded model failed its integrity check."
    with _validation_lock:
        _validations[choice.key] = (signature, error)
    return error


def is_downloaded(key: Optional[str] = None) -> bool:
    return _validation_error(key) is None


def downloaded_keys() -> list[str]:
    return [choice.key for choice in REGISTRY if is_downloaded(choice.key)]


def active_key(preferred: Optional[str] = None) -> str:
    """Which model a generation would actually use.

    A preference only counts when that model is on disk — otherwise picking the
    bigger one in Settings would break suggestions that were working, which is
    never what choosing a model is meant to do.
    """
    ready = downloaded_keys()
    if preferred and preferred in ready:
        return preferred
    if ready:
        return ready[0]
    return preferred if any(c.key == preferred for c in REGISTRY) else DEFAULT_KEY


def download_state() -> dict:
    with _download_lock:
        return dict(_download)


def _free_disk_bytes() -> int:
    try:
        return shutil.disk_usage(_models_dir()).free
    except OSError:
        return REQUIRED_FREE_BYTES  # can't tell; let the download try


def start_download(key: Optional[str] = None) -> dict:
    """Kick off the one-time model download in a background thread."""
    choice = choice_for(key)
    ok, reason = supported(choice)
    with _download_lock:
        if _download["status"] == "downloading" or is_downloaded(choice.key):
            return dict(_download)
        if not ok:
            _download.update(
                status="error", done=0, total=0, model=choice.key, error=reason
            )
            return dict(_download)
        free = _free_disk_bytes()
        if free < choice.required_free_bytes:
            _download.update(
                status="error", done=0, total=0, model=choice.key,
                error=f"Not enough free disk space: {choice.name} needs about "
                      f"{choice.required_free_bytes / 1e9:.0f} GB free, but only "
                      f"{free / 1e9:.1f} GB is available. "
                      "Free some space and try again.",
            )
            return dict(_download)
        _download.update(
            status="downloading", done=0, total=0, error=None, model=choice.key
        )

    def work():
        part = model_path(choice.key) + ".part"
        try:
            # pinned model URL; the download is size- and SHA-256-verified
            request = urllib.request.Request(  # noqa: S310
                choice.url, headers={"User-Agent": "tdsnap-editor"}
            )
            digest = hashlib.sha256()
            first_bytes = b""
            # pinned model URL; the download is size- and SHA-256-verified
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                total = int(response.headers.get("Content-Length") or 0)
                with _download_lock:
                    _download["total"] = total
                with open(part, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 512)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        if len(first_bytes) < 4:
                            first_bytes = (first_bytes + chunk)[:4]
                        with _download_lock:
                            _download["done"] += len(chunk)
            size = os.path.getsize(part)
            if first_bytes != b"GGUF":
                raise ValueError("The download is not a GGUF model.")
            if choice.size is not None and size != choice.size:
                raise ValueError("The model download has the wrong size.")
            if choice.sha256 and digest.hexdigest().lower() != choice.sha256.lower():
                raise ValueError("The model download failed its integrity check.")
            os.replace(part, model_path(choice.key))
            with _validation_lock:
                _validations.pop(choice.key, None)
            with _download_lock:
                _download["status"] = "ready"
        except Exception as exc:  # network errors surface in the UI
            with contextlib.suppress(OSError):
                os.remove(part)
            with _download_lock:
                _download.update(status="error", error=str(exc))

    threading.Thread(target=work, daemon=True).start()
    return download_state()


def status(preferred: Optional[str] = None) -> dict:
    """Everything the UI needs to describe the built-in engine, in one read."""
    memory = total_memory_bytes()
    selected = active_key(preferred)
    described = []
    for choice in REGISTRY:
        ok, reason = supported(choice, memory)
        described.append({
            "key": choice.key,
            "name": choice.name,
            "license": choice.license,
            "size": choice.size_hint,
            "summary": choice.summary,
            "downloaded": is_downloaded(choice.key),
            "supported": ok,
            "reason": reason,
        })
    active = choice_for(selected)
    return {
        "engine_available": engine_available(),
        "downloaded": is_downloaded(selected),
        "download": download_state(),
        "selected": selected,
        "memory_bytes": memory,
        "memory_measured": memory > 0,
        "choices": described,
        # The one the rest of the UI talks about, kept flat because most of the
        # panel only ever names a single model.
        "model": {
            "key": active.key,
            "name": active.name,
            "license": active.license,
            "size": active.size_hint,
        },
    }


def _load_llm(key: Optional[str] = None):
    global _llm, _llm_path
    path = model_path(key)
    with _llm_lock:
        if _llm is None or _llm_path != path:
            error = _validation_error(key)
            if error:
                raise RuntimeError(error)
            from llama_cpp import Llama

            _llm = Llama(
                model_path=path,
                n_ctx=2048,
                n_threads=max(2, (os.cpu_count() or 4) - 1),
                verbose=False,
            )
            _llm_path = path
        return _llm


def generate_words(
    category: str,
    count: int = 10,
    kind: str = "words",
    function: Optional[str] = None,
    existing: Optional[Sequence[str]] = None,
    reference: Optional[str] = None,
    avoid: Optional[Sequence[str]] = None,
    like: Optional[Sequence[str]] = None,
    style: Optional[Sequence[str]] = None,
    model_key: Optional[str] = None,
) -> tuple[list, Optional[str]]:
    """Return ``(words, error)`` from the built-in model."""
    if not engine_available():
        return [], "The built-in AI engine isn't available in this install."
    key = active_key(model_key)
    error = _validation_error(key)
    if error:
        return [], error
    count = max(1, min(int(count), 60))
    prompt = prompts.build_prompt(
        category, count, kind, function, existing, reference,
        avoid=avoid, like=like, style=style,
    )
    try:
        llm = _load_llm(key)
        with _llm_lock:
            result = llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={
                    "type": "json_object",
                    "schema": prompts.response_schema(kind),
                },
                max_tokens=800,
                temperature=0.7,
            )
        content = result["choices"][0]["message"]["content"]
    except Exception as exc:
        return [], f"The built-in model failed: {exc}"
    words = prompts.parse_items(content or "", count, kind)
    if words is None:
        return [], "The built-in model returned something that wasn't valid JSON."
    return words, None
