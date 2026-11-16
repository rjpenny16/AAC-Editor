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


def test_a_failure_while_writing_the_data_keeps_the_original(tmp_path, monkeypatch):
    """doc 04 F1-F4 for atomic.py itself: the temp file's own write fails."""
    import os

    from tdsnap import atomic

    dest = tmp_path / "settings.json"
    dest.write_text("old", encoding="utf-8")
    real_fdopen = os.fdopen

    class Failing:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()

        def write(self, _data):
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(atomic.os, "fdopen", lambda fd, *a, **k: Failing(real_fdopen(fd, *a, **k)))
    with pytest.raises(OSError):
        atomic.atomic_write(str(dest), "new")
    assert dest.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_a_replace_refused_for_a_moment_is_retried(tmp_path, monkeypatch):
    """REL-020: Windows refuses to rename over a file another handle has open."""
    dest = tmp_path / "current"
    dest.write_bytes(b"old")
    real_replace = os.replace
    refusals = {"left": 3}

    def busy_replace(src, dst):
        if refusals["left"]:
            refusals["left"] -= 1
            raise PermissionError(13, "The process cannot access the file")
        return real_replace(src, dst)

    monkeypatch.setattr(atomic.os, "replace", busy_replace)
    monkeypatch.setattr(atomic.time, "sleep", lambda _s: None)
    atomic.atomic_write(str(dest), b"new")
    assert dest.read_bytes() == b"new"


def test_a_replace_refused_for_good_still_keeps_the_original(tmp_path, monkeypatch):
    dest = tmp_path / "current"
    dest.write_bytes(b"old")

    def always_busy(_src, _dst):
        raise PermissionError(13, "busy")

    monkeypatch.setattr(atomic.os, "replace", always_busy)
    monkeypatch.setattr(atomic.time, "sleep", lambda _s: None)
    with pytest.raises(PermissionError):
        atomic.atomic_write(str(dest), b"new")
    assert dest.read_bytes() == b"old"
    assert litter(tmp_path) == []
