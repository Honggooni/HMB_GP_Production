from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_RESOURCES = {
    "resources/image_bash/compatibility.json",
    "resources/cgt/server-trust.json",
    "resources/maya/HMB_Maya_Background_Preview.py",
    "resources/blender/HMB_Blender_Background_Preview.py",
    "resources/picker/HMB_Marker_Catalog.json",
    "resources/agent/superwings12/hmb_agent_core.dat",
    "resources/agent/Dinoster5/project.json",
    "resources/agent/Katuri8/project.json",
    "resources/agent/superwings12/project.json",
}
DISTRIBUTION_ONLY_FILES = (
    "Install_HMB_GP_Production.ps1",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "SBOM.spdx.json",
    "tools/hmb_color_lut_native_header_patch.py",
    "tools/hmb_native_semantic_adapter.py",
    "resources/editor/hmb-color-lut-native-header.js",
    "resources/editor/hmb-shot-basket.js",
    "resources/editor/hmb-rodong-mart-launcher.webp",
    "resources/editor/hmb-rodong-mart-launcher-extra.webp",
    "resources/editor/hmb-rodong-mart-header.webp",
    "resources/editor/native-editor-patch.json",
    "tools/hmb_editor_0130_header.py",
    "tools/restore_rodong_local_editor.py",
    "tools/hmb_rodong_editor_0130.py",
    "tools/hmb_editor_0130_override.py",
    "resources/editor/hmb-header-0130.js",
    "resources/editor/hmb-rodong-editor-0130.js",
    "resources/editor/hmb-continue-work-art.js",
    "resources/editor/hmb-continue-work-01-10.webp",
    "resources/editor/hmb-continue-work-11-20.webp",
    "resources/editor/hmb-continue-work-21-30.webp",
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
diagnostics_spec = importlib.util.spec_from_file_location(
    "_hmb_runtime_diagnostics", ROOT / "_hmb_build_diagnostics.py"
)
assert diagnostics_spec is not None and diagnostics_spec.loader is not None
diagnostics = importlib.util.module_from_spec(diagnostics_spec)
diagnostics_spec.loader.exec_module(diagnostics)
# The diagnostic receipt reader must recognize the same independently packaged
# members. A valid installer receipt must not be rejected as an extra-file list.
assert len(diagnostics.RUNTIME_FILE_PATHS) == len(set(diagnostics.RUNTIME_FILE_PATHS)) == 69
assert set(diagnostics.RUNTIME_FILE_PATHS) == set(runtime_install_files)
distribution_only_files = tuple(packager.DISTRIBUTION_ONLY_FILES)
assert len(runtime_install_files) == 69
assert distribution_only_files == DISTRIBUTION_ONLY_FILES
assert source_files == (*runtime_install_files, *distribution_only_files)
assert len(source_files) == 91
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
assert "foreach ($relative in $retainedMembers)" in installer
assert "foreach ($record in $retainedRecords)" in installer
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
# Execute only the installer's manifest-count gate, never its install actions.
# Use the actual current package closure so a stale, hard-coded installer count
# cannot pass by sharing that same stale expectation in this regression.
release_version, package_sources = packager.validate_sources()
package_records = packager.make_release_records(release_version, package_sources)
package_manifest = json.loads(next(
    record["data"] for record in package_records
    if record["path"] == packager.RELEASE_MANIFEST_PATH
))
count_gate = installer.split("$records = @($manifest.files)", 1)[1].split(
    "$verifiedMembers =", 1
)[0]
assert "HMB release manifest install/distribution boundary mismatch." in count_gate
shell = shutil.which("pwsh") or shutil.which("powershell")
assert shell, "PowerShell is required to verify the real installer boundary."
fixtures = [{"name": "current_package", "accepted": True, "manifest": package_manifest}]
for key in ("file_count", "install_file_count", "distribution_file_count"):
    for offset in (-1, 1):
        changed = dict(package_manifest, **{key: package_manifest[key] + offset})
        fixtures.append({"name": f"{key}_{offset}", "accepted": False, "manifest": changed})
for label, files in (("missing_member", package_manifest["files"][:-1]),
                     ("extra_member", package_manifest["files"] + [package_manifest["files"][0]])):
    fixtures.append({"name": label, "accepted": False,
                     "manifest": dict(package_manifest, files=files, file_count=len(files))})
with tempfile.TemporaryDirectory(prefix="hmb-installer-count-gate-") as temporary:
    root = Path(temporary)
    (root / "fixtures.json").write_text(json.dumps(fixtures), encoding="utf-8")
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "function Test-ManifestBoundary { param($manifest)\n"
        "$records = @($manifest.files)\n" + count_gate + "}\n"
        "$fixtures = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'fixtures.json') | ConvertFrom-Json\n"
        "foreach ($fixture in $fixtures) {\n"
        "  $accepted = $true\n"
        "  try { Test-ManifestBoundary $fixture.manifest }\n"
        "  catch { if ($_.Exception.Message -notlike 'HMB release manifest*') { throw }; $accepted = $false }\n"
        "  if ($accepted -ne $fixture.accepted) { throw ('Unexpected package admission: ' + $fixture.name) }\n"
        "}\n"
        "Write-Output ('INSTALLER_COUNT_GATE_PASS cases=' + $fixtures.Count)\n"
    )
    script_path = root / "gate.ps1"
    script_path.write_text(script, encoding="utf-8-sig")
    checked = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-File", str(script_path)],
                             cwd=root, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=30)
