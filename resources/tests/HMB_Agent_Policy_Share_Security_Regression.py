from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = ROOT / "resources" / "admin" / "Configure_HMB_Agent_Policy_Share.ps1"
CLIENT_TEST = ROOT / "resources" / "admin" / "Test_HMB_Agent_Policy_Share.ps1"
FINALIZE_SCRIPT = (
    ROOT / "resources" / "admin" / "Finalize_HMB_Agent_Policy_Migration.ps1"
)
RUNBOOK = ROOT / "resources" / "admin" / "HMB_Agent_Policy_Share_Runbook.md"

server = SERVER_SCRIPT.read_text(encoding="utf-8")
client = CLIENT_TEST.read_text(encoding="utf-8")
finalize = FINALIZE_SCRIPT.read_text(encoding="utf-8")
runbook = RUNBOOK.read_text(encoding="utf-8")

for anchor in (
    "#Requires -RunAsAdministrator",
    "SupportsShouldProcess = $true",
    'ShareName = "HMB_AgentPolicy$"',
    "SetAccessRuleProtection($true, $false)",
    "ReadAndExecute",
    "FullControl",
    'CachingMode = "None"',
    "EncryptData = $true",
    "Revoke-SmbShareAccess",
    "Where-Object { -not $_.Special }",
    "already exposed by SMB share",
    "fully qualified local drive path",
    "ReparsePoint",
    "DeleteSubdirectoriesAndFiles",
    "Assert-ProtectedAcl",
    "$expectedShareRights",
    "Test_HMB_Agent_Policy_Share.ps1",
):
    assert anchor in server, anchor

assert "Composite_Team" not in server
assert 'FullAccess = @($Readers)' not in server
assert "Everyone FullControl" not in server

for anchor in (
    "READ=PASS",
    "ExpectedSha256",
    "Test-IsAccessDeniedException",
    "CREATE",
    "RENAME",
    "DELETE",
    "LOADER=PASS SIGNATURE=VALID",
    "__acl_delete_probe.tmp",
    "SetEnvironmentVariable",
    '"HMB_AGENT_POLICY_PATH"',
):
    assert anchor in client, anchor

assert "Remove-Item -LiteralPath $PolicyUNC" not in client
for anchor in (
    "#Requires -RunAsAdministrator",
    "ReaderValidationPassed",
    "ShouldProcess",
    "Policy SHA-256 verification failed; nothing was removed.",
    "Remove-Item -LiteralPath $LegacyPolicy -Force",
    "DEDICATED_POLICY=RETAINED",
):
    assert anchor in finalize, anchor
for anchor in (
    "HMB_AgentPolicy_Readers",
    "HMB_AgentPolicy_Admins",
    "Configure_HMB_Agent_Policy_Share.ps1",
    "Test_HMB_Agent_Policy_Share.ps1",
    "Finalize_HMB_Agent_Policy_Migration.ps1",
    "LOADER=PASS SIGNATURE=VALID",
):
    assert anchor in runbook, anchor
assert "Composite_Team" not in runbook
assert not (ROOT / "resources" / "build_prompt_library_release.py").exists()

print("HMB dedicated Agent policy SMB/ACL scripts regression: PASS")
