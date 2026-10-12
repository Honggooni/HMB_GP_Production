[CmdletBinding()]
param(
    [string]$SourceRoot = $PSScriptRoot,
    [string]$TargetRoot = (
        Join-Path ([Environment]::GetFolderPath('MyDocuments')) `
            'GriptapeNodes\libraries\HMB_GP_Production'
    ),
    [string]$RollbackRoot = (
        Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) `
            'HMB_GP_Production\install-rollback'
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Windows PowerShell normally supplies $PSScriptRoot while binding script
# parameters, but some non-interactive launchers expose it only after binding.
# Recover from the invoked script path so the documented no-argument install
# command never passes an empty SourceRoot into path validation.
if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = [System.IO.Path]::GetDirectoryName(
        [string]$MyInvocation.MyCommand.Path
    )
}
if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    throw 'Could not resolve the extracted HMB package directory.'
}

function Get-HmbFullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Get-HmbRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $prefix = $Root.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $Path.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escaped the HMB library root: $Path"
    }
    return $Path.Substring($prefix.Length)
}

function Assert-HmbRelativeMember {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (
        [System.IO.Path]::IsPathRooted($Path) -or
        $Path.Contains(':') -or
        $Path -match '(^|[\\/])\.\.([\\/]|$)'
    ) {
        throw "Unsafe release member path: $Path"
    }
}

function Get-HmbInventoryFingerprint {
    param([Parameter(Mandatory = $true)][object[]]$Items)
    $byPath = @{}
    foreach ($item in $Items) { $byPath[[string]$item.path] = $item }
    [string[]]$names = @($byPath.Keys)
    [System.Array]::Sort($names, [System.StringComparer]::Ordinal)
    $rows = @(foreach ($name in $names) {
        $item = $byPath[$name]
        [ordered]@{ bytes = [long]$item.bytes; path = [string]$item.path; sha256 = [string]$item.sha256 }
    })
    $encoded = [System.Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $rows -Depth 4 -Compress))
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { return ([System.BitConverter]::ToString($hasher.ComputeHash($encoded))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}

$source = Get-HmbFullPath -Path $SourceRoot
$target = Get-HmbFullPath -Path $TargetRoot
$expectedParent = Get-HmbFullPath -Path (
    Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'GriptapeNodes\libraries'
)
if (
    (Split-Path -Leaf $target) -ne 'HMB_GP_Production' -or
    (Get-HmbFullPath -Path (Split-Path -Parent $target)) -ne $expectedParent
) {
    throw "Refusing an unexpected HMB install target: $target"
}
$targetPrefix = $target + [System.IO.Path]::DirectorySeparatorChar
if (
    $source.Equals($target, [System.StringComparison]::OrdinalIgnoreCase) -or
    $source.StartsWith($targetPrefix, [System.StringComparison]::OrdinalIgnoreCase)
) {
    throw 'Run the installer from an extracted package outside the active library target.'
}
$rollbackRootPath = Get-HmbFullPath -Path $RollbackRoot
$librariesPrefix = $expectedParent + [System.IO.Path]::DirectorySeparatorChar
if (
    $rollbackRootPath.Equals($expectedParent, [System.StringComparison]::OrdinalIgnoreCase) -or
    $rollbackRootPath.StartsWith($librariesPrefix, [System.StringComparison]::OrdinalIgnoreCase)
) {
    throw 'Rollback data must be stored outside the Griptape libraries folder.'
}

$running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match 'griptape' -or
    ($_.ProcessName -match '^python' -and $_.Path -like '*griptape*')
}
if ($running) {
    throw 'Close Griptape completely before installing HMB_GP_Production.'
}

$manifestPath = Join-Path $source 'release-manifest.json'
$checksumsPath = Join-Path $source 'SHA256SUMS'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Verified runtime package manifest not found: $manifestPath"
}
if (-not (Test-Path -LiteralPath $checksumsPath -PathType Leaf)) {
    throw "Verified runtime package checksums not found: $checksumsPath"
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne 'hmb-release-closure' -or [int]$manifest.version -ne 1) {
    throw 'Unsupported HMB release manifest.'
}
$records = @($manifest.files)
if ($records.Count -ne [int]$manifest.file_count) {
    throw 'HMB release manifest file_count does not match its file list.'
}
if (
    [int]$manifest.install_file_count -ne 34 -or
    [int]$manifest.distribution_file_count -ne 4 -or
    $records.Count -ne 38
) {
    throw 'HMB release manifest install/distribution boundary mismatch.'
}

