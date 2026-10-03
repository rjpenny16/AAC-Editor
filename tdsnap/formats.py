"""Which AAC file format a file is, and a structure-only report for formats not yet supported.

AAC Editor edits two kinds of file today: TD Snap page sets (``.sps``/``.spb``,
SQLite) and Grid 3 grid sets (``.gridset``, a zip of XML). ``detect`` tells them
apart by content, not by name, and recognises the formats it deliberately does
not open so it can say why instead of failing on a parse error:

* ``.gridsetx`` (Grid 3 protected sets, WordPower among them) are encrypted
  and will not be supported. See README.
* Chat Editor (TouchChat, NovaChat, ChatFusion) ``.ce`` files and PRC-Saltillo
  Empower vocabularies are *not yet* supported. Their formats have to be
  documented from real, disposable files before a writer can be trusted,
  which is what :func:`inspect` is for.

``inspect`` prints how a file is built, never what it says: container type,
entry shapes and sizes, whether entries look encrypted, SQLite table and
column names with row counts, XML element names, and JSON keys. No label,
message, or other value is read out, so the report is safe to paste into an
issue. Entry names are generalised (``Grids/*/grid.xml``) because folder and
file names can themselves be vocabulary; ``show_names`` lifts that for
someone inspecting their own file.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import posixpath
import sqlite3
import tempfile
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

from . import gridset
from .errors import PagesetError
from .grid3 import PROTECTED_MESSAGE
from .pageset import harden_untrusted, is_sqlite_file

SPS = "sps"
GRIDSET = "gridset"
GRIDSETX = "gridsetx"
CHAT_EDITOR = "chateditor"
EMPOWER = "empower"
OBZ = "obz"
UNKNOWN = "unknown"

SUPPORTED = (SPS, GRIDSET)

_CHAT_EDITOR_SUFFIXES = (".ce",)
# Empower's file type is not documented yet; the name is matched loosely so a
# person who picked one is told the truth rather than "not a page set".
_EMPOWER_HINTS = ("empower",)

NOT_YET_MESSAGE = (
    "{product} files are not supported yet. AAC Editor will only edit a format "
    "once it has been documented from real files and every edit can be checked "
    "afterwards. You can help: run `python -m tdsnap inspect-format \"{name}\"` "
    "and share the report. It describes how the file is built and never prints "
    "your words."
)

# What inspect will read, so a hostile file costs a refusal.
MAX_INSPECT_ENTRIES = 50_000
MAX_SQLITE_BYTES = 512 * 1024 * 1024
MAX_XML_BYTES = 16 * 1024 * 1024
SAMPLE_BYTES = 4096
_TEXT_EXTENSIONS = {"", ".xml", ".json", ".db", ".sqlite", ".sqlite3", ".c4v", ".ini",
                    ".txt", ".dat", ".bin", ".plist", ".cfg", ".config", ".manifest"}


def detect(path: str, filename: str | None = None) -> str:
    """The format of the file at *path*; *filename* is the name it was chosen as."""
    name = (filename or os.path.basename(path)).lower()
    if name.endswith(".gridsetx"):
        return GRIDSETX
    if is_sqlite_file(path):
        return SPS
    if zipfile.is_zipfile(path):
        if gridset.is_gridset_file(path):
            return GRIDSET
        with contextlib.suppress(OSError, zipfile.BadZipFile), zipfile.ZipFile(path) as package:
            names = package.namelist()
            if "manifest.json" in names and any(n.endswith(".obf") for n in names):
                return OBZ
            if any(n.startswith("Grids/") for n in names):
                return GRIDSETX
    if name.endswith(_CHAT_EDITOR_SUFFIXES):
        return CHAT_EDITOR
    if any(hint in name for hint in _EMPOWER_HINTS):
        return EMPOWER
    return UNKNOWN


def require_supported(path: str, filename: str) -> str:
    """The format, or a PagesetError that says exactly why it cannot be opened."""
    kind = detect(path, filename)
    if kind in SUPPORTED:
        return kind
    if kind == GRIDSETX:
        raise PagesetError(PROTECTED_MESSAGE)
    if kind == CHAT_EDITOR:
        raise PagesetError(NOT_YET_MESSAGE.format(
            product="Chat Editor (TouchChat, NovaChat, ChatFusion)", name=filename))
    if kind == EMPOWER:
        raise PagesetError(NOT_YET_MESSAGE.format(product="Empower", name=filename))
    if kind == OBZ:
        raise PagesetError(
            f"{filename!r} is an Open Board file. Open your page set or grid set first, "
            "then use Open Board files on the Build screen to bring its boards in."
        )
    raise PagesetError(
        f"{filename!r} is not a TD Snap page set (.sps/.spb export) or an "
        "unprotected Grid 3 grid set (.gridset)."
    )


# ---------------------------------------------------------------------------
# structure-only inspection


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum(count / total * math.log2(count / total) for count in counts.values())


def _looks_encrypted(data: bytes, size: int) -> bool:
    """High-entropy bytes in 16-byte blocks: the shape of block-cipher output.

    The same evidence the README's .gridsetx position rests on. Compressed
    data is high-entropy too, which is why this is only ever applied to
    bytes after the zip layer has inflated them.
    """
    return len(data) >= 256 and _entropy(data) > 7.5 and size % 16 == 0


_STRUCTURAL_STEMS = {"settings", "styles", "manifest", "filemap", "grid", "index",
                     "info", "metadata", "content", "config", "version", "data"}


def _shape(name: str, show_names: bool, repeated: frozenset = frozenset()) -> str:
    """*name* with everything that could be somebody's vocabulary replaced by ``*``.

    The top folder is kept (it is the format's own layout), folders below it
    are not, and a file name is kept only when it is plainly structural: a
    known name, or one that repeats across folders (``grid.xml``). A single
    ``Sam's words.c4v`` becomes ``*.c4v``.
    """
    if show_names:
        return name
    *folders, last = name.split("/")
    stem, ext = posixpath.splitext(last)
    keep = ext.lower() in _TEXT_EXTENSIONS and (
        stem.lower() in _STRUCTURAL_STEMS or last in repeated
    )
    tail = last if keep else f"*{ext.lower()}"
    if not folders:
        return tail
    return "/".join([folders[0], *("*" for _ in folders[1:]), tail])


def _xml_shape(data: bytes) -> dict:
    try:
        root = ET.fromstring(data)  # noqa: S314 - local file, size-bounded, structure only
    except ET.ParseError:
        return {"xml": "unparseable"}
    return {"xml_root": root.tag,
            "xml_children": sorted({child.tag for child in root})[:40],
            "xml_attributes": sorted(root.attrib)[:20]}


def _json_shape(data: bytes) -> dict:
    try:
        value = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return {"json": "unparseable"}
    if isinstance(value, dict):
        return {"json_keys": sorted(value)[:60]}
    return {"json_type": type(value).__name__}


def _sqlite_shape(path: str) -> dict:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        harden_untrusted(conn)
        tables = []
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ):
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [f"{row[1]} {row[2]}".strip()
                       for row in conn.execute(f"PRAGMA table_info({quoted})")]
            try:
                rows = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]  # noqa: S608
            except sqlite3.Error:
                rows = None
            tables.append({"table": table, "columns": columns, "rows": rows})
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error as exc:
        return {"sqlite": f"unreadable ({exc.__class__.__name__})"}
    finally:
        conn.close()
    return {"sqlite_user_version": version, "sqlite_tables": tables}


def _content_shape(data: bytes, size: int, read_sqlite) -> dict:
    head = data[:16]
    if head.startswith(b"SQLite format 3\x00"):
        return read_sqlite()
    stripped = data.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"<"):
        return _xml_shape(data) if len(data) == size else {"xml": "too large to read"}
    if stripped[:1] in (b"{", b"["):
        return _json_shape(data) if len(data) == size else {"json": "too large to read"}
    if data.startswith(b"PK\x03\x04"):
        return {"nested": "zip"}
    return {"encrypted_looking": _looks_encrypted(data[:SAMPLE_BYTES], size),
            "entropy": round(_entropy(data[:SAMPLE_BYTES]), 2)}


def inspect(path: str, *, show_names: bool = False) -> dict:
    """A structure-only report on any file, for documenting a new format."""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        head = handle.read(SAMPLE_BYTES)
    report = {
        "detected": detect(path),
        "bytes": size,
        "magic": head[:8].hex(),
        "names_shown": show_names,
    }
    if head.startswith(b"SQLite format 3\x00"):
        report["container"] = "sqlite"
        report.update(_sqlite_shape(path))
        return report
    if not zipfile.is_zipfile(path):
        report["container"] = "other"
        report.update(_content_shape(head, size, lambda: {}))
        if size > SAMPLE_BYTES:
            report.pop("xml", None)
            report.pop("json", None)
        return report
    report["container"] = "zip"
    with zipfile.ZipFile(path) as package:
        infos = package.infolist()
        if len(infos) > MAX_INSPECT_ENTRIES:
            raise PagesetError("This file has more entries than AAC Editor will inspect.")
        report["entries"] = len(infos)
        report["zip_encrypted_entries"] = sum(1 for info in infos if info.flag_bits & 0x1)
        shapes: dict[str, dict] = {}
        last_names = Counter(info.filename.rsplit("/", 1)[-1] for info in infos
                             if not info.is_dir() and "/" in info.filename)
        repeated = frozenset(name for name, count in last_names.items() if count > 1)
        for info in infos:
            if info.is_dir():
                continue
            shape = _shape(info.filename, show_names, repeated)
            entry = shapes.setdefault(shape, {"entry": shape, "count": 0, "bytes": 0})
            entry["count"] += 1
            entry["bytes"] += info.file_size
            if "content" in entry or info.flag_bits & 0x1:
                continue
            limit = MAX_XML_BYTES if info.file_size <= MAX_XML_BYTES else SAMPLE_BYTES
            with package.open(info) as reader:
                data = reader.read(limit)

            def read_sqlite(info=info):
                if info.file_size > MAX_SQLITE_BYTES:
                    return {"sqlite": "too large to inspect"}
                handle, temporary = tempfile.mkstemp(prefix="aac-inspect-")
                os.close(handle)
                try:
                    with package.open(info) as reader, open(temporary, "wb") as writer:
                        while chunk := reader.read(1024 * 1024):
                            writer.write(chunk)
                    return _sqlite_shape(temporary)
                finally:
                    with contextlib.suppress(OSError):
                        os.remove(temporary)

            entry["content"] = _content_shape(data, info.file_size, read_sqlite)
        report["entry_shapes"] = sorted(shapes.values(), key=lambda item: item["entry"])
        report["encrypted_looking_entries"] = sum(
            1 for item in shapes.values()
            if item.get("content", {}).get("encrypted_looking")
        )
    return report


def format_report(report: dict) -> str:
    """The report as plain text for a terminal or an issue."""
    lines = [
        f"Detected format: {report['detected']}",
        f"Container: {report['container']} ({report['bytes']} bytes, magic {report['magic']})",
    ]
    if report["container"] == "zip":
        lines.append(f"Entries: {report['entries']} "
                     f"(zip-encrypted: {report['zip_encrypted_entries']}, "
                     f"look encrypted: {report['encrypted_looking_entries']})")
        for item in report["entry_shapes"]:
            lines.append(f"  {item['entry']}  x{item['count']}  {item['bytes']} bytes")
            for key, value in sorted(item.get("content", {}).items()):
                if key == "sqlite_tables":
                    lines.extend(_table_lines(value, "    "))
                else:
                    lines.append(f"    {key}: {value}")
    else:
        for key, value in sorted(report.items()):
            if key in {"detected", "container", "bytes", "magic", "names_shown"}:
                continue
            if key == "sqlite_tables":
                lines.extend(_table_lines(value, "  "))
            else:
                lines.append(f"  {key}: {value}")
    if not report["names_shown"]:
        lines.append("Entry names are generalised; nothing in this report is your vocabulary.")
    return "\n".join(lines)


def _table_lines(tables: list, indent: str) -> list[str]:
    lines = []
    for table in tables:
        lines.append(f"{indent}table {table['table']} ({table['rows']} rows)")
        lines.append(f"{indent}  {', '.join(table['columns'])}")
    return lines
