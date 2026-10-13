"""Real filesystem observations, tampering and unsigned receipt boundaries."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_build_diagnostics as diag

with tempfile.TemporaryDirectory(prefix="hmb-build-diag-") as directory:
    root = Path(directory)
    for name in diag.RUNTIME_FILE_PATHS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic runtime " + name.encode())
    (root / "griptape-nodes-library.json").write_text(json.dumps({"metadata": {"library_version": "0.7.82"}}), encoding="utf-8")
    files = [{"path": name, "bytes": (root/name).stat().st_size,
              "sha256": hashlib.sha256((root/name).read_bytes()).hexdigest()} for name in diag.RUNTIME_FILE_PATHS]
    expected = diag.inventory_fingerprint(files)
    receipt = {"schema": "hmb-install-receipt", "version": 1, "release_version": "0.7.82",
               "runtime_fingerprint_sha256": expected, "build_fingerprint_sha256": "a"*64,
               "source_manifest_sha256": "b"*64, "installed_at": "2026-10-09T00:00:00Z", "runtime_files": files}
    (root/diag.RECEIPT_NAME).write_text(json.dumps(receipt), encoding="utf-8")
    untouched = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with mock.patch.object(diag, "_verify_policy", side_effect=AssertionError("explicitly disabled")):
        result = diag.get_build_diagnostics(root, verify_policy=False)
    assert result["runtime"]["fingerprint_sha256"] == expected
    assert result["install"]["receipt_status"] == "matches_recorded_inventory"
    assert result["channel"] == "local_even"
    assert result["policy"]["signature_status"] == "not_checked"
    assert result["policy"]["source_status"] == "not_inspected"
    assert untouched == {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    (root/"_hmb_common.py").write_bytes((ROOT/"_hmb_common.py").read_bytes())
    (root/"resources/agent/superwings12/hmb_agent_core.dat").write_bytes((ROOT/"resources/agent/superwings12/hmb_agent_core.dat").read_bytes())
    # Standalone signed verification must not initialize SDK/session modules or
    # produce bytecode in an otherwise empty diagnostic directory.
    paths_before = {str(path.relative_to(root)) for path in root.rglob("*")}
    standalone = diag.get_build_diagnostics(root)
    assert standalone["policy"]["signature_status"] == "verified"
    assert paths_before == {str(path.relative_to(root)) for path in root.rglob("*")}
    # A valid legacy SW signature cannot authorize either pending project.
    wrong_project = root / "resources/agent/Katuri8/hmb_agent_core.dat"
    wrong_project.write_bytes((ROOT/"resources/agent/superwings12/hmb_agent_core.dat").read_bytes())
    projects = {row["project_id"]: row for row in diag.get_build_diagnostics(root)["projects"]}
    assert projects["katuri8"]["signature_status"] == "invalid_or_verifier_unavailable"
    assert projects["katuri8"]["policy_version"] == ""
    wrong_project.unlink()
    (root/"_hmb_common.py").write_text("raise AssertionError('candidate trust code must never execute')", encoding="utf-8")
    assert diag.get_build_diagnostics(root)["policy"]["signature_status"] == "verified"
    for relative in ("_hmb_common.py", "resources/agent/superwings12/hmb_agent_core.dat"):
        (root/relative).write_bytes(untouched[root/relative])
    # Same version changed source bytes must be distinguishable and show only
    # a relative member identity, never source contents or machine paths.
    (root/"HMBSeedanceGeneration.py").write_bytes(b"secret fixture contents")
    tampered = diag.get_build_diagnostics(root, verify_policy=False)
    assert tampered["runtime"]["fingerprint_sha256"] != expected
    assert tampered["install"]["receipt_status"] == "mismatch"
    assert tampered["package"]["mismatch_paths"] == ["HMBSeedanceGeneration.py"]
    assert "secret fixture contents" not in json.dumps(tampered)
    assert str(root) not in json.dumps(tampered)
    (root/"HMBSeedanceGeneration.py").unlink()
    missing = diag.get_build_diagnostics(root, verify_policy=False)
    assert missing["runtime"]["fingerprint_sha256"] == ""
    assert missing["runtime"]["missing_paths"] == ["HMBSeedanceGeneration.py"]
    receipt["runtime_files"][0]["path"] = "../credential.json"
    (root/diag.RECEIPT_NAME).write_text(json.dumps(receipt), encoding="utf-8")
    assert diag.get_build_diagnostics(root, verify_policy=False)["install"]["receipt_status"] == "invalid"

# Real production signed DAT verification is read-only and does not synchronize
# the external Manager. An invalid signature must never become "verified".
before = (ROOT/"resources/agent/superwings12/hmb_agent_core.dat").read_bytes()
actual = diag.get_build_diagnostics(ROOT)
assert actual["policy"]["signature_status"] == "verified", actual["policy"]
project_status = {row["project_id"]: row for row in actual["projects"]}
assert project_status["superwings12"]["signature_status"] == "verified"
for project_id in ("dinoster5", "katuri8"):
    assert project_status[project_id]["status"] == "pending"
    assert project_status[project_id]["signature_status"] == "unavailable"
    assert project_status[project_id]["policy_version"] == ""
    assert project_status[project_id]["envelope_sha256"] == ""
assert before == (ROOT/"resources/agent/superwings12/hmb_agent_core.dat").read_bytes()
with mock.patch.object(diag, "_verify_policy", side_effect=ValueError("private decoded source")):
    invalid = diag.get_build_diagnostics(ROOT)
    assert invalid["policy"]["signature_status"] == "invalid_or_verifier_unavailable"
    assert "private decoded source" not in json.dumps(invalid)

# Execute only the installer fingerprint function, never the installer body or
# any install/move operation. Case/underscore ordering must match Python's
# ordinal ordering regardless of PowerShell culture.
if os.name == "nt":
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell, "Windows PowerShell parser required"
    rows = [{"path": "_hmb_review.py", "bytes": 1, "sha256": "a"*64},
            {"path": "HMBAgentLibrary.py", "bytes": 2, "sha256": "b"*64},
            {"path": "resources/agent/superwings12/hmb_agent_core.dat", "bytes": 3, "sha256": "c"*64}]
    command = r"""
$errors = $null; $tokens = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Installer parse errors' }
$definition = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-HmbInventoryFingerprint' }, $true)
Invoke-Expression $definition.Extent.Text
$rows = @([pscustomobject]@{path='_hmb_review.py';bytes=1;sha256=('a'*64)}, [pscustomobject]@{path='HMBAgentLibrary.py';bytes=2;sha256=('b'*64)}, [pscustomobject]@{path='resources/agent/superwings12/hmb_agent_core.dat';bytes=3;sha256=('c'*64)})
Get-HmbInventoryFingerprint -Items $rows
"""
    # Use environment for the fixed local file path, avoiding shell-built path
    # expressions and PowerShell -Command trailing argument interpretation.
    command = command.replace("$args[0]", "$env:HMB_INSTALLER_PARSE_PATH")
    env = dict(os.environ, HMB_INSTALLER_PARSE_PATH=str(ROOT/"Install_HMB_GP_Production.ps1"))
    completed = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
                               env=env, text=True, encoding="utf-8", capture_output=True, check=True)
    assert completed.stdout.strip() == diag.inventory_fingerprint(rows), completed.stdout
print("HMB build diagnostics regression: PASS (observed bytes, same-version drift, unsigned receipt, signed policy, no writes)")
