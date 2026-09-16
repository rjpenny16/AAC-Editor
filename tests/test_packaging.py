import os
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

import tdsnap

ROOT = Path(__file__).parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_version_has_one_source_and_is_ready_for_release():
    project = read("pyproject.toml")
    assert tdsnap.__version__ == "2.3.0"
    assert 'dynamic = ["version"]' in project
    assert 'version = { attr = "tdsnap.__version__" }' in project
    assert '\nversion = "2.3.0"' not in project


def test_unsigned_build_never_requests_uiaccess():
    # Windows will not start a uiAccess="true" executable without a trusted
    # Authenticode signature, and releases are unsigned.
    manifest = ElementTree.parse(ROOT / "packaging" / "aac-editor.manifest")
    level = manifest.find(
        ".//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel"
    )
    assert level is not None
    assert level.attrib == {"level": "asInvoker", "uiAccess": "false"}

    spec = read("packaging/tdsnap.spec")
    assert "uac_uiaccess" not in spec
    assert 'uiAccess="false"' in read("packaging/verify_manifest.ps1")
    assert 'for package in ("llama_cpp", "uiautomation")' in spec
    assert "Required packaged dependency is missing" in spec
    assert "except Exception" not in spec

    installer = read("packaging/installer.iss")
    assert "DefaultDirName={autopf}\\AAC Editor" in installer
    assert "DisableDirPage=yes" in installer
    assert "UsePreviousAppDir=no" in installer
    assert "PrivilegesRequired=admin" in installer
    assert 'Source: "..\\dist\\AACEditor\\*"; DestDir: "{app}"' in installer
    assert 'Filename: "{app}\\AAC Editor.exe"' in installer
    assert "Permissions: users-" not in installer


def test_packaged_executable_manifest_is_extracted_from_the_binary():
    verifier = read("packaging/verify_manifest.ps1")
    assert "FindResource" in verifier
    assert "No embedded application manifest was found" in verifier

    executable = ROOT / "dist" / "AACEditor" / "AAC Editor.exe"
    if sys.platform != "win32" or not executable.exists():
        pytest.skip("packaged executable is validated by Package smoke CI")
    result = subprocess.run(
        [
            "powershell", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "packaging" / "verify_manifest.ps1"),
            "-Executable", str(executable),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Verified embedded" in result.stdout


def test_local_signing_is_explicit_and_fails_without_configuration():
    script = read("packaging/build.ps1")
    assert "AAC_EDITOR_SIGNING_THUMBPRINT" in script
    assert "New-SelfSignedCertificate" not in script
    assert "Import-Certificate" not in script
    assert '[ValidateSet("All", "App", "Installer")]' in script
    assert '"/fd", "SHA256"' in script

    if sys.platform != "win32":
        pytest.skip("local Authenticode guard is Windows-only")
    env = os.environ.copy()
    env.pop("AAC_EDITOR_SIGNING_THUMBPRINT", None)
    result = subprocess.run(
        [
            "powershell", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "packaging" / "build.ps1"), "-Sign",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "Signing was requested" in result.stderr


def test_release_is_tag_exact_attested_and_smoke_tested():
    workflow = read(".github/workflows/release.yml")
    assert "ref: ${{ env.RELEASE_TAG }}" in workflow
    assert "git describe --exact-match --tags HEAD" in workflow
    assert "Source version $version does not match tag" in workflow
    assert "signpath" not in workflow.lower()
    assert "AAC_EDITOR_SIGNING_THUMBPRINT" not in workflow
    assert "Get-AuthenticodeSignature" not in workflow
    assert "packaging/smoke_test.ps1" in workflow
    assert "actions/attest@" in workflow
    assert "Get-FileHash $installer -Algorithm SHA256" in workflow
    assert "draft: true" in workflow
    assert "Windows protected your PC" in workflow
    assert "python -m pip install --constraint packaging/release-constraints.txt pip" in workflow

    smoke = read("packaging/smoke_test.ps1")
    assert "Get-AuthenticodeSignature" not in smoke
    assert "verify_manifest.ps1" in smoke
    assert 'Invoke-RestMethod "$base/api/health"' in smoke
    assert "Packaged version" in smoke
    assert "unins000.exe" in smoke

    package_workflow = read(".github/workflows/package-smoke.yml")
    assert "New-SelfSignedCertificate" not in package_workflow
    assert "-Sign" not in package_workflow
    assert "packaging/smoke_test.ps1" in package_workflow


def test_project_metadata_is_the_dependency_source_of_truth():
    project = read("pyproject.toml")
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "scripts" / "make_icon.py").exists()
    assert "python -m pip install ." in read("launch.bat")
    assert "python3 -m pip install ." in read("launch.sh")
    assert '"requests' not in project
    assert "coverage[toml]" in project
    assert "pip-audit" in project
    assert "ruff" in project

    # Every direct release input is pinned exactly; Dependabot moves the numbers.
    constraints = read("packaging/release-constraints.txt")
    for name in ("pip", "pytest", "pyinstaller", "llama-cpp-python"):
        assert re.search(rf"^{re.escape(name)}==\d+\.\d+\.\d+$", constraints, re.M), name

    quality_workflow = read(".github/workflows/tests.yml")
    assert "python -m pip_audit ." in quality_workflow


def test_repository_hygiene_covers_windows_and_grid3():
    attributes = read(".gitattributes")
    assert "*.bat text eol=crlf" in attributes
    assert "*.ps1 text eol=crlf" in attributes
    assert "*.png binary" in attributes

    issue_template = read(".github/ISSUE_TEMPLATE/bug_report.yml")
    assert "Live Grid 3 editing" in issue_template


def test_release_documentation_says_unsigned_and_how_to_verify():
    readme = read("README.md")
    contributing = read("CONTRIBUTING.md")
    security = read("SECURITY.md")

    assert "Releases are not code-signed" in readme
    assert "Windows protected your PC" in readme
    assert "gh attestation verify" in readme
    assert "UIAccess" not in readme
    assert "SignPath" not in readme
    assert "Releases are not code-signed" in contributing
    assert 'uiAccess="false"' in contributing
    assert "SIGNPATH" not in contributing
    assert "Releases are not code-signed" in security
    assert not (ROOT / "docs" / "UIACCESS_TESTING.md").exists()
