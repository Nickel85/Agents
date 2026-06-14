# Mongoose

Mongoose is a local-first capability runtime for AI agents. It decouples AI
functionality from underlying models, tools, storage, APIs, and execution
environments so agents can declare what they need while Mongoose provides those
capabilities through common interfaces.

Today, this repository contains one concrete agent, Njord, and Mongoose, the
local runtime CLI used to install, inspect, route to, update, and run declared
agent capabilities from this repository.

## Mongoose Vision

Mongoose is being developed toward a local-first capability runtime for AI
agents that enables agents to be installed, configured, discovered, and
executed consistently across different environments.

The current CLI already supports local agent installation, manifest validation,
capability discovery, deterministic routing, user-local state, and installed
agent execution. The broader platform vision is that agents declare the
capabilities they require, such as LLMs, memory, tools, storage, and configured
APIs, and Mongoose provides those capabilities through common interfaces. That
would allow the same agent to run on a personal laptop, enterprise workstation,
or server without modification.

That full runtime surface is roadmap work, not current behavior. The active
roadmap tracks:

- provider-neutral LLM runtime support in [#23](https://github.com/Nickel85/Mongoose/issues/23)
- persistent scheduling and jobs in [#1](https://github.com/Nickel85/Mongoose/issues/1), [#2](https://github.com/Nickel85/Mongoose/issues/2), [#4](https://github.com/Nickel85/Mongoose/issues/4), and [#5](https://github.com/Nickel85/Mongoose/issues/5)
- cross-platform runtime support in [#38](https://github.com/Nickel85/Mongoose/issues/38)
- dependency and environment isolation in [#39](https://github.com/Nickel85/Mongoose/issues/39)
- package registry and versioning in [#40](https://github.com/Nickel85/Mongoose/issues/40)
- portable agent execution contracts in [#41](https://github.com/Nickel85/Mongoose/issues/41)
- common memory, storage, tool, and API provider interfaces in [#42](https://github.com/Nickel85/Mongoose/issues/42)

The current runtime contract and provider interface design is documented in
[docs/runtime-contract.md](docs/runtime-contract.md).
The provider-neutral LLM profile and ping contract is documented in
[docs/llm-runtime.md](docs/llm-runtime.md).
Generated architecture views for the runtime, agents, SysML text, and Mermaid
diagrams are documented in
[docs/architecture/README.md](docs/architecture/README.md).

## Njord Budget-Maintenance Release Path

Njord's release path is anchored on a methodical budget-maintenance loop rather
than direct natural-language writes. The intended progression is:

```text
Analyze budget state
-> propose money movement or new-money allocation plan
-> explain rationale, evidence, risk, and expected impact
-> require explicit approval
-> execute only approved YNAB writes
-> reconcile the resulting budget state
-> record outcomes for preference learning
```

This keeps the Mongoose architecture intact: Mongoose supplies reusable runtime
contracts for providers, jobs, state, logs, approvals, execution, and audit
records; Njord supplies the finance-specific analysis, budgeting policy, and
YNAB operation semantics.

Implementation should stay inside this release path. Work is in scope when it
directly improves Njord's ability to analyze a YNAB budget, draft budget
maintenance plans, collect approval decisions, execute approved writes,
reconcile results, or learn from reviewed outcomes. Work is out of scope when
it introduces unrelated agents, commerce integrations, general UI surfaces, or
broad Mongoose platform features that are not required by the current Njord
budget-maintenance milestone.

The budget-maintenance milestones are:

- v1.0 proves a stable local runtime and read-only Njord/LLM finance narration.
- v1.2 adds guarded budget-maintenance planning for allocating new money and
  moving money between categories without executing writes.
- v1.4 adds approved YNAB write execution, audit records, and reconciliation.
- v2.1 adds decision metrics, preference learning, and policy-gated
  auto-approval after enough user-reviewed evidence exists.

Mongoose platform milestones and Njord agent-value milestones are intentionally
sequenced separately. Njord is the first concrete use case and should prove
useful deterministic finance workflows before the platform grows package,
runtime, capability, and provider abstractions beyond what real agents need.
Release scope gates are documented in
[docs/release-scope-gates.md](docs/release-scope-gates.md) so later milestones
start only after their dependency gates are satisfied.

## Release Branch Workflow

Mongoose uses release branches for configuration management. Start each release
from `main` with the `Start Release Branch` GitHub Actions workflow. The
workflow creates `release/v<version>`, rolls `MONGOOSE_VERSION`, and seeds the
matching changelog section from the selected release type and roadmap theme.
Issue branches for that release start from the release branch and target their
pull requests back to that release branch.

The version is selected at release-branch start from the roadmap and SemVer
impact: patch for corrective fixes, minor for additive release capability, and
major for incompatible runtime or automation changes. The release branch keeps
`MONGOOSE_VERSION`, `CHANGELOG.md`, milestone scope, and release notes aligned
while issues are merged into it.

When the release branch is merged to `main`, GitHub Actions creates the matching
`v<version>` tag and GitHub Release. The tag build then attaches the official
`dist\mongoose.exe` asset.

## Agents

| Agent | Description | Documentation |
| --- | --- | --- |
| Njord | First concrete Mongoose-managed agent; personal finance analysis for YNAB budget data, financial summaries, and future recommendations. | [agents/njord/README.md](agents/njord/README.md) |

## Structure

Each agent lives in its own directory under `agents/`. An agent directory should contain a `README.md` that explains the agent's purpose, operating notes, dependencies, and how to use it.

Capabilities for an agent live under that agent's `capabilities/` directory. Each capability gets its own folder with a `README.md` describing what it does, when to use it, inputs, outputs, and any important constraints.

Executable agents should expose an entrypoint script. The preferred filename is `agent.py` inside each agent's own directory, so many agents can safely have their own `agent.py`. The globally unique value is the `commandName` in `agent.json`, because that becomes the installed user-local command.

```text
agents/
  <agent-name>/
    agent.json
    agent.py
    README.md
    router.py
    config.py
    capabilities/
      <capability-name>/
        README.md
        <capability_program>.py
```

## Adding An Agent

1. Copy `agents/_template/` to `agents/<agent-name>/`.
2. Update the agent `README.md` with the agent's particulars.
3. Add capability folders under `agents/<agent-name>/capabilities/`.
4. Document each capability in its own `README.md`.
5. Add or update `agent.py` and `router.py` when capabilities should be callable from natural-language requests.
6. Add an `agent.json` manifest so the root installer can discover the agent. Its `commandName` must be unique across the repo.
7. Document installation from the agent's own `README.md`.

## Installing An Agent

The preferred installer and runtime entrypoint is `mongoose`.

Build and install it from the repository root:

```text
.\build-mongoose.cmd
.\install-mongoose.cmd
```

For development, use the source-backed test environment instead of replacing
your normal installed `mongoose` release:

```powershell
.\dev\setup-dev-env.ps1
$env:Path = "$PWD\.dev-bin;$env:Path"
mongoose-dev --version
mongoose-dev install Njord
Njord-dev
```

`mongoose-dev` and `Njord-dev` use the current checkout every time and keep
their state under `.dev-localappdata`. Your normal `%LOCALAPPDATA%\Agents`
install and `mongoose` command are unchanged. See [dev/README.md](dev/README.md).

Then use:

```powershell
mongoose list
mongoose install Njord
mongoose show Njord
mongoose capabilities
mongoose route --task-type budget-summary "current budget"
mongoose run Njord config status
mongoose run Njord brief
mongoose jobs list
mongoose status
mongoose llm setup
mongoose remove Njord
mongoose update
mongoose update --registry-only
mongoose update --self-only
mongoose architecture generate --root .
mongoose architecture validate --root .
```

`mongoose update` refreshes the configured GitHub-backed registry and checks the
installed Mongoose CLI against the latest stable GitHub Release asset. Use
`mongoose update --registry-only` for automation that should only refresh the
agent registry. Use `mongoose update --self-only` or the legacy alias
`mongoose update --self` to only update the installed Mongoose CLI.

Mongoose discovers installable agents by scanning `agents/*/agent.json`. Add that manifest when creating a new agent and it will appear in `mongoose list` automatically.

Each manifest's `entrypointPath` is resolved relative to that agent's directory. Multiple agents can use `agent.py`; they just cannot share the same `commandName`.

Installed agent metadata is stored under `%LOCALAPPDATA%\Agents\state\agents`. Removing an agent deletes the local command shim and installed metadata, not the source package.

If the requested agent does not exist, Mongoose prints the available agent names.

Manifests can also declare capability metadata, supported task types, configuration requirements, compatibility constraints, and optional LLM needs. Mongoose reads that metadata without importing agent code:

```powershell
mongoose validate
mongoose show Njord
mongoose capabilities
```

Once agents are installed, Mongoose can route requests across declared capabilities with deterministic task-type matching:

```powershell
mongoose route --task-type budget-summary "current budget"
mongoose route --task-type weekly-brief "weekly financial brief"
```

Mongoose records jobs for `mongoose run` and non-dry-run `mongoose route`
executions. Inspect recent activity and runtime health with:

```powershell
mongoose jobs list
mongoose jobs show <job-id>
mongoose status
mongoose runtime status
```

Configure an LLM profile through a terminal-first guided setup flow:

```powershell
mongoose llm setup
mongoose llm ping
```

For local Ollama setup, Mongoose can also bootstrap the local provider:

```powershell
mongoose llm setup --provider ollama --yes --bootstrap
```

Secrets do not belong in manifests. Manifests should reference configuration names such as `YNAB_ACCESS_TOKEN`; actual tokens stay in environment variables, user-local config, or future Mongoose secret/profile storage.

Architecture artifacts can be regenerated from manifests and runtime metadata:

```powershell
mongoose architecture generate --root .
mongoose architecture validate --root .
```

The generated Mermaid diagrams and SysML text both use the shared architecture
model in `docs/architecture/model.json`; Mermaid is the visual projection and
SysML is the formal textual view.

Each agent README contains the agent-specific install name, configuration, examples, and any extra setup:

- [Njord install instructions](agents/njord/README.md)

Installers should not require administrator privileges. User-local command shims, configuration files, and secrets should stay scoped to the current user wherever possible.

See [mongoose/README.md](mongoose/README.md) for Mongoose runtime details.

## VS Code Setup

This repository includes workspace settings in `.vscode/`.

Recommended first step:

1. Open the repository in VS Code.
2. Install the recommended extensions when prompted.
3. Run the task `Create local .env`.
4. Add local secret values to `.env`.

The `.env` file is ignored by Git. Commit `.env.example` only.

## Testing

Tests live in `tests/` and are run by GitHub Actions on `push` and `pull_request`. See [tests/README.md](tests/README.md) for the current test list and local run instructions.

`mongoose.exe` is built by GitHub Actions for pull requests targeting `main` or
`release/v*`, pushes to `main` or `release/v*`, and version tags. Pull request
builds upload `mongoose.exe` as an Actions artifact, and version tag builds
attach it to the GitHub Release.

GitHub Actions also smoke-tests the built executable by running `mongoose list`, `mongoose install`, `mongoose uninstall`, and scoped/default `mongoose update` flows.

## License

This repository is source-available under the
[Mongoose Source-Available and Commercial Permission License](LICENSE).

You may use this project to build new non-commercial applications, agents,
integrations, and experiments. Commercial or monetized use is not permitted
under the public license. That includes paid applications, hosted services,
client work, commercial integrations, or other revenue-generating use where this
project is a material component.

Commercial use requires prior written permission from the copyright holder and
may require a paid license. The copyright holder reserves the right to
commercialize, license, sell, transfer, or otherwise monetize this project.

## Directory Guide

- `agents/`: All agent definitions.
- `agents/njord/`: Personal finance agent for analyzing YNAB budget data.
- `agents/njord/agent.json`: Install metadata for the `Njord` command.
- `agents/njord/agent.py`: Njord command-line entrypoint.
- `agents/njord/router.py`: Natural-language request router.
- `install.cmd`: One-file no-admin installer for installable agents.
- `install/`: User-local installer support scripts.
- `mongoose/`: Mongoose runtime CLI and launcher source.
- `docs/`: Runtime, architecture, release scope, and project planning guidance.
- `build-mongoose.cmd`: Builds `dist/mongoose.exe`.
- `dev/`: Source-backed local development environment for testing current repo
  code without replacing the installed release.
- `install-mongoose.cmd`: Installs `mongoose.exe` as a user-local CLI.
- `tests/`: Local validation scripts also used by GitHub Actions.
- `agents/_template/`: Starter template for a new agent.
- `agents/_template/capabilities/_template/`: Starter template for a new capability.

