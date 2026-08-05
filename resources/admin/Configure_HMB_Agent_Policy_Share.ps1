#Requires -RunAsAdministrator
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory = $true)]
    [string]$SecureContainer,

    [Parameter(Mandatory = $true)]
    [string]$Readers,

    [Parameter(Mandatory = $true)]
    [string]$PolicyAdmins,

    [Parameter(Mandatory = $true)]
    [string]$SourcePolicy,

    [string]$ShareName = "HMB_AgentPolicy$",
    [string]$ExpectedServerName = "FIN-RCOMP1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:COMPUTERNAME -ine $ExpectedServerName) {
    throw "Run this script locally on $ExpectedServerName in an elevated PowerShell window."
}
if (
    $SecureContainer -notmatch '^[A-Za-z]:\\' -or
    $SecureContainer.StartsWith("\\?\") -or
    $SecureContainer.StartsWith("\\.\")
) {
    throw "SecureContainer must be a fully qualified local drive path."
}
$containerPath = [System.IO.Path]::GetFullPath($SecureContainer).TrimEnd("\")
$containerRoot = [System.IO.Path]::GetPathRoot($containerPath).TrimEnd("\")
if ($containerPath -ieq $containerRoot) {
    throw "SecureContainer must not be a drive root."
}
if (-not (Test-Path -LiteralPath ([System.IO.Path]::GetPathRoot($containerPath)) -PathType Container)) {
    throw "SecureContainer drive does not exist."
}
if (Test-Path -LiteralPath $containerPath) {
    throw "SecureContainer already exists. Choose a new administrator-only path."
}
$containerParent = Split-Path -Parent $containerPath
if (-not (Test-Path -LiteralPath $containerParent -PathType Container)) {
    throw "SecureContainer parent directory does not exist."
}
if (-not (Test-Path -LiteralPath $SourcePolicy -PathType Leaf)) {
    throw "SourcePolicy does not exist."
}
if ([System.IO.Path]::GetExtension($SourcePolicy) -ine ".dat") {
    throw "SourcePolicy must be a .dat file."
}
if ($ShareName -notmatch '^[A-Za-z0-9_.-]+\$$') {
    throw "ShareName must be a valid hidden SMB share name ending in $."
}
if (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue) {
    throw "The requested SMB share already exists."
}

$sidType = [System.Security.Principal.SecurityIdentifier]
$readerSid = ([System.Security.Principal.NTAccount]::new($Readers)).Translate($sidType)
$policyAdminSid = ([System.Security.Principal.NTAccount]::new($PolicyAdmins)).Translate($sidType)
$systemSid = [System.Security.Principal.SecurityIdentifier]::new("S-1-5-18")
$builtinAdminsSid = [System.Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
$everyoneSid = [System.Security.Principal.SecurityIdentifier]::new("S-1-1-0")
$authenticatedUsersSid = [System.Security.Principal.SecurityIdentifier]::new("S-1-5-11")
$builtinUsersSid = [System.Security.Principal.SecurityIdentifier]::new("S-1-5-32-545")
if (
    $readerSid -eq $policyAdminSid -or
    $readerSid -eq $systemSid -or
    $readerSid -eq $builtinAdminsSid
) {
    throw "Readers must be separate from PolicyAdmins and local administrators."
}
if ($policyAdminSid -eq $systemSid -or $policyAdminSid -eq $builtinAdminsSid) {
    throw "PolicyAdmins must be a dedicated administration identity."
}
$builtinAdminsName = $builtinAdminsSid.Translate(
    [System.Security.Principal.NTAccount]
).Value
$everyoneName = $everyoneSid.Translate(
    [System.Security.Principal.NTAccount]
).Value

# Reject junctions/symlinks in every existing ancestor. Lexical path checks do
# not prove that a reparse point stays outside a broader share backing tree.
$ancestor = Get-Item -LiteralPath $containerParent -Force
while ($null -ne $ancestor) {
    if (($ancestor.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "SecureContainer ancestors must not contain reparse points."
    }
    $nextParent = Split-Path -Parent $ancestor.FullName
    if (-not $nextParent -or $nextParent -eq $ancestor.FullName) {
        break
    }
    $ancestor = Get-Item -LiteralPath $nextParent -Force
}

# A reader with FILE_DELETE_CHILD on the local parent could rename/delete the
# protected container without touching its own DACL. Refuse common broad
# principals and the configured Readers identity when that right applies.
$dangerousParentSids = @(
    $readerSid.Value,
    $everyoneSid.Value,
    $authenticatedUsersSid.Value,
    $builtinUsersSid.Value
)
$parentAcl = Get-Acl -LiteralPath $containerParent
$parentRules = $parentAcl.GetAccessRules(
    $true,
    $true,
    [System.Security.Principal.SecurityIdentifier]
)
foreach ($rule in $parentRules) {
    $isAllow = $rule.AccessControlType -eq (
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $isInheritOnly = ($rule.PropagationFlags -band (
        [System.Security.AccessControl.PropagationFlags]::InheritOnly
    )) -ne 0
    $hasDeleteChild = ($rule.FileSystemRights -band (
        [System.Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles
    )) -ne 0
    if (
        $isAllow -and
        -not $isInheritOnly -and
        $hasDeleteChild -and
        $dangerousParentSids -contains $rule.IdentityReference.Value
    ) {
        throw "SecureContainer parent grants Delete child to a reader/broad principal."
    }
}

# Refuse any location already reachable through another non-administrative
# share. Otherwise a broader share could bypass the new read-only share ACL.
foreach ($existingShare in Get-SmbShare | Where-Object { -not $_.Special }) {
    $existingPath = [string]$existingShare.Path
    if (-not [System.IO.Path]::IsPathRooted($existingPath)) {
        continue
    }
    $existingFullPath = [System.IO.Path]::GetFullPath($existingPath).TrimEnd("\")
    $existingPrefix = $existingFullPath + "\"
    if (
        $containerPath.Equals(
            $existingFullPath,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or
        $containerPath.StartsWith(
            $existingPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "SecureContainer is already exposed by SMB share $($existingShare.Name)."
    }
}

$policyRoot = Join-Path $containerPath "AgentPolicy"
$destinationPolicy = Join-Path $policyRoot "hmb_agent_core.dat"
$clientTestPath = Join-Path $policyRoot "Test_HMB_Agent_Policy_Share.ps1"
$clientTestSource = Join-Path $PSScriptRoot "Test_HMB_Agent_Policy_Share.ps1"
$deleteProbePath = Join-Path $policyRoot "__acl_delete_probe.tmp"
$uncPolicy = "\\$ExpectedServerName\$ShareName\hmb_agent_core.dat"
if (-not (Test-Path -LiteralPath $clientTestSource -PathType Leaf)) {
    throw "The companion client test script is missing beside this script."
}

function Set-ProtectedFolderAcl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [switch]$GrantReader
    )

    $acl = [System.Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner($builtinAdminsSid)
    $inheritance = [System.Security.AccessControl.InheritanceFlags](
        [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
        [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
    )
    $propagation = [System.Security.AccessControl.PropagationFlags]::None
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    foreach ($sid in @($systemSid, $builtinAdminsSid, $policyAdminSid)) {
        [void]$acl.AddAccessRule(
            [System.Security.AccessControl.FileSystemAccessRule]::new(
                $sid,
                [System.Security.AccessControl.FileSystemRights]::FullControl,
                $inheritance,
                $propagation,
                $allow
            )
        )
    }
    if ($GrantReader) {
        [void]$acl.AddAccessRule(
            [System.Security.AccessControl.FileSystemAccessRule]::new(
                $readerSid,
                [System.Security.AccessControl.FileSystemRights]::ReadAndExecute,
                $inheritance,
                $propagation,
                $allow
            )
        )
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

$operation = "Create protected policy folder and SMB share $ShareName"
if (-not $PSCmdlet.ShouldProcess($ExpectedServerName, $operation)) {
    return
}

New-Item -ItemType Directory -Path $containerPath | Out-Null
Set-ProtectedFolderAcl -Path $containerPath
New-Item -ItemType Directory -Path $policyRoot | Out-Null
Set-ProtectedFolderAcl -Path $policyRoot -GrantReader

$sourceHash = (Get-FileHash -LiteralPath $SourcePolicy -Algorithm SHA256).Hash
Copy-Item -LiteralPath $SourcePolicy -Destination $destinationPolicy
$destinationHash = (
    Get-FileHash -LiteralPath $destinationPolicy -Algorithm SHA256
).Hash
if ($sourceHash -ne $destinationHash) {
    throw "Policy SHA-256 mismatch after copy."
}

Copy-Item -LiteralPath $clientTestSource -Destination $clientTestPath
[System.IO.File]::WriteAllText(
    $deleteProbePath,
    "ACL verification probe. Do not use the policy file for delete tests.",
    [System.Text.UTF8Encoding]::new($false)
)

$shareParameters = @{
    Name = $ShareName
    Path = $policyRoot
    FullAccess = @($PolicyAdmins, $builtinAdminsName)
    ReadAccess = @($Readers)
    FolderEnumerationMode = "AccessBased"
    CachingMode = "None"
    EncryptData = $true
    Description = "HMB Agent policy - read-only clients"
}
New-SmbShare @shareParameters | Out-Null
$revokeParameters = @{
    Name = $ShareName
    AccountName = $everyoneName
    Force = $true
    ErrorAction = "SilentlyContinue"
}
Revoke-SmbShareAccess @revokeParameters | Out-Null

$createdShare = Get-SmbShare -Name $ShareName
if (
    $createdShare.Path -ine $policyRoot -or
    -not $createdShare.EncryptData -or
    [string]$createdShare.CachingMode -ine "None" -or
    [string]$createdShare.FolderEnumerationMode -ine "AccessBased"
) {
    throw "Created SMB share verification failed."
}

function Assert-ProtectedAcl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [bool]$ExpectProtected,
        [Parameter(Mandatory = $true)]
        [bool]$AllowReader
    )

    $actualAcl = Get-Acl -LiteralPath $Path
    if ($actualAcl.AreAccessRulesProtected -ne $ExpectProtected) {
        throw "Unexpected inheritance protection state: $Path"
    }
    $actualRules = $actualAcl.GetAccessRules(
        $true,
        $true,
        [System.Security.Principal.SecurityIdentifier]
    )
    $allowedSids = @(
        $systemSid.Value,
        $builtinAdminsSid.Value,
        $policyAdminSid.Value
    )
    if ($AllowReader) {
        $allowedSids += $readerSid.Value
    }
    $dangerousReaderRights = (
        [System.Security.AccessControl.FileSystemRights]::WriteData -bor
        [System.Security.AccessControl.FileSystemRights]::CreateFiles -bor
        [System.Security.AccessControl.FileSystemRights]::AppendData -bor
        [System.Security.AccessControl.FileSystemRights]::Delete -bor
        [System.Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [System.Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [System.Security.AccessControl.FileSystemRights]::TakeOwnership -bor
        [System.Security.AccessControl.FileSystemRights]::WriteAttributes -bor
        [System.Security.AccessControl.FileSystemRights]::WriteExtendedAttributes
    )
    foreach ($rule in $actualRules) {
        $sidValue = $rule.IdentityReference.Value
        if (
            $rule.AccessControlType -ne (
                [System.Security.AccessControl.AccessControlType]::Allow
            ) -or
            $allowedSids -notcontains $sidValue
        ) {
            throw "Unexpected NTFS access rule: $Path"
        }
        if ($sidValue -eq $readerSid.Value) {
            if (-not $AllowReader) {
                throw "Readers unexpectedly have access to the secure container."
            }
            if (
                ($rule.FileSystemRights -band $dangerousReaderRights) -ne 0 -or
                ($rule.FileSystemRights -band (
                    [System.Security.AccessControl.FileSystemRights]::ReadAndExecute
                )) -ne (
                    [System.Security.AccessControl.FileSystemRights]::ReadAndExecute
                )
            ) {
                throw "Readers do not have the required read-only NTFS rights."
            }
        } elseif (
            ($rule.FileSystemRights -band (
                [System.Security.AccessControl.FileSystemRights]::FullControl
            )) -ne (
                [System.Security.AccessControl.FileSystemRights]::FullControl
            )
        ) {
            throw "An administrative NTFS identity lacks FullControl: $Path"
        }
    }
    foreach ($requiredSid in $allowedSids) {
        if (-not ($actualRules | Where-Object {
            $_.IdentityReference.Value -eq $requiredSid
        })) {
            throw "A required NTFS access rule is missing: $Path"
        }
    }
}

Assert-ProtectedAcl -Path $containerPath -ExpectProtected $true -AllowReader $false
Assert-ProtectedAcl -Path $policyRoot -ExpectProtected $true -AllowReader $true
Assert-ProtectedAcl -Path $destinationPolicy -ExpectProtected $false -AllowReader $true
Assert-ProtectedAcl -Path $clientTestPath -ExpectProtected $false -AllowReader $true
Assert-ProtectedAcl -Path $deleteProbePath -ExpectProtected $false -AllowReader $true

$shareRules = @(Get-SmbShareAccess -Name $ShareName)
$expectedShareRights = @{
    $readerSid.Value = "Read"
    $policyAdminSid.Value = "Full"
    $builtinAdminsSid.Value = "Full"
}
$seenShareSids = @{}
foreach ($shareRule in $shareRules) {
    if ($shareRule.AccessControlType -ne "Allow") {
        throw "Unexpected SMB deny rule."
    }
    $shareSid = ([System.Security.Principal.NTAccount]::new(
        [string]$shareRule.AccountName
    )).Translate($sidType).Value
    if (-not $expectedShareRights.ContainsKey($shareSid)) {
        throw "Unexpected SMB access identity."
    }
    if ([string]$shareRule.AccessRight -ine $expectedShareRights[$shareSid]) {
        throw "Unexpected SMB access right."
    }
    $seenShareSids[$shareSid] = $true
}
foreach ($expectedSid in $expectedShareRights.Keys) {
    if (-not $seenShareSids.ContainsKey($expectedSid)) {
        throw "A required SMB access rule is missing."
    }
}

Write-Host "POLICY_UNC=$uncPolicy"
Write-Host "SHA256=$($destinationHash.ToLowerInvariant())"
Get-SmbShareAccess -Name $ShareName |
    Format-Table AccountName, AccessControlType, AccessRight
Get-Acl -LiteralPath $policyRoot |
    Select-Object -ExpandProperty Access |
    Format-Table IdentityReference, FileSystemRights, AccessControlType, IsInherited
