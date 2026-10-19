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
import ast, csv, importlib.metadata as metadata, io, json, os, pathlib, re, subprocess, sys
root = pathlib.Path(sys.argv[1]).resolve()
prepare, clean = sys.argv[2] == '1', sys.argv[3] == '1'
if sys.version_info[:2] != (3, 12) or root.name != 'HMB_GP_Production' or not root.is_dir():
    raise SystemExit('Unsupported installer runtime or library root')
flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
def run(args, *, data=None, timeout=300):
    result = subprocess.run(args, input=data, capture_output=True, text=True,
                            timeout=timeout, creationflags=flags)
    if result.returncode:
        raise RuntimeError('Isolated dependency setup failed; no credentials or provider request was used')
    return result.stdout
def local(path):
    current = path
    while current != root:
        if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise RuntimeError('Linked dependency environment is not supported')
        if current == current.parent or not current.resolve().is_relative_to(root):
            raise RuntimeError('Dependency environment escaped the installed library')
        current = current.parent
    return path
tos_root = local(root / '.venv-tos')
tos_python = tos_root / 'Scripts/python.exe'
report = {'schema': 'hmb-tos-isolation-install/v1', 'prepared': False, 'legacy_packages_removed': [],
          'engine_backed_duplicates_removed': [], 'removed_versions': {},
          'provider_calls': 0, 'credentials_read': False}
if prepare:
    if not tos_python.is_file():
        if tos_root.exists():
            raise RuntimeError('An incomplete TOS environment already exists; its files were preserved')
        run([sys.executable, '-I', '-B', '-m', 'uv', 'venv', '--python', sys.executable, str(tos_root)])
        run([sys.executable, '-I', '-B', '-m', 'uv', 'pip', 'install', '--python', str(tos_python), 'tos==2.9.2'])
    tree = ast.parse((root / 'HMBSeedanceGeneration.py').read_text('utf-8-sig'))
    values = [ast.literal_eval(item.value) for item in tree.body if isinstance(item, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == '_TOS_HELPER_SOURCE' for target in item.targets)]
    if len(values) != 1 or type(values[0]) is not str or len(values[0]) > 65536:
        raise RuntimeError('The verified TOS helper is unavailable')
    request = json.dumps({'version': 1, 'runtime_root': str(tos_root), 'operation': 'probe'})
    output = run([str(tos_python), '-I', '-B', '-c', values[0]], data=request, timeout=30)
    if len(output) > 32768:
        raise RuntimeError('TOS runtime probe exceeded its response limit')
    probe = json.loads(output)
    if not (probe.get('version') == 1 and probe.get('ok') is True and probe.get('isolated') is True
            and pathlib.Path(probe.get('runtime_root', '')).resolve() == tos_root
            and probe.get('tos_version') == '2.9.2' and probe.get('wrapt_version') == '1.16.0'):
        raise RuntimeError('TOS runtime isolation probe failed')
    report['prepared'] = True
    report['runtime_probe'] = probe
if clean:
    edit = local(root / '.venv')
    site = edit / 'Lib/site-packages'
    python = edit / 'Scripts/python.exe'
    if not python.is_file() or not site.is_dir():
        raise RuntimeError('The legacy edit environment is incomplete; rollback retains it')
    def norm(value):
        return re.sub(r'[-_.]+', '-', value).lower()
    distributions = {norm(item.metadata['Name']): item for item in metadata.distributions(path=[str(site)])}
    legacy = {'tos', 'wrapt', 'deprecated'} & distributions.keys()
    from packaging.version import Version
    known_engine_backed = {'anyio', 'charset-normalizer', 'idna', 'urllib3'}
    engine_versions = {name: metadata.version(name) for name in known_engine_backed}
    engine_backed = {name for name in known_engine_backed & distributions.keys()
                     if Version(distributions[name].version) < Version(engine_versions[name])}
    removable = legacy | engine_backed
    removed_versions = {name: distributions[name].version for name in sorted(removable)}
    # Preserve custom packages rather than silently removing their requirements.
    # The engine already supplies its own compatible wrapt outside this venv.
    from packaging.requirements import Requirement
    for name, item in distributions.items():
        if name in removable:
            continue
        for raw in item.requires or []:
            requirement = Requirement(raw)
            if requirement.marker is not None and not requirement.marker.evaluate({'extra': ''}):
                continue
            dependency = norm(requirement.name)
            if dependency in legacy:
                raise RuntimeError('A custom edit dependency needs a legacy TOS package; original environment preserved')
            if dependency in engine_backed and (requirement.url is not None or
                    not requirement.specifier.contains(engine_versions[dependency], prereleases=True)):
                raise RuntimeError('A custom edit dependency rejects the engine component; original environment preserved')
    # uv follows wheel RECORD paths while uninstalling. Prove every removable
    # file stays in the disposable edit copy, including normal Scripts entries.
    # Missing/foreign records are not permission to delete unverified files.
    for name in sorted(removable):
        record = distributions[name].read_text('RECORD')
        if record is None or not record or len(record) > 2 * 1024 * 1024:
            raise RuntimeError('A removable package has no file inventory; original environment preserved')
        # Distribution.files filters out missing paths in Python 3.12. Inspect
        # the raw CSV as well so a currently absent foreign target is rejected.
        for member in csv.reader(io.StringIO(record)):
            if not member or not member[0] or len(member) != 3:
                raise RuntimeError('A removable package has an invalid file inventory; original environment preserved')
            file_path = pathlib.Path(distributions[name].locate_file(member[0]))
            try:
                file_path.resolve().relative_to(edit.resolve())
            except (OSError, ValueError):
                raise RuntimeError('A package file escaped its edit environment; original environment preserved') from None
            local(file_path)
    if removable:
        run([sys.executable, '-I', '-B', '-m', 'uv', 'pip', 'uninstall', '--python', str(python), *sorted(removable)])
    remaining = {norm(item.metadata['Name']) for item in metadata.distributions(path=[str(site)])}
    if removable & remaining:
        raise RuntimeError('Legacy TOS editor packages were not removed')
    report['legacy_packages_removed'] = sorted(legacy)
    report['engine_backed_duplicates_removed'] = sorted(engine_backed)
    report['removed_versions'] = removed_versions
print(json.dumps(report, ensure_ascii=False))
'@
    $output = & $python -I -B -c $repair $LibraryRoot ([int]$PrepareRuntime) ([int]$CleanLegacyEnvironment)
    if ($LASTEXITCODE -ne 0) {
        throw 'TOS isolation migration failed; restoring the previous library and its original environment.'
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
    [int]$manifest.install_file_count -ne 40 -or
    [int]$manifest.distribution_file_count -ne 4 -or
    $records.Count -ne 44
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
if (Test-Path -LiteralPath $target) {
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
    Move-Item -LiteralPath $target -Destination $rollback
    $candidateVenv = Join-Path $rollback '.venv'
    if (Test-Path -LiteralPath $candidateVenv -PathType Container) {
        $preservedVenv = $candidateVenv
    }
    $candidateTosVenv = Join-Path $rollback '.venv-tos'
    if (Test-Path -LiteralPath $candidateTosVenv -PathType Container) {
        $preservedTosVenv = $candidateTosVenv
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
    elseif (Test-Path -LiteralPath $target) {
        New-Item -ItemType Directory -Path $rollbackRootPath -Force | Out-Null
        $failedTarget = Join-Path $rollbackRootPath ('failed-first-install-' + [guid]::NewGuid().ToString('N'))
        Move-Item -LiteralPath $target -Destination $failedTarget
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