assert checked.returncode == 0, checked.stdout + checked.stderr
assert "INSTALLER_COUNT_GATE_PASS cases=9" in checked.stdout
assert "_hmb_reference_leases.py" in runtime_install_files
assert "HMBImageGeneration.py" in runtime_install_files
assert "_hmb_image_generation.py" in runtime_install_files
assert "widgets/HMBImageGenerationWidget.js" in runtime_install_files
assert "widgets/HMBImageBashWidget.js" in runtime_install_files
assert "_hmb_agent_media.py" in runtime_install_files
assert "_hmb_build_diagnostics.py" in runtime_install_files
assert "_hmb_broker_config.py" in runtime_install_files
assert "_hmb_library_bootstrap.py" in runtime_install_files
assert "_hmb_deletion_guard.py" in runtime_install_files
assert "_hmb_connection_management.py" in runtime_install_files
assert "_hmb_workflow_migration.py" in runtime_install_files
assert "_hmb_workflow_serialization_compat.py" in runtime_install_files
assert "_hmb_image_limits.py" in runtime_install_files
assert "_hmb_review.py" in runtime_install_files
assert "_hmb_web_rerender.py" in runtime_install_files
assert "_hmb_color_lut_usage.py" in runtime_install_files
assert "hmb-install-receipt" in installer
assert "runtime_fingerprint_sha256" in installer
assert "foreach ($relative in $relocatedUserMembers)" in installer
assert "Remove-Item" not in installer
# Recovery journals are preserved user state, never shipped runtime members.
# Their directory name must not weaken the explicit archive allowlist.
assert "'.hmb-environment-backups'" in installer
assert not any("backup" in path.casefold() for path in source_files)
ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
for generated in (".venv-tos-stage-*/", ".hmb-environment-backups/",
                  ".hmb-tos-migration.lock", ".hmb-tos-prepare.lock",
                  ".hmb-tos-runtime-needed.json", ".hmb-tos-runtime-ready.json",
                  ".hmb-tos-runtime-*.json.*.tmp",
                  ".hmb-install-receipt.json"):
    assert generated in ignore.splitlines(), generated

picker = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")
assert not (ROOT / "HMB_Agent_Griptape.bat").exists()
assert 'env["PYTHONDONTWRITEBYTECODE"] = "1"' in picker
assert "sys.dont_write_bytecode=True" in picker

print(
    "HMB runtime resource cleanliness regression: PASS "
    "(exact runtime closure, .venv preservation, no launcher residue, "
    "Maya runner bytecode isolation)"
)
