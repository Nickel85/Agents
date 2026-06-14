<#
.SYNOPSIS
Validates the source-backed development environment shims.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$setup = Join-Path $repoRoot "dev\setup-dev-env.ps1"
$devBin = Join-Path $repoRoot ".dev-bin"
$devLocalAppData = Join-Path $repoRoot ".dev-localappdata"
$mongooseDev = Join-Path $devBin "mongoose-dev.cmd"
$njordDev = Join-Path $devBin "Njord-dev.cmd"

function Assert-True {
    param(
        [object]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-DevCommand {
    param(
        [string]$FileName,
        [string[]]$Arguments = @(),
        [string]$InputText = ""
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FileName
    $startInfo.Arguments = ($Arguments | ForEach-Object { '"' + ($_ -replace '"', '\"') + '"' }) -join " "
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.UseShellExecute = $false

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    if ($InputText) {
        $process.StandardInput.Write($InputText)
    }
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = ($stdout + $stderr)
    }
}

if (Test-Path $devLocalAppData) {
    Remove-Item -Path $devLocalAppData -Recurse -Force
}
if (Test-Path $devBin) {
    Remove-Item -Path $devBin -Recurse -Force
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $setup | Out-Host
Assert-True ($LASTEXITCODE -eq 0) "dev setup failed."
Assert-True (Test-Path $mongooseDev) "mongoose-dev shim was not created."
Assert-True (Test-Path $njordDev) "Njord-dev shim was not created."
Assert-True (Test-Path (Join-Path $devLocalAppData "Agents\mongoose\config.json")) "dev mongoose config was not created."

$version = Invoke-DevCommand -FileName $mongooseDev -Arguments @("--version")
Assert-True ($version.ExitCode -eq 0) "mongoose-dev --version failed. Output: $($version.Output)"
Assert-True ($version.Output -match "development") "mongoose-dev should report a development build."

$state = Invoke-DevCommand -FileName $mongooseDev -Arguments @("state", "--init", "--json")
Assert-True ($state.ExitCode -eq 0) "mongoose-dev state failed. Output: $($state.Output)"
$stateJson = $state.Output | ConvertFrom-Json
Assert-True ($stateJson.state -match [regex]::Escape($devLocalAppData)) "mongoose-dev state did not use isolated LOCALAPPDATA."

$list = Invoke-DevCommand -FileName $mongooseDev -Arguments @("list")
Assert-True ($list.ExitCode -eq 0) "mongoose-dev list failed. Output: $($list.Output)"
Assert-True ($list.Output -match "Njord") "mongoose-dev list did not see repo Njord manifest."

$install = Invoke-DevCommand -FileName $mongooseDev -Arguments @("install", "Njord")
Assert-True ($install.ExitCode -eq 0) "mongoose-dev install Njord failed. Output: $($install.Output)"
Assert-True (Test-Path (Join-Path $devLocalAppData "Agents\state\agents\Njord.json")) "mongoose-dev did not install Njord into isolated state."
Assert-True (Test-Path (Join-Path $devLocalAppData "Agents\bin\Njord.cmd")) "mongoose-dev did not create isolated Njord launcher."

$run = Invoke-DevCommand -FileName $mongooseDev -Arguments @("run", "Njord", "hello-world", "--name", "Dev")
Assert-True ($run.Output -match "Hello, Dev.") "mongoose-dev run did not execute current checkout Njord capability."
Assert-True ($run.Output -match "Njord is ready") "mongoose-dev run did not execute the Njord source capability."

$llm = Invoke-DevCommand -FileName $mongooseDev -Arguments @("llm", "add", "fake-main", "--provider", "fake", "--model", "fake-chat", "--default")
Assert-True ($llm.ExitCode -eq 0) "mongoose-dev llm add fake-main failed. Output: $($llm.Output)"

$chat = Invoke-DevCommand -FileName $njordDev -InputText "review my finances`nexit`n"
Assert-True ($chat.ExitCode -eq 0) "Njord-dev finance chat failed. Output: $($chat.Output)"
Assert-True ($chat.Output -match "Fake LLM narration") "Njord-dev did not use the dev fake LLM backend for finance chat."
Assert-True ($chat.Output -notmatch "Capability: finance-review") "Njord-dev finance chat exposed command-style capability metadata."

$njord = Invoke-DevCommand -FileName $njordDev -InputText "exit`n"
Assert-True ($njord.ExitCode -eq 0) "Njord-dev REPL failed. Output: $($njord.Output)"
Assert-True ($njord.Output -match "Njord>") "Njord-dev did not open the REPL prompt."

Write-Host "Dev environment validation passed."
