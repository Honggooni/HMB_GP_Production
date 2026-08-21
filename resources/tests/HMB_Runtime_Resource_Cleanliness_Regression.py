from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_RESOURCES = {
    "resources/maya/HMB_Maya_Background_Preview.py",
    "resources/maya/HMB_Maya_Binding_Setup.py",
    "resources/maya/HMBVideoPicker_Maya_Guide.txt",
    "resources/picker/HMB_Marker_Catalog.json",
    "resources/tls/hmb_agent_broker_ca.pem",
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
assert "Install_HMB_GP_Production.ps1" in source_files
assert {path for path in source_files if path.startswith("resources/")} == RUNTIME_RESOURCES
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
assert "Close Griptape completely" in installer
assert "Get-ChildItem -LiteralPath $target -Force -Recurse -File" in installer
assert "Move-Item -LiteralPath $target -Destination $rollback" in installer
assert "Move-Item -LiteralPath $preservedVenv" in installer
assert "LocalApplicationData" in installer
assert "Rollback data must be stored outside the Griptape libraries folder" in installer
assert "Remove-Item" not in installer
assert "backup" not in installer.casefold()

launcher = (ROOT / "HMB_Agent_Griptape.bat").read_text(encoding="utf-8")
picker = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")
assert 'set "PYTHONDONTWRITEBYTECODE=1"' in launcher
assert 'env["PYTHONDONTWRITEBYTECODE"] = "1"' in picker
assert "sys.dont_write_bytecode=True" in picker

print(
    "HMB runtime resource cleanliness regression: PASS "
    "(exact runtime closure, .venv preservation, no bytecode debris)"
)
