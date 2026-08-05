#Requires -RunAsAdministrator
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory = $true)]
    [string]$LegacyPolicy,

    [Parameter(Mandatory = $true)]
    [string]$PolicyUNC,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedSha256,

    [Parameter(Mandatory = $true)]
    [switch]$ReaderValidationPassed,

    [string]$ShareName = "HMB_AgentPolicy$",
    [string]$ExpectedServerName = "FIN-RCOMP1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:COMPUTERNAME -ine $ExpectedServerName) {
    throw "Run this script locally on $ExpectedServerName as Administrator."
}
if (-not $ReaderValidationPassed) {
    throw "Reader validation must pass before retiring the legacy copy."
}
if ($ExpectedSha256 -notmatch '^[0-9A-Fa-f]{64}$') {
    throw "ExpectedSha256 must contain exactly 64 hexadecimal characters."
}
$expectedHash = $ExpectedSha256.ToLowerInvariant()

function Get-ValidatedPolicyUncParts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (
        -not $Path.StartsWith("\\") -or
        $Path.StartsWith("\\?\") -or
        $Path.StartsWith("\\.\")
    ) {
        throw "Policy paths must be normal UNC paths."
    }
    $parts = $Path.Substring(2).Split([char]'\')
    if (
        $parts.Count -ne 3 -or
        $parts[0] -ine $ExpectedServerName -or
        [string]::IsNullOrWhiteSpace($parts[1]) -or
        $parts[2] -ine "hmb_agent_core.dat"
    ) {
        throw "Policy paths must identify hmb_agent_core.dat on $ExpectedServerName."
    }
    return $parts
}

$legacyParts = Get-ValidatedPolicyUncParts -Path $LegacyPolicy
$newParts = Get-ValidatedPolicyUncParts -Path $PolicyUNC
if ($legacyParts[1] -ieq $newParts[1]) {
    throw "LegacyPolicy and PolicyUNC must use different SMB shares."
}
if ($newParts[1] -ine $ShareName) {
    throw "PolicyUNC does not use the dedicated policy share."
}
if (-not (Test-Path -LiteralPath $LegacyPolicy -PathType Leaf)) {
    throw "The legacy policy copy is unavailable."
}
if (-not (Test-Path -LiteralPath $PolicyUNC -PathType Leaf)) {
    throw "The dedicated policy copy is unavailable."
}
$legacyHash = (
    Get-FileHash -LiteralPath $LegacyPolicy -Algorithm SHA256
).Hash.ToLowerInvariant()
$newHash = (
    Get-FileHash -LiteralPath $PolicyUNC -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($legacyHash -ne $expectedHash -or $newHash -ne $expectedHash) {
    throw "Policy SHA-256 verification failed; nothing was removed."
}

$share = Get-SmbShare -Name $ShareName
if (
    -not $share.EncryptData -or
    [string]$share.CachingMode -ine "None" -or
    [string]$share.FolderEnumerationMode -ine "AccessBased"
) {
    throw "Dedicated policy SMB security verification failed."
}

$operation = "Remove verified legacy policy copy after Reader validation"
if (-not $PSCmdlet.ShouldProcess($LegacyPolicy, $operation)) {
    return
}
Remove-Item -LiteralPath $LegacyPolicy -Force
if (Test-Path -LiteralPath $LegacyPolicy) {
    throw "Legacy policy removal could not be verified."
}
Write-Host "LEGACY_POLICY=REMOVED"
Write-Host "DEDICATED_POLICY=RETAINED SHA256=$newHash"
