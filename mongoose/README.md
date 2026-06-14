# Mongoose

Mongoose is the local-first capability runtime CLI for this agent repository.
It decouples AI functionality from underlying models, tools, storage, APIs, and
execution environments while still providing lifecycle commands for installing,
updating, and running agents.

The long-term goal is to make agents portable, reusable, and easy to manage
throughout their lifecycle. In that vision, agents declare the capabilities
they require, including LLMs, memory, tools, storage, and configured APIs, and
Mongoose provides those capabilities through a common interface so the same
agent can run on a personal laptop, enterprise workstation, or server without
modification.

That vision is not fully implemented yet. The sections below distinguish what
Mongoose does today from committed roadmap work and longer-term platform goals.

It installs as:

```text
mongoose
```

## Current Capabilities

Mongoose currently provides a Windows-focused, user-local CLI for installing
and running agents from this repository. It can:

- list available agents
- install an agent command from the configured registry or a local agent path
- inspect installed agent metadata and capabilities
- validate agent manifests without importing agent code
- enumerate and route across installed capabilities by task type
- run an installed agent entrypoint
- remove an installed agent command and state
- update the local agent registry from GitHub
- initialize and inspect user-local Mongoose state
- generate and validate architecture model, SysML, and Mermaid documentation
- inspect persisted jobs, runtime health, and guided LLM setup status

Check the CLI version:

```powershell
mongoose --version
```

Development/source builds report as `development`. Executables built by the
GitHub release workflow from a matching `v*` tag report as `official release`
and include the tag.

Human-readable Mongoose and Njord output uses terminal color when stdout is an
interactive terminal. Redirected output stays plain by default, and JSON output
is never colorized. Disable color explicitly with:

```powershell
mongoose --no-color state
Njord --no-color brief
```

Color can also be disabled with `NO_COLOR=1`, `MONGOOSE_NO_COLOR=1`, or
`NJORD_NO_COLOR=1`. For troubleshooting captured output, force color with
`MONGOOSE_FORCE_COLOR=1` or `NJORD_FORCE_COLOR=1`.

Show local state, registry path, and registry revision diagnostics:

```powershell
mongoose state
mongoose state --json
mongoose status
```

Implemented agent metadata includes manifest schema validation, local entrypoint
resolution, command-name uniqueness, declared capability metadata, required
configuration names, compatibility metadata, and descriptive LLM metadata.

Implemented routing is deterministic. It selects installed capabilities from
manifest metadata and dispatches through the current subprocess entrypoint
shape. Mongoose does not yet provide a portable runtime context, common
provider interfaces, managed dependency isolation, or cross-platform execution
guarantees.

## Roadmap

Mongoose is being developed in layers so current agents remain useful while the
runtime grows toward the broader platform vision:

