"""Open, list and save TD Snap page sets — always on a working copy.

The user's exported file is copied before any connection is opened, so the
original can never be corrupted. ``save_as`` writes the finished result to a
separate ``*.edited`` file for re-import into TD Snap.
"""

import os
import shutil
import sqlite3
from typing import List, Optional, Tuple

from . import schema
from .errors import PagesetError

SQLITE_MAGIC = b"SQLite format 3\x00"

# PageType values observed in a real export: 1 = vocabulary page (what users
# see and navigate), 3/4 = message-bar and other system pages.
PAGE_TYPE_VOCAB = 1


def is_sqlite_file(path: str) -> bool:
    """Return True if *path* begins with the SQLite file magic header."""
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def default_output_path(source: str) -> str:
    """Return the sibling ``<name>.edited<ext>`` path for *source*."""
    base, ext = os.path.splitext(source)
    return f"{base}.edited{ext}"


class Pageset:
    """An editable working copy of a TD Snap page set."""

    def __init__(
        self, path: str, working_copy: Optional[str] = None, cleanup: bool = False
    ):
        """Copy *path* to *working_copy* and open that copy for editing.

        ``cleanup=True`` removes the working copy on :meth:`close`, so a
        scratch file doesn't linger next to the user's page set after
        ``save_as`` has written the result.
        """
        if not is_sqlite_file(path):
            raise PagesetError(
                f"{os.path.basename(path)!r} is not a SQLite database. TD Snap "
                "page-set exports (.sps/.spb) are SQLite files; if this came "
                "from TD Snap, the export may be incomplete."
            )

        if working_copy is None:
            base, ext = os.path.splitext(path)
            working_copy = f"{base}.editing{ext}"

        shutil.copyfile(path, working_copy)
        self.source_path = path
        self.working_path = working_copy
        self._cleanup = cleanup
        self.conn = sqlite3.connect(working_copy)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA foreign_keys=ON")
            schema.require_tables(self.conn)
        except Exception:
            self.conn.close()
            raise

    # -- context manager -------------------------------------------------

    def __enter__(self) -> "Pageset":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()
        if self._cleanup:
            try:
                os.remove(self.working_path)
            except OSError:
                pass

    # -- reading ----------------------------------------------------------

    @property
    def schema_version(self) -> str:
        return schema.schema_version(self.conn)

    def list_pages(self) -> List[Tuple[int, str]]:
        """Return ``(Id, title)`` for every user-visible vocabulary page."""
        rows = self.conn.execute(
            "SELECT Id, COALESCE(NULLIF(Title, ''), 'Page ' || Id) AS DisplayName "
            "FROM Page WHERE PageType = ? "
            "ORDER BY DisplayName COLLATE NOCASE",
            (PAGE_TYPE_VOCAB,),
        ).fetchall()
        return [(row["Id"], row["DisplayName"]) for row in rows]

    def find_page_id_by_name(self, name: str) -> int:
        """Return the Id of the vocabulary page titled *name* (case-insensitive)."""
        matches = [
            page_id
            for page_id, display in self.list_pages()
            if display.casefold() == name.casefold()
        ]
        if not matches:
            raise PagesetError(f"No page named {name!r} found.")
        if len(matches) > 1:
            raise PagesetError(
                f"Page name {name!r} is ambiguous ({len(matches)} pages share it); "
                "use the numeric page Id instead."
            )
        return matches[0]

    def grid_dimension(self) -> Tuple[int, int]:
        """Return the page set's ``(cols, rows)`` grid.

        Prefers ``PageSetProperties.GridDimension``; falls back to the most
        common ``PageLayoutSetting`` among vocabulary pages.
        """
        row = self.conn.execute(
            "SELECT GridDimension FROM PageSetProperties LIMIT 1"
        ).fetchone()
        if row and row["GridDimension"]:
            return schema.parse_grid(row["GridDimension"])

        row = self.conn.execute(
            "SELECT pl.PageLayoutSetting AS s, COUNT(*) AS c FROM PageLayout pl "
            "JOIN Page p ON pl.PageId = p.Id WHERE p.PageType = ? "
            "GROUP BY pl.PageLayoutSetting ORDER BY c DESC LIMIT 1",
            (PAGE_TYPE_VOCAB,),
        ).fetchone()
        if row and row["s"]:
            return schema.parse_grid(row["s"])

        raise PagesetError("Could not determine the page set's grid dimensions.")

    # -- saving -----------------------------------------------------------

    def save_as(self, dest_path: Optional[str] = None) -> str:
        """Flush writes and copy the edited database to *dest_path*.

        Defaults to ``<original>.edited<ext>`` next to the source file. The
        WAL checkpoint guards against a working copy that was switched to WAL
        journaling, where a plain file copy would miss unflushed pages.
        """
        if dest_path is None:
            dest_path = default_output_path(self.source_path)
        self.conn.commit()
        journal_mode = self.conn.execute("PRAGMA journal_mode").fetchone()[0]
        if str(journal_mode).lower() == "wal":
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copyfile(self.working_path, dest_path)
        return dest_path
