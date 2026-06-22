<#
.SYNOPSIS
Smoke-tests the built mongoose.exe capability runtime.
#>

[CmdletBinding()]
param(
    [string]$MongooseExe = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $MongooseExe) {
    $MongooseExe = Join-Path $repoRoot "dist\mongoose.exe"
}

$MongooseExe = (Resolve-Path $MongooseExe).Path
$testLocalAppData = Join-Path $repoRoot ".test-localappdata-mongoose-exe"
$testCloneRoot = Join-Path $repoRoot ".test-mongoose-update-registry"
$testRegistryOnlyRoot = Join-Path $repoRoot ".test-mongoose-registry-only-update"

function Assert-True {
    param(
        [object]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-MongooseExe {
    param([string[]]$Arguments)

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $MongooseExe
    $quotedArguments = $Arguments | ForEach-Object {
        '"' + ($_ -replace '"', '\"') + '"'
    }
    $startInfo.Arguments = $quotedArguments -join " "
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = ($stdout + $stderr)
    }
}

Assert-True (Test-Path $MongooseExe) "mongoose.exe is missing: $MongooseExe"

foreach ($path in @($testLocalAppData, $testCloneRoot, $testRegistryOnlyRoot)) {
    if (Test-Path $path) {
        Remove-Item -Path $path -Recurse -Force
    }
}

New-Item -ItemType Directory -Path $testLocalAppData -Force | Out-Null
$env:LOCALAPPDATA = $testLocalAppData

$version = Invoke-MongooseExe -Arguments @("--version")
Assert-True ($version.ExitCode -eq 0) "mongoose.exe --version failed. Output: $($version.Output)"
Assert-True ($version.Output -match "mongoose 0.9.0") "mongoose.exe --version did not report expected version."
$expectedReleaseKind = "development"
if ($env:GITHUB_REF_TYPE -eq "tag" -and $env:GITHUB_REF_NAME -match "^v") {
    $expectedReleaseKind = "official release"
}
Assert-True ($version.Output -match $expectedReleaseKind) "mongoose.exe --version did not report expected release kind '$expectedReleaseKind'. Output: $($version.Output)"

$setup = Invoke-MongooseExe -Arguments @("setup", "--registry-root", $repoRoot)
Assert-True ($setup.ExitCode -eq 0) "mongoose setup failed. Output: $($setup.Output)"

$state = Invoke-MongooseExe -Arguments @("state", "--init", "--json")
Assert-True ($state.ExitCode -eq 0) "mongoose state failed. Output: $($state.Output)"
$statePaths = $state.Output | ConvertFrom-Json
Assert-True (Test-Path $statePaths.state) "mongoose state did not create the shared state directory."
Assert-True (Test-Path $statePaths.logs) "mongoose state did not create the log directory."
Assert-True (Test-Path $statePaths.jobs) "mongoose state did not create the jobs directory."
Assert-True ($statePaths.version -eq "0.9.0") "mongoose state did not report CLI version."
if ($env:GITHUB_REF_TYPE -eq "tag" -and $env:GITHUB_REF_NAME -match "^v") {
    Assert-True ($statePaths.releaseKind -eq "official") "mongoose state did not report official release kind."
    Assert-True ($statePaths.releaseTag -eq $env:GITHUB_REF_NAME) "mongoose state did not report the release tag."
} else {
    Assert-True ($statePaths.releaseKind -eq "development") "mongoose state did not report development release kind."
    Assert-True ($statePaths.releaseTag -eq "") "mongoose state should not report a release tag for development builds."
}
Assert-True ($statePaths.registryRevision -notin @("", "missing", "not a git checkout")) "mongoose state did not report registry revision."

$list = Invoke-MongooseExe -Arguments @("list")
Assert-True ($list.ExitCode -eq 0) "mongoose list failed. Output: $($list.Output)"
Assert-True ($list.Output -match "Njord") "mongoose list did not include Njord."

$install = Invoke-MongooseExe -Arguments @("install", "Njord")
Assert-True ($install.ExitCode -eq 0) "mongoose install Njord failed. Output: $($install.Output)"
Assert-True ($install.Output -match "State:") "mongoose install did not report installed state."

$nickLauncher = Join-Path $testLocalAppData "Agents\bin\Njord.cmd"
Assert-True (Test-Path $nickLauncher) "mongoose install did not create Njord launcher."
$njordStatePath = Join-Path $testLocalAppData "Agents\state\agents\Njord.json"
Assert-True (Test-Path $njordStatePath) "mongoose install did not create Njord state."

$show = Invoke-MongooseExe -Arguments @("show", "Njord")
Assert-True ($show.ExitCode -eq 0) "mongoose show Njord failed. Output: $($show.Output)"
Assert-True ($show.Output -match "Status: installed") "mongoose show did not report installed status."

$installedList = Invoke-MongooseExe -Arguments @("list", "--installed")
Assert-True ($installedList.ExitCode -eq 0) "mongoose list --installed failed. Output: $($installedList.Output)"
Assert-True ($installedList.Output -match "Njord") "mongoose list --installed did not include Njord."

$uninstall = Invoke-MongooseExe -Arguments @("remove", "Njord")
Assert-True ($uninstall.ExitCode -eq 0) "mongoose remove Njord failed. Output: $($uninstall.Output)"
Assert-True (-not (Test-Path $nickLauncher)) "mongoose uninstall did not remove Njord launcher."
Assert-True (-not (Test-Path $njordStatePath)) "mongoose uninstall did not remove Njord state."

$setupForUpdate = Invoke-MongooseExe -Arguments @(
    "setup",
    "--registry-root",
    $testCloneRoot,
    "--registry-url",
    $repoRoot
)
Assert-True ($setupForUpdate.ExitCode -eq 0) "mongoose setup for update failed. Output: $($setupForUpdate.Output)"

$releaseMetadataPath = Join-Path $testLocalAppData "mongoose-releases.json"
$releaseMetadata = @"
[
  {
    "tag_name": "v0.6.1",
    "draft": false,
    "prerelease": false,
    "assets": []
  }
]
"@
Set-Content -Path $releaseMetadataPath -Value $releaseMetadata -Encoding ASCII
$env:MONGOOSE_RELEASES_API_URL = ([System.Uri](Resolve-Path $releaseMetadataPath).Path).AbsoluteUri
$update = Invoke-MongooseExe -Arguments @("update")
Assert-True ($update.ExitCode -eq 0) "mongoose update failed. Output: $($update.Output)"
Assert-True (Test-Path (Join-Path $testCloneRoot "agents\njord\agent.json")) "mongoose update did not clone the registry."
Assert-True ($update.Output -match "Mongoose registry update") "mongoose update did not report the registry phase."
Assert-True ($update.Output -match "Mongoose CLI update") "mongoose update did not report the CLI phase."
Assert-True ($update.Output -match "Update summary") "mongoose update did not report a phase summary."
Assert-True ($update.Output -match "Mongoose is already current") "mongoose update did not report the already-current CLI state."
$env:MONGOOSE_RELEASES_API_URL = $null

$setupForRegistryOnly = Invoke-MongooseExe -Arguments @(
    "setup",
    "--registry-root",
    $testRegistryOnlyRoot,
    "--registry-url",
    $repoRoot
)
Assert-True ($setupForRegistryOnly.ExitCode -eq 0) "mongoose setup for registry-only update failed. Output: $($setupForRegistryOnly.Output)"

$registryOnly = Invoke-MongooseExe -Arguments @("update", "--registry-only")
Assert-True ($registryOnly.ExitCode -eq 0) "mongoose update --registry-only failed. Output: $($registryOnly.Output)"
Assert-True ($registryOnly.Output -match "Mongoose registry update") "registry-only update did not report the registry phase."
Assert-True ($registryOnly.Output -notmatch "Mongoose CLI update") "registry-only update should not run the CLI phase."
Assert-True (Test-Path (Join-Path $testRegistryOnlyRoot "agents\njord\agent.json")) "mongoose update --registry-only did not clone the registry."

Write-Host "Mongoose EXE smoke tests passed."

