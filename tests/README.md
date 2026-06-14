# Tests

This directory contains local validation scripts that are also run by GitHub Actions.

## GitHub Actions

The workflow lives at `.github/workflows/install-validation.yml`.

The Mongoose executable build workflow lives at `.github/workflows/mongoose-build.yml`.

The mongoose command smoke workflow lives at `.github/workflows/mongoose-smoke.yml`.

The generated architecture validation workflow lives at
`.github/workflows/architecture-validation.yml`.

The release-start workflow lives at
`.github/workflows/start-release-branch.yml`.

The release-on-merge workflow lives at
`.github/workflows/release-on-merge.yml`.

Install validation runs on:

- `push`
- `pull_request`

The mongoose build workflow runs on:

- pull requests targeting `main`
- pull requests targeting `release/v*`
- pushes to `main`
- pushes to `release/v*`
- version tags matching `v*`

It uploads `dist/mongoose.exe` as an Actions artifact. On version tags, it also attaches `mongoose.exe` to the GitHub Release.

The mongoose smoke workflow runs on the same pull request, push, and tag triggers. It builds `mongoose.exe`, validates installed-binary self-update behavior, then smoke-tests `list`, `install`, `uninstall`, and default/scoped `update` flows.

The release-start workflow is manually triggered with a target version, release
type, and roadmap theme. It creates `release/v<version>`, rolls
`MONGOOSE_VERSION`, seeds the matching changelog section, validates release
metadata, commits the version roll, and pushes the release branch.

The release-on-merge workflow runs when a merged pull request to `main` came
from a `release/v*` branch. It validates release metadata, creates the matching
tag, extracts that version's changelog section into release notes, and creates
the GitHub Release. The tag then triggers the build workflow that attaches the
official `mongoose.exe` asset.

The architecture validation workflow runs on `push` and `pull_request` and
fails when generated architecture artifacts are stale.

All workflows use `windows-latest` because the installer and executable are currently Windows-focused.

## Install Validation

Script:

```text
tests/install-validation.ps1
```

Run locally from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tests\install-validation.ps1
```

This test verifies:

- `install.cmd` exists.
- `install/install-agent.ps1` exists.
- every real agent directory has an `agent.json`.
- template directories beginning with `_` are ignored.
- each manifest has `commandName`, `displayName`, `entrypointPath`, `example`, and `description`.
- `commandName` values are valid command names.
- `commandName` values are unique across all agents.
- `entrypointPath` is relative, not absolute.
- `entrypointPath` resolves to an existing file.
- `entrypointPath` stays inside its own agent directory.
- unknown agents fail and print available agents.
- known agents install into a user-local test bin directory.
- generated launchers call the configured entrypoint and pass arguments through
  without forcing `ask`.

The test uses `.test-localappdata/` as a temporary local AppData substitute. That folder is ignored by Git.

## Mongoose Validation

Script:

```text
tests/mongoose-validation.ps1
```

Run locally from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tests\mongoose-validation.ps1
```

This test verifies:

- the Python-backed `mongoose` CLI exists.
- `mongoose setup` writes configuration against the local repo.
- `mongoose --help` includes install, routing, and update guidance.
- `mongoose state --init --json` reports and creates shared local state paths.
- `mongoose status`, `mongoose runtime`, and `mongoose jobs` expose runtime
  observability.
- `mongoose llm setup` configures provider profiles through guided setup paths.
- `mongoose llm` configures, lists, shows, selects, and pings secret-safe LLM profiles.
- `mongoose list` discovers available agents from `agent.json`.
- installing a missing agent fails and prints available agents.
- `mongoose install Njord` creates a user-local `Njord.cmd` launcher.
- `mongoose install <local path>` installs a fixture agent from its manifest.
- `mongoose list --installed` shows installed agent state.
- `mongoose show <agent>` displays manifest, version, source, entrypoint, and capability metadata.
- `mongoose capabilities` enumerates routeable installed capability metadata.
- `mongoose route` selects and dispatches capabilities by task type or request text.
- `mongoose route` passes Runtime Contract v1 context to fixture capabilities.
- missing config, unavailable providers, and incompatible runtime contracts emit structured runtime error codes.
- missing LLM profiles, missing LLM secrets, and fake-provider ping behavior are validated.
- manifest validation checks valid, malformed, unsupported, and secret-like provider requirement declarations.
- ambiguous and unsupported routes fail with actionable messages.
- `mongoose validate` checks manifest shape, compatibility metadata, capability metadata, and secret-free declarations.
- `mongoose run <agent> ...` dispatches to an installed fixture agent entrypoint and passes Runtime Contract v1 context.
- `mongoose remove <agent>` removes the launcher and installed state without deleting source files.
- the generated launcher calls the agent entrypoint directly so no-arg commands
  can open the agent's interactive session.
- `mongoose uninstall Njord` removes the launcher.

## Njord REPL Validation

Script:

```text
tests/njord-repl-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-repl-validation.py
```

This test verifies:

