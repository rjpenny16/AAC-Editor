"""Durable atomic writes: all-or-nothing, flushed to disk, no temp litter."""

import os

import pytest

from tdsnap import atomic


def litter(directory):
    return sorted(name for name in os.listdir(directory) if name.startswith("."))


def test_write_creates_and_replaces_text_and_bytes(tmp_path):
    target = tmp_path / "out.json"
    atomic.atomic_write(str(target), "héllo")
    assert target.read_text(encoding="utf-8") == "héllo"
    atomic.atomic_write(str(target), b"\x00\x01")
    assert target.read_bytes() == b"\x00\x01"
    assert litter(tmp_path) == []


def test_write_flushes_to_disk_before_the_rename(tmp_path, monkeypatch):
    order = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1])
    atomic.atomic_write(str(tmp_path / "out"), "x")
    assert order[:2] == ["fsync", "replace"]


def test_failed_rename_keeps_the_original_and_removes_the_temp_file(tmp_path, monkeypatch):
    target = tmp_path / "out"
    target.write_text("original")

    def deny(*_args):
        raise PermissionError("in use")

    monkeypatch.setattr(os, "replace", deny)
    with pytest.raises(PermissionError):
        atomic.atomic_write(str(target), "new")
    assert target.read_text() == "original"
    assert litter(tmp_path) == []


def test_failed_flush_keeps_the_original(tmp_path, monkeypatch):
    target = tmp_path / "out"
    target.write_text("original")

    def full(_fd):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", full)
    with pytest.raises(OSError):
        atomic.atomic_write(str(target), "new")
    assert target.read_text() == "original"
    assert litter(tmp_path) == []


def test_copy_is_all_or_nothing(tmp_path, monkeypatch):
    source = tmp_path / "src"
    source.write_bytes(b"data")
    target = tmp_path / "dst"
    atomic.atomic_copy(str(source), str(target))
    assert target.read_bytes() == b"data"
    source.write_bytes(b"newer")
    monkeypatch.setattr(os, "replace", lambda *_a: (_ for _ in ()).throw(OSError("busy")))
    with pytest.raises(OSError):
        atomic.atomic_copy(str(source), str(target))
    assert target.read_bytes() == b"data"
    assert litter(tmp_path) == []
