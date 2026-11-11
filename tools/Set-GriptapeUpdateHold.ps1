[CmdletBinding(SupportsShouldProcess)]
param([switch]$CurrentUser)

$ErrorActionPreference = 'Stop'
$processes = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'griptape-nodes-desktop.exe' -or
    $_.ExecutablePath -like '*griptape*engine-bundle*'
}
if ($processes) { throw 'Save work and close Griptape Desktop before applying the update hold.' }

if ($CurrentUser) {
    $name = 'GTN_DESKTOP_DISABLE_UPDATES'
    $previous = [Environment]::GetEnvironmentVariable($name, 'User')
    if ($PSCmdlet.ShouldProcess($name, 'Hold Desktop updates for this Windows user')) {
        [Environment]::SetEnvironmentVariable($name, '1', 'User')
        [Environment]::SetEnvironmentVariable($name, '1', 'Process')
        if ([Environment]::GetEnvironmentVariable($name, 'User') -ne '1') {
            throw 'The user update hold could not be verified.'
        }
        [pscustomobject]@{ Scope = 'CurrentUser'; Applied = $true; PreviousValue = $previous }
    }
    return
}

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'The computer policy must be deployed by an administrator.'
}
$directory = Join-Path $env:ProgramData 'GriptapeNodes'
$policy = Join-Path $directory 'policy.json'
$existing = $null
if (Test-Path -LiteralPath $directory) {
    if ((Get-Item -LiteralPath $directory).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'The policy directory must not be a reparse point.'
    }
}
if (Test-Path -LiteralPath $policy) {
    if ((Get-Item -LiteralPath $policy).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'The policy file must not be a reparse point.'
    }
    $existing = [IO.File]::ReadAllBytes($policy)
    $settings = [Text.Encoding]::UTF8.GetString($existing).TrimStart([char]0xFEFF) | ConvertFrom-Json
    if ($settings -isnot [pscustomobject]) { throw 'The existing policy must be a JSON object.' }
    if ($settings.disableUpdates -is [bool] -and $settings.disableUpdates) {
        [pscustomobject]@{ Scope = 'Computer'; Applied = $true; Path = $policy; AlreadySet = $true }
        return
    }
} else {
    $settings = [pscustomobject]@{}
}
if ($PSCmdlet.ShouldProcess($policy, 'Hold Desktop updates on this computer')) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $settings | Add-Member -NotePropertyName disableUpdates -NotePropertyValue $true -Force
    $suffix = [Guid]::NewGuid().ToString('N')
    $pending = Join-Path $directory "policy-$suffix.tmp"
    $backup = if ($null -ne $existing) { Join-Path $directory "policy-$suffix.bak" } else { $null }
    try {
        [IO.File]::WriteAllText($pending, ($settings | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
        if ($null -ne $existing) {
            if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($policy)) -cne [Convert]::ToBase64String($existing)) {
                throw 'The policy changed while preparing the update hold.'
            }
            [IO.File]::Replace($pending, $policy, $backup)
        } else {
            [IO.File]::Move($pending, $policy)
        }
        $verified = Get-Content -LiteralPath $policy -Raw | ConvertFrom-Json
        if ($verified.disableUpdates -isnot [bool] -or -not $verified.disableUpdates) {
            throw 'The computer policy could not be verified.'
        }
        [pscustomobject]@{ Scope = 'Computer'; Applied = $true; Path = $policy; Backup = $backup }
    } finally {
        if (Test-Path -LiteralPath $pending) { Remove-Item -LiteralPath $pending }
    }
}
