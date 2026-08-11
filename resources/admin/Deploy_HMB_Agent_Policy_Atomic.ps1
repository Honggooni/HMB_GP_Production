#Requires -Version 5.1
#Requires -RunAsAdministrator

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$SourcePolicy,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedSourceSha256,

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

$sourceItem = Get-Item -LiteralPath $SourcePolicy -Force -ErrorAction Stop
if ($sourceItem.PSIsContainer -or
    ($sourceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "SourcePolicy must be a regular, non-reparse file."
}
if ([System.IO.Path]::GetExtension($sourceItem.Name) -ine ".dat") {
    throw "SourcePolicy must have the .dat extension."
}
$sourcePath = $sourceItem.FullName
if (
    (Test-HmbPathIsSameOrChild -Candidate $sourcePath -Parent $script:HmbPolicyPhysicalRoot) -or
    (Test-HmbPathIsSameOrChild -Candidate $script:HmbPolicyPhysicalRoot -Parent $sourcePath)
) {
    throw "SourcePolicy must be staged outside D:\agent."
}
Invoke-HmbPolicyArtifactVerifier `
    -Path $sourcePath `
    -ExpectedSha256 $ExpectedSourceSha256 `
    -LibraryRoot $LibraryRoot `
    -PythonExe $PythonExe

$expectedSourceHash = $ExpectedSourceSha256.ToLowerInvariant()
$expectedCurrentHash = $ExpectedCurrentSha256.ToLowerInvariant()
if ($expectedSourceHash -eq $expectedCurrentHash) {
    throw "The source and current policy hashes are identical; no deployment is needed."
}
$currentHash = Get-HmbPolicySha256 -Path $script:HmbPolicyLiveFile
if ($currentHash -ne $expectedCurrentHash) {
    throw "The live policy changed or does not match ExpectedCurrentSha256."
}

$backupName = New-HmbPolicyBackupName -Sha256 $currentHash
$backupPath = Join-Path $script:HmbPolicyBackupRoot $backupName
$stagePath = Join-Path $script:HmbPolicyBackupRoot (
    "hmb_agent_core.stage.{0}.{1}.dat" -f
    $expectedSourceHash,
    [guid]::NewGuid().ToString("N")
)
$automaticRestorePath = Join-Path $script:HmbPolicyBackupRoot (
    "hmb_agent_core.restore.{0}.{1}.dat" -f
    $currentHash,
    [guid]::NewGuid().ToString("N")
)
foreach ($path in @($backupPath, $stagePath, $automaticRestorePath)) {
    if (Test-Path -LiteralPath $path) {
        throw "A generated deployment path already exists; nothing was changed."
    }
}

$operation = (
    "Back up {0}, verify the signed replacement, then atomically replace the live policy" -f
    $script:HmbPolicyLiveFile
)
if (-not $PSCmdlet.ShouldProcess($script:HmbPolicyServerFqdn, $operation)) {
    return
}

$switched = $false
$deploymentSucceeded = $false
try {
    Copy-HmbPolicyFileWithFlush `
        -Source $script:HmbPolicyLiveFile -Destination $backupPath
    Set-HmbPolicyAdminFileAcl -Path $backupPath `
        -IdentityContext $identityContext
    if ((Get-HmbPolicySha256 -Path $backupPath) -ne $currentHash) {
        throw "The administrator-only backup does not match the pre-deployment live file."
    }

    Copy-HmbPolicyFileWithFlush -Source $sourcePath -Destination $stagePath
    Set-HmbPolicyLiveFileAcl -Path $stagePath `
        -IdentityContext $identityContext
    Invoke-HmbPolicyArtifactVerifier `
        -Path $stagePath `
        -ExpectedSha256 $expectedSourceHash `
        -LibraryRoot $LibraryRoot `
        -PythonExe $PythonExe

    if ((Get-HmbPolicySha256 -Path $script:HmbPolicyLiveFile) -ne $currentHash) {
        throw "The live policy changed after backup and before the atomic switch."
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
        -ExpectedSha256 $expectedSourceHash `
        -LibraryRoot $LibraryRoot `
        -PythonExe $PythonExe
    Assert-HmbPolicyDirectoryShape
    Assert-HmbPolicyAclState -IdentityContext $identityContext
    Assert-HmbPolicyShareState -IdentityContext $identityContext
    $deploymentSucceeded = $true
} catch {
    $deploymentError = $_
    if ($switched) {
        try {
            Copy-HmbPolicyFileWithFlush `
                -Source $backupPath -Destination $automaticRestorePath
            Set-HmbPolicyLiveFileAcl -Path $automaticRestorePath `
                -IdentityContext $identityContext
            if ((Get-HmbPolicySha256 -Path $automaticRestorePath) -ne $currentHash) {
                throw "Automatic restoration staging hash mismatch."
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
                throw "Automatic restoration live hash mismatch."
            }
            Assert-HmbPolicyAclState -IdentityContext $identityContext
        } catch {
            throw (
                "Deployment failed and automatic restoration also failed. " +
                "Deployment: {0}; restoration: {1}" -f
                $deploymentError.Exception.Message,
                $_.Exception.Message
            )
        }
        throw (
            "Deployment failed; the previous live bytes were atomically restored. Cause: {0}" -f
            $deploymentError.Exception.Message
        )
    }
    throw $deploymentError
} finally {
    foreach ($temporaryPath in @($stagePath, $automaticRestorePath)) {
        if (Test-Path -LiteralPath $temporaryPath) {
            [System.IO.File]::Delete($temporaryPath)
        }
    }
}

if (-not $deploymentSucceeded) {
    throw "Deployment did not reach the verified success state."
}
Write-Host "ATOMIC_DEPLOY=PASS"
Write-Host "LIVE_SHA256=$expectedSourceHash"
Write-Host "BACKUP_PATH=$backupPath"
Write-Host "BACKUP_SHA256=$currentHash"
