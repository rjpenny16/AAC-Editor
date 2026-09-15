"""Shared fixtures: a minimal but structurally real page set.

``seeded_pageset`` builds a database from the committed schema snapshot (the
CREATE statements of a genuine TD Snap 4.13 export) and populates the smallest
set of rows that make it a valid editing target: page-set properties, a sync
ledger, one vocabulary page with a layout, one real speaking chain and one
real navigation chain. Unit tests run against this without needing the
proprietary fixture file.
"""

import contextlib
import importlib
import os
import pathlib
import re
import sqlite3
import time
import uuid

import pytest

from tdsnap.pageset import Pageset

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SNAPSHOT = FIXTURES / "schema_snapshot.sql"
EXAMPLE = FIXTURES / "example.sps"

HOME_UUID = "11111111-1111-4111-8111-111111111111"
TICKS_2025 = 638_700_000_000_000_000


def build_seeded_db(path: str) -> None:
    """Create a minimal valid page set at *path*."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SNAPSHOT.read_text(encoding="utf-8"))

        conn.execute(
            "INSERT INTO PageSetProperties (ContentIdentifier, ContentVersion, "
            "SchemaVersion, UniqueId, Language, Timestamp, SyncHash, "
            "DefaultHomePageUniqueId, GridDimension, FriendlyName) "
            "VALUES ('TEST', '1.0', '4.13', ?, 'en_US', ?, 42, ?, '4,3', 'Test Set')",
            (str(uuid.uuid4()), TICKS_2025, HOME_UUID),
        )
        conn.execute(
            "INSERT INTO Synchronization (SyncServerIdentifier, PageSetTimestamp, "
            "PageSetSyncHash) VALUES (NULL, ?, 7)",
            (TICKS_2025,),
        )

        # Home page: the template page, nav-button host, and speak-chain host.
        conn.execute(
            "INSERT INTO Page (UniqueId, Title, PageType, Timestamp, SyncHash) "
            "VALUES (?, 'Home Page', 1, ?, 1001)",
            (HOME_UUID, TICKS_2025),
        )
        home_id = conn.execute(
            "SELECT Id FROM Page WHERE UniqueId = ?", (HOME_UUID,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO SyncData (UniqueId, Type, Timestamp, SyncHash, Deleted, "
            "Description) VALUES (?, 1, ?, 1001, 0, 'Home Page')",
            (HOME_UUID, TICKS_2025),
        )
        layout_id = conn.execute(
            "INSERT INTO PageLayout (PageLayoutSetting, PageId) VALUES ('4,3,True,0', ?)",
            (home_id,),
        ).lastrowid

        # A second page for navigation to target.
        other_uuid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO Page (UniqueId, Title, PageType, Timestamp, SyncHash) "
            "VALUES (?, 'Food', 1, ?, 1002)",
            (other_uuid, TICKS_2025),
        )
        conn.execute(
            "INSERT INTO SyncData (UniqueId, Type, Timestamp, SyncHash, Deleted, "
            "Description) VALUES (?, 1, ?, 1002, 0, 'Food')",
            (other_uuid, TICKS_2025),
        )

        def add_cell(page_id, layout, slot, label, flags, commands, link_uuid=None):
            ref_id = conn.execute(
                "INSERT INTO ElementReference (ElementType, ForegroundColor, "
                "BackgroundColor, AudioCueRecordingId, PageId) "
                "VALUES (0, -132102, -16777216, 0, ?)",
                (page_id,),
            ).lastrowid
            button_id = conn.execute(
                "INSERT INTO Button (Label, LabelOwnership, Message, ImageOwnership, "
                "BorderThickness, CommandFlags, ContentType, UniqueId, "
                "ActiveContentType, LibrarySymbolId, PageSetImageId, "
                "MessageRecordingId, ElementReferenceId, SymbolColorDataId) "
                "VALUES (?, 3, NULL, 3, 0.0, ?, 6, ?, 0, 0, 0, 0, ?, 0)",
                (label, flags, str(uuid.uuid4()), ref_id),
            ).lastrowid
            conn.execute(
                "INSERT INTO CommandSequence (SerializedCommands, ButtonId) "
                "VALUES (?, ?)",
                (commands, button_id),
            )
            conn.execute(
                "INSERT INTO ElementPlacement (GridPosition, GridSpan, Visible, "
                "ElementReferenceId, PageLayoutId) VALUES (?, '1,1', 1, ?, ?)",
                (f"{slot[0]},{slot[1]}", ref_id, layout),
            )
            if link_uuid:
                conn.execute(
                    "INSERT INTO ButtonPageLink (ButtonId, PageUniqueId) "
                    "VALUES (?, ?)",
                    (button_id, link_uuid),
                )
            return button_id

        add_cell(
            home_id, layout_id, (0, 0), "hello", 8,
            '{"$type":"1","$values":[{"$type":"3","MessageAction":0}]}',
        )
        add_cell(
            home_id, layout_id, (1, 0), "Food", 9,
            '{"$type":"1","$values":[{"$type":"2","LinkedPageId":"%s","IsVisit":false}]}'
            % other_uuid,
            link_uuid=other_uuid,
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def seeded_source(tmp_path):
    """Path to a fresh minimal page set file."""
    path = tmp_path / "test.sps"
    build_seeded_db(str(path))
    return str(path)


@pytest.fixture
def seeded_pageset(seeded_source, tmp_path):
    """An open Pageset working copy of the minimal page set."""
    ps = Pageset(seeded_source, working_copy=str(tmp_path / "test.editing.sps"))
    yield ps
    ps.close()


def require_example() -> pathlib.Path:
    """Skip the calling test when the real fixture hasn't been downloaded."""
    if not EXAMPLE.exists():
        pytest.skip(
            "Real page-set fixture missing; run scripts/fetch_fixture.py"
        )
    return EXAMPLE


