# PyInstaller spec for the packaged desktop app.
# Build:  pyinstaller packaging/tdsnap.spec
# Output: dist/AACEditor/ (one-dir build: starts fast, easy to zip)

import importlib.util
import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
here = SPECPATH  # PyInstaller sets this to the spec file's directory
root = os.path.abspath(os.path.join(here, ".."))

datas = [(os.path.join(root, "tdsnap", "web", "static"), "tdsnap/web/static")]
binaries = []
hiddenimports = []

# Release builds promise both engines. A missing dynamic import must fail the
# build instead of producing an apparently successful but incomplete installer.
for package in ("llama_cpp", "uiautomation"):
    if importlib.util.find_spec(package) is None:
        raise RuntimeError(f"Required packaged dependency is missing: {package}")
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [os.path.join(here, "launcher.py")],
    pathex=[root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AAC Editor",
    console=False,
    icon=os.path.join(here, "icon.ico"),
    manifest=os.path.join(here, "aac-editor.manifest"),
    uac_uiaccess=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="AACEditor",
)
