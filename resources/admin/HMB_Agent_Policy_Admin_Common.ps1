# Shared, non-executable helpers for the HMB Agent policy administration scripts.
# This file deliberately contains no policy text and never prints policy payloads.

$script:HmbPolicyServerNetBios = "FIN-RCOMP7"
$script:HmbPolicyServerFqdn = "FIN-RCOMP7.funnyflux.local"
$script:HmbPolicyPhysicalRoot = "D:\agent"
$script:HmbPolicyLiveFile = "D:\agent\hmb_agent_core.dat"
$script:HmbPolicyBackupRoot = "D:\agent\backup"
$script:HmbPolicyShareName = "HMB_AgentPolicy$"
$script:HmbPolicyUnc = (
    "\\{0}\{1}\hmb_agent_core.dat" -f
    $script:HmbPolicyServerFqdn,
    $script:HmbPolicyShareName
)
$script:HmbPolicyMaximumBytes = 128KB

function Assert-HmbPolicyServerLocal {
    if ($env:COMPUTERNAME -ine $script:HmbPolicyServerNetBios) {
        throw (
            "This script must run locally on {0}; current computer is {1}." -f
            $script:HmbPolicyServerNetBios,
            $env:COMPUTERNAME
        )
    }
    $root = [System.IO.Path]::GetFullPath($script:HmbPolicyPhysicalRoot).TrimEnd("\")
    if ($root -ine "D:\agent") {
        throw "The protected policy root is not the approved physical D:\agent path."
    }
}

function ConvertTo-HmbPolicySid {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Identity
    )

    try {
        return ([System.Security.Principal.NTAccount]::new($Identity)).Translate(
            [System.Security.Principal.SecurityIdentifier]
        )
    } catch {
        throw "Unable to resolve the supplied ACL identity: $Identity"
    }
}

function Get-HmbPolicyIdentityContext {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Readers,

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$PolicyAdmins
    )

    $readerSid = ConvertTo-HmbPolicySid -Identity $Readers
    $policyAdminSid = ConvertTo-HmbPolicySid -Identity $PolicyAdmins
    $systemSid = [System.Security.Principal.SecurityIdentifier]::new("S-1-5-18")
    $builtinAdminsSid = [System.Security.Principal.SecurityIdentifier]::new(
        "S-1-5-32-544"
    )
    $forbiddenReaderSids = @(
        "S-1-1-0",       # Everyone
        "S-1-5-11",      # Authenticated Users
        "S-1-5-32-545",  # BUILTIN\Users
        $systemSid.Value,
        $builtinAdminsSid.Value,
        $policyAdminSid.Value
    )
    $forbiddenAdminSids = @(
        "S-1-1-0",
        "S-1-5-11",
        "S-1-5-32-545",
        $systemSid.Value,
        $builtinAdminsSid.Value,
        $readerSid.Value
    )
    if ($forbiddenReaderSids -contains $readerSid.Value) {
        throw "Readers must be a dedicated, non-administrative identity."
    }
    if ($forbiddenAdminSids -contains $policyAdminSid.Value) {
        throw "PolicyAdmins must be a dedicated administration identity."
    }

    return [pscustomobject]@{
        Readers = $Readers
        PolicyAdmins = $PolicyAdmins
        ReaderSid = $readerSid
        PolicyAdminSid = $policyAdminSid
        SystemSid = $systemSid
        BuiltinAdminsSid = $builtinAdminsSid
        BuiltinAdminsName = $builtinAdminsSid.Translate(
            [System.Security.Principal.NTAccount]
        ).Value
        EveryoneName = (
            [System.Security.Principal.SecurityIdentifier]::new("S-1-1-0")
        ).Translate([System.Security.Principal.NTAccount]).Value
    }
}

function Test-HmbPathIsSameOrChild {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,

        [Parameter(Mandatory = $true)]
        [string]$Parent
    )

    $candidatePath = [System.IO.Path]::GetFullPath($Candidate).TrimEnd("\")
    $parentPath = [System.IO.Path]::GetFullPath($Parent).TrimEnd("\")
    return (
        $candidatePath.Equals(
            $parentPath,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or
        $candidatePath.StartsWith(
            $parentPath + "\",
            [System.StringComparison]::OrdinalIgnoreCase
        )
    )
}

function Assert-HmbNoReparsePoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Required protected path does not exist: $Path"
    }
    $item = Get-Item -LiteralPath $Path -Force
    while ($null -ne $item) {
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Protected policy paths must not contain reparse points: $($item.FullName)"
        }
        $parent = Split-Path -Parent $item.FullName
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $item.FullName) {
            break
        }
        $item = Get-Item -LiteralPath $parent -Force
    }
}

