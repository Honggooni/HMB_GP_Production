from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_RESOURCES = {
    "resources/maya/HMB_Maya_Background_Preview.py",
    "resources/picker/HMB_Marker_Catalog.json",
    "resources/agent/hmb_agent_core.dat",
}
DISTRIBUTION_ONLY_FILES = (
    "Install_HMB_GP_Production.ps1",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "SBOM.spdx.json",
)
EXCLUDED_PACKAGE_FILES = {
    "README.md",
    "SECURITY.md",
    "pyproject.toml",
    "resources/maya/HMBVideoPicker_Maya_Guide.txt",
}


def load_packager():
    path = ROOT / "tools" / "package_runtime_release.py"
    spec = importlib.util.spec_from_file_location("_hmb_runtime_packager", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assert not (ROOT / "resources" / "build_developer_release.py").exists()
packager = load_packager()
source_files = tuple(packager.SOURCE_FILES)
runtime_install_files = tuple(packager.RUNTIME_INSTALL_FILES)
distribution_only_files = tuple(packager.DISTRIBUTION_ONLY_FILES)
assert len(runtime_install_files) == 22
assert distribution_only_files == DISTRIBUTION_ONLY_FILES
assert source_files == (*runtime_install_files, *distribution_only_files)
assert len(source_files) == 26
assert not EXCLUDED_PACKAGE_FILES.intersection(source_files)
assert not set(runtime_install_files).intersection(distribution_only_files)
assert {
    path for path in runtime_install_files if path.startswith("resources/")
} == RUNTIME_RESOURCES
assert not any(
    forbidden in path.casefold()
    for path in source_files
    for forbidden in (
        "resources/admin/",
        "resources/tests/",
        "resources/policy/",
        "__pycache__",
        ".pyc",
        "build_developer_release.py",
        "hmbvideopicker_test_8objects",
    )
)

installer = (ROOT / "Install_HMB_GP_Production.ps1").read_text(encoding="utf-8")
assert "release-manifest.json" in installer
assert "SHA256SUMS" in installer
assert "Get-FileHash -Algorithm SHA256" in installer
assert "$installProperty.Value" in installer
assert "foreach ($relative in $installMembers)" in installer
assert "foreach ($record in $installRecords)" in installer
assert "Compare-Object $expectedDistributionOnlyMembers $distributionOnlyMembers" in installer
assert "$null = $allowed.Add('release-manifest.json')" not in installer
assert "$null = $allowed.Add('SHA256SUMS')" not in installer
assert "Close Griptape completely" in installer
assert "Get-ChildItem -LiteralPath $target -Force -Recurse -File" in installer
assert "Move-Item -LiteralPath $target -Destination $rollback" in installer
assert "Move-Item -LiteralPath $preservedVenv" in installer
assert "LocalApplicationData" in installer
assert "Rollback data must be stored outside the Griptape libraries folder" in installer
assert "MyInvocation.MyCommand.Path" in installer
assert "Could not resolve the extracted HMB package directory" in installer
assert "Remove-Item" not in installer
assert "backup" not in installer.casefold()

picker = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")
assert not (ROOT / "HMB_Agent_Griptape.bat").exists()
assert 'env["PYTHONDONTWRITEBYTECODE"] = "1"' in picker
assert "sys.dont_write_bytecode=True" in picker

print(
    "HMB runtime resource cleanliness regression: PASS "
    "(exact runtime closure, .venv preservation, no launcher residue, "
    "Maya runner bytecode isolation)"
)
