"""Command-line interface: the add round trip and scratch-file hygiene."""

import os
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
