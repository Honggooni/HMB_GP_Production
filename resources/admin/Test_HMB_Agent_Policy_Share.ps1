[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PolicyUNC,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedSha256,

    [Parameter(Mandatory = $true)]
    [string]$LibraryRoot,

    [Parameter(Mandatory = $true)]
    [string]$PolicyAdmins,

    [string]$PythonExe = "python",
    [string]$ExpectedServerName = "FIN-RCOMP1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (
    -not $PolicyUNC.StartsWith("\\") -or
    $PolicyUNC.StartsWith("\\?\") -or
    $PolicyUNC.StartsWith("\\.\")
) {
    throw "PolicyUNC must be a normal UNC path."
}
$uncParts = $PolicyUNC.Substring(2).Split([char]'\')
if (
    $uncParts.Count -ne 3 -or
    $uncParts[0] -ine $ExpectedServerName -or
    [string]::IsNullOrWhiteSpace($uncParts[1]) -or
    $uncParts[2] -ine "hmb_agent_core.dat"
) {
    throw "PolicyUNC must identify the dedicated policy file on $ExpectedServerName."
}
if ($ExpectedSha256 -notmatch '^[0-9A-Fa-f]{64}$') {
    throw "ExpectedSha256 must contain exactly 64 hexadecimal characters."
}
$expectedHash = $ExpectedSha256.ToLowerInvariant()
$resolvedLibraryRoot = (Resolve-Path -LiteralPath $LibraryRoot).Path
if (-not (Test-Path -LiteralPath (
    Join-Path $resolvedLibraryRoot "_hmb_common.py"
) -PathType Leaf)) {
    throw "LibraryRoot does not contain _hmb_common.py."
}
[void](Get-Command -Name $PythonExe -ErrorAction Stop)

$sidType = [System.Security.Principal.SecurityIdentifier]
$policyAdminSid = ([System.Security.Principal.NTAccount]::new(
    $PolicyAdmins
)).Translate($sidType)
$builtinAdminsSid = [System.Security.Principal.SecurityIdentifier]::new(
    "S-1-5-32-544"
)
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$tokenSidValues = @($identity.User.Value)
$tokenSidValues += @($identity.Groups | ForEach-Object { $_.Value })
if (
    $tokenSidValues -contains $policyAdminSid.Value -or
    $tokenSidValues -contains $builtinAdminsSid.Value
) {
    throw "Run this test as an ordinary Reader, not as PolicyAdmins/Administrator."
}

$shareRoot = Split-Path -Parent $PolicyUNC
$deleteProbe = Join-Path $shareRoot "__acl_delete_probe.tmp"
$renameProbe = Join-Path $shareRoot (
    "__acl_rename_probe_{0}.tmp" -f [guid]::NewGuid().ToString("N")
)
$createProbe = Join-Path $shareRoot (
    "__acl_create_probe_{0}.tmp" -f [guid]::NewGuid().ToString("N")
)

if (-not (Test-Path -LiteralPath $PolicyUNC -PathType Leaf)) {
    throw "READ=FAIL: policy file is unavailable."
}
$handle = [System.IO.File]::Open(
    $PolicyUNC,
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    [System.IO.FileShare]::Read
)
$handle.Dispose()
$policyHash = (
    Get-FileHash -LiteralPath $PolicyUNC -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($policyHash -ne $expectedHash) {
    throw "READ=FAIL: policy SHA-256 does not match the administrator value."
}
Write-Host "READ=PASS SHA256=$policyHash"

function Test-IsAccessDeniedException {
    param(
        [Parameter(Mandatory = $true)]
        [System.Exception]$Exception
    )

    $current = $Exception
    while ($null -ne $current) {
        if ($current -is [System.UnauthorizedAccessException]) {
            return $true
        }
        if (($current.HResult -band 0xFFFF) -eq 5) {
            return $true
        }
        $current = $current.InnerException
    }
    return $false
}

function Invoke-ExpectedAccessDenied {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Operation,
        [scriptblock]$UnexpectedSuccessCleanup
    )

    $denied = $false
    try {
        & $Operation
    } catch {
        if (Test-IsAccessDeniedException -Exception $_.Exception) {
            $denied = $true
        } else {
            throw "$Label=INCONCLUSIVE: an error other than access denied occurred."
        }
    }
    if (-not $denied) {
        if ($null -ne $UnexpectedSuccessCleanup) {
            try { & $UnexpectedSuccessCleanup } catch {}
        }
        throw "$Label=FAIL: the Reader operation was allowed."
    }
    Write-Host "$Label=PASS (access denied)"
}

if (Test-Path -LiteralPath $createProbe) {
    throw "CREATE=INCONCLUSIVE: generated probe path already exists."
}
Invoke-ExpectedAccessDenied -Label "CREATE" -Operation {
    $created = [System.IO.File]::Open(
        $createProbe,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    $created.Dispose()
} -UnexpectedSuccessCleanup {
    [System.IO.File]::Delete($createProbe)
}
if (Test-Path -LiteralPath $createProbe) {
    throw "CREATE=INCONCLUSIVE: failed attempt left a file behind."
}

if (-not (Test-Path -LiteralPath $deleteProbe -PathType Leaf)) {
    throw "The administrator-created ACL probe is missing."
}
if (Test-Path -LiteralPath $renameProbe) {
    throw "RENAME=INCONCLUSIVE: generated target path already exists."
}
Invoke-ExpectedAccessDenied -Label "RENAME" -Operation {
    [System.IO.File]::Move($deleteProbe, $renameProbe)
} -UnexpectedSuccessCleanup {
    if (Test-Path -LiteralPath $renameProbe) {
        [System.IO.File]::Move($renameProbe, $deleteProbe)
    }
}
if (
    -not (Test-Path -LiteralPath $deleteProbe -PathType Leaf) -or
    (Test-Path -LiteralPath $renameProbe)
) {
    throw "RENAME=INCONCLUSIVE: probe state changed unexpectedly."
}

Invoke-ExpectedAccessDenied -Label "DELETE" -Operation {
    [System.IO.File]::Delete($deleteProbe)
}
if (-not (Test-Path -LiteralPath $deleteProbe -PathType Leaf)) {
    throw "DELETE=FAIL: the Reader deleted the administrator probe."
}

$previousProcessPolicy = $env:HMB_AGENT_POLICY_PATH
$env:HMB_AGENT_POLICY_PATH = $PolicyUNC
$loaderPassed = $false
try {
    $pythonCode = @'
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import _hmb_common as common
payload = common._load_agent_rule_payload()
policy, binding = common.get_internal_policy_documents()
if not isinstance(payload, dict) or not policy.strip() or not binding.strip():
    raise RuntimeError("signed policy payload is incomplete")
print("LOADER=PASS SIGNATURE=VALID")
'@
    & $PythonExe -c $pythonCode $resolvedLibraryRoot
    if ($LASTEXITCODE -ne 0) {
        throw "LOADER=FAIL: signed policy validation failed."
    }
    $loaderPassed = $true
} finally {
    if (-not $loaderPassed) {
        if ($null -eq $previousProcessPolicy) {
            Remove-Item Env:HMB_AGENT_POLICY_PATH -ErrorAction SilentlyContinue
        } else {
            $env:HMB_AGENT_POLICY_PATH = $previousProcessPolicy
        }
    }
}

[Environment]::SetEnvironmentVariable(
    "HMB_AGENT_POLICY_PATH",
    $PolicyUNC,
    "User"
)
Write-Host "HMB_AGENT_POLICY_PATH configured for the current user."
Write-Host "Restart Griptape, then run the HMB Agent policy regressions."
