"""Format detection, the structure-only inspect report, and the CLI's .gridset paths."""

import json
import os
import sqlite3
import zipfile

import pytest

from tdsnap import cli, formats, gridset
from tdsnap.errors import PagesetError
from tests.test_gridset import make


def sqlite_file(path, rows=("secret word",)):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE buttons (id INTEGER PRIMARY KEY, label TEXT, page_id INTEGER)")
    conn.executemany("INSERT INTO buttons (label) VALUES (?)", [(row,) for row in rows])
    conn.commit()
    conn.close()
    return str(path)


def test_detects_formats_by_content_and_name(tmp_path):
    assert formats.detect(make(tmp_path)) == formats.GRIDSET
    assert formats.detect(sqlite_file(tmp_path / "set.sps")) == formats.SPS
    sealed = tmp_path / "WordPower.gridsetx"
    sealed.write_bytes(os.urandom(64))
    assert formats.detect(str(sealed)) == formats.GRIDSETX
    renamed = tmp_path / "upload"
    with zipfile.ZipFile(renamed, "w") as package:
        package.writestr("Grids/Home/grid.xml", os.urandom(64))
    assert formats.detect(str(renamed)) == formats.GRIDSETX
    vocab = tmp_path / "vocab.ce"
    vocab.write_bytes(b"\x00" * 32)
    assert formats.detect(str(vocab)) == formats.CHAT_EDITOR
    other = tmp_path / "upload2"
    other.write_bytes(b"hello")
    assert formats.detect(str(other), "My Empower backup") == formats.EMPOWER
    assert formats.detect(str(other), "notes.txt") == formats.UNKNOWN
    boards = tmp_path / "boards"
    with zipfile.ZipFile(boards, "w") as package:
        package.writestr("manifest.json", "{}")
        package.writestr("boards/1.obf", "{}")
    assert formats.detect(str(boards)) == formats.OBZ


@pytest.mark.parametrize("filename, message", [
    ("vocab.ce", "Chat Editor .* not supported yet"),
    ("Empower vocab", "Empower files are not supported yet"),
    ("WordPower.gridsetx", "protected .gridsetx"),
    ("notes.txt", "is not a TD Snap page set"),
])
def test_unsupported_formats_say_why(tmp_path, filename, message):
    path = tmp_path / "upload"
    path.write_bytes(b"not a vocabulary")
    with pytest.raises(PagesetError, match=message):
        formats.require_supported(str(path), filename)


def test_supported_formats_pass(tmp_path):
    assert formats.require_supported(make(tmp_path), "x.gridset") == formats.GRIDSET


def test_inspect_reports_sqlite_structure_without_content(tmp_path):
    path = sqlite_file(tmp_path / "vocab.c4v")
    report = formats.inspect(path)
    assert report["container"] == "sqlite"
    table = report["sqlite_tables"][0]
    assert table == {"table": "buttons", "rows": 1,
                     "columns": ["id INTEGER", "label TEXT", "page_id INTEGER"]}
    assert "secret word" not in json.dumps(report)
    assert "secret word" not in formats.format_report(report)


def test_inspect_reads_a_database_inside_a_zip_and_hides_names(tmp_path):
    database = sqlite_file(tmp_path / "db")
    archive = tmp_path / "Sam's words.ce"
    with zipfile.ZipFile(archive, "w") as package:
        package.write(database, "Sam's words.c4v")
        package.writestr("Images/apple juice.png", b"\x89PNG" + b"\x00" * 100)
        package.writestr("Pages/Snacks/settings.xml", "<Page><Title>Snacks</Title></Page>")
        package.writestr("Pages/Drinks/settings.xml", "<Page><Title>Drinks</Title></Page>")
        package.writestr("blob.bin", os.urandom(4096))
    report = formats.inspect(str(archive))
    text = formats.format_report(report) + json.dumps(report)
    for private in ("Sam", "apple", "Snacks", "Drinks", "secret word"):
        assert private not in text
    shapes = {item["entry"]: item for item in report["entry_shapes"]}
    assert shapes["*.c4v"]["content"]["sqlite_tables"][0]["table"] == "buttons"
    assert shapes["Images/*.png"]["count"] == 1
    assert shapes["Pages/*/settings.xml"]["count"] == 2
    assert shapes["Pages/*/settings.xml"]["content"]["xml_children"] == ["Title"]
    assert shapes["*.bin"]["content"]["encrypted_looking"] is True
    assert report["encrypted_looking_entries"] == 1
    shown = formats.inspect(str(archive), show_names=True)
    assert any(item["entry"] == "Sam's words.c4v" for item in shown["entry_shapes"])


def test_inspect_other_files(tmp_path):
    xml = tmp_path / "a.xml"
    xml.write_text("<Root a='1'><Child>words</Child></Root>")
    report = formats.inspect(str(xml))
    assert report["container"] == "other" and report["xml_root"] == "Root"
    noise = tmp_path / "b.dat"
    noise.write_bytes(os.urandom(1024))
    assert formats.inspect(str(noise))["encrypted_looking"] is True
    data = tmp_path / "c.json"
    data.write_text('{"boards": [], "name": "Sam"}')
    report = formats.inspect(str(data))
    assert report["json_keys"] == ["boards", "name"]
    assert "Sam" not in formats.format_report(report)


# -- the command line ----------------------------------------------------------


def test_cli_inspect_format(tmp_path, capsys):
    path = sqlite_file(tmp_path / "vocab.c4v")
    assert cli.main(["inspect-format", path]) == 0
    assert "table buttons (1 rows)" in capsys.readouterr().out
    assert cli.main(["inspect-format", path, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["container"] == "sqlite"


def test_cli_lists_and_exports_a_gridset(tmp_path, capsys):
    path = make(tmp_path, name="My Set.gridset")
    assert cli.main(["list", path]) == 0
    out = capsys.readouterr().out
    assert "Home" in out and str(gridset.page_id("Food")) in out
    dest = str(tmp_path / "out.obz")
    assert cli.main(["export-obz", path, "-o", dest]) == 0
    assert "Exported 2 page(s)" in capsys.readouterr().out


def test_cli_imports_an_obz_into_a_gridset(tmp_path, capsys):
    source = make(tmp_path, name="Source.gridset")
    boards = str(tmp_path / "boards.obz")
    assert cli.main(["export-obz", source, "-o", boards]) == 0
    target = make(tmp_path, name="Target.gridset",
                  grids={"Start": "<Grid><ColumnDefinitions><ColumnDefinition/>"
                                  "<ColumnDefinition/><ColumnDefinition/></ColumnDefinitions>"
                                  "<RowDefinitions><RowDefinition/><RowDefinition/>"
                                  "</RowDefinitions><Cells/></Grid>"})
    capsys.readouterr()
    assert cli.main(["import-obz", target, boards, "--parent-name", "start"]) == 0
    out = capsys.readouterr().out
    assert "Added 2 grid(s)" in out
    edited = str(tmp_path / "Target.edited.gridset")
    with gridset.GridsetFile(edited) as result:
        assert set(result.names()) == {"Start", "Home", "Food"}
    assert cli.main(["import-obz", target, boards, "--parent-name", "nope"]) == 1