# --- the real built-in model -----------------------------------------------
#
# Downloads a small GGUF (Qwen2.5 0.5B, ~400 MB) and runs actual generations
# through llama.cpp, proving the exact code path the packaged app uses. Both
# opt-in real-model suites — the smoke test and the eval set — share this one
# fixture so CI fetches the model once rather than once per file.

SMOKE_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
SMOKE_MODEL_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"

# Fetching ~400 MB from a third-party CDN fails for reasons that say nothing
# about this code: rate limits, 5xx, DNS, a dropped connection. Those skip.
# Anything else — above all a failed integrity check, a wrong size, or a file
# that is not GGUF — is a real defect in the download path and must fail.
TRANSPORT_FAILURE = re.compile(
    r"HTTP Error (?:429|5\d\d)"
    r"|timed out|timeout"
    r"|name resolution|nodename nor servname|getaddrinfo"
    r"|[Cc]onnection (?:reset|refused|aborted)"
    r"|Remote end closed"
    r"|URLError",
)


@pytest.fixture(scope="session")
def smoke_localai(tmp_path_factory):
    """The built-in engine, pointed at a small real model in a temp home.

    Restores the environment and reloads the module afterwards: the override
    replaces the whole model registry, and leaving it in place would change
    what the ordinary unit tests see.
    """
    pytest.importorskip("llama_cpp")
    tmp = tmp_path_factory.mktemp("model-home")
    previous = {
        name: os.environ.get(name)
        for name in ("XDG_DATA_HOME", "LOCALAPPDATA",
                     "TDSNAP_MODEL_URL", "TDSNAP_MODEL_FILE")
    }
    os.environ["XDG_DATA_HOME"] = str(tmp)
    os.environ["LOCALAPPDATA"] = str(tmp)
    os.environ["TDSNAP_MODEL_URL"] = SMOKE_MODEL_URL
    os.environ["TDSNAP_MODEL_FILE"] = SMOKE_MODEL_FILE

    from tdsnap.web import localai

    importlib.reload(localai)  # pick up the env overrides
    try:
        localai.start_download()
        deadline = time.time() + 600
        while time.time() < deadline:
            if localai.download_state()["status"] in ("ready", "error"):
                break
            time.sleep(2)
        final = localai.download_state()
        if final["status"] != "ready":
            error = str(final.get("error") or "")
            if TRANSPORT_FAILURE.search(error):
                pytest.skip(f"could not fetch the model from the CDN: {error}")
            pytest.fail(f"model download failed: {final}")
        yield localai
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        with contextlib.suppress(Exception):
            importlib.reload(localai)
