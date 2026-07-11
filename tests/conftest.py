"""Shared fixtures: a minimal but structurally real page set.

``seeded_pageset`` builds a database from the committed schema snapshot (the
CREATE statements of a genuine TD Snap 4.13 export) and populates the smallest
set of rows that make it a valid editing target: page-set properties, a sync
ledger, one vocabulary page with a layout, one real speaking chain and one
real navigation chain. Unit tests run against this without needing the
proprietary fixture file.
"""

import pathlib
import sqlite3
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
