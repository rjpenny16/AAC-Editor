"""Command-line interface: the add round trip and scratch-file hygiene."""

import hashlib
import os
import pathlib
import sqlite3

from tdsnap.cli import main


def test_add_roundtrip_leaves_only_the_edited_file(seeded_source, capsys):
    source_dir = os.path.dirname(seeded_source)
    code = main(
        [
            "add", seeded_source,
            "--title", "Snacks",
            "--items", "Chips,Apple|I would like an apple please",
            "--parent-name", "Home Page",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "All validation checks passed." in out

    edited = seeded_source.replace(".sps", ".edited.sps")
    assert os.path.exists(edited)
    # No stray .editing working copy next to the user's file.
    leftovers = [n for n in os.listdir(source_dir) if ".editing" in n]
    assert leftovers == []

    conn = sqlite3.connect(edited)
    try:
        labels = {
            row[0] for row in conn.execute("SELECT Label FROM Button")
        }
    finally:
        conn.close()
    assert {"Chips", "Apple", "Snacks"} <= labels


def test_add_rejects_missing_parent(seeded_source, capsys):
    code = main(
        ["add", seeded_source, "--title", "X", "--items", "a",
         "--parent-name", "No Such Page"]
    )
    assert code == 1
    assert "No page named" in capsys.readouterr().err


def test_verify_passes_on_seeded_file(seeded_source, capsys):
    assert main(["verify", seeded_source]) == 0
    assert "OK" in capsys.readouterr().out


def test_verify_normalizes_malformed_sqlite_error(tmp_path, capsys):
    wrong = tmp_path / "wrong.sps"
    with sqlite3.connect(wrong) as conn:
        conn.execute("CREATE TABLE Unrelated (x)")

    assert main(["verify", str(wrong)]) == 1
    assert "missing tables" in capsys.readouterr().err


def test_cli_refuses_to_overwrite_source(seeded_source, capsys):
    before = hashlib.sha256(pathlib.Path(seeded_source).read_bytes()).hexdigest()
    code = main([
        "add", seeded_source, "--title", "Unsafe", "--items", "word",
        "--output", seeded_source,
    ])

    assert code == 1
    assert "overwrite the original" in capsys.readouterr().err
    assert hashlib.sha256(pathlib.Path(seeded_source).read_bytes()).hexdigest() == before


def test_list_prints_vocabulary_pages(seeded_source, capsys):
    assert main(["list", seeded_source]) == 0
    assert "Home Page" in capsys.readouterr().out


def test_inspect_prints_schema_and_row_counts(seeded_source, capsys):
    assert main(["inspect", seeded_source]) == 0
    out = capsys.readouterr().out
    assert "SchemaVersion:" in out and "Button" in out


def test_verify_show_sync_survives_a_bad_timestamp(seeded_source, capsys):
    with sqlite3.connect(seeded_source) as conn:
        conn.execute("UPDATE Page SET Timestamp = 'garbage' WHERE PageType = 1")
    assert main(["verify", seeded_source, "--show-sync"]) in (0, 1)
    assert "invalid timestamp" in capsys.readouterr().out


def test_missing_file_is_an_error_not_a_traceback(tmp_path, capsys):
    assert main(["verify", str(tmp_path / "absent.sps")]) == 1
    assert "Error:" in capsys.readouterr().err
