#Requires -Version 5.1
#Requires -RunAsAdministrator

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$BackupPolicy,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedBackupSha256,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedCurrentSha256,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Readers,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PolicyAdmins,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$TargetLibraryRoot,

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

$backupItem = Get-Item -LiteralPath $BackupPolicy -Force -ErrorAction Stop
if ($backupItem.PSIsContainer -or
    ($backupItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "BackupPolicy must be a regular, non-reparse file."
}
$backupPath = $backupItem.FullName
$backupParent = [System.IO.Path]::GetFullPath(
    (Split-Path -Parent $backupPath)
).TrimEnd("\")
if ($backupParent -ine $script:HmbPolicyBackupRoot) {
    throw "BackupPolicy must be an immediate file in D:\agent\backup."
}
Invoke-HmbPolicyArtifactVerifier `
    -Path $backupPath `
    -ExpectedSha256 $ExpectedBackupSha256 `
    -LibraryRoot $TargetLibraryRoot `
    -PythonExe $PythonExe

$expectedBackupHash = $ExpectedBackupSha256.ToLowerInvariant()
$expectedCurrentHash = $ExpectedCurrentSha256.ToLowerInvariant()
if ($expectedBackupHash -eq $expectedCurrentHash) {
    throw "The selected backup already matches the live hash; no rollback is needed."
}
$currentHash = Get-HmbPolicySha256 -Path $script:HmbPolicyLiveFile
if ($currentHash -ne $expectedCurrentHash) {
    throw "The live policy changed or does not match ExpectedCurrentSha256."
}

$safetyBackupName = New-HmbPolicyBackupName -Sha256 $currentHash
$safetyBackupPath = Join-Path $script:HmbPolicyBackupRoot $safetyBackupName
$stagePath = Join-Path $script:HmbPolicyBackupRoot (
    "hmb_agent_core.stage.{0}.{1}.dat" -f
    $expectedBackupHash,
    [guid]::NewGuid().ToString("N")
)
$automaticRestorePath = Join-Path $script:HmbPolicyBackupRoot (
    "hmb_agent_core.restore.{0}.{1}.dat" -f
    $currentHash,
    [guid]::NewGuid().ToString("N")
)
foreach ($path in @($safetyBackupPath, $stagePath, $automaticRestorePath)) {
    if (Test-Path -LiteralPath $path) {
        throw "A generated rollback path already exists; nothing was changed."
    }
}

$operation = (
    "Create a safety backup, verify the selected backup, then atomically roll back the live policy"
)
if (-not $PSCmdlet.ShouldProcess($script:HmbPolicyServerFqdn, $operation)) {
    return
}

$switched = $false
$rollbackSucceeded = $false
try {
    Copy-HmbPolicyFileWithFlush `
        -Source $script:HmbPolicyLiveFile -Destination $safetyBackupPath
    Set-HmbPolicyAdminFileAcl -Path $safetyBackupPath `
        -IdentityContext $identityContext
    if ((Get-HmbPolicySha256 -Path $safetyBackupPath) -ne $currentHash) {
        throw "The pre-rollback safety backup hash does not match the live file."
    }

    Copy-HmbPolicyFileWithFlush -Source $backupPath -Destination $stagePath
    Set-HmbPolicyLiveFileAcl -Path $stagePath `
        -IdentityContext $identityContext
    Invoke-HmbPolicyArtifactVerifier `
        -Path $stagePath `
        -ExpectedSha256 $expectedBackupHash `
        -LibraryRoot $TargetLibraryRoot `
        -PythonExe $PythonExe
    if ((Get-HmbPolicySha256 -Path $script:HmbPolicyLiveFile) -ne $currentHash) {
        throw "The live policy changed after the safety backup and before rollback."
    }

    [System.IO.File]::Replace(
        $stagePath,
        $script:HmbPolicyLiveFile,
        $null,
        $true
    )
    $switched = $true
    Set-HmbPolicyLiveFileAcl -Path $script:HmbPolicyLiveFile `
        -IdentityContext $identityContext
    Invoke-HmbPolicyArtifactVerifier `
        -Path $script:HmbPolicyLiveFile `
        -ExpectedSha256 $expectedBackupHash `
        -LibraryRoot $TargetLibraryRoot `
        -PythonExe $PythonExe
    Assert-HmbPolicyDirectoryShape
    Assert-HmbPolicyAclState -IdentityContext $identityContext
    Assert-HmbPolicyShareState -IdentityContext $identityContext
    $rollbackSucceeded = $true
} catch {
    $rollbackError = $_
    if ($switched) {
        try {
            Copy-HmbPolicyFileWithFlush `
                -Source $safetyBackupPath -Destination $automaticRestorePath
            Set-HmbPolicyLiveFileAcl -Path $automaticRestorePath `
                -IdentityContext $identityContext
            if ((Get-HmbPolicySha256 -Path $automaticRestorePath) -ne $currentHash) {
                throw "Automatic re-restoration staging hash mismatch."
            }
            [System.IO.File]::Replace(
                $automaticRestorePath,
                $script:HmbPolicyLiveFile,
                $null,
                $true
            )
            Set-HmbPolicyLiveFileAcl -Path $script:HmbPolicyLiveFile `
                -IdentityContext $identityContext
            if ((Get-HmbPolicySha256 -Path $script:HmbPolicyLiveFile) -ne $currentHash) {
                throw "Automatic re-restoration live hash mismatch."
            }
            Assert-HmbPolicyAclState -IdentityContext $identityContext
        } catch {
            throw (
                "Rollback failed and automatic re-restoration also failed. " +
                "Rollback: {0}; re-restoration: {1}" -f
                $rollbackError.Exception.Message,
                $_.Exception.Message
            )
        }
        throw (
            "Rollback failed; the pre-rollback live bytes were atomically restored. Cause: {0}" -f
            $rollbackError.Exception.Message
        )
    }
    throw $rollbackError
} finally {
    foreach ($temporaryPath in @($stagePath, $automaticRestorePath)) {
        if (Test-Path -LiteralPath $temporaryPath) {
            [System.IO.File]::Delete($temporaryPath)
        }
    }
}

if (-not $rollbackSucceeded) {
    throw "Rollback did not reach the verified success state."
}
Write-Host "ATOMIC_ROLLBACK=PASS"
Write-Host "LIVE_SHA256=$expectedBackupHash"
Write-Host "SAFETY_BACKUP_PATH=$safetyBackupPath"
Write-Host "SAFETY_BACKUP_SHA256=$currentHash"