- `Njord`/`agent.py` with no args opens the `Njord>` prompt.
- `exit`, `quit`, `/exit`, and `/quit` exit cleanly.
- `help` explains natural conversational examples instead of command menus.
- slash-prefixed input is rejected with guidance to ask naturally.
- finance prompts route through natural-language capability selection.
- natural-language input routes through the existing deterministic request path.
- launcher-style free-form arguments continue to route through `ask`.

The test uses `.test-localappdata-mongoose/` as a temporary local AppData substitute. That folder is ignored by Git.

## Njord LLM Runtime Validation

Script:

```text
tests/njord-llm-runtime-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-llm-runtime-validation.py
```

This test verifies:

- LLM prompts with non-CP1252 characters are passed to child processes as UTF-8.
- slow LLM invocations return diagnostics instead of crashing the REPL.

## Mongoose State Validation

Script:

```text
tests/mongoose-state-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\mongoose-state-validation.py
```

This test verifies:

- shared state directories are created under `%LOCALAPPDATA%\Agents`.
- atomic JSON writes round trip through the helper API.
- missing JSON files can return a caller-provided default.
- corrupted JSON raises an error that includes the file path.
- secret-like keys and log messages are redacted.
- expired JSONL log files are removed by retention cleanup.
- `mongoose state --init --json` reports the expected path contract.

The test uses `.test-localappdata-mongoose-state/` as a temporary local AppData substitute. That folder is ignored by Git.

## Runtime Observability Validation

Script:

```text
tests/mongoose-runtime-observability-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\mongoose-runtime-observability-validation.py
```

This test verifies:

- guided fake, local HTTP/Ollama-style, and remote-provider LLM setup flows.
- API-key values are never written to stored profile JSON.
- runtime status start/stop state is persisted.
- `mongoose run` creates job records, runtime context files, per-job logs, and
  redacted output summaries.
- `mongoose jobs list`, `mongoose jobs show`, and `mongoose status` report the
  recorded activity.

## Release Version Validation

Script:

```text
tests/release-version-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\release-version-validation.py
```

This test verifies:

- `MONGOOSE_VERSION` is present and semver-like.
- `CHANGELOG.md` has a matching section for the current CLI version.
- `docs/release-scope-gates.md` documents release gates and release-prep
  checklist sections.
- release-branch configuration management is documented and enforced.
- release branches named `release/v<version>` match `MONGOOSE_VERSION`.
- version-tagged GitHub Actions runs use a tag that matches the CLI version.
- source builds default to `development` release metadata.
- the default registry URL points at the public Mongoose repository.
- active project docs/code do not contain stale legacy repository references.
- GitHub Actions runs release-version validation before building, uploading, or
  attaching release assets.
- GitHub Actions builds and smokes pull requests and pushes for `release/v*`
  branches.
- merged release branches to `main` create the matching tag and GitHub Release.

## Architecture Validation

Script:

```text
tests/architecture-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\architecture-validation.py
```

This test verifies that the committed architecture model, SysML text views, and
Mermaid diagrams are fresh relative to current agent manifests and Mongoose
runtime metadata.

## Self-Update Validation

Script:

```text
tests/mongoose-self-update-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\mongoose-self-update-validation.py
```

This test verifies Mongoose CLI self-update behavior without live network access:

- release version comparison and prerelease filtering.
- already-current releases do not download or replace the executable.
- update-available releases download and target `%LOCALAPPDATA%\Agents\bin\mongoose.exe`.
- missing assets, failed downloads, and failed replacements fail with actionable output.
- default `mongoose update` runs registry then CLI phases and prints a summary.
- `--registry-only`, `--self-only`, and legacy `--self` scope update phases.
- invalid scoped flag combinations fail before update phases run.

## Installed Mongoose Self-Update Validation

Script:

```text
tests/mongoose-installed-self-update-validation.ps1
```

Run locally from the repository root after building `dist\mongoose.exe`:

```powershell
.\build-mongoose.cmd
powershell -ExecutionPolicy Bypass -File .\tests\mongoose-installed-self-update-validation.ps1
```

This test verifies installed-binary self-update behavior without live network access:

- `mongoose update --self` runs from `%LOCALAPPDATA%\Agents\bin\mongoose.exe`.
- local release metadata and a local fake `mongoose.exe` release asset drive the update.
- Windows locked-executable replacement is deferred and completes after the command exits.
- failed replacement output includes a staged download recovery path and manual recovery guidance.

## Terminal Output Validation

Script:

```text
tests/terminal-output-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\terminal-output-validation.py
```

This test verifies:

- redirected Mongoose and Njord output remains plain by default.
- forced color output includes ANSI styling.
- `--no-color` suppresses color even when color is forced by the environment.

## YNAB API Validation

Script:

```text
tests/ynab-api-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\ynab-api-validation.py
```

This test verifies the read-only YNAB API foundation without calling the live API:

