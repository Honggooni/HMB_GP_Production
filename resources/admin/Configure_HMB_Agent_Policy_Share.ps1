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
Assert-HmbPolicyDirectoryShape -AllowMissingBackup
Assert-HmbNoOverlappingNonAdministrativeShare
Invoke-HmbPolicyArtifactVerifier `
    -Path $script:HmbPolicyLiveFile `
    -ExpectedSha256 $ExpectedSha256 `
    -LibraryRoot $LibraryRoot `
    -PythonExe $PythonExe

$rootAclBefore = (Get-Acl -LiteralPath $script:HmbPolicyPhysicalRoot).Sddl
$liveAclBefore = (Get-Acl -LiteralPath $script:HmbPolicyLiveFile).Sddl
$backupExisted = Test-Path -LiteralPath $script:HmbPolicyBackupRoot -PathType Container
$backupAclBefore = $null
$backupFileAclsBefore = @{}
if ($backupExisted) {
    $backupAclBefore = (Get-Acl -LiteralPath $script:HmbPolicyBackupRoot).Sddl
    foreach ($file in @(Get-ChildItem -LiteralPath $script:HmbPolicyBackupRoot -File -Force)) {
        $backupFileAclsBefore[$file.FullName] = (Get-Acl -LiteralPath $file.FullName).Sddl
    }
}

function Restore-HmbFileAclFromSddl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Sddl,

        [Parameter(Mandatory = $true)]
        [ValidateSet("File", "Directory")]
        [string]$Kind
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    if ($Kind -eq "Directory") {
        $security = [System.Security.AccessControl.DirectorySecurity]::new()
    } else {
        $security = [System.Security.AccessControl.FileSecurity]::new()
    }
    $security.SetSecurityDescriptorSddlForm($Sddl)
    Set-Acl -LiteralPath $Path -AclObject $security
}

$operation = (
    "Protect D:\agent and create encrypted hidden share {0} for approved ACL identities" -f
    $script:HmbPolicyShareName
)
if (-not $PSCmdlet.ShouldProcess($script:HmbPolicyServerFqdn, $operation)) {
    return
}

$shareCreated = $false
$backupCreated = $false
try {
    Set-HmbPolicyRootAcl -IdentityContext $identityContext
    if (-not $backupExisted) {
        [void](New-Item -ItemType Directory -Path $script:HmbPolicyBackupRoot)
        $backupCreated = $true
    }
    Set-HmbPolicyBackupAcl -IdentityContext $identityContext
    foreach ($file in @(Get-ChildItem -LiteralPath $script:HmbPolicyBackupRoot -File -Force)) {
        Set-HmbPolicyAdminFileAcl -Path $file.FullName `
            -IdentityContext $identityContext
    }
    Set-HmbPolicyLiveFileAcl -Path $script:HmbPolicyLiveFile `
        -IdentityContext $identityContext

    $shareParameters = @{
        Name = $script:HmbPolicyShareName
        Path = $script:HmbPolicyPhysicalRoot
        FullAccess = @(
            $PolicyAdmins,
            $identityContext.BuiltinAdminsName
        )
        ReadAccess = @($Readers)
        EncryptData = $true
        CachingMode = "None"
        FolderEnumerationMode = "AccessBased"
        Description = "HMB Agent signed policy; live read-only, backup administrators only"
    }
    [void](New-SmbShare @shareParameters)
    $shareCreated = $true
    Revoke-SmbShareAccess `
        -Name $script:HmbPolicyShareName `
        -AccountName $identityContext.EveryoneName `
        -Force `
        -ErrorAction SilentlyContinue | Out-Null

    Assert-HmbPolicyDirectoryShape
    Assert-HmbNoOverlappingNonAdministrativeShare -AllowExpectedShare
    Assert-HmbPolicyAclState -IdentityContext $identityContext
    Assert-HmbPolicyShareState -IdentityContext $identityContext
    Invoke-HmbPolicyArtifactVerifier `
        -Path $script:HmbPolicyLiveFile `
        -ExpectedSha256 $ExpectedSha256 `
        -LibraryRoot $LibraryRoot `
        -PythonExe $PythonExe
} catch {
    $configurationError = $_
    $restoreErrors = [System.Collections.Generic.List[string]]::new()
    if ($shareCreated) {
        try {
            Remove-SmbShare -Name $script:HmbPolicyShareName -Force
        } catch {
            $restoreErrors.Add("share removal: $($_.Exception.Message)")
        }
    }
    foreach ($entry in $backupFileAclsBefore.GetEnumerator()) {
        try {
            Restore-HmbFileAclFromSddl `
                -Path $entry.Key -Sddl $entry.Value -Kind File
        } catch {
            $restoreErrors.Add("backup file ACL restore: $($_.Exception.Message)")
        }
    }
    if ($backupExisted -and $null -ne $backupAclBefore) {
        try {
            Restore-HmbFileAclFromSddl `
                -Path $script:HmbPolicyBackupRoot `
                -Sddl $backupAclBefore `
                -Kind Directory
        } catch {
            $restoreErrors.Add("backup folder ACL restore: $($_.Exception.Message)")
        }
    } elseif ($backupCreated) {
        try {
            if (@(Get-ChildItem -LiteralPath $script:HmbPolicyBackupRoot -Force).Count -eq 0) {
                Remove-Item -LiteralPath $script:HmbPolicyBackupRoot -Force
            } else {
                $restoreErrors.Add("new backup folder was not empty and was retained")
            }
        } catch {
            $restoreErrors.Add("new backup folder cleanup: $($_.Exception.Message)")
        }
    }
    try {
        Restore-HmbFileAclFromSddl `
            -Path $script:HmbPolicyLiveFile -Sddl $liveAclBefore -Kind File
    } catch {
        $restoreErrors.Add("live file ACL restore: $($_.Exception.Message)")
    }
    try {
        Restore-HmbFileAclFromSddl `
            -Path $script:HmbPolicyPhysicalRoot -Sddl $rootAclBefore -Kind Directory
    } catch {
        $restoreErrors.Add("root ACL restore: $($_.Exception.Message)")
    }
    if ($restoreErrors.Count -ne 0) {
        throw (
            "Configuration failed and automatic restoration was incomplete. Cause: {0}; restoration: {1}" -f
            $configurationError.Exception.Message,
            ($restoreErrors -join " | ")
        )
    }
    throw $configurationError
}

Write-Host "CONFIGURE=PASS"
Write-Host "POLICY_UNC=$script:HmbPolicyUnc"
Write-Host "PHYSICAL_PATH=$script:HmbPolicyLiveFile"
Write-Host "BACKUP_ACCESS=ADMIN_ONLY"
Write-Host "LIVE_ACCESS=READER_READ_ONLY"
Write-Host "SMB_ENCRYPTION=REQUIRED CACHING=NONE ABE=ENABLED"
