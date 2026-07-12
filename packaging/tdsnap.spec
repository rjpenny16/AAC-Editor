# PyInstaller spec for the packaged desktop app.
# Build:  pyinstaller packaging/tdsnap.spec
# Output: dist/TDSnapPageBuilder/ (one-dir build: starts fast, easy to zip)

import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
here = SPECPATH  # PyInstaller sets this to the spec file's directory
root = os.path.abspath(os.path.join(here, ".."))

datas = [(os.path.join(root, "tdsnap", "web", "static"), "tdsnap/web/static")]
binaries = []
hiddenimports = []

# Bundle the built-in AI engine when it's installed in the build environment.
try:
    llama_datas, llama_binaries, llama_hidden = collect_all("llama_cpp")
    datas += llama_datas
    binaries += llama_binaries
    hiddenimports += llama_hidden
except Exception:
    pass

try:
    auto_datas, auto_binaries, auto_hidden = collect_all("uiautomation")
    datas += auto_datas
    binaries += auto_binaries
    hiddenimports += auto_hidden
except Exception:
    pass

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
    name="TD Snap Page Builder",
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="TDSnapPageBuilder",
)
