# PyInstaller spec for the packaged desktop app.
# Build:  pyinstaller packaging/tdsnap.spec
# Output: dist/AACEditor/ (one-dir build: starts fast, easy to zip)

import importlib.util
import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
here = SPECPATH  # PyInstaller sets this to the spec file's directory
root = os.path.abspath(os.path.join(here, ".."))

# Which privilege the packaged executable requests. An allow-list rather than
# a path, because this file decides what the process may do: an environment
# variable that could name any manifest would be a way to hand the app
# uiAccess, or administrator rights, from outside the build.
#
# "uiaccess" is only ever selected by packaging/build.ps1 under -Sign. Windows
# will not start a uiAccess="true" executable without a trusted Authenticode
# signature, so an unsigned build that embedded it would not run at all.
MANIFESTS = {
    "asinvoker": "aac-editor.manifest",
    "uiaccess": "aac-editor-uiaccess.manifest",
}
manifest_mode = os.environ.get("AAC_EDITOR_MANIFEST", "asinvoker").strip().lower()
if manifest_mode not in MANIFESTS:
    raise RuntimeError(
        f"AAC_EDITOR_MANIFEST must be one of {sorted(MANIFESTS)}: {manifest_mode!r}"
    )
manifest_path = os.path.join(here, MANIFESTS[manifest_mode])

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
    manifest=manifest_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="AACEditor",
)
