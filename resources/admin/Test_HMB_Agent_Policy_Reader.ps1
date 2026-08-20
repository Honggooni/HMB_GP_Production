#Requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Readers,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PolicyAdmins,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedSha256,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$LibraryRoot,

    [ValidateNotNullOrEmpty()]
    [string]$PythonExe = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "HMB_Agent_Policy_Admin_Common.ps1")

$identityContext = Get-HmbPolicyIdentityContext `
    -Readers $Readers -PolicyAdmins $PolicyAdmins
$shareRoot = "\\$script:HmbPolicyServerFqdn\$script:HmbPolicyShareName"
$hardenedPathsKey = (
    "HKLM:\SOFTWARE\Policies\Microsoft\Windows\NetworkProvider\HardenedPaths"
)
if (-not (Test-Path -LiteralPath $hardenedPathsKey)) {
    throw "CLIENT_HARDENED_UNC=FAIL: the HardenedPaths policy key is missing."
}
$hardenedProperties = Get-ItemProperty -LiteralPath $hardenedPathsKey
$property = $hardenedProperties.PSObject.Properties[$shareRoot]
if ($null -eq $property) {
    throw "CLIENT_HARDENED_UNC=FAIL: the exact dedicated share entry is missing."
}
$hardenedValue = [string]$property.Value
$requiredHardenedTokens = @(
    "RequireMutualAuthentication=1",
    "RequireIntegrity=1",
    "RequirePrivacy=1"
)
foreach ($token in $requiredHardenedTokens) {
    $escapedToken = [regex]::Escape($token)
    if ($hardenedValue -notmatch "(?:^|,)\s*$escapedToken\s*(?:,|$)") {
        throw "CLIENT_HARDENED_UNC=FAIL: required protection is missing for the exact share."
    }
}
Write-Host "CLIENT_HARDENED_UNC=PASS"

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$tokenSids = @($identity.User.Value)
$tokenSids += @($identity.Groups | ForEach-Object { $_.Value })
if ($tokenSids -notcontains $identityContext.ReaderSid.Value) {
    throw "Run this test as an approved Readers identity."
}
if (
    $tokenSids -contains $identityContext.PolicyAdminSid.Value -or
    $tokenSids -contains $identityContext.BuiltinAdminsSid.Value
) {
    throw "Run this test as a non-administrative Reader, not PolicyAdmins/Administrator."
}

if (-not (Test-Path -LiteralPath $script:HmbPolicyUnc -PathType Leaf)) {
    throw "READER_READ=FAIL: the dedicated policy UNC is unavailable."
}
$actualHash = Get-HmbPolicySha256 -Path $script:HmbPolicyUnc
if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) {
    throw "READER_READ=FAIL: live policy SHA-256 does not match."
}
Write-Host "READER_READ=PASS SHA256=$actualHash"

$writeHandle = $null
try {
    $writeHandle = [System.IO.File]::Open(
        $script:HmbPolicyUnc,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::Read
    )
} catch [System.UnauthorizedAccessException] {
    Write-Host "READER_WRITE_OPEN=PASS (access denied)"
} catch {
    if (($_.Exception.HResult -band 0xFFFF) -eq 5) {
        Write-Host "READER_WRITE_OPEN=PASS (access denied)"
    } else {
        throw "READER_WRITE_OPEN=INCONCLUSIVE: unexpected transport or filesystem error."
    }
} finally {
    if ($null -ne $writeHandle) {
        $writeHandle.Dispose()
    }
}
if ($null -ne $writeHandle) {
    throw "READER_WRITE_OPEN=FAIL: the Reader obtained a write handle."
}

$visibleNames = @(Get-ChildItem -LiteralPath $shareRoot -Force |
    ForEach-Object { $_.Name })
if (
    $visibleNames.Count -ne 1 -or
    $visibleNames[0] -ine "hmb_agent_core.dat"
) {
    throw "ABE=FAIL: a Reader can enumerate an unexpected share entry."
}
if (Test-Path -LiteralPath (Join-Path $shareRoot "backup")) {
    throw "BACKUP_ISOLATION=FAIL: the Reader can reach the backup folder."
}
Write-Host "ABE=PASS BACKUP_ISOLATION=PASS"

$connections = @(Get-SmbConnection | Where-Object {
    [string]$_.ShareName -ieq $script:HmbPolicyShareName -and
    [string]$_.ServerName -in @(
        $script:HmbPolicyServerFqdn,
        $script:HmbPolicyServerNetBios
    )
})
if ($connections.Count -ne 1) {
    throw "SMB_TRANSPORT=FAIL: exactly one dedicated FQDN policy connection is required."
}
$dialect = [version]([string]$connections[0].Dialect)
if ($dialect.Major -lt 3 -or -not [bool]$connections[0].Encrypted) {
    throw "SMB_TRANSPORT=FAIL: SMB 3 encryption is not active for the policy share."
}
Write-Host "SMB_TRANSPORT=PASS DIALECT=$dialect ENCRYPTED=True"

$resolvedRoot = (Resolve-Path -LiteralPath $LibraryRoot -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRoot "_hmb_common.py") -PathType Leaf)) {
    throw "LibraryRoot does not contain _hmb_common.py."
}
[void](Get-Command -Name $PythonExe -ErrorAction Stop)
$pythonCode = @'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve(strict=True)
expected_sha256 = sys.argv[2].lower()
sys.path.insert(0, str(root))
import _hmb_common as common

encoded = common._read_agent_policy_envelope()
if hashlib.sha256(encoded).hexdigest() != expected_sha256:
    raise RuntimeError("runtime read hash mismatch")
payload = common._load_agent_rule_payload()
print("READER_LOADER=PASS " + json.dumps({
    "sha256": expected_sha256,
    "version": payload["final_policy_version"],
    "contract_sha256": payload["final_motion_look_policy_sha256"],
}, sort_keys=True, separators=(",", ":")))
'@
$loaderOutput = @(& $PythonExe -I -B -c $pythonCode `
    $resolvedRoot $ExpectedSha256.ToLowerInvariant() 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "READER_LOADER=FAIL: signed runtime validation failed."
}
$loaderLines = @($loaderOutput | ForEach-Object { [string]$_ } |
    Where-Object { $_.StartsWith("READER_LOADER=PASS ") })
if ($loaderLines.Count -ne 1) {
    throw "READER_LOADER=FAIL: verifier returned an unexpected result."
}
Write-Host $loaderLines[0]
Write-Host "READER_VERIFY=PASS"
