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

$allowed = New-Object 'System.Collections.Generic.HashSet[string]' `
    ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($record in $records) {
    $relative = ([string]$record.path).Replace('/', '\')
    Assert-HmbRelativeMember -Path $relative
    if (-not $allowed.Add($relative)) {
        throw "Duplicate HMB release member: $relative"
    }
    $sourceFile = Join-Path $source $relative
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
        throw "Missing HMB release member: $relative"
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceFile).Hash
    if ($actual -ne ([string]$record.sha256).ToUpperInvariant()) {
        throw "HMB release member hash mismatch: $relative"
    }
}
$null = $allowed.Add('release-manifest.json')
$null = $allowed.Add('SHA256SUMS')

$rollback = $null
$preservedVenv = $null
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
}

try {
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    foreach ($relative in $allowed) {
        $sourceFile = Join-Path $source $relative
        if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
            continue
        }
        $destination = Join-Path $target $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force |
            Out-Null
        Copy-Item -LiteralPath $sourceFile -Destination $destination -Force
    }

    foreach ($record in $records) {
        $relative = ([string]$record.path).Replace('/', '\')
        $installed = Join-Path $target $relative
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $installed).Hash
        if ($actual -ne ([string]$record.sha256).ToUpperInvariant()) {
            throw "Installed HMB member hash mismatch: $relative"
        }
    }

    $resourceMembers = @(
        $records |
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
    if (@(Compare-Object @($allowed) $installedRuntimeFiles).Count -ne 0) {
        throw 'Installed HMB files do not match the exact runtime release closure.'
    }

    if ($preservedVenv) {
        Move-Item -LiteralPath $preservedVenv -Destination (Join-Path $target '.venv')
    }
}
catch {
    if ($rollback -and (Test-Path -LiteralPath $rollback)) {
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
Write-Output ("RUNTIME_FILES=$($records.Count)")
Write-Output ("RESOURCE_FILES=$($resourceMembers.Count)")
Write-Output ("ROLLBACK=$rollback")
