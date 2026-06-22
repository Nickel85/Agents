# Changelog

## v0.9.0 - Shared Memory and Prompt Context

Planned release type: minor.

This release adds the second pre-v1 runtime pillar after interaction-first
Njord: shared local memory and prompt-context retrieval for agents that need to
remember prior decisions, preferences, evidence, experiments, and outcomes
without gaining approval or write authority.

### Added

- Add the local `mongoose.memory.v1` provider with append, list, show, and
  prompt-context commands.
- Define the v0.9 `loop_aware_memory_record` contract, user-facing loop events,
  and transient same-line `Thinking.`, `Thinking..`, `Thinking...` indicators.
- Add prompt-context retrieval with provenance, confidence/outcome markers,
  deterministic fallback, redaction, and informational-only guardrails.
- Store Njord finance review audit summaries as loop-aware memory records
  through the shared Mongoose memory provider.
- Add the Portfolio reference agent for memory-backed investment thesis
  management, including thesis records, position association, evidence storage,
  deployed-capital review, and research-only guardrails.

### Changed

- Mark shared memory as an implemented Runtime Contract v1 provider while
  leaving the full shared Loop Runtime, Execution Traces, and Loop Tuner for
  later roadmap milestones.
- Update architecture artifacts, runtime docs, and validation coverage for the
  new memory and prompt-context surfaces.

### Validation

- Add validation for the memory provider, loop-aware memory contract, Njord
  finance audit memory records, Portfolio thesis memory records, and prompt
  context redaction/guardrails.

## v0.8.0 - Interactive Njord Finance Review Foundation

Planned release type: minor.

This release makes Njord more useful from the REPL before adding guarded
planning, writes, UI, or background automation.

### Added

- Add Njord's interaction-first `finance-review` capability and `/review` REPL
  command.
- Define Njord AI capability loop contracts, execution envelope, dependency
  map, and milestone sequencing gates.
- Add deterministic finance fact packets for cash-flow forecasting and
  financial risk loops.
- Add an LLM decision contract validator that rejects missing fields, forbidden
  write claims, cash-floor violations, and balance mutation language.
- Add read-only cash-flow forecasting and financial-risk scoring inside the
  finance review.

### Changed

- Update Njord capability metadata, docs, and validation coverage for the new
  loop foundation.

## v0.7.1 - Discoverable Ollama LLM Bootstrap

Planned release type: patch.

This release makes first-time local LLM setup easier to discover and easier to
complete from the terminal.

### Added

- Add discoverable LLM setup quick-start guidance and an opt-in Ollama
  bootstrap path for `mongoose llm setup`.

## v0.7.0 - LLM Capability Provider Runtime

Planned release type: minor.

This release makes the provider-neutral LLM runtime usable by installed
capabilities and by Njord's REPL for safe, read-only finance narration.

### Added

- Add `mongoose llm invoke` as the first provider-neutral LLM invocation path
  for installed capabilities.
- Expose an `invokeCommand` in the Runtime Contract v1 `llm` provider
  descriptor so agents can invoke configured profiles without reading secrets
  or hard-coding providers.
- Add fake-provider invocation support for deterministic validation without
  network access.
- Connect Njord finance answers to the Mongoose-managed LLM runtime for
  labeled, read-only narration from deterministic budget facts.
- Add `text_delta` response events and renderer behavior for progressive
  session output.

### Changed

- Mark Njord finance capabilities as optional LLM consumers while preserving
  deterministic fallback behavior when no compatible LLM profile is configured.
- Update LLM/runtime contract docs and generated architecture artifacts for the
  invocable LLM provider interface.

### Validation

- Add Mongoose validation coverage for `mongoose llm invoke`, missing-provider
  fallback, fake-provider invocation, and routed capability access to the LLM
  invoke command.
- Add Njord REPL validation coverage for fake-provider narration and
  progressive response-event rendering.

## v0.6.1 - Njord REPL-First Session

Planned release type: patch.

This release makes Njord open an interactive REPL by default while preserving
one-shot capability commands for Mongoose routing, scripts, and automation.

### Added

- Add the Njord `Njord>` interactive session with `/help`, `/status`,
  `/brief`, `/summary`, `/spending`, `/exit`, and `/quit`.
- Add a response-event session layer for text, warnings, errors, prompts,
  approval requests, and completion events.
- Add REPL validation coverage for no-arg startup, clean exits, slash commands,
  natural-language routing, and launcher-style free-form requests.

### Changed

- Update installed `Njord.cmd` launchers to pass user arguments directly to the
  agent entrypoint instead of forcing `ask`.
- Keep free-form installed invocations routing through the existing `ask` path
  while bare `Njord` opens the REPL.
- Update Njord documentation so the REPL is the primary human workflow and
  one-shot commands remain documented for automation.

## v0.6.0 - Persistent Runtime, Observability, and LLM Setup

Planned release type: minor.

This release adds the first persistent runtime observability layer and a guided
LLM setup flow so users can inspect Mongoose activity and connect provider
profiles from the terminal.

### Added

- Add `mongoose status` for runtime, registry, job, installed-agent, and LLM
  setup health.
- Add `mongoose runtime status/start/stop/restart` for the local runtime
  foundation.
- Add `mongoose jobs list/show/cancel` for persisted run records created by
  `mongoose run` and non-dry-run `mongoose route`.
- Persist job metadata, runtime context paths, per-job logs, exit status, and
  redacted output previews under user-local Mongoose state.
- Add `mongoose llm setup` as a guided terminal-first setup path for
  Ollama/local HTTP, OpenAI, Anthropic, and fake/test providers.
- Add v0.6 runtime observability validation coverage.