function Assert-HmbNoAlternateDataStreams {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $streamCommand = Get-Command -Name Get-Item -ErrorAction Stop
    if (-not $streamCommand.Parameters.ContainsKey("Stream")) {
        throw "NTFS alternate-stream inspection is unavailable on this host."
    }
    $streams = @(Get-Item -LiteralPath $Path -Stream * -ErrorAction Stop)
    $nonDefault = @($streams | Where-Object {
        [string]$_.Stream -notin @(':$DATA', '::$DATA')
    })
    if ($nonDefault.Count -ne 0) {
        throw "Alternate data streams are forbidden on protected policy files: $Path"
    }
}

function Assert-HmbPolicyDirectoryShape {
    param(
        [switch]$AllowMissingBackup
    )

    if (-not (Test-Path -LiteralPath $script:HmbPolicyPhysicalRoot -PathType Container)) {
        throw "The approved physical policy directory is missing: D:\agent"
    }
    if (-not (Test-Path -LiteralPath $script:HmbPolicyLiveFile -PathType Leaf)) {
        throw "The live hmb_agent_core.dat file is missing from D:\agent."
    }
    Assert-HmbNoReparsePoint -Path $script:HmbPolicyPhysicalRoot
    Assert-HmbNoReparsePoint -Path $script:HmbPolicyLiveFile
    Assert-HmbNoAlternateDataStreams -Path $script:HmbPolicyLiveFile

    $allowedNames = @("hmb_agent_core.dat", "backup")
    $unexpected = @(Get-ChildItem -LiteralPath $script:HmbPolicyPhysicalRoot -Force |
        Where-Object { $allowedNames -notcontains $_.Name })
    if ($unexpected.Count -ne 0) {
        throw (
            "D:\agent contains entries that would be exposed by the dedicated share: {0}" -f
            (($unexpected | ForEach-Object { $_.Name }) -join ", ")
        )
    }

    if (-not (Test-Path -LiteralPath $script:HmbPolicyBackupRoot)) {
        if ($AllowMissingBackup) {
            return
        }
        throw "The administrator-only D:\agent\backup folder is missing."
    }
    if (-not (Test-Path -LiteralPath $script:HmbPolicyBackupRoot -PathType Container)) {
        throw "D:\agent\backup is not a directory."
    }
    Assert-HmbNoReparsePoint -Path $script:HmbPolicyBackupRoot
    $backupEntries = @(Get-ChildItem -LiteralPath $script:HmbPolicyBackupRoot -Force)
    foreach ($entry in $backupEntries) {
        if (
            $entry.PSIsContainer -or
            ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $entry.Name -notmatch '^hmb_agent_core(?:\.[A-Za-z0-9_-]+)*\.[0-9A-Fa-f]{16,64}\.\d{8}T\d{6}(?:\d{3})?Z?\.dat$'
        ) {
            throw "Unexpected or unsafe entry in D:\agent\backup: $($entry.Name)"
        }
        Assert-HmbNoAlternateDataStreams -Path $entry.FullName
    }
}

function Assert-HmbNoOverlappingNonAdministrativeShare {
    param(
        [switch]$AllowExpectedShare
    )

    foreach ($share in @(Get-SmbShare -ErrorAction Stop)) {
        if ($share.Name -ieq $script:HmbPolicyShareName) {
            if (-not $AllowExpectedShare) {
                throw "The dedicated share already exists; verify it instead of recreating it."
            }
            continue
        }
        if ($share.Special) {
            # Administrative shares such as D$ are restricted to administrators.
            continue
        }
        $sharePath = [string]$share.Path
        if ([string]::IsNullOrWhiteSpace($sharePath) -or
            -not [System.IO.Path]::IsPathRooted($sharePath)) {
            continue
        }
        if (
            (Test-HmbPathIsSameOrChild -Candidate $script:HmbPolicyPhysicalRoot -Parent $sharePath) -or
            (Test-HmbPathIsSameOrChild -Candidate $sharePath -Parent $script:HmbPolicyPhysicalRoot)
        ) {
            throw (
                "A non-administrative SMB share overlaps D:\agent: {0} -> {1}" -f
                $share.Name,
                $share.Path
            )
        }
    }
}

