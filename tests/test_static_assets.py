"""The frontend ships as plain ES modules, so packaging has to carry them all.

`pyproject.toml` declares package data as an explicit glob. A module added in
a subdirectory would still work from a source checkout, and would still work in
the PyInstaller bundle (which copies the whole static tree) — but would 404
under `pip install`. That combination hides the break from every local test, so
it gets an explicit one.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
STATIC = ROOT / "tdsnap" / "web" / "static"

# Matches `from "./preview.js"` in both static and dynamic import forms.
IMPORT_TARGET = re.compile(r"""(?:from|import)\s*\(?\s*["'](\./[^"']+)["']""")


def module_files():
    return sorted(STATIC.glob("*.js"))


def test_the_frontend_is_actually_split():
    """Guards the split itself: one huge file is the state this replaced."""
    assert len(module_files()) >= 5


def test_every_import_target_exists():
    missing = []
    for module in module_files():
        for target in IMPORT_TARGET.findall(module.read_text(encoding="utf-8")):
            if not (module.parent / target).exists():
                missing.append(f"{module.name} -> {target}")
    assert not missing, f"unresolved imports: {missing}"


def test_package_data_glob_covers_every_static_file():
    """`static/*` only reaches one level down; a subdirectory needs its own glob.

    Expanded with Path.glob from the package directory, which is the same
    semantics setuptools applies — `*` does not cross a path separator.
    """
    package = ROOT / "tdsnap" / "web"
    declared = re.findall(r'"tdsnap\.web" = \[(.*?)\]', (ROOT / "pyproject.toml").read_text())
    assert declared, "package-data for tdsnap.web is missing"
    patterns = re.findall(r'"([^"]+)"', declared[0])

    covered = {path for pattern in patterns for path in package.glob(pattern) if path.is_file()}
    uncovered = sorted(
        path.relative_to(package).as_posix()
        for path in STATIC.rglob("*")
        if path.is_file() and path not in covered
    )
    assert not uncovered, (
        f"these static files are not covered by package-data and would 404 under "
        f"`pip install .`: {uncovered}"
    )


@pytest.mark.parametrize("module", [p.name for p in module_files()])
def test_modules_are_referenced(module):
    """Every module is reachable from the entry point, directly or transitively."""
    if module == "app.js":
        return
    referenced = any(
        f'"./{module}"' in other.read_text(encoding="utf-8")
        for other in module_files()
        if other.name != module
    )
    assert referenced, f"{module} is never imported; it would ship as dead weight"


def test_index_loads_the_entry_point_as_a_module():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'type="module"' in index, "ES modules need type=module or the imports fail"
    assert 'src="/static/app.js"' in index