- plans, plan details, accounts, categories, months, transactions, and scheduled transactions parse from fixture responses.
- transaction query parameters normalize dates and optional filters.
- milliunit currency values and ISO dates normalize consistently.
- configured plan selection is deterministic.
- missing tokens, auth failures, 404s, rate limits, malformed JSON, URL errors, and timeouts return structured errors.
- error messages do not leak token-like details.
- malformed response shapes produce actionable messages.

## YNAB Config Validation

Script:

```text
tests/njord-config-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-config-validation.py
```

This test verifies Njord YNAB configuration handling without calling the live API:

- the preferred user-local config file can supply `YNAB_ACCESS_TOKEN` and `YNAB_BUDGET_ID`.
- missing tokens produce actionable status output.
- configured budget/plan IDs are validated against returned plans.
- installed-command style `Njord config status` works as an explicit subcommand.
- secret values are not printed in status output.

## Njord Snapshot Validation

Script:

```text
tests/njord-snapshot-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-snapshot-validation.py
```

This test verifies Njord's normalized financial snapshot model without calling the live API:

- accounts, category groups, categories, months, transactions, and scheduled transactions normalize from representative YNAB payloads.
- snapshot metadata includes source, selected plan, included resources, and freshness timestamp.
- summary helpers calculate open on-budget balance and underfunded categories from domain objects.
- snapshot serialization excludes raw payload fields and secret-like values.

## Njord Review Validation

Script:

```text
tests/njord-review-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-review-validation.py
```

This test verifies review-needed detection without calling the live API:

- negative category balances are flagged.
- categories with spending but little or no assigned budget coverage are flagged.
- category activity materially above assigned budget is flagged.
- uncategorized transactions are flagged.
- unusually large outflow transactions are flagged.
- stale scheduled transactions are flagged.
- hidden categories do not produce review flags.
- each flag includes neutral language, severity, confidence, and supporting evidence.

## Njord Spending Validation

Script:

```text
tests/njord-spending-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-spending-validation.py
```

This test verifies spending review analysis without calling the live API:

- current month date ranges are resolved from snapshot freshness.
- previous month and explicit date ranges are supported.
- YNAB milliunit income, outflows, and net cash flow calculate correctly.
- top spending categories group transaction outflows.
- notable transactions are selected by absolute amount.
- previous-period comparison is included when matching prior transactions exist.
- natural-language spending requests route to the spending review capability.

## Njord Recommendation Validation

Script:

```text
tests/njord-recommendation-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-recommendation-validation.py
```

This test verifies deterministic recommendation generation without calling the
live API:

- recommendations are generated from review-needed flags and spending reviews.
- each recommendation includes facts, interpretation, recommendation, expected impact, confidence, risks, and evidence.
- category, transaction, scheduled transaction, spending concentration, and cash-flow recommendations are covered.
- recommendation language remains read-only and nonjudgmental.

## Njord Brief Validation

Script:

```text
tests/njord-brief-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-brief-validation.py
```

This test verifies manual brief composition without calling the live API:

- observations, spending highlights, notable transactions, review items, suggested next actions, and boundaries are rendered.
- the brief uses deterministic snapshot, spending, review, and recommendation outputs.
- read-only/write-safety boundaries are included.
- weekly financial brief requests route to the `brief` capability.

## Njord Write Safety Validation

Script:

```text
tests/njord-write-safety-validation.py
```

Run locally from the repository root:

```powershell
python .\tests\njord-write-safety-validation.py
```

This test verifies the design contract for future YNAB writes without calling
the live API:

- the write safety document distinguishes recommendations, proposed plans,
  approved plans, executed writes, and reconciliation records.
- supported operation classes, approval decisions, audit records,
  reconciliation statuses, and idempotency are documented.
- the current shared YNAB API client remains read-only.

## Mongoose EXE Smoke

Script:

```text
tests/mongoose-exe-smoke.ps1
```

Run locally from the repository root after building `dist\mongoose.exe`:

```powershell
.\build-mongoose.cmd
powershell -ExecutionPolicy Bypass -File .\tests\mongoose-exe-smoke.ps1
```

This test verifies the built executable can:

- run `mongoose setup` against the local repo.
- run `mongoose list` and discover `Njord`.
- run `mongoose install Njord` and create `Njord.cmd`.
- run `mongoose uninstall Njord` and remove `Njord.cmd`.
- run default `mongoose update` against local registry and release metadata fixtures.
- run `mongoose update --registry-only` without checking the CLI phase.

The test uses `.test-localappdata-mongoose-exe/`, `.test-mongoose-update-registry/`, and `.test-mongoose-registry-only-update/` as temporary folders. All are ignored by Git.

## Dev Environment Validation

Script:

```text
tests/dev-environment-validation.ps1
```

Run locally from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tests\dev-environment-validation.ps1
```

This test verifies the source-backed development environment can:

- create `.dev-bin\mongoose-dev.cmd` and `.dev-bin\Njord-dev.cmd`.
- keep state under `.dev-localappdata` instead of the normal install.
- run `mongoose-dev --version`.
- discover Njord from the current checkout.
- open the `Njord-dev` REPL.