function Assert-HmbSmbServerBaseline {
    $configuration = Get-SmbServerConfiguration -ErrorAction Stop
    if (
        -not $configuration.EnableSMB2Protocol -or
        -not $configuration.RejectUnencryptedAccess
    ) {
        throw (
            "SMB2+ and RejectUnencryptedAccess must both be enabled before " +
            "publishing the Agent policy share."
        )
    }
    # Global EncryptData may remain false. This boundary requires and verifies
    # encryption on HMB_AgentPolicy$ itself.
    $computerSystem = Get-CimInstance -ClassName Win32_ComputerSystem
    if (
        -not $computerSystem.PartOfDomain -or
        [string]$computerSystem.Domain -ine "funnyflux.local"
    ) {
        throw "FIN-RCOMP7 must remain joined to the funnyflux.local domain."
    }
}

function New-HmbDirectorySecurity {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext,

        [switch]$GrantReaderOnDirectory
    )

    $security = [System.Security.AccessControl.DirectorySecurity]::new()
    $security.SetAccessRuleProtection($true, $false)
    $security.SetOwner($IdentityContext.BuiltinAdminsSid)
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    $inheritance = [System.Security.AccessControl.InheritanceFlags](
        [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
        [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
    )
    foreach ($sid in @(
        $IdentityContext.SystemSid,
        $IdentityContext.BuiltinAdminsSid,
        $IdentityContext.PolicyAdminSid
    )) {
        [void]$security.AddAccessRule(
            [System.Security.AccessControl.FileSystemAccessRule]::new(
                $sid,
                [System.Security.AccessControl.FileSystemRights]::FullControl,
                $inheritance,
                [System.Security.AccessControl.PropagationFlags]::None,
                $allow
            )
        )
    }
    if ($GrantReaderOnDirectory) {
        [void]$security.AddAccessRule(
            [System.Security.AccessControl.FileSystemAccessRule]::new(
                $IdentityContext.ReaderSid,
                [System.Security.AccessControl.FileSystemRights]::ReadAndExecute,
                [System.Security.AccessControl.InheritanceFlags]::None,
                [System.Security.AccessControl.PropagationFlags]::None,
                $allow
            )
        )
    }
    return $security
}

function New-HmbFileSecurity {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext,

        [switch]$GrantReader
    )

    $security = [System.Security.AccessControl.FileSecurity]::new()
    $security.SetAccessRuleProtection($true, $false)
    $security.SetOwner($IdentityContext.BuiltinAdminsSid)
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    foreach ($sid in @(
        $IdentityContext.SystemSid,
        $IdentityContext.BuiltinAdminsSid,
        $IdentityContext.PolicyAdminSid
    )) {
        [void]$security.AddAccessRule(
            [System.Security.AccessControl.FileSystemAccessRule]::new(
                $sid,
                [System.Security.AccessControl.FileSystemRights]::FullControl,
                $allow
            )
        )
    }
    if ($GrantReader) {
        [void]$security.AddAccessRule(
            [System.Security.AccessControl.FileSystemAccessRule]::new(
                $IdentityContext.ReaderSid,
                [System.Security.AccessControl.FileSystemRights]::ReadAndExecute,
                $allow
            )
        )
    }
    return $security
}

