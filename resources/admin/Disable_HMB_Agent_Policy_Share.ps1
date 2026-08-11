#Requires -Version 5.1
#Requires -RunAsAdministrator

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Readers,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PolicyAdmins,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedLiveSha256
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "HMB_Agent_Policy_Admin_Common.ps1")

Assert-HmbPolicyServerLocal
$identityContext = Get-HmbPolicyIdentityContext `
    -Readers $Readers -PolicyAdmins $PolicyAdmins
Assert-HmbPolicyDirectoryShape
Assert-HmbNoOverlappingNonAdministrativeShare -AllowExpectedShare
Assert-HmbPolicyAclState -IdentityContext $identityContext
Assert-HmbPolicyShareState -IdentityContext $identityContext
$expectedHash = $ExpectedLiveSha256.ToLowerInvariant()
if ((Get-HmbPolicySha256 -Path $script:HmbPolicyLiveFile) -ne $expectedHash) {
    throw "The live policy does not match ExpectedLiveSha256; share state was not changed."
}

$operation = (
    "Disable only the dedicated HMB policy share; retain hardened NTFS ACLs, live file, and backups"
)
if (-not $PSCmdlet.ShouldProcess($script:HmbPolicyServerFqdn, $operation)) {
    return
}

Remove-SmbShare -Name $script:HmbPolicyShareName -Force
if (Get-SmbShare -Name $script:HmbPolicyShareName -ErrorAction SilentlyContinue) {
    throw "The dedicated policy share could not be verified as disabled."
}
if (
    -not (Test-Path -LiteralPath $script:HmbPolicyLiveFile -PathType Leaf) -or
    -not (Test-Path -LiteralPath $script:HmbPolicyBackupRoot -PathType Container) -or
    (Get-HmbPolicySha256 -Path $script:HmbPolicyLiveFile) -ne $expectedHash
) {
    throw "The share was disabled, but retained local policy state needs administrator review."
}

Write-Host "SHARE_DISABLE=PASS"
Write-Host "LOCAL_LIVE=RETAINED SHA256=$expectedHash"
Write-Host "LOCAL_BACKUP=RETAINED ADMIN_ONLY"