## v0.5.0 - Architecture Modeling And Diagram Generation

Planned release type: minor.

This release adds generated architecture documentation so Mongoose can describe
agents, capabilities, routing behavior, runtime providers, and external API
boundaries from the same manifest-backed model.

### Added

- Add `mongoose architecture generate` and `mongoose architecture validate`.
- Generate a shared architecture model at `docs/architecture/model.json`.
- Generate SysML v2 text views for agent structure and runtime routing.
- Generate Mermaid diagram views for agents, routing, and runtime providers.
- Add SysML modeling conventions for structure, behavior, variants, and branch
  terminology.
- Add CI validation that fails when generated architecture artifacts are stale.

## v0.4.0 - Provider-Neutral LLM Runtime Interfaces

Planned release type: minor.

This release adds the first provider-neutral LLM profile and ping surface so
agents can depend on Mongoose-managed LLM configuration instead of hard-coding
providers or owning raw credentials.

### Added

- Add `mongoose llm add`, `mongoose llm list`, `mongoose llm use`,
  `mongoose llm show`, and `mongoose llm ping`.
- Add secret-safe LLM profile storage under user-local Mongoose state.
- Add provider-neutral profile support for OpenAI-compatible, Anthropic-style,
  local HTTP, and fake validation providers.
- Add LLM profile resolution to Runtime Contract v1 provider descriptors.
- Allow LLM-required capabilities to run when their configured profile resolves.
- Add structured errors for missing profiles, missing secrets, invalid profiles,
  and ping failures.

### Changed

- Manifest validation continues to reject secret-bearing LLM metadata while
  allowing profile names and requirement declarations.
- Validation fixtures now cover fake-provider ping, missing profiles, missing
  secrets, provider diagnostics, and redacted profile output.

## v0.3.1 - Capability Requirement Validation

Planned release type: patch.

This corrective v0.3 release completes the capability runtime contract
milestone by validating manifest provider requirements and adding concrete
contract examples.

### Added

- Add manifest `requires` validation for runtime provider declarations.
- Reject malformed provider requirements, unknown provider names, unsupported
  required providers, and secret-like provider metadata.
- Add Njord and non-finance examples for Runtime Contract v1.
- Clarify that package management supports runtime discovery but does not
  define runtime access.

## v0.3.0 - Capability Runtime Contract

Planned release type: minor.

This release introduces Mongoose Runtime Contract v1: a portable execution
context that lets agents discover host state, selected capability metadata,
configuration status, provider availability, and structured diagnostics without
knowing the local environment layout.

### Added

- Add `MONGOOSE_RUNTIME_CONTEXT` and `MONGOOSE_RUNTIME_CONTRACT_VERSION` for
  `mongoose run` and non-dry-run `mongoose route` executions.
- Add Runtime Contract v1 context files under user-local Mongoose runtime state.
- Add provider descriptors for configuration, logs, state, local storage,
  memory, tools, API profiles, and LLM.
- Add agent/capability-scoped local storage provider paths.
- Add structured runtime error codes for missing agents, missing entrypoints,
  missing required configuration, unavailable providers, and incompatible
  runtime contracts.
- Add runtime contract and provider-interface documentation.

### Changed

- Preserve existing agent subprocess argument shapes while adding runtime
  context through environment variables.
- Extend validation fixtures to prove agents receive runtime context and can
  discover providers without importing Mongoose internals.

## v0.2.0 - Update Lifecycle Release

Planned release type: minor.

This release makes the install/update/release loop reliable enough for the
next capability-runtime milestones. Mongoose remains local-first and
capability-runtime-first: install, update, versioning, and release artifacts
are lifecycle support for portable agents, not the whole product identity.

### Added

- Add installed-binary self-update validation for `%LOCALAPPDATA%\Agents\bin\mongoose.exe`.
- Add release scope gates and a release-prep checklist for milestone discipline.
- Add validation that guards against repository-name drift, default registry URL
  drift, and release workflow ordering problems.

### Changed

- Make `mongoose update` run both registry refresh and Mongoose CLI update
  phases with explicit output and a phase summary.
- Add `mongoose update --registry-only` and `mongoose update --self-only` for
  automation and recovery workflows while keeping `mongoose update --self` as
  an alias.
- Reposition docs around Mongoose as a local-first capability runtime.

### Recovery Notes

- If self-update cannot replace the running executable immediately, Mongoose
  schedules replacement after the command exits and tells the user to confirm
  with `mongoose --version` in a new terminal.
- If replacement fails, Mongoose reports the staged download path and manual
  recovery guidance.
- The previous release asset remains available from the GitHub Releases page.

## v0.1.2 - CLI Version Hotfix

Planned release type: hotfix.

### Fixed

- Update the Mongoose CLI version reported by `mongoose --version` and
  `mongoose state` to `0.1.2`.
- Correct the release-version drift where the `v0.1.1` release asset still
  reported `mongoose 0.1.0`.
- Report whether a build is a development build or an official release build.
- Add CI validation so version-tagged release builds fail when the tag does not
  match the Mongoose CLI version.

### Changed

- Includes the colored terminal output work merged after `v0.1.1`.

## v0.1.1 - Maintenance Release

Planned release type: maintenance.

This release aligns the public release artifacts with the current Mongoose
project identity and licensing posture.

### Changed

- Rename the public repository identity from Agents to Mongoose.
- Add the Mongoose source-available commercial-permission license to the
  release source snapshot.
- Add README license guidance for non-commercial use and commercial permission.

### Notes

- No functional CLI changes are planned from v0.1.0.
- The release should include a fresh `mongoose.exe` asset built by GitHub
  Actions from the tagged source.
- The release should not be marked as a prerelease.