function Set-HmbPolicyRootAcl {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext
    )
    $acl = New-HmbDirectorySecurity -IdentityContext $IdentityContext `
        -GrantReaderOnDirectory
    Set-Acl -LiteralPath $script:HmbPolicyPhysicalRoot -AclObject $acl
}

function Set-HmbPolicyBackupAcl {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext
    )
    $acl = New-HmbDirectorySecurity -IdentityContext $IdentityContext
    Set-Acl -LiteralPath $script:HmbPolicyBackupRoot -AclObject $acl
}

function Set-HmbPolicyAdminFileAcl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext
    )
    $acl = New-HmbFileSecurity -IdentityContext $IdentityContext
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Set-HmbPolicyLiveFileAcl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext
    )
    $acl = New-HmbFileSecurity -IdentityContext $IdentityContext -GrantReader
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Assert-HmbAcl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext,

        [Parameter(Mandatory = $true)]
        [bool]$AllowReader
    )

    $acl = Get-Acl -LiteralPath $Path
    if (-not $acl.AreAccessRulesProtected) {
        throw "NTFS ACL inheritance must be disabled: $Path"
    }
    $rules = @($acl.GetAccessRules(
        $true,
        $true,
        [System.Security.Principal.SecurityIdentifier]
    ))
    $allowedSids = @(
        $IdentityContext.SystemSid.Value,
        $IdentityContext.BuiltinAdminsSid.Value,
        $IdentityContext.PolicyAdminSid.Value
    )
    if ($AllowReader) {
        $allowedSids += $IdentityContext.ReaderSid.Value
    }
    $dangerousReaderRights = [System.Security.AccessControl.FileSystemRights](
        [System.Security.AccessControl.FileSystemRights]::Write -bor
        [System.Security.AccessControl.FileSystemRights]::Delete -bor
        [System.Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [System.Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [System.Security.AccessControl.FileSystemRights]::TakeOwnership
    )
    $seen = @{}
    foreach ($rule in $rules) {
        $sid = $rule.IdentityReference.Value
        if (
            $rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow -or
            $rule.IsInherited -or
            $allowedSids -notcontains $sid
        ) {
            throw "Unexpected NTFS access rule on protected path: $Path"
        }
        if ($sid -eq $IdentityContext.ReaderSid.Value) {
            if (
                -not $AllowReader -or
                ($rule.FileSystemRights -band $dangerousReaderRights) -ne 0 -or
                ($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::ReadAndExecute) -ne
                    [System.Security.AccessControl.FileSystemRights]::ReadAndExecute
            ) {
                throw "Readers do not have an exact read-only NTFS boundary: $Path"
            }
        } elseif (
            ($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -ne
                [System.Security.AccessControl.FileSystemRights]::FullControl
        ) {
            throw "A required administrator identity lacks FullControl: $Path"
        }
        $seen[$sid] = $true
    }
    foreach ($sid in $allowedSids) {
        if (-not $seen.ContainsKey($sid)) {
            throw "A required NTFS identity is missing from protected path: $Path"
        }
    }
}

function Assert-HmbPolicyAclState {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext
    )

    Assert-HmbAcl -Path $script:HmbPolicyPhysicalRoot `
        -IdentityContext $IdentityContext -AllowReader $true
    Assert-HmbAcl -Path $script:HmbPolicyLiveFile `
        -IdentityContext $IdentityContext -AllowReader $true
    Assert-HmbAcl -Path $script:HmbPolicyBackupRoot `
        -IdentityContext $IdentityContext -AllowReader $false
    foreach ($backup in @(Get-ChildItem -LiteralPath $script:HmbPolicyBackupRoot -File -Force)) {
        Assert-HmbAcl -Path $backup.FullName `
            -IdentityContext $IdentityContext -AllowReader $false
    }
}

function Assert-HmbPolicyShareState {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$IdentityContext
    )

    $share = Get-SmbShare -Name $script:HmbPolicyShareName -ErrorAction Stop
    if (
        [System.IO.Path]::GetFullPath([string]$share.Path).TrimEnd("\") -ine
            $script:HmbPolicyPhysicalRoot -or
        -not $share.EncryptData -or
        [string]$share.CachingMode -ine "None" -or
        [string]$share.FolderEnumerationMode -ine "AccessBased"
    ) {
        throw "The dedicated SMB share does not match the required hardened settings."
    }
    $expectedRights = @{
        $IdentityContext.ReaderSid.Value = "Read"
        $IdentityContext.PolicyAdminSid.Value = "Full"
        $IdentityContext.BuiltinAdminsSid.Value = "Full"
    }
    $seen = @{}
    foreach ($rule in @(Get-SmbShareAccess -Name $script:HmbPolicyShareName)) {
        if ([string]$rule.AccessControlType -ine "Allow") {
            throw "The dedicated SMB share contains an unexpected deny rule."
        }
        $sid = ConvertTo-HmbPolicySid -Identity ([string]$rule.AccountName)
        if (-not $expectedRights.ContainsKey($sid.Value)) {
            throw "The dedicated SMB share contains an unexpected identity."
        }
        if ([string]$rule.AccessRight -ine $expectedRights[$sid.Value]) {
            throw "The dedicated SMB share contains an unexpected access right."
        }
        $seen[$sid.Value] = $true
    }
    foreach ($sid in $expectedRights.Keys) {
        if (-not $seen.ContainsKey($sid)) {
            throw "The dedicated SMB share is missing a required identity."
        }
    }
}

function Get-HmbPolicySha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-HmbSha256Text {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )
    if ($Value -notmatch '^[0-9A-Fa-f]{64}$') {
        throw "$Name must contain exactly 64 hexadecimal characters."
    }
}

function Invoke-HmbPolicyArtifactVerifier {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedSha256,

        [Parameter(Mandatory = $true)]
        [string]$LibraryRoot,

        [ValidateNotNullOrEmpty()]
        [string]$PythonExe = "python"
    )

    Assert-HmbSha256Text -Value $ExpectedSha256 -Name "ExpectedSha256"
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Policy artifact does not exist: $Path"
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (
        ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
        $item.Length -le 0 -or
        $item.Length -gt $script:HmbPolicyMaximumBytes
    ) {
        throw "Policy artifact has an unsafe type or size: $Path"
    }
    Assert-HmbNoAlternateDataStreams -Path $Path
    $actualHash = Get-HmbPolicySha256 -Path $Path
    if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "Policy artifact SHA-256 does not match the caller-approved candidate value."
    }
    $resolvedRoot = (Resolve-Path -LiteralPath $LibraryRoot -ErrorAction Stop).Path
    $commonPath = Join-Path $resolvedRoot "_hmb_common.py"
    if (-not (Test-Path -LiteralPath $commonPath -PathType Leaf)) {
        throw "LibraryRoot does not contain the matching _hmb_common.py verifier."
    }
    [void](Get-Command -Name $PythonExe -ErrorAction Stop)

    $pythonCode = @'
import hashlib
import json
import sys
from pathlib import Path

library_root = Path(sys.argv[1]).resolve(strict=True)
artifact = Path(sys.argv[2]).resolve(strict=True)
expected_sha256 = sys.argv[3].lower()
sys.path.insert(0, str(library_root))
import _hmb_common as common

encoded = artifact.read_bytes()
if hashlib.sha256(encoded).hexdigest() != expected_sha256:
    raise RuntimeError("artifact hash changed during verification")
payload = common._decode_signed_agent_policy_envelope(encoded)
validated = common._validate_agent_policy_payload(payload)
print("HMB_POLICY_VERIFIED=" + json.dumps({
    "sha256": expected_sha256,
    "version": validated["final_policy_version"],
    "contract_sha256": validated["final_motion_look_policy_sha256"],
}, sort_keys=True, separators=(",", ":")))
'@
    $output = @(& $PythonExe -I -B -c $pythonCode `
        $resolvedRoot $item.FullName $ExpectedSha256.ToLowerInvariant() 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Signed policy verification failed; no payload text was emitted."
    }
    $resultLines = @($output | ForEach-Object { [string]$_ } |
        Where-Object { $_.StartsWith("HMB_POLICY_VERIFIED=") })
    if ($resultLines.Count -ne 1) {
        throw "Signed policy verifier returned an unexpected result."
    }
    Write-Host $resultLines[0]
}

function Copy-HmbPolicyFileWithFlush {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,

        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $sourceStream = [System.IO.File]::Open(
        $Source,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    try {
        if ($sourceStream.Length -le 0 -or $sourceStream.Length -gt $script:HmbPolicyMaximumBytes) {
            throw "Policy artifact has an unsafe size."
        }
        $destinationStream = [System.IO.File]::Open(
            $Destination,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        try {
            $sourceStream.CopyTo($destinationStream)
            $destinationStream.Flush($true)
        } finally {
            $destinationStream.Dispose()
        }
    } finally {
        $sourceStream.Dispose()
    }
}

function New-HmbPolicyBackupName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Sha256
    )
    Assert-HmbSha256Text -Value $Sha256 -Name "Sha256"
    $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
    return "hmb_agent_core.$($Sha256.ToLowerInvariant()).$timestamp.dat"
}
