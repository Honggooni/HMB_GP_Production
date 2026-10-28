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
    ),
    [switch]$PrepareTosRuntime,
    [string]$EnginePython = (
        Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) `
            'ai.griptape.nodes.desktop\current\resources\engine-bundle\python\python.exe'
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

function Assert-HmbNoReparsePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    # Check the named path itself as well as every existing ancestor. Resolving
    # the path first would hide a junction that redirects user data elsewhere.
    $cursor = [System.IO.Path]::GetFullPath($Path)
    while ($cursor) {
        try {
            $attributes = [System.IO.File]::GetAttributes($cursor)
            if ($attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "Refusing an HMB install path containing a reparse point: $cursor"
            }
        }
        catch [System.IO.FileNotFoundException] { }
        catch [System.IO.DirectoryNotFoundException] { }
        $parent = [System.IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) { break }
        $cursor = $parent.FullName
    }
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

function Repair-HmbTosIsolation {
    param([string]$LibraryRoot, [bool]$PrepareRuntime, [bool]$CleanLegacyEnvironment)
    if (-not $PrepareRuntime -and -not $CleanLegacyEnvironment) { return $null }
    $python = Get-HmbFullPath -Path $EnginePython
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Griptape Python 3.12 is required for TOS dependency migration. Supply -EnginePython with its installed path.'
    }
    # No SDK imports, credentials, rendered media, or runtime pip operations.
    # This installer-only migration keeps TOS in a dedicated child interpreter.
    # The original edit environment remains in the rollback directory intact.
    $repair = @'
import ast, hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
source = root / '_hmb_library_bootstrap.py'
if source.stat().st_size > 1024 * 1024:
    raise SystemExit('The shared dependency repair exceeds its source limit')
tree = ast.parse(source.read_text('utf-8-sig'))
values = [ast.literal_eval(item.value) for item in tree.body if isinstance(item, ast.Assign)
          and any(isinstance(target, ast.Name) and target.id == '_HMB_TOS_ENVIRONMENT_REPAIR_SOURCE' for target in item.targets)]
if len(values) != 1 or type(values[0]) is not str or len(values[0]) > 256 * 1024:
    raise SystemExit('The shared dependency repair is unavailable')
namespace = {'__name__': '_hmb_installer_shared_repair'}
exec(compile(values[0], '<HMB isolated environment repair>', 'exec'), namespace)
request = {'version': 1, 'operation': 'install', 'library_root': str(root),
           'prepare_runtime': sys.argv[2] == '1', 'clean_legacy': sys.argv[3] == '1',
           'expected_manifest_sha256': hashlib.sha256((root / 'griptape-nodes-library.json').read_bytes()).hexdigest()}
try:
    report = namespace['_repair_request'](request)
except Exception:
    raise SystemExit('Isolated dependency migration failed; original rollback data was preserved') from None
output = json.dumps(report, ensure_ascii=True)
if len(output.encode()) > 1024 * 1024:
    raise SystemExit('The shared dependency repair exceeded its response limit')
print(output)
if report.get('ok') is not True:
    raise SystemExit(1)
'@
    $output = & $python -I -B -c $repair $LibraryRoot ([int]$PrepareRuntime) ([int]$CleanLegacyEnvironment)
    if ($LASTEXITCODE -ne 0) {
        throw 'TOS isolation migration failed; restoring the previous library and its original environment.'
    }
    return ($output | ConvertFrom-Json)
}

function Invoke-HmbNativeEditorPatch {
    param([ValidateSet('prepare', 'apply', 'rollback')][string]$Action, [string]$Plan)
    $python = Get-HmbFullPath -Path $EnginePython
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'The bundled Griptape Python is required to verify and install the native editor UI.'
    }
    $patcher = Join-Path $source 'tools\hmb_color_lut_native_header_patch.py'
    $arguments = @('-I', '-B', $patcher, '--release-action', $Action)
    if ($Plan) { $arguments += @('--release-plan', $Plan) }
    $output = & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Native editor $Action failed; installation was not completed. Check the SDK/editor compatibility error above, update Griptape if required, then use the verified Runtime ZIP."
    }
    return ($output | ConvertFrom-Json)
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
foreach ($boundary in @($source, $target, $rollbackRootPath, (Get-HmbFullPath -Path $EnginePython))) {
    Assert-HmbNoReparsePath -Path $boundary
}

# One install owns the library and native-editor transaction together. The
# per-target OS mutex is released automatically if an installer process exits.
$mutexHasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $mutexKey = [System.BitConverter]::ToString($mutexHasher.ComputeHash(
        [System.Text.Encoding]::UTF8.GetBytes($target.ToLowerInvariant()))).Replace('-', '')
}
finally { $mutexHasher.Dispose() }
$installMutex = New-Object System.Threading.Mutex($false, ('Local\HMB_GP_Production.Install.' + $mutexKey))
$ownsInstallMutex = $false
try {
    try { $ownsInstallMutex = $installMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $ownsInstallMutex = $true }
    if (-not $ownsInstallMutex) { throw 'Another HMB installation for this library is already in progress.' }

$running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match 'griptape' -or
    ($_.ProcessName -match '^python' -and $_.Path -like '*griptape*')
}
if ($running) {
    throw 'Close Griptape completely before installing HMB_GP_Production.'
}

$manifestPath = Join-Path $source 'release-manifest.json'
$checksumsPath = Join-Path $source 'SHA256SUMS'
Assert-HmbNoReparsePath -Path $manifestPath
Assert-HmbNoReparsePath -Path $checksumsPath
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
    [int]$manifest.install_file_count -ne 60 -or
    [int]$manifest.distribution_file_count -ne 8 -or
    $records.Count -ne 68
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
    Assert-HmbNoReparsePath -Path $sourceFile
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
    'SBOM.spdx.json',
    'tools\hmb_color_lut_native_header_patch.py',
    'tools\hmb_native_semantic_adapter.py',
    'resources\editor\hmb-color-lut-native-header.js',
    'resources\editor\native-editor-patch.json'
)
if (
    $installRecords.Count -ne [int]$manifest.install_file_count -or
    $distributionOnlyMembers.Count -ne [int]$manifest.distribution_file_count -or
    @(Compare-Object $expectedDistributionOnlyMembers $distributionOnlyMembers).Count -ne 0
) {
    throw 'HMB release manifest distribution-only members are invalid.'
}
$expectedAgentMembers = @(
    'resources\agent\Dinoster5\project.json',
    'resources\agent\Katuri8\project.json',
    'resources\agent\superwings12\project.json',
    'resources\agent\superwings12\hmb_agent_core.dat'
)
$actualAgentMembers = @($installMembers | Where-Object { $_ -like 'resources\agent\*' })
if (@(Compare-Object $expectedAgentMembers $actualAgentMembers -CaseSensitive).Count -ne 0) {
    throw 'HMB project policy folders do not match the release closure.'
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
$preservedTosVenv = $null
$legacyTosEnvironment = $false
$needsTosMigration = $false
$environmentMigration = $null
$preservedUserMembers = @()
$relocatedUserMembers = New-Object 'System.Collections.Generic.List[string]'
$nativeEditorPlan = $null
$nativeEditorResult = $null
$hadExistingTarget = Test-Path -LiteralPath $target
$backupMoved = $false
if ($hadExistingTarget) {
    foreach ($migrationLock in @('.hmb-tos-migration.lock', '.hmb-tos-prepare.lock')) {
        if (Test-Path -LiteralPath (Join-Path $target $migrationLock)) {
            throw 'An environment migration lock remains. Close Griptape and let its guarded recovery finish before installing; existing files were preserved.'
        }
    }
    $reparsePoints = Get-ChildItem -LiteralPath $target -Force -Recurse -ErrorAction Stop |
        Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }
    if ($reparsePoints) {
        throw "Refusing to replace a library containing a reparse point: $($reparsePoints[0].FullName)"
    }
    $editSite = Join-Path $target '.venv\Lib\site-packages'
    if (Test-Path -LiteralPath $editSite -PathType Container) {
        $legacyTosEnvironment = @(Get-ChildItem -LiteralPath $editSite -Directory -Filter 'tos-*.dist-info').Count -gt 0
        $needsTosMigration = $legacyTosEnvironment -or (Test-Path -LiteralPath (Join-Path $editSite 'wrapt-1.16.0.dist-info'))
        if (-not $needsTosMigration) {
            foreach ($knownPattern in @('anyio-*.dist-info', 'charset_normalizer-*.dist-info', 'idna-*.dist-info', 'urllib3-*.dist-info')) {
                if (@(Get-ChildItem -LiteralPath $editSite -Directory -Filter $knownPattern).Count -gt 0) {
                    $needsTosMigration = $true
                    break
                }
            }
        }
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
    # Complete all discovery while the original target is still in place.
    # Only the destination paths below refer to the planned rollback folder.
    $candidateVenv = Join-Path $target '.venv'
    if (Test-Path -LiteralPath $candidateVenv -PathType Container) {
        $preservedVenv = Join-Path $rollback '.venv'
    }
    $candidateTosVenv = Join-Path $target '.venv-tos'
    if (Test-Path -LiteralPath $candidateTosVenv -PathType Container) {
        $preservedTosVenv = Join-Path $rollback '.venv-tos'
    }
    # Runtime code is replaced only from the verified package. Carry legacy
    # user reports forward; current recovery/review data lives in LocalAppData
    # and project media lives outside this target, so neither is touched.
    $preservedUserMembers = @(Get-ChildItem -LiteralPath $target -Force | Where-Object {
        $relative = [string]$_.Name
        if ($installMembers.Contains($relative) -or $relative -eq '.hmb-install-receipt.json' -or
            $relative -eq 'release-manifest.json' -or $relative -eq 'SHA256SUMS') { return $false }
        if ($_.PSIsContainer) { return $relative -in @('reports', 'reviews', 'user-data', '.hmb-environment-backups') }
        return $_.Extension.ToLowerInvariant() -in @('.json', '.txt', '.md', '.csv', '.log')
    } | ForEach-Object { [string]$_.Name })
}

# Validate the editor before the first runtime move. Unsupported app versions,
# modified bundles or a running desktop leave the existing library untouched.
$nativeEditorPlan = Invoke-HmbNativeEditorPatch -Action 'prepare'
try {
    if ($hadExistingTarget) {
        Move-Item -LiteralPath $target -Destination $rollback
        $backupMoved = $true
    }
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
        if ($needsTosMigration) {
            # Keep the exact original in rollback while editing only this copy.
            Copy-Item -LiteralPath $preservedVenv -Destination (Join-Path $target '.venv') -Recurse
        }
        else {
            Move-Item -LiteralPath $preservedVenv -Destination (Join-Path $target '.venv')
            $relocatedUserMembers.Add('.venv')
        }
    }
    if ($preservedTosVenv) {
        Move-Item -LiteralPath $preservedTosVenv -Destination (Join-Path $target '.venv-tos')
        $relocatedUserMembers.Add('.venv-tos')
    }
    foreach ($relative in $preservedUserMembers) {
        Assert-HmbRelativeMember -Path $relative
        Move-Item -LiteralPath (Join-Path $rollback $relative) -Destination (Join-Path $target $relative)
        $relocatedUserMembers.Add($relative)
    }
    $environmentMigration = Repair-HmbTosIsolation -LibraryRoot $target `
        -PrepareRuntime ($PrepareTosRuntime.IsPresent -or $legacyTosEnvironment) `
        -CleanLegacyEnvironment $needsTosMigration
    $nativeEditorResult = Invoke-HmbNativeEditorPatch -Action 'apply' -Plan $nativeEditorPlan.plan
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
        isolated_tos_migration = $environmentMigration
        native_editor_patch = $nativeEditorResult
    }
    $receiptPath = Join-Path $target '.hmb-install-receipt.json'
    [System.IO.File]::WriteAllText($receiptPath, (ConvertTo-Json -InputObject $receipt -Depth 8),
        (New-Object System.Text.UTF8Encoding($false)))
}
catch {
    $installFailure = $_
    $nativeRollbackFailure = $null
    if ($nativeEditorPlan) {
        try { Invoke-HmbNativeEditorPatch -Action 'rollback' -Plan $nativeEditorPlan.plan | Out-Null }
        catch { $nativeRollbackFailure = $_ }
    }
    if ($rollback -and (Test-Path -LiteralPath $rollback) -and
        ($backupMoved -or -not (Test-Path -LiteralPath $target))) {
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
    elseif (-not $hadExistingTarget -and (Test-Path -LiteralPath $target)) {
        New-Item -ItemType Directory -Path $rollbackRootPath -Force | Out-Null
        $failedTarget = Join-Path $rollbackRootPath ('failed-first-install-' + [guid]::NewGuid().ToString('N'))
        Move-Item -LiteralPath $target -Destination $failedTarget
    }
    if ($nativeRollbackFailure) {
        throw ("Library rollback completed, but native editor recovery requires inspection: " +
            $nativeRollbackFailure.Exception.Message + ' Original install error: ' + $installFailure.Exception.Message)
    }
    throw $installFailure
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
Write-Output ("NATIVE_EDITOR_SHA256=$($nativeEditorResult.sha256)")
Write-Output ("NATIVE_EDITOR_CHANGED=$($nativeEditorResult.changed)")
}
finally {
    if ($ownsInstallMutex) { $installMutex.ReleaseMutex() }
    $installMutex.Dispose()
}
