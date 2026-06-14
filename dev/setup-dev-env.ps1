<#
.SYNOPSIS
Creates a source-backed Mongoose/Njord development environment.

.DESCRIPTION
The development environment is isolated from the normal user-local install
under %LOCALAPPDATA%\Agents. It creates repo-local command shims under
.dev-bin and state under .dev-localappdata so current source changes can be
tested without reinstalling the official mongoose.exe release.
#>

[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [switch]$Reset
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = Join-Path $PSScriptRoot ".."
}

$repo = (Resolve-Path $RepoRoot).Path
$mongooseCli = Join-Path $repo "mongoose\mongoose.py"
$njordAgent = Join-Path $repo "agents\njord\agent.py"
$devLocalAppData = Join-Path $repo ".dev-localappdata"
$devBin = Join-Path $repo ".dev-bin"

if (-not (Test-Path $mongooseCli)) {
    throw "Could not find mongoose CLI source at $mongooseCli"
}

if (-not (Test-Path $njordAgent)) {
    throw "Could not find Njord agent source at $njordAgent"
}

if ($Reset -and (Test-Path $devLocalAppData)) {
    Remove-Item -Path $devLocalAppData -Recurse -Force
}

New-Item -ItemType Directory -Path $devBin -Force | Out-Null
New-Item -ItemType Directory -Path $devLocalAppData -Force | Out-Null

$escapedRepo = $repo.Replace('"', '""')
$escapedLocalAppData = $devLocalAppData.Replace('"', '""')
$escapedMongoose = $mongooseCli.Replace('"', '""')
$escapedNjord = $njordAgent.Replace('"', '""')

$mongooseDev = @"
@echo off
setlocal
set "LOCALAPPDATA=$escapedLocalAppData"
python "$escapedMongoose" %*
"@

$njordDev = @"
@echo off
setlocal
set "LOCALAPPDATA=$escapedLocalAppData"
set "MONGOOSE_LLM_INVOKE=python ""$escapedMongoose"" llm invoke --json"
python "$escapedNjord" %*
"@

Set-Content -Path (Join-Path $devBin "mongoose-dev.cmd") -Value $mongooseDev -Encoding ASCII
Set-Content -Path (Join-Path $devBin "Njord-dev.cmd") -Value $njordDev -Encoding ASCII

& (Join-Path $devBin "mongoose-dev.cmd") setup --registry-root $repo | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "mongoose-dev setup failed."
}

Write-Host ""
Write-Host "Mongoose development environment is ready."
Write-Host "Dev bin: $devBin"
Write-Host "Dev state: $devLocalAppData\Agents"
Write-Host ""
Write-Host "Use in this terminal:"
Write-Host "  `$env:Path = `"$devBin;`$env:Path`""
Write-Host "  mongoose-dev --version"
Write-Host "  mongoose-dev install Njord"
Write-Host "  Njord-dev"
Write-Host ""
Write-Host "Your normal installed mongoose command is unchanged."
