#Requires -Version 5.1
#Requires -RunAsAdministrator

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

Assert-HmbPolicyServerLocal
Assert-HmbSmbServerBaseline
$identityContext = Get-HmbPolicyIdentityContext `
    -Readers $Readers -PolicyAdmins $PolicyAdmins
Assert-HmbPolicyDirectoryShape
Assert-HmbNoOverlappingNonAdministrativeShare -AllowExpectedShare
Assert-HmbPolicyAclState -IdentityContext $identityContext
Assert-HmbPolicyShareState -IdentityContext $identityContext
Invoke-HmbPolicyArtifactVerifier `
    -Path $script:HmbPolicyLiveFile `
    -ExpectedSha256 $ExpectedSha256 `
    -LibraryRoot $LibraryRoot `
    -PythonExe $PythonExe

$serverConfiguration = Get-SmbServerConfiguration
$share = Get-SmbShare -Name $script:HmbPolicyShareName
$backupCount = @(
    Get-ChildItem -LiteralPath $script:HmbPolicyBackupRoot -File -Force
).Count

Write-Host "SERVER_VERIFY=PASS"
Write-Host "POLICY_UNC=$script:HmbPolicyUnc"
Write-Host "PHYSICAL_ROOT=$script:HmbPolicyPhysicalRoot"
Write-Host "BACKUP_COUNT=$backupCount BACKUP_ACCESS=ADMIN_ONLY"
Write-Host "LIVE_ACCESS=READER_READ_ONLY"
Write-Host (
    "SMB2={0} REJECT_UNENCRYPTED={1} SHARE_ENCRYPTION={2} CACHING={3} ABE={4}" -f
    [bool]$serverConfiguration.EnableSMB2Protocol,
    [bool]$serverConfiguration.RejectUnencryptedAccess,
    [bool]$share.EncryptData,
    [string]$share.CachingMode,
    [string]$share.FolderEnumerationMode
)
