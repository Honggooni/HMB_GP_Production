#Requires -Version 5.1

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$adminRoot = Join-Path $root "resources\admin"
$scriptNames = @(
    "HMB_Agent_Policy_Admin_Common.ps1",
    "Configure_HMB_Agent_Policy_Share.ps1",
    "Disable_HMB_Agent_Policy_Share.ps1",
    "Test_HMB_Agent_Policy_Share.ps1",
    "Test_HMB_Agent_Policy_Reader.ps1",
    "Deploy_HMB_Agent_Policy_Atomic.ps1",
    "Rollback_HMB_Agent_Policy_Atomic.ps1"
)
$asts = @{}
$sources = @{}

foreach ($name in $scriptNames) {
    $path = Join-Path $adminRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing policy administration script: $name"
    }
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $path,
        [ref]$tokens,
        [ref]$parseErrors
    )
    if (@($parseErrors).Count -ne 0) {
        throw (
            "PowerShell parse failure in {0}: {1}" -f
            $name,
            ((@($parseErrors) | ForEach-Object { $_.Message }) -join " | ")
        )
    }
    $asts[$name] = $ast
    $sources[$name] = [System.IO.File]::ReadAllText(
        $path,
        [System.Text.Encoding]::UTF8
    )
}

$allSource = ($sources.Values -join "`n")
foreach ($forbidden in @(
    "FIN-RCOMP1",
    "192.168.203.245",
    "HMB_AGENT_POLICY_PATH",
    "Invoke-Command",
    "Enter-PSSession",
    "New-PSSession",
    "Set-SmbServerConfiguration"
)) {
    if ($allSource.IndexOf($forbidden, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        throw "Forbidden legacy, redirectable, remote, or global-mutation token: $forbidden"
    }
}
if ($allSource -match '(?i)Get-Content[^\r\n]*hmb_agent_core') {
    throw "Administration scripts must never print or parse policy content with Get-Content."
}
if ($allSource -match '(?i)Remove-Item[^\r\n]*-Recurse') {
    throw "Administration scripts must not perform recursive deletion."
}

$common = $sources["HMB_Agent_Policy_Admin_Common.ps1"]
foreach ($required in @(
    '"FIN-RCOMP7"',
    '"FIN-RCOMP7.funnyflux.local"',
    '"D:\agent"',
    '"D:\agent\hmb_agent_core.dat"',
    '"D:\agent\backup"',
    '"HMB_AgentPolicy$"',
    "ReparsePoint",
    "Get-SmbShare",
    "RejectUnencryptedAccess",
    "funnyflux.local",
    "_decode_signed_agent_policy_envelope",
    "_validate_agent_policy_payload"
)) {
    if (-not $common.Contains($required)) {
        throw "Common administration boundary is missing: $required"
    }
}

$identityScripts = @(
    "Configure_HMB_Agent_Policy_Share.ps1",
    "Disable_HMB_Agent_Policy_Share.ps1",
    "Test_HMB_Agent_Policy_Share.ps1",
    "Test_HMB_Agent_Policy_Reader.ps1",
    "Deploy_HMB_Agent_Policy_Atomic.ps1",
    "Rollback_HMB_Agent_Policy_Atomic.ps1"
)
foreach ($name in $identityScripts) {
    $ast = $asts[$name]
    if ($null -eq $ast.ParamBlock) {
        throw "Script-level parameter block is missing: $name"
    }
    foreach ($parameterName in @("Readers", "PolicyAdmins")) {
        $parameter = @($ast.ParamBlock.Parameters | Where-Object {
            $_.Name.VariablePath.UserPath -eq $parameterName
        })
        if ($parameter.Count -ne 1) {
            throw "$name must declare exactly one $parameterName parameter."
        }
        if ($null -ne $parameter[0].DefaultValue) {
            throw "$name must not guess a default $parameterName identity."
        }
        $parameterAttribute = @($parameter[0].Attributes | Where-Object {
            $_.TypeName.FullName -eq "Parameter"
        })
        $mandatory = @($parameterAttribute.NamedArguments | Where-Object {
            $_.ArgumentName -eq "Mandatory" -and
            $_.Argument.Extent.Text -eq '$true'
        })
        if ($mandatory.Count -ne 1) {
            throw "$name must require the $parameterName identity."
        }
    }
}

$configure = $sources["Configure_HMB_Agent_Policy_Share.ps1"]
foreach ($required in @(
    "SupportsShouldProcess",
    "#Requires -RunAsAdministrator",
    "New-SmbShare",
    'EncryptData = $true',
    'CachingMode = "None"',
    'FolderEnumerationMode = "AccessBased"',
    "Set-HmbPolicyBackupAcl",
    "Set-HmbPolicyLiveFileAcl",
    "Assert-HmbNoOverlappingNonAdministrativeShare"
)) {
    if (-not $configure.Contains($required)) {
        throw "Share configuration safety control is missing: $required"
    }
}

foreach ($name in @(
    "Disable_HMB_Agent_Policy_Share.ps1",
    "Deploy_HMB_Agent_Policy_Atomic.ps1",
    "Rollback_HMB_Agent_Policy_Atomic.ps1"
)) {
    $source = $sources[$name]
    foreach ($required in @(
        "SupportsShouldProcess",
        "#Requires -RunAsAdministrator"
    )) {
        if (-not $source.Contains($required)) {
            throw "Atomic policy script $name is missing: $required"
        }
    }
    if ($name -eq "Disable_HMB_Agent_Policy_Share.ps1") {
        foreach ($required in @(
            "Remove-SmbShare",
            "LOCAL_LIVE=RETAINED",
            "LOCAL_BACKUP=RETAINED"
        )) {
            if (-not $source.Contains($required)) {
                throw "Safe share-disable script is missing: $required"
            }
        }
        continue
    }
    foreach ($required in @(
        "[System.IO.File]::Replace",
        "Copy-HmbPolicyFileWithFlush",
        "Set-HmbPolicyAdminFileAcl",
        "Set-HmbPolicyLiveFileAcl"
    )) {
        if (-not $source.Contains($required)) {
            throw "Atomic policy script $name is missing: $required"
        }
    }
    $verifierMatches = [regex]::Matches(
        $source,
        "Invoke-HmbPolicyArtifactVerifier"
    )
    if ($verifierMatches.Count -lt 3) {
        throw "$name must verify before staging, before switch, and after switch."
    }
    $replaceIndex = $source.IndexOf("[System.IO.File]::Replace")
    if (
        $verifierMatches[0].Index -gt $replaceIndex -or
        $verifierMatches[$verifierMatches.Count - 1].Index -lt $replaceIndex
    ) {
        throw "$name does not statically bracket atomic replacement with verification."
    }
}

$reader = $sources["Test_HMB_Agent_Policy_Reader.ps1"]
foreach ($required in @(
    "RequireMutualAuthentication=1",
    "RequireIntegrity=1",
    "RequirePrivacy=1",
    "Get-SmbConnection",
    "Encrypted",
    "FileAccess]::Write",
    "BACKUP_ISOLATION=PASS",
    "_load_agent_rule_payload"
)) {
    if (-not $reader.Contains($required)) {
        throw "Reader verification safety control is missing: $required"
    }
}

$runbookPath = Join-Path $adminRoot "HMB_Agent_Policy_Share_Runbook.md"
if (-not (Test-Path -LiteralPath $runbookPath -PathType Leaf)) {
    throw "Korean policy share runbook is missing."
}
$runbook = [System.IO.File]::ReadAllText(
    $runbookPath,
    [System.Text.Encoding]::UTF8
)
foreach ($required in @(
    "FIN-RCOMP7.funnyflux.local",
    "D:\agent\backup",
    "RequireMutualAuthentication=1,RequireIntegrity=1,RequirePrivacy=1",
    "-WhatIf",
    "Deploy_HMB_Agent_Policy_Atomic.ps1",
    "Rollback_HMB_Agent_Policy_Atomic.ps1"
)) {
    if (-not $runbook.Contains($required)) {
        throw "Korean runbook boundary is missing: $required"
    }
}
if (-not [regex]::IsMatch($runbook, '[\uAC00-\uD7A3]')) {
    throw "The local review runbook must contain Korean guidance."
}

Write-Host "HMB Agent policy administration PowerShell parse/static regression: PASS"