$verifiedMembers = New-Object 'System.Collections.Generic.HashSet[string]' `
    ([System.StringComparer]::OrdinalIgnoreCase)
$installMembers = New-Object 'System.Collections.Generic.HashSet[string]' `
    ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($record in $records) {
    $relative = ([string]$record.path).Replace('/', '\')
    Assert-HmbRelativeMember -Path $relative
    if (-not $verifiedMembers.Add($relative)) {
        throw "Duplicate HMB release member: $relative"
    }
    $installProperty = $record.PSObject.Properties['install']
    if ($null -eq $installProperty -or $installProperty.Value -isnot [bool]) {
        throw "HMB release member has an invalid install flag: $relative"
    }
    $sourceFile = Join-Path $source $relative
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
        throw "Missing HMB release member: $relative"
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceFile).Hash
    if ([string]$record.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $actual -ne ([string]$record.sha256).ToUpperInvariant() -or
        (Get-Item -LiteralPath $sourceFile).Length -ne [long]$record.bytes) {
        throw "HMB release member hash mismatch: $relative"
    }
    if ($installProperty.Value -and -not $installMembers.Add($relative)) {
        throw "Duplicate HMB runtime install member: $relative"
    }
}

$installRecords = @($records | Where-Object { $_.install -eq $true })
$distributionOnlyMembers = @(
    $records |
        Where-Object { $_.install -eq $false } |
        ForEach-Object { ([string]$_.path).Replace('/', '\') }
)
$expectedDistributionOnlyMembers = @(
    'Install_HMB_GP_Production.ps1',
    'LICENSE',
    'THIRD_PARTY_NOTICES.md',
    'SBOM.spdx.json'
)
if (
    $installRecords.Count -ne [int]$manifest.install_file_count -or
    $distributionOnlyMembers.Count -ne [int]$manifest.distribution_file_count -or
    @(Compare-Object $expectedDistributionOnlyMembers $distributionOnlyMembers).Count -ne 0
) {
    throw 'HMB release manifest distribution-only members are invalid.'
}
if ((Get-HmbInventoryFingerprint -Items $records) -cne [string]$manifest.build_fingerprint_sha256 -or
    (Get-HmbInventoryFingerprint -Items $installRecords) -cne [string]$manifest.runtime_fingerprint_sha256) {
    throw 'HMB release build fingerprint mismatch.'
}
$manifestSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
$expectedChecksums = @($records | ForEach-Object { '{0}  {1}' -f $_.sha256, $_.path })
$expectedChecksums += "$manifestSha256  release-manifest.json"
$actualChecksums = @(Get-Content -LiteralPath $checksumsPath)
if ($actualChecksums.Count -ne $expectedChecksums.Count -or
    @(Compare-Object $expectedChecksums $actualChecksums -CaseSensitive).Count -ne 0) {
    throw 'HMB release checksums inventory mismatch.'
}

$rollback = $null
$preservedVenv = $null
$preservedUserMembers = @()
$relocatedUserMembers = New-Object 'System.Collections.Generic.List[string]'
if (Test-Path -LiteralPath $target) {
    $reparsePoints = Get-ChildItem -LiteralPath $target -Force -Recurse -ErrorAction Stop |
        Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }
    if ($reparsePoints) {
        throw "Refusing to replace a library containing a reparse point: $($reparsePoints[0].FullName)"
    }
    New-Item -ItemType Directory -Path $rollbackRootPath -Force | Out-Null
    $rollbackName = 'v{0}-{1}-{2}' -f (
        [string]$manifest.release_version,
        (Get-Date).ToString('yyyyMMdd-HHmmss'),
        ([guid]::NewGuid().ToString('N').Substring(0, 8))
    )
    $rollback = Join-Path $rollbackRootPath $rollbackName
    if (Test-Path -LiteralPath $rollback) {
        throw "Refusing to overwrite an existing rollback directory: $rollback"
    }
    Move-Item -LiteralPath $target -Destination $rollback
    $candidateVenv = Join-Path $rollback '.venv'
    if (Test-Path -LiteralPath $candidateVenv -PathType Container) {
        $preservedVenv = $candidateVenv
    }
    # Runtime code is replaced only from the verified package. Carry legacy
    # user reports forward; current recovery/review data lives in LocalAppData
    # and project media lives outside this target, so neither is touched.
    $preservedUserMembers = @(Get-ChildItem -LiteralPath $rollback -Force | Where-Object {
        $relative = [string]$_.Name
        if ($installMembers.Contains($relative) -or $relative -eq '.hmb-install-receipt.json' -or
            $relative -eq 'release-manifest.json' -or $relative -eq 'SHA256SUMS') { return $false }
        if ($_.PSIsContainer) { return $relative -in @('reports', 'reviews', 'user-data') }
        return $_.Extension.ToLowerInvariant() -in @('.json', '.txt', '.md', '.csv', '.log')
    } | ForEach-Object { [string]$_.Name })
}

try {
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    foreach ($relative in $installMembers) {
        $sourceFile = Join-Path $source $relative
        $destination = Join-Path $target $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force |
            Out-Null
        Copy-Item -LiteralPath $sourceFile -Destination $destination -Force
    }

    foreach ($record in $installRecords) {
        $relative = ([string]$record.path).Replace('/', '\')
        $installed = Join-Path $target $relative
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $installed).Hash
        if ($actual -ne ([string]$record.sha256).ToUpperInvariant()) {
            throw "Installed HMB member hash mismatch: $relative"
        }
    }

    $resourceMembers = @(
        $installRecords |
            ForEach-Object { ([string]$_.path).Replace('/', '\') } |
            Where-Object { $_ -like 'resources\*' }
    )
    $resourceRoot = Join-Path $target 'resources'
    $installedResources = @(
        Get-ChildItem -LiteralPath $resourceRoot -Force -Recurse -File |
            ForEach-Object { Get-HmbRelativePath -Root $target -Path $_.FullName }
    )
    if (@(Compare-Object $resourceMembers $installedResources).Count -ne 0) {
        throw 'Installed HMB resources do not match the runtime release closure.'
    }

    $installedRuntimeFiles = @(
        Get-ChildItem -LiteralPath $target -Force -Recurse -File |
            ForEach-Object { Get-HmbRelativePath -Root $target -Path $_.FullName }
    )
    if (@(Compare-Object @($installMembers) $installedRuntimeFiles).Count -ne 0) {
        throw 'Installed HMB files do not match the exact runtime release closure.'
    }

    if ($preservedVenv) {
        Move-Item -LiteralPath $preservedVenv -Destination (Join-Path $target '.venv')
        $relocatedUserMembers.Add('.venv')
    }
    foreach ($relative in $preservedUserMembers) {
        Assert-HmbRelativeMember -Path $relative
        Move-Item -LiteralPath (Join-Path $rollback $relative) -Destination (Join-Path $target $relative)
        $relocatedUserMembers.Add($relative)
    }
    $receipt = [ordered]@{
        schema = 'hmb-install-receipt'; version = 1
        release_version = [string]$manifest.release_version
        installed_at = [DateTime]::UtcNow.ToString('o')
        source_manifest_sha256 = $manifestSha256
        build_fingerprint_sha256 = [string]$manifest.build_fingerprint_sha256
        runtime_fingerprint_sha256 = [string]$manifest.runtime_fingerprint_sha256
        policy_identity = $manifest.policy_identity
        verification = 'file_hashes_and_inventory_matched_unsigned_local_record'
        runtime_files = @($installRecords | ForEach-Object {
            [ordered]@{ path = [string]$_.path; bytes = [long]$_.bytes; sha256 = [string]$_.sha256 }
        })
        preserved_user_members = @($relocatedUserMembers)
    }
    $receiptPath = Join-Path $target '.hmb-install-receipt.json'
    [System.IO.File]::WriteAllText($receiptPath, (ConvertTo-Json -InputObject $receipt -Depth 8),
        (New-Object System.Text.UTF8Encoding($false)))
}
catch {
    if ($rollback -and (Test-Path -LiteralPath $rollback)) {
        # If receipt writing fails after carrying user data forward, put those
        # exact paths back before restoring the old library.
        foreach ($relative in $relocatedUserMembers) {
            $moved = Join-Path $target $relative
            if (Test-Path -LiteralPath $moved) {
                Move-Item -LiteralPath $moved -Destination (Join-Path $rollback $relative)
            }
        }
        $failedTarget = Join-Path $rollbackRootPath (
            'failed-new-{0}-{1}' -f (
                (Get-Date).ToString('yyyyMMdd-HHmmss'),
                ([guid]::NewGuid().ToString('N').Substring(0, 8))
            )
        )
        if (Test-Path -LiteralPath $target) {
            Move-Item -LiteralPath $target -Destination $failedTarget
        }
        Move-Item -LiteralPath $rollback -Destination $target
    }
    throw
}

Write-Output 'HMB_RUNTIME_INSTALL_OK'
Write-Output ("TARGET=$target")
Write-Output ("VERSION=$($manifest.release_version)")
Write-Output ("RUNTIME_FILES=$($installRecords.Count)")
Write-Output ("RESOURCE_FILES=$($resourceMembers.Count)")
Write-Output ("ROLLBACK=$rollback")
Write-Output ("RUNTIME_FINGERPRINT=$($manifest.runtime_fingerprint_sha256)")
Write-Output ("BUILD_FINGERPRINT=$($manifest.build_fingerprint_sha256)")
Write-Output ("SOURCE_MANIFEST_SHA256=$manifestSha256")
Write-Output ("PRESERVED_USER_MEMBERS=$($relocatedUserMembers.Count)")
Write-Output ("RECEIPT=$receiptPath")
