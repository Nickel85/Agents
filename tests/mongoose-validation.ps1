<#
.SYNOPSIS
Validates the mongoose capability runtime CLI behavior without requiring a compiler.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$mongooseCli = Join-Path $repoRoot "mongoose\mongoose.py"
$testLocalAppData = Join-Path $repoRoot ".test-localappdata-mongoose"
$fixtureRoot = Join-Path $repoRoot ".test-mongoose-fixtures"

function Assert-True {
    param(
        [object]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-Mongoose {
    param([string[]]$Arguments)

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "python"
    $quotedArguments = @('"' + ($mongooseCli -replace '"', '\"') + '"') + ($Arguments | ForEach-Object {
        '"' + ($_ -replace '"', '\"') + '"'
    })
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

function New-FixtureAgent {
    param(
        [string]$Name,
        [string]$Description
    )

    $agentDirectory = Join-Path $fixtureRoot "agents\$($Name.ToLowerInvariant())"
    New-Item -ItemType Directory -Path $agentDirectory -Force | Out-Null

    $agentPython = @"
import json
import os
import subprocess
import sys

print("$Name fixture agent")
print("ARGS=" + "|".join(sys.argv[1:]))
context_path = os.environ.get("MONGOOSE_RUNTIME_CONTEXT", "")
if context_path:
    with open(context_path, "r", encoding="utf-8") as handle:
        context = json.load(handle)
    print("CTX_VERSION=" + str(context.get("contractVersion")))
    print("CTX_MODE=" + str(context.get("invocation", {}).get("mode")))
    print("CTX_AGENT=" + str(context.get("agent", {}).get("commandName")))
    print("CTX_CAPABILITY=" + str((context.get("capability") or {}).get("name", "")))
    print("CTX_STORAGE=" + str(context.get("providers", {}).get("storage", {}).get("available")))
    print("CTX_CONFIG_PROVIDER=" + str(context.get("providers", {}).get("configuration", {}).get("interface", "")))
    print("CTX_LLM_PROVIDER=" + str(context.get("providers", {}).get("llm", {}).get("interface", "")))
    print("CTX_LLM_AVAILABLE=" + str(context.get("providers", {}).get("llm", {}).get("available")))
    print("CTX_RUNTIME_PATH=" + str(bool(context.get("paths", {}).get("runtime"))))
    secret_value = os.environ.get("ALPHA_SECRET_TOKEN", "")
    print("CTX_HAS_SECRET=" + str(bool(secret_value and secret_value in json.dumps(context))))
    if len(sys.argv) > 1 and sys.argv[1] == "llm-ready":
        command = context.get("providers", {}).get("llm", {}).get("invokeCommand", [])
        if not command:
            print("LLM_INVOKE_MISSING=True")
            raise SystemExit(3)
        completed = subprocess.run(
            command,
            input="Explain this fixture capability result.",
            text=True,
            capture_output=True,
            check=False,
        )
        print("LLM_INVOKE_EXIT=" + str(completed.returncode))
        if completed.stdout:
            payload = json.loads(completed.stdout)
            print("LLM_INVOKE_OK=" + str(payload.get("ok")))
            print("LLM_INVOKE_PROFILE=" + str(payload.get("profile")))
            print("LLM_INVOKE_TEXT=" + str(payload.get("response", {}).get("content", "")))
"@
    Set-Content -Path (Join-Path $agentDirectory "agent.py") -Value $agentPython -Encoding ASCII

    $capabilities = @(
        @{
            name = "echo"
            description = "Echo fixture arguments."
            taskTypes = @("test", "echo")
            entrypointPath = "agent.py"
            requires = @{
                storage = @{
                    mode = "required"
                }
                logs = @{
                    mode = "optional"
                }
            }
        }
    )
    if ($Name -eq "Alpha") {
        $capabilities += @{
            name = "plan"
            description = "Plan fixture work."
            taskTypes = @("planning", "work-plan")
            entrypointPath = "agent.py"
        }
        $capabilities += @{
            name = "secure"
            description = "Require fixture configuration."
            taskTypes = @("secure")
            entrypointPath = "agent.py"
            configuration = @{
                required = @("ALPHA_SECRET_TOKEN")
            }
        }
        $capabilities += @{
            name = "llm-only"
            description = "Require an unavailable LLM runtime."
            taskTypes = @("llm-only")
            entrypointPath = "agent.py"
            llm = @{
                mode = "required"
                profile = "missing-llm-profile"
                deterministicFallback = "This fixture intentionally requires an LLM for validation."
            }
        }
        $capabilities += @{
            name = "llm-ready"
            description = "Require the configured fake LLM runtime."
            taskTypes = @("llm-ready")
            entrypointPath = "agent.py"
            llm = @{
                mode = "required"
                profile = "fake-main"
                deterministicFallback = "This fixture uses the fake LLM profile for validation."
            }
        }
    }
    if ($Name -eq "Beta") {
        $capabilities += @{
            name = "report"
            description = "Build fixture reports and summaries."
            taskTypes = @("report", "summary")
            entrypointPath = "agent.py"
        }
    }

    $manifest = @{
        commandName = $Name
        displayName = $Name
        version = "1.0.0"
        entrypointPath = "agent.py"
        example = "hello from $Name"
        description = $Description
        requires = @{
            state = @{
                mode = "required"
            }
        }
        capabilities = $capabilities
    } | ConvertTo-Json -Depth 5
    Set-Content -Path (Join-Path $agentDirectory "agent.json") -Value $manifest -Encoding ASCII

    return $agentDirectory
}

function New-InvalidFixtureAgent {
    $agentDirectory = Join-Path $fixtureRoot "agents\invalid"
    New-Item -ItemType Directory -Path $agentDirectory -Force | Out-Null
    Set-Content -Path (Join-Path $agentDirectory "agent.py") -Value "print('invalid')" -Encoding ASCII
    $manifest = @{
        commandName = "Invalid"
        displayName = "Invalid"
        entrypointPath = "missing.py"
        example = "invalid"
        description = "Invalid fixture."
        capabilities = @(
            @{
                name = "broken"
                description = "Broken fixture."
                taskTypes = "not-a-list"
                llm = @{
                    mode = "optional"
                    api_key = "secret-fixture-key"
                }
                requires = @{
                    storage = "required"
                    tools = @{
                        mode = "required"
                    }
                    apiProfiles = @{
                        mode = "optional"
                        profiles = @("token=fixture-secret")
                    }
                    unknownProvider = @{
                        mode = "optional"
                    }
                }
            }
        )
    } | ConvertTo-Json -Depth 5
    Set-Content -Path (Join-Path $agentDirectory "agent.json") -Value $manifest -Encoding ASCII
    return $agentDirectory
}

function New-UnsupportedSchemaFixtureAgent {
    $agentDirectory = Join-Path $fixtureRoot "agents\unsupported-schema"
    New-Item -ItemType Directory -Path $agentDirectory -Force | Out-Null
    Set-Content -Path (Join-Path $agentDirectory "agent.py") -Value "print('unsupported schema')" -Encoding ASCII
    $manifest = @{
        schemaVersion = 999
        commandName = "UnsupportedSchema"
        displayName = "Unsupported Schema"
        entrypointPath = "agent.py"
        example = "unsupported"
        description = "Fixture with a manifest schema newer than this Mongoose supports."
    } | ConvertTo-Json -Depth 5
    Set-Content -Path (Join-Path $agentDirectory "agent.json") -Value $manifest -Encoding ASCII
    return $agentDirectory
}

function New-IncompatibleRuntimeFixtureAgent {
    $agentDirectory = Join-Path $fixtureRoot "agents\future-runtime"
    New-Item -ItemType Directory -Path $agentDirectory -Force | Out-Null
    Set-Content -Path (Join-Path $agentDirectory "agent.py") -Value "print('future runtime')" -Encoding ASCII
    $manifest = @{
        commandName = "FutureRuntime"
        displayName = "Future Runtime"
        version = "1.0.0"
        entrypointPath = "agent.py"
        example = "future"
        description = "Fixture requiring a future Mongoose runtime contract."
        compatibility = @{
            mongooseRuntimeContract = 999
        }
        capabilities = @(
            @{
                name = "future"
                description = "Future runtime fixture capability."
                taskTypes = @("future-runtime")
                entrypointPath = "agent.py"
            }
        )
    } | ConvertTo-Json -Depth 5
    Set-Content -Path (Join-Path $agentDirectory "agent.json") -Value $manifest -Encoding ASCII
    return $agentDirectory
}

Assert-True (Test-Path $mongooseCli) "mongoose CLI is missing."

if (Test-Path $testLocalAppData) {
    Remove-Item -Path $testLocalAppData -Recurse -Force
}
if (Test-Path $fixtureRoot) {
    Remove-Item -Path $fixtureRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $testLocalAppData -Force | Out-Null
$alphaPath = New-FixtureAgent -Name "Alpha" -Description "Alpha fixture agent."
$betaPath = New-FixtureAgent -Name "Beta" -Description "Beta fixture agent."
$futureRuntimePath = New-IncompatibleRuntimeFixtureAgent
$invalidPath = New-InvalidFixtureAgent
$env:LOCALAPPDATA = $testLocalAppData

$setup = Invoke-Mongoose -Arguments @("setup", "--registry-root", $repoRoot)
Assert-True ($setup.ExitCode -eq 0) "mongoose setup failed. Output: $($setup.Output)"

$help = Invoke-Mongoose -Arguments @("--help")
Assert-True ($help.ExitCode -eq 0) "mongoose --help failed. Output: $($help.Output)"
Assert-True ($help.Output -match "mongoose --version") "mongoose --help did not include version example."
Assert-True ($help.Output -match "quick start") "mongoose --help did not include quick start guidance."
Assert-True ($help.Output -match "mongoose setup") "mongoose --help did not include setup quick start guidance."
Assert-True ($help.Output -match "mongoose capabilities") "mongoose --help did not include capabilities example."
Assert-True ($help.Output -match "mongoose install Njord") "mongoose --help did not include install example."
Assert-True ($help.Output -match "mongoose show Njord") "mongoose --help did not include show example."
Assert-True ($help.Output -match "mongoose run Njord") "mongoose --help did not include run example."
Assert-True ($help.Output -match "mongoose route") "mongoose --help did not include route example."
Assert-True ($help.Output -match "mongoose llm setup") "mongoose --help did not include guided LLM setup example."
Assert-True ($help.Output -match "mongoose llm setup --provider ollama --yes --bootstrap") "mongoose --help did not include Ollama bootstrap example."
Assert-True ($help.Output -match "mongoose validate") "mongoose --help did not include validate example."
Assert-True ($help.Output -match "mongoose remove Njord") "mongoose --help did not include remove example."
Assert-True ($help.Output -match "mongoose update") "mongoose --help did not include update guidance."
Assert-True ($help.Output -match "mongoose state --init") "mongoose --help did not include state guidance."

$llmHelp = Invoke-Mongoose -Arguments @("llm", "--help")
Assert-True ($llmHelp.ExitCode -eq 0) "mongoose llm --help failed. Output: $($llmHelp.Output)"
Assert-True ($llmHelp.Output -match "mongoose llm setup") "mongoose llm --help did not recommend guided setup."
Assert-True ($llmHelp.Output -match "mongoose llm setup --provider ollama --yes") "mongoose llm --help did not include Ollama setup example."
Assert-True ($llmHelp.Output -match "mongoose llm invoke") "mongoose llm --help did not include invocation example."
Assert-True ($llmHelp.Output -match "advanced manual setup") "mongoose llm --help did not distinguish manual setup."

$version = Invoke-Mongoose -Arguments @("--version")
Assert-True ($version.ExitCode -eq 0) "mongoose --version failed. Output: $($version.Output)"
Assert-True ($version.Output -match "mongoose 0.9.0") "mongoose --version did not report expected version."
Assert-True ($version.Output -match "development") "mongoose --version did not report development release kind."

$state = Invoke-Mongoose -Arguments @("state", "--init", "--json")
Assert-True ($state.ExitCode -eq 0) "mongoose state failed. Output: $($state.Output)"
$statePaths = $state.Output | ConvertFrom-Json
Assert-True (Test-Path $statePaths.state) "mongoose state did not create the shared state directory."
Assert-True (Test-Path $statePaths.logs) "mongoose state did not create the log directory."
Assert-True (Test-Path $statePaths.jobs) "mongoose state did not create the jobs directory."
Assert-True ($statePaths.version -eq "0.9.0") "mongoose state did not report CLI version."
Assert-True ($statePaths.releaseKind -eq "development") "mongoose state did not report development release kind."
Assert-True ($statePaths.releaseTag -eq "") "mongoose state should not report a release tag for development builds."
Assert-True ($statePaths.cliSource -match "mongoose.py") "mongoose state did not report CLI source."
Assert-True ($statePaths.registry -eq $repoRoot) "mongoose state did not report configured registry path."
Assert-True ($statePaths.registryRevision -notin @("", "missing", "not a git checkout")) "mongoose state did not report registry Git revision."
Assert-True ($statePaths.registryStatus -in @("clean", "dirty")) "mongoose state did not report registry Git status."
Assert-True ($statePaths.llmProfiles -match "profiles.json") "mongoose state did not report LLM profile storage."

$emptyLlmList = Invoke-Mongoose -Arguments @("llm", "list")
Assert-True ($emptyLlmList.ExitCode -eq 0) "mongoose llm list failed before profiles were configured. Output: $($emptyLlmList.Output)"
Assert-True ($emptyLlmList.Output -match "No LLM profiles configured") "empty LLM profile list did not explain there are no profiles."

$missingLlmPing = Invoke-Mongoose -Arguments @("llm", "ping")
Assert-True ($missingLlmPing.ExitCode -ne 0) "mongoose llm ping unexpectedly passed without a default profile. Output: $($missingLlmPing.Output)"
Assert-True ($missingLlmPing.Output -match "mongoose.llm_profile_missing") "missing default LLM ping did not emit a structured error."

$missingLlmStatus = Invoke-Mongoose -Arguments @("status")
Assert-True ($missingLlmStatus.ExitCode -eq 0) "mongoose status failed before LLM setup. Output: $($missingLlmStatus.Output)"
Assert-True ($missingLlmStatus.Output -match "No default LLM profile configured. Run: mongoose llm setup") "mongoose status did not guide users to LLM setup."

$fakeOllama = Join-Path $fixtureRoot "fake-ollama.exe"
New-Item -ItemType File -Path $fakeOllama -Force | Out-Null
$env:MONGOOSE_OLLAMA_BIN = $fakeOllama
$env:MONGOOSE_TEST_OLLAMA_MODELS = "llama3.2"
$ollamaSetup = Invoke-Mongoose -Arguments @("llm", "setup", "--provider", "ollama", "--yes", "--bootstrap", "--skip-ping")
Remove-Item Env:\MONGOOSE_OLLAMA_BIN
Remove-Item Env:\MONGOOSE_TEST_OLLAMA_MODELS
Assert-True ($ollamaSetup.ExitCode -eq 0) "mongoose llm setup --bootstrap failed with mocked Ollama. Output: $($ollamaSetup.Output)"
Assert-True ($ollamaSetup.Output -match "Ollama bootstrap") "mocked Ollama bootstrap did not run."
Assert-True ($ollamaSetup.Output -match "Model: llama3.2") "mocked Ollama bootstrap did not configure the default model."
Assert-True ($ollamaSetup.Output -match "Default: yes") "mocked Ollama bootstrap did not select the default profile."

$missingSecretProfile = Invoke-Mongoose -Arguments @("llm", "add", "openai-main", "--provider", "openai", "--model", "gpt-test", "--api-key-env", "MONGOOSE_TEST_OPENAI_KEY")
Assert-True ($missingSecretProfile.ExitCode -eq 0) "mongoose llm add openai-main failed. Output: $($missingSecretProfile.Output)"
Assert-True ($missingSecretProfile.Output -notmatch "secret-fixture-key") "mongoose llm add leaked an unrelated secret-like value."

$missingSecretPing = Invoke-Mongoose -Arguments @("llm", "ping", "openai-main")
Assert-True ($missingSecretPing.ExitCode -ne 0) "mongoose llm ping unexpectedly passed with a missing secret. Output: $($missingSecretPing.Output)"
Assert-True ($missingSecretPing.Output -match "mongoose.llm_secret_missing") "missing LLM secret ping did not emit a structured error."
Assert-True ($missingSecretPing.Output -match "MONGOOSE_TEST_OPENAI_KEY") "missing LLM secret ping did not identify the env var name."

$fakeProfile = Invoke-Mongoose -Arguments @("llm", "add", "fake-main", "--provider", "fake", "--model", "fake-chat", "--default", "--capability", "chat")
Assert-True ($fakeProfile.ExitCode -eq 0) "mongoose llm add fake-main failed. Output: $($fakeProfile.Output)"
Assert-True ($fakeProfile.Output -match "Mongoose LLM profile configured") "mongoose llm add did not report configuration success."
Assert-True ($fakeProfile.Output -match "Default: yes") "mongoose llm add --default did not select the profile."

$llmList = Invoke-Mongoose -Arguments @("llm", "list")
Assert-True ($llmList.ExitCode -eq 0) "mongoose llm list failed. Output: $($llmList.Output)"
Assert-True ($llmList.Output -match "fake-main") "mongoose llm list did not include fake-main."
Assert-True ($llmList.Output -match "\[default\]") "mongoose llm list did not mark the default profile."
Assert-True ($llmList.Output -notmatch "super-secret-fixture-token") "mongoose llm list leaked a secret value."

$llmShow = Invoke-Mongoose -Arguments @("llm", "show", "fake-main")
Assert-True ($llmShow.ExitCode -eq 0) "mongoose llm show failed. Output: $($llmShow.Output)"
Assert-True ($llmShow.Output -match "Provider: fake") "mongoose llm show did not report provider."
Assert-True ($llmShow.Output -match "Model: fake-chat") "mongoose llm show did not report model."

$llmPing = Invoke-Mongoose -Arguments @("llm", "ping", "fake-main")
Assert-True ($llmPing.ExitCode -eq 0) "mongoose llm ping fake-main failed. Output: $($llmPing.Output)"
Assert-True ($llmPing.Output -match "LLM provider reachable") "mongoose llm ping did not report reachability."
Assert-True ($llmPing.Output -match "Response: pong") "mongoose llm ping fake provider did not report fake response."

$llmInvoke = Invoke-Mongoose -Arguments @("llm", "invoke", "--profile", "fake-main", "Explain fixture facts")
Assert-True ($llmInvoke.ExitCode -eq 0) "mongoose llm invoke fake-main failed. Output: $($llmInvoke.Output)"
Assert-True ($llmInvoke.Output -match "LLM provider invoked") "mongoose llm invoke did not report invocation success."
Assert-True ($llmInvoke.Output -match "Fake LLM narration") "mongoose llm invoke did not print fake-provider narration."

$llmInvokeJson = Invoke-Mongoose -Arguments @("llm", "invoke", "--profile", "fake-main", "--json", "Explain fixture facts")
Assert-True ($llmInvokeJson.ExitCode -eq 0) "mongoose llm invoke --json fake-main failed. Output: $($llmInvokeJson.Output)"
Assert-True ($llmInvokeJson.Output -match '"ok": true') "mongoose llm invoke --json did not report ok."
Assert-True ($llmInvokeJson.Output -match '"profile": "fake-main"') "mongoose llm invoke --json did not report the profile."
Assert-True ($llmInvokeJson.Output -notmatch "super-secret-fixture-token") "mongoose llm invoke --json leaked a secret value."

$list = Invoke-Mongoose -Arguments @("list")
Assert-True ($list.ExitCode -eq 0) "mongoose list failed. Output: $($list.Output)"
Assert-True ($list.Output -match "Njord") "mongoose list did not include Njord."

$validateRegistry = Invoke-Mongoose -Arguments @("validate")
Assert-True ($validateRegistry.ExitCode -eq 0) "mongoose validate failed. Output: $($validateRegistry.Output)"
Assert-True ($validateRegistry.Output -match "Validated") "mongoose validate did not report validated manifests."

$missing = Invoke-Mongoose -Arguments @("install", "DefinitelyMissingAgent")
Assert-True ($missing.ExitCode -ne 0) "mongoose install unexpectedly succeeded for a missing agent."
Assert-True ($missing.Output -match "does not exist") "missing-agent output did not explain the failure."
Assert-True ($missing.Output -match "Available agents") "missing-agent output did not list available agents."

$install = Invoke-Mongoose -Arguments @("install", "Njord")
Assert-True ($install.ExitCode -eq 0) "mongoose install Njord failed. Output: $($install.Output)"
Assert-True ($install.Output -match "State:") "mongoose install did not report installed state path."

$launcherPath = Join-Path $testLocalAppData "Agents\bin\Njord.cmd"
Assert-True (Test-Path $launcherPath) "mongoose did not create Njord launcher."
$njordStatePath = Join-Path $testLocalAppData "Agents\state\agents\Njord.json"
Assert-True (Test-Path $njordStatePath) "mongoose did not write Njord installed state."

$launcher = Get-Content -Raw -Path $launcherPath
Assert-True ($launcher -notmatch "\sask\s") "Njord launcher should not force ask."
Assert-True ($launcher -match "%\*") "Njord launcher does not pass user arguments through."
Assert-True ($launcher -match "njord") "Njord launcher does not point at Njord."

$showNjord = Invoke-Mongoose -Arguments @("show", "Njord")
Assert-True ($showNjord.ExitCode -eq 0) "mongoose show Njord failed. Output: $($showNjord.Output)"
Assert-True ($showNjord.Output -match "Status: installed") "mongoose show Njord did not report installed status."
Assert-True ($showNjord.Output -match "Capabilities") "mongoose show Njord did not include capabilities."
Assert-True ($showNjord.Output -match "Manifest schema: 1") "mongoose show Njord did not include manifest schema."
Assert-True ($showNjord.Output -match "Task types: finance") "mongoose show Njord did not include task types."
Assert-True ($showNjord.Output -match "Required config: YNAB_ACCESS_TOKEN") "mongoose show Njord did not include configuration requirements."
Assert-True ($showNjord.Output -match "LLM mode: optional") "mongoose show Njord did not include LLM metadata."

$installedList = Invoke-Mongoose -Arguments @("list", "--installed")
Assert-True ($installedList.ExitCode -eq 0) "mongoose list --installed failed. Output: $($installedList.Output)"
Assert-True ($installedList.Output -match "Njord") "mongoose list --installed did not include Njord."

$configStatusDryRun = Invoke-Mongoose -Arguments @("route", "--task-type", "credential-status", "--dry-run", "config", "status")
Assert-True ($configStatusDryRun.ExitCode -eq 0) "Njord config-status dry-run should not require YNAB configuration. Output: $($configStatusDryRun.Output)"
Assert-True ($configStatusDryRun.Output -match "Selected: Njord::config-status") "Njord config-status route did not select the config capability."

$uninstall = Invoke-Mongoose -Arguments @("uninstall", "Njord")
Assert-True ($uninstall.ExitCode -eq 0) "mongoose uninstall Njord failed. Output: $($uninstall.Output)"
Assert-True (-not (Test-Path $launcherPath)) "mongoose uninstall did not remove Njord launcher."
Assert-True (-not (Test-Path $njordStatePath)) "mongoose uninstall did not remove Njord installed state."

$validateInvalid = Invoke-Mongoose -Arguments @("validate", $invalidPath)
Assert-True ($validateInvalid.ExitCode -ne 0) "mongoose validate unexpectedly passed invalid fixture. Output: $($validateInvalid.Output)"
Assert-True ($validateInvalid.Output -match "Invalid agent manifest") "invalid manifest output did not identify the manifest."
Assert-True ($validateInvalid.Output -match "entrypointPath does not exist") "invalid manifest output did not explain the missing entrypoint."
Assert-True ($validateInvalid.Output -match "taskTypes must be a list") "invalid manifest output did not explain invalid capability taskTypes."
Assert-True ($validateInvalid.Output -match "requires.storage must be an object") "invalid manifest output did not explain malformed provider requirement shape."
Assert-True ($validateInvalid.Output -match "requires provider 'tools'") "invalid manifest output did not explain unsupported required provider."
Assert-True ($validateInvalid.Output -match "unknownProvider is not a supported provider requirement") "invalid manifest output did not explain unknown provider requirement."
Assert-True ($validateInvalid.Output -match "must not contain a secret-like value") "invalid manifest output did not reject secret-like provider metadata."
Assert-True ($validateInvalid.Output -match "llm.api_key must not contain a secret value") "invalid manifest output did not reject secret-bearing LLM metadata."

Remove-Item -Path $invalidPath -Recurse -Force

$unsupportedSchemaPath = New-UnsupportedSchemaFixtureAgent
$validateUnsupportedSchema = Invoke-Mongoose -Arguments @("validate", $unsupportedSchemaPath)
Assert-True ($validateUnsupportedSchema.ExitCode -ne 0) "mongoose validate unexpectedly passed unsupported schema fixture. Output: $($validateUnsupportedSchema.Output)"
Assert-True ($validateUnsupportedSchema.Output -match "schemaVersion 999 is newer than supported version 1") "unsupported schema output did not explain the compatibility failure."

Remove-Item -Path $unsupportedSchemaPath -Recurse -Force

$setupFixtures = Invoke-Mongoose -Arguments @("setup", "--registry-root", $fixtureRoot)
Assert-True ($setupFixtures.ExitCode -eq 0) "mongoose setup for fixture registry failed. Output: $($setupFixtures.Output)"

$fixtureList = Invoke-Mongoose -Arguments @("list")
Assert-True ($fixtureList.ExitCode -eq 0) "mongoose list fixture registry failed. Output: $($fixtureList.Output)"
Assert-True ($fixtureList.Output -match "Alpha") "mongoose list did not include Alpha fixture."
Assert-True ($fixtureList.Output -match "Beta") "mongoose list did not include Beta fixture."

$installAlphaByPath = Invoke-Mongoose -Arguments @("install", $alphaPath)
Assert-True ($installAlphaByPath.ExitCode -eq 0) "mongoose install by path failed. Output: $($installAlphaByPath.Output)"
$alphaLauncher = Join-Path $testLocalAppData "Agents\bin\Alpha.cmd"
$alphaStatePath = Join-Path $testLocalAppData "Agents\state\agents\Alpha.json"
Assert-True (Test-Path $alphaLauncher) "mongoose install by path did not create Alpha launcher."
Assert-True (Test-Path $alphaStatePath) "mongoose install by path did not write Alpha state."

$installBetaByPath = Invoke-Mongoose -Arguments @("install", $betaPath)
Assert-True ($installBetaByPath.ExitCode -eq 0) "mongoose install by path for Beta failed. Output: $($installBetaByPath.Output)"
$betaLauncher = Join-Path $testLocalAppData "Agents\bin\Beta.cmd"
$betaStatePath = Join-Path $testLocalAppData "Agents\state\agents\Beta.json"
Assert-True (Test-Path $betaLauncher) "mongoose install by path did not create Beta launcher."
Assert-True (Test-Path $betaStatePath) "mongoose install by path did not write Beta state."

$installFutureRuntimeByPath = Invoke-Mongoose -Arguments @("install", $futureRuntimePath)
Assert-True ($installFutureRuntimeByPath.ExitCode -eq 0) "mongoose install by path for FutureRuntime failed. Output: $($installFutureRuntimeByPath.Output)"
$futureRuntimeLauncher = Join-Path $testLocalAppData "Agents\bin\FutureRuntime.cmd"
$futureRuntimeStatePath = Join-Path $testLocalAppData "Agents\state\agents\FutureRuntime.json"
Assert-True (Test-Path $futureRuntimeLauncher) "mongoose install by path did not create FutureRuntime launcher."
Assert-True (Test-Path $futureRuntimeStatePath) "mongoose install by path did not write FutureRuntime state."

$showAlpha = Invoke-Mongoose -Arguments @("show", "Alpha")
Assert-True ($showAlpha.ExitCode -eq 0) "mongoose show Alpha failed. Output: $($showAlpha.Output)"
Assert-True ($showAlpha.Output -match "Version: 1.0.0") "mongoose show Alpha did not include version."
Assert-True ($showAlpha.Output -match "echo") "mongoose show Alpha did not include capability metadata."

$capabilities = Invoke-Mongoose -Arguments @("capabilities")
Assert-True ($capabilities.ExitCode -eq 0) "mongoose capabilities failed. Output: $($capabilities.Output)"
Assert-True ($capabilities.Output -match "Alpha::echo") "mongoose capabilities did not include Alpha echo."
Assert-True ($capabilities.Output -match "Alpha::plan") "mongoose capabilities did not include Alpha plan."
Assert-True ($capabilities.Output -match "Beta::report") "mongoose capabilities did not include Beta report."

$missingConfigRoute = Invoke-Mongoose -Arguments @("route", "--task-type", "secure")
Assert-True ($missingConfigRoute.ExitCode -ne 0) "mongoose route unexpectedly ran a capability with missing config. Output: $($missingConfigRoute.Output)"
Assert-True ($missingConfigRoute.Output -match "mongoose.missing_required_configuration") "missing config route did not emit a structured error code."
Assert-True ($missingConfigRoute.Output -match "ALPHA_SECRET_TOKEN") "missing config route did not identify the missing config name."

$env:ALPHA_SECRET_TOKEN = "super-secret-fixture-token"
$secureRoute = Invoke-Mongoose -Arguments @("route", "--task-type", "secure", "check")
Assert-True ($secureRoute.ExitCode -eq 0) "mongoose route did not run secure capability with required config present. Output: $($secureRoute.Output)"
Assert-True ($secureRoute.Output -match "CTX_HAS_SECRET=False") "runtime context leaked a secret environment value."
Assert-True ($secureRoute.Output -notmatch "super-secret-fixture-token") "secure route output leaked a secret environment value."
Remove-Item Env:\ALPHA_SECRET_TOKEN

$llmRoute = Invoke-Mongoose -Arguments @("route", "--task-type", "llm-only")
Assert-True ($llmRoute.ExitCode -ne 0) "mongoose route unexpectedly ran an LLM-required capability. Output: $($llmRoute.Output)"
Assert-True ($llmRoute.Output -match "mongoose.provider_unavailable") "LLM-required route did not emit a structured provider error."

$llmReadyRoute = Invoke-Mongoose -Arguments @("route", "--task-type", "llm-ready", "hello")
Assert-True ($llmReadyRoute.ExitCode -eq 0) "mongoose route did not run an LLM-required capability with a configured fake profile. Output: $($llmReadyRoute.Output)"
Assert-True ($llmReadyRoute.Output -match "Selected: Alpha::llm-ready") "mongoose route did not select the llm-ready capability."
Assert-True ($llmReadyRoute.Output -match "Selector: LLM \(fake-main\)") "mongoose route did not report configured LLM capability selection."
Assert-True ($llmReadyRoute.Output -match "ARGS=llm-ready\|hello") "mongoose route did not pass llm-ready capability arguments."
Assert-True ($llmReadyRoute.Output -match "CTX_LLM_PROVIDER=mongoose.llm.v1") "runtime context did not expose the LLM provider interface."
Assert-True ($llmReadyRoute.Output -match "CTX_LLM_AVAILABLE=True") "runtime context did not mark the fake LLM provider available."
Assert-True ($llmReadyRoute.Output -match "LLM_INVOKE_EXIT=0") "fixture capability could not invoke the Mongoose LLM runtime."
Assert-True ($llmReadyRoute.Output -match "LLM_INVOKE_OK=True") "fixture capability did not receive an ok LLM invocation result."
Assert-True ($llmReadyRoute.Output -match "LLM_INVOKE_PROFILE=fake-main") "fixture capability did not invoke the expected LLM profile."
Assert-True ($llmReadyRoute.Output -match "Fake LLM narration") "fixture capability did not receive fake-provider narration."

$futureRuntimeRoute = Invoke-Mongoose -Arguments @("route", "--task-type", "future-runtime")
Assert-True ($futureRuntimeRoute.ExitCode -ne 0) "mongoose route unexpectedly ran an incompatible runtime capability. Output: $($futureRuntimeRoute.Output)"
Assert-True ($futureRuntimeRoute.Output -match "mongoose.incompatible_runtime_contract") "incompatible runtime route did not emit a structured error."

$futureRuntimeRun = Invoke-Mongoose -Arguments @("run", "FutureRuntime")
Assert-True ($futureRuntimeRun.ExitCode -ne 0) "mongoose run unexpectedly ran an incompatible runtime agent. Output: $($futureRuntimeRun.Output)"
Assert-True ($futureRuntimeRun.Output -match "mongoose.incompatible_runtime_contract") "incompatible runtime run did not emit a structured error."

$routeAlpha = Invoke-Mongoose -Arguments @("route", "--task-type", "work-plan", "build", "steps")
Assert-True ($routeAlpha.ExitCode -eq 0) "mongoose route did not dispatch to Alpha. Output: $($routeAlpha.Output)"
Assert-True ($routeAlpha.Output -match "Selected: Alpha::plan") "mongoose route did not select Alpha plan."
Assert-True ($routeAlpha.Output -match "Alpha fixture agent") "mongoose route did not execute Alpha fixture."
Assert-True ($routeAlpha.Output -match "ARGS=plan\|build\|steps") "mongoose route did not pass Alpha capability arguments."
Assert-True ($routeAlpha.Output -match "CTX_VERSION=1") "mongoose route did not pass runtime contract version to Alpha fixture."
Assert-True ($routeAlpha.Output -match "CTX_MODE=route") "mongoose route context did not identify route mode."
Assert-True ($routeAlpha.Output -match "CTX_AGENT=Alpha") "mongoose route context did not identify the agent."
Assert-True ($routeAlpha.Output -match "CTX_CAPABILITY=plan") "mongoose route context did not identify the selected capability."
Assert-True ($routeAlpha.Output -match "CTX_STORAGE=True") "mongoose route context did not expose the local storage provider."
Assert-True ($routeAlpha.Output -match "CTX_CONFIG_PROVIDER=mongoose.configuration.v1") "mongoose route context did not expose configuration provider metadata."

$routeBeta = Invoke-Mongoose -Arguments @("route", "please", "build", "a", "summary")
Assert-True ($routeBeta.ExitCode -eq 0) "mongoose route did not dispatch to Beta from natural-language request. Output: $($routeBeta.Output)"
Assert-True ($routeBeta.Output -match "Selected: Beta::report") "mongoose route did not select Beta report."
Assert-True ($routeBeta.Output -match "Selector: LLM \(fake-main\)") "natural-language route did not use the configured LLM selector."
Assert-True ($routeBeta.Output -match "Beta fixture agent") "mongoose route did not execute Beta fixture."
Assert-True ($routeBeta.Output -match "ARGS=report\|please\|build\|a\|summary") "mongoose route did not pass Beta capability arguments."

$ambiguousRoute = Invoke-Mongoose -Arguments @("route", "--task-type", "test", "--dry-run")
Assert-True ($ambiguousRoute.ExitCode -eq 0) "configured LLM selector did not resolve an ambiguous task type. Output: $($ambiguousRoute.Output)"
Assert-True ($ambiguousRoute.Output -match "Selected: Alpha::echo") "configured LLM selector did not choose an installed ambiguous capability."
Assert-True ($ambiguousRoute.Output -match "Selector: LLM \(fake-main\)") "ambiguous route did not report configured LLM selection."

$missingRoute = Invoke-Mongoose -Arguments @("route", "--task-type", "definitely-missing")
Assert-True ($missingRoute.ExitCode -ne 0) "mongoose route unexpectedly resolved unsupported task type. Output: $($missingRoute.Output)"
Assert-True ($missingRoute.Output -match "No installed capability can handle") "unsupported route output did not explain the failure."

$missingToolRoute = Invoke-Mongoose -Arguments @("route", "weather", "in", "Boston")
Assert-True ($missingToolRoute.ExitCode -ne 0) "mongoose route unexpectedly ran a missing weather tool. Output: $($missingToolRoute.Output)"
Assert-True ($missingToolRoute.Output -match "Suggested capability or tool to add") "missing tool route did not include an LLM-suggested tool section."
Assert-True ($missingToolRoute.Output -match "Name: weather-lookup") "missing tool route did not propose the weather lookup capability."
Assert-True ($missingToolRoute.Output -match "LLM selector: fake-main") "missing tool proposal did not identify the configured LLM selector."

$runAlpha = Invoke-Mongoose -Arguments @("run", "Alpha", "echo", "hello")
Assert-True ($runAlpha.ExitCode -eq 0) "mongoose run Alpha failed. Output: $($runAlpha.Output)"
Assert-True ($runAlpha.Output -match "Alpha fixture agent") "mongoose run Alpha did not execute fixture agent."
Assert-True ($runAlpha.Output -match "ARGS=echo\|hello") "mongoose run Alpha did not pass agent arguments."
Assert-True ($runAlpha.Output -match "CTX_VERSION=1") "mongoose run did not pass runtime contract version to Alpha fixture."
Assert-True ($runAlpha.Output -match "CTX_MODE=run") "mongoose run context did not identify run mode."
Assert-True ($runAlpha.Output -match "CTX_AGENT=Alpha") "mongoose run context did not identify the agent."
Assert-True ($runAlpha.Output -match "CTX_RUNTIME_PATH=True") "mongoose run context did not include runtime state path."

$removeAlpha = Invoke-Mongoose -Arguments @("remove", "Alpha")
Assert-True ($removeAlpha.ExitCode -eq 0) "mongoose remove Alpha failed. Output: $($removeAlpha.Output)"
Assert-True (-not (Test-Path $alphaLauncher)) "mongoose remove did not remove Alpha launcher."
Assert-True (-not (Test-Path $alphaStatePath)) "mongoose remove did not remove Alpha state."

$removeBeta = Invoke-Mongoose -Arguments @("remove", "Beta")
Assert-True ($removeBeta.ExitCode -eq 0) "mongoose remove Beta failed. Output: $($removeBeta.Output)"
Assert-True (-not (Test-Path $betaLauncher)) "mongoose remove did not remove Beta launcher."
Assert-True (-not (Test-Path $betaStatePath)) "mongoose remove did not remove Beta state."

$removeFutureRuntime = Invoke-Mongoose -Arguments @("remove", "FutureRuntime")
Assert-True ($removeFutureRuntime.ExitCode -eq 0) "mongoose remove FutureRuntime failed. Output: $($removeFutureRuntime.Output)"
Assert-True (-not (Test-Path $futureRuntimeLauncher)) "mongoose remove did not remove FutureRuntime launcher."
Assert-True (-not (Test-Path $futureRuntimeStatePath)) "mongoose remove did not remove FutureRuntime state."

Write-Host "Mongoose validation passed."