- Provider-neutral LLM runtime configuration and invocation are tracked in
  [#23](https://github.com/Nickel85/Mongoose/issues/23).
- Event-based and timer-based scheduling are tracked in
  [#1](https://github.com/Nickel85/Mongoose/issues/1) and
  [#2](https://github.com/Nickel85/Mongoose/issues/2).
- Agent job and status commands are tracked in
  [#4](https://github.com/Nickel85/Mongoose/issues/4), with persistent scheduler
  runtime work in [#5](https://github.com/Nickel85/Mongoose/issues/5).
- Cross-platform runtime support is tracked in
  [#38](https://github.com/Nickel85/Mongoose/issues/38).
- Agent dependency and environment isolation are tracked in
  [#39](https://github.com/Nickel85/Mongoose/issues/39).
- Package registry and versioning are tracked in
  [#40](https://github.com/Nickel85/Mongoose/issues/40).
- A portable agent execution contract is tracked in
  [#41](https://github.com/Nickel85/Mongoose/issues/41).
- Common capability provider interfaces for memory, storage, tools, and
  configured APIs are tracked in
  [#42](https://github.com/Nickel85/Mongoose/issues/42).

## Platform Direction

Mongoose's platform direction is local-first agent lifecycle management:
install, configure, discover, execute, update, route, observe, and remove
agents through a consistent runtime surface.

The intended future agent contract is provider-neutral. Agents should be able
to ask Mongoose for declared capabilities such as LLM profiles, durable memory,
local storage, tool invocation, external API profiles, logs, and job context
without binding themselves to a single host environment or secret layout.

Njord is the first concrete agent use case, not the whole platform. The Njord
roadmap is expected to prove useful deterministic financial workflows before
guarded autonomy is added. The core Njord budget-maintenance path is:

```text
Analyze budget state
-> draft a money-movement or new-money allocation plan
-> require user approval
-> execute only approved YNAB writes
-> reconcile state and record decision outcomes
```

The manual weekly brief tracked in
[#28](https://github.com/Nickel85/Mongoose/issues/28) remains read-only
financial value. The guarded write-planning work in
[#17](https://github.com/Nickel85/Mongoose/issues/17),
[#18](https://github.com/Nickel85/Mongoose/issues/18),
[#19](https://github.com/Nickel85/Mongoose/issues/19), and
[#121](https://github.com/Nickel85/Mongoose/issues/121) turns recommendations
into reviewable budget-maintenance plans. The guarded write-execution work in
[#20](https://github.com/Nickel85/Mongoose/issues/20) and
[#21](https://github.com/Nickel85/Mongoose/issues/21) executes only approved
plans and reconciles the result. Decision metrics and learned budgeting
preferences are tracked in
[#66](https://github.com/Nickel85/Mongoose/issues/66) and the broader
v2.1 decision-learning milestone.

Mongoose separately adds the package, scheduling, provider, capability, and
portability features needed for agents to run consistently across environments.
Those platform features should be pulled into Njord releases only when they are
required to preserve the budget-maintenance contract. The Njord roadmap should
not absorb unrelated Mongoose platform expansion, commerce capabilities, or UI
host work simply because those features are also useful later.

This sequencing is intentional. Agent-value milestones validate what the
platform actually needs; Mongoose platform milestones then generalize those
needs into reusable runtime features.

## Command Summary

The CLI can:

- list available agents
- install an agent command from the configured registry or a local agent path
- inspect installed agent metadata and capabilities
- enumerate and route across installed capabilities by task type
- run an installed agent entrypoint
- remove an installed agent command and state
- update the local agent registry from GitHub

## Build The EXE

From the repository root:

```text
.\build-mongoose.cmd
```

This generates:

```text
dist\mongoose.exe
```

The build currently uses `gcc` on Windows.

GitHub Actions also builds `mongoose.exe` for pull requests targeting `main`, pushes to `main`, and version tags. PR builds upload the executable as an Actions artifact. Tag builds attach it to the GitHub Release.

## Source-Backed Development Environment

Use the development environment when testing current source changes while
keeping the installed release available:

```powershell
.\dev\setup-dev-env.ps1
$env:Path = "$PWD\.dev-bin;$env:Path"
mongoose-dev --version
mongoose-dev install Njord
Njord-dev
```

This creates repo-local shims and state:

```text
.dev-bin\mongoose-dev.cmd
.dev-bin\Njord-dev.cmd
.dev-localappdata\Agents\
```

`mongoose-dev` runs `mongoose\mongoose.py` from the current checkout, and
`Njord-dev` runs `agents\njord\agent.py` from the current checkout. No release
build or reinstall is needed after editing source files.

Reset the dev state:

```powershell
.\dev\setup-dev-env.ps1 -Reset
```

## Install Mongoose

From the repository root:

```text
.\install-mongoose.cmd
```

This copies:

```text
dist\mongoose.exe
```

to:

```text
%LOCALAPPDATA%\Agents\bin\mongoose.exe
```

It also copies the Python CLI implementation to:

```text
%LOCALAPPDATA%\Agents\mongoose\mongoose.py
```

The installer adds `%LOCALAPPDATA%\Agents\bin` to the current user's `PATH`. Open a new terminal after installing.

No administrator privileges are required.

## Commands

List available agents:

```powershell
mongoose list
```

List installed agents:

```powershell
mongoose list --installed
```

Install an agent:

```powershell
mongoose install Njord
```

Install an agent directly from a local package path:

```powershell
mongoose install C:\path\to\agent
```

Show installed metadata and discovered capabilities:

```powershell
mongoose show Njord
```

List routeable installed capabilities:

```powershell
mongoose capabilities
```

Route a request to an installed capability:

```powershell
mongoose route --task-type budget-summary "current budget"
mongoose route "summarize my current budget"
mongoose route --task-type budget-summary --dry-run
```

Validate manifests:

```powershell
mongoose validate
mongoose validate agents\njord
```

Generate or validate architecture artifacts from manifests and runtime metadata:

```powershell
mongoose architecture generate --root .
mongoose architecture validate --root .
```

This writes a shared model, SysML v2 text views, and Mermaid diagram views under
`docs/architecture/`. Mermaid does not parse SysML directly; both outputs are
generated from the same architecture model.

Run an installed agent entrypoint through Mongoose:

```powershell
mongoose run Njord config status
mongoose run Njord ask "Get me my latest budget"
```

Configure and test an LLM profile before LLM-backed agents use it:

```powershell
mongoose llm setup
mongoose llm setup --provider ollama --yes --bootstrap
mongoose llm add fake-main --provider fake --model fake-chat --default
mongoose llm ping fake-main
mongoose llm list
mongoose llm show fake-main
```

Remote providers store secret references only:

```powershell
mongoose llm add openai-main --provider openai --model gpt-4.1-mini --api-key-env OPENAI_API_KEY --default
mongoose llm ping openai-main
```

The guided setup flow asks for provider metadata and stores environment variable
names, not raw secrets. It supports Ollama/local HTTP, OpenAI, Anthropic, and a
fake/test provider:

```powershell
mongoose llm setup
mongoose llm setup --provider fake --yes
mongoose llm setup --provider ollama --yes
mongoose llm setup --provider ollama --yes --bootstrap
```

The Ollama bootstrap path checks for Ollama, starts it when possible, pulls the
selected model when needed, configures `ollama-local`, pings it, and performs a
small invocation check. The default bootstrap model is `llama3.2`; use
`--model gemma4` or another installed model when you want a larger local model.

Remove an installed agent:

```powershell
mongoose remove Njord
```

`mongoose uninstall Njord` remains available as an alias.

Pull down registry updates:

```powershell
mongoose update
```

`mongoose update` runs a two-phase update flow:

- refresh the configured registry path.
- check the installed Mongoose CLI against GitHub Releases.

If the registry is a Git checkout, Mongoose runs `git pull --ff-only`. If the
configured registry path does not exist, it clones the configured GitHub
registry URL. The command prints each phase and an update summary so registry
and CLI status are distinct.

Run only the registry phase:

```powershell
mongoose update --registry-only
```

Update the installed Mongoose CLI:

```powershell
mongoose update --self-only
```

`mongoose update --self-only` checks GitHub Releases for the latest stable
`Nickel85/Mongoose` release, compares it with the installed CLI version,
downloads the released `mongoose.exe` asset when a newer version is available,
and replaces the user-local executable under `%LOCALAPPDATA%\Agents\bin`.
Prereleases are ignored unless `--include-prerelease` is passed. The older
`mongoose update --self` spelling remains available as an alias.

After pulling registry changes, rerun `mongoose install <agent>` to refresh
installed agent metadata and launchers from the current registry. Local
contributors can still use `build-mongoose.cmd` and `install-mongoose.cmd` for
development builds.

Show the user-local state contract:

```powershell
mongoose state
mongoose state --init --json
mongoose status --json
```

`mongoose state --init` creates the shared no-admin directory layout under `%LOCALAPPDATA%\Agents`.
`mongoose state` also reports the Mongoose CLI version, CLI source path,
configured registry URL/path, registry Git revision when available, and whether
the registry checkout is clean, dirty, missing, or not a Git checkout.

## Local State

Mongoose keeps user-local state outside the repository so install metadata, runtime files, logs, and future agent configuration do not need administrator access and do not get committed by accident.

The shared layout is:

```text
%LOCALAPPDATA%\Agents\
  bin\                 Installed command shims and mongoose.exe
  mongoose\            Mongoose CLI config and registry metadata
    config.json        Registry configuration
    registry\Mongoose\ Default cloned registry location
  state\
    config\            Non-secret shared configuration
    agents\            Installed agent metadata and agent-scoped local state
    jobs\              Job records from mongoose run and route executions
    runtime\           Runtime context files and runtime foundation status
  logs\                JSONL logs
```

Only non-secret configuration belongs under `state\config`. Access tokens, API keys, passwords, and other credentials should stay in environment variables or future secret storage. Mongoose redacts secret-like keys and `token=value` style text before writing structured logs.

Logs are JSONL files under `%LOCALAPPDATA%\Agents\logs`. Use `mongoose state --cleanup-logs` to remove log files older than the default 30-day retention window. Pass `--log-retention-days <days>` to use a different retention window.

`mongoose run` and non-dry-run `mongoose route` create job records under
`%LOCALAPPDATA%\Agents\state\jobs` and per-job JSONL logs under
`%LOCALAPPDATA%\Agents\logs`. Inspect them with:

```powershell
mongoose jobs list
mongoose jobs show <job-id>
mongoose jobs cancel <job-id>
```

The v0.6 runtime foundation records local runtime state for observability. It is
not a full background scheduler daemon yet:

```powershell
mongoose runtime start
mongoose runtime status
mongoose runtime stop
```

To reset local Mongoose state, uninstall agent commands first if needed, then remove `%LOCALAPPDATA%\Agents`. Reinstall with `install-mongoose.cmd` or rerun `mongoose setup`.

## Registry

Mongoose reads installable agents from:

```text
agents\*\agent.json
```

Each manifest provides the installed command name and local entrypoint for that agent.

When an agent is installed, Mongoose writes a small installed-agent record under:

```text
%LOCALAPPDATA%\Agents\state\agents\<commandName>.json
```

That record stores the manifest, source path, entrypoint, launcher path, install timestamp, version, and discovered capability metadata. It does not copy or delete the source package. `mongoose remove <agent>` removes the launcher and installed-agent record only.

Capabilities are discovered from a manifest `capabilities` array when present. If the manifest does not declare capabilities yet, Mongoose falls back to listing folders under `capabilities\`. The richer manifest contract is tracked separately in issue #26.

## Capability Routing

`mongoose route` is the deterministic Mongoose orchestrator. It reads installed-agent records from `%LOCALAPPDATA%\Agents\state\agents`, enumerates declared capabilities, and selects one capability without importing agent code.

Selection works in this order:

- `--agent` and `--capability` restrict the candidate set when provided.
- `--task-type <type>` matches declared capability `taskTypes`; agent-level `taskTypes` are used as fallback metadata for each capability.
- Without `--task-type`, Mongoose scores the request text against capability names, display names, descriptions, and task types.
- If exactly one installed capability matches, Mongoose dispatches to that capability.
- If multiple capabilities tie, Mongoose reports an ambiguous request and asks for `--agent`, `--capability`, or a more specific `--task-type`.
- If nothing matches, Mongoose lists installed capabilities so the user can see what is currently routeable.

Before dispatching, Mongoose checks that required environment-backed configuration is present and that the selected capability does not require an unavailable LLM runtime. Dispatch uses this stable invocation shape:

```text
python <capability entrypoint> <capability name> <request arguments...>
```

Capability-specific `entrypointPath` overrides the agent default entrypoint. `--dry-run` prints the selected capability, entrypoint, and argument vector without executing agent code.

## Runtime Contract

Mongoose Runtime Contract v1 lets agents discover host state and provider
availability without reading Mongoose internals. Existing agent arguments remain
stable, and Mongoose adds:

```text
MONGOOSE_RUNTIME_CONTEXT=<path-to-json-context>
MONGOOSE_RUNTIME_CONTRACT_VERSION=1
```

The context file includes invocation metadata, selected agent and capability
metadata, user-local state paths, provider descriptors, and structured runtime
error metadata. Provider descriptors currently include configuration, logs,
state, local storage, memory, tools, API profiles, and LLM. Secret values are
never written to manifests, logs, job metadata, package directories, or runtime
context files.

See [Runtime Contract v1](../docs/runtime-contract.md) for the full contract and
provider interface design.
See [LLM Runtime v1](../docs/llm-runtime.md) for provider-neutral LLM profile
configuration, ping behavior, and guardrails.
See [Mongoose Architecture](../docs/architecture/README.md) for generated SysML
and Mermaid views.

## Manifest Contract

Mongoose reads `agent.json` without importing agent code. Current manifests are backward-compatible with the original required fields and may opt into richer metadata with `schemaVersion: 1`.

Required fields:

```json
{
  "commandName": "Njord",
  "displayName": "Njord",
  "entrypointPath": "agent.py",
  "example": "Get me my latest budget",
  "description": "Personal finance agent for YNAB budget analysis and financial summaries."
}
```

Recommended metadata:

```json
{
  "schemaVersion": 1,
  "id": "njord",
  "version": "0.1.0",
  "entrypoints": {
    "default": "agent.py"
  },
  "taskTypes": ["finance", "budget", "ynab"],
  "requiredInputs": ["YNAB_ACCESS_TOKEN", "YNAB_BUDGET_ID"],
  "configuration": {
    "required": ["YNAB_ACCESS_TOKEN", "YNAB_BUDGET_ID"],
    "optional": [],
    "secretRefs": ["YNAB_ACCESS_TOKEN"]
  },
  "compatibility": {
    "platforms": ["windows"],
    "python": ">=3.11",
    "mongooseManifestSchema": 1,
    "mongooseRuntimeContract": 1
  },
  "requires": {
    "state": { "mode": "required" },
    "logs": { "mode": "optional" },
    "storage": { "mode": "optional" }
  },
  "llm": {
    "mode": "none",
    "deterministicFallback": "All current capabilities run without an LLM."
  },
  "capabilities": [
    {
      "name": "ynab-budget-summary",
      "displayName": "YNAB Budget Summary",
      "description": "Read YNAB data and summarize the current budget state.",
      "entrypointPath": "agent.py",
      "taskTypes": ["finance", "budget-summary", "ynab"],
      "requiredInputs": ["YNAB_ACCESS_TOKEN", "YNAB_BUDGET_ID"],
      "configuration": {
        "required": ["YNAB_ACCESS_TOKEN", "YNAB_BUDGET_ID"],
        "optional": [],
        "secretRefs": ["YNAB_ACCESS_TOKEN"]
      },
      "requires": {
        "configuration": { "mode": "required" },
        "logs": { "mode": "optional" },
        "storage": { "mode": "optional" },
        "llm": { "mode": "optional" }
      },
      "llm": {
        "mode": "none",
        "deterministicFallback": "Summary uses deterministic reads and calculations."
      }
    }
  ]
}
```

LLM metadata references runtime profiles only. Provider credentials and API keys must not be stored in manifests. Agents should reference configuration names or Mongoose LLM profile names; actual secrets belong in environment variables or future Mongoose secret storage.

Schema version policy:

- Keep `schemaVersion` unchanged for additive optional metadata that older Mongoose versions can ignore safely.
- Increment `schemaVersion` for breaking manifest contract changes: new required fields, renamed or removed fields, changed field types or meanings, changed entrypoint invocation semantics, changed capability routing semantics, or required configuration/LLM contract changes.
- Update `SUPPORTED_MANIFEST_SCHEMA_VERSION`, this policy, the manifest examples, and the validation tests in the same change that introduces a breaking manifest contract.
- Mongoose rejects manifests with a `schemaVersion` newer than it supports, so agent authors get an explicit compatibility failure instead of a confusing install or runtime error.

Invalid manifests fail `mongoose validate`, registry listing, installation, or show commands with actionable errors. Mongoose validates relative entrypoints, capability metadata shape, supported schema versions, and obvious secret-bearing keys.

