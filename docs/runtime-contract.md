# Mongoose Runtime Contract v1

Mongoose Runtime Contract v1 is the agent-facing agreement used when Mongoose
executes an installed agent or routed capability. Existing positional arguments
remain unchanged. Mongoose adds a structured JSON context file and points the
agent to it with environment variables.

## Invocation

For every `mongoose run` and non-dry-run `mongoose route` invocation, Mongoose
sets:

```text
MONGOOSE_RUNTIME_CONTEXT=<path-to-json-context>
MONGOOSE_RUNTIME_CONTRACT_VERSION=1
```

Agents may ignore these variables and continue using their existing command-line
arguments. Agents that need host state, provider availability, or diagnostics
should read the JSON file referenced by `MONGOOSE_RUNTIME_CONTEXT`.

## Context Shape

The context file contains:

- `contractVersion`: runtime contract version, currently `1`.
- `invocation`: invocation id, mode (`run` or `route`), original agent
  arguments, and creation time.
- `mongoose`: CLI version, release kind, release tag, and supported runtime
  contract version.
- `agent`: command name, display name, version, source path, manifest path, and
  manifest schema version.
- `capability`: selected capability metadata for routed executions, otherwise
  `null`.
- `route`: selected route, task type, and query for routed executions, otherwise
  `null`.
- `paths`: user-local state paths reported by `mongoose state`.
- `providers`: provider descriptors available to the agent.
- `errors`: the structured runtime error interface.

Secret values are never written to the context file. Configuration entries are
reported by name, required/optional status, availability, and whether the name
appears secret-bearing.

## Provider Interfaces

Runtime Contract v1 defines provider descriptors, not a full SDK. A descriptor
tells an agent whether a provider is available and what stable interface name it
implements.

Available v1 providers:

- `configuration`: `mongoose.configuration.v1`; exposes config names and
  availability, never values.
- `logs`: `mongoose.logs.v1`; exposes the Mongoose log root path.
- `state`: `mongoose.state.v1`; exposes the shared Mongoose state root path.
- `storage`: `mongoose.storage.local.v1`; exposes an agent/capability-scoped
  local storage path.
- `memory`: `mongoose.memory.v1`; exposes a redacted local JSONL memory record
  store plus append/list/context commands. The `contextCommand` returns compact
  `mongoose.prompt-context.v1` summaries with source record ids, timestamps,
  confidence, outcomes, user-decision markers, redaction, and explicit
  informational-only guardrails. v0.9 memory records are intentionally
  lightweight so loop-aware capabilities can persist useful decisions, state
  summaries, and outcomes before the full Loop Runtime and Execution Traces
  milestones.
- `llm`: `mongoose.llm.v1`; available when a compatible profile is configured.
  Exposes non-secret profile metadata and an `invokeCommand` that agents can run
  with prompt text on stdin to receive JSON output from the configured provider.

Reserved v1 descriptors:

- `tools`: `mongoose.tools.v1`; unavailable until tool invocation is added.
- `apiProfiles`: `mongoose.api-profiles.v1`; unavailable until profile
  resolution is added.

Deterministic agents can use the `storage`, `state`, and `logs` descriptors
without requiring an LLM.

## Manifest Requirement Fields

Agents and capabilities may declare runtime provider needs with `requires`.
Each provider requirement is an object with `mode: "required"` or
`mode: "optional"`.

Supported requirement names:

- `configuration`
- `logs`
- `state`
- `storage`
- `memory`
- `tools`
- `apiProfiles`
- `apis`
- `models`
- `llm`
- `execution`

Runtime Contract v1 currently supports required `configuration`, `logs`,
`state`, `storage`, `memory`, and `llm` providers. Required `tools`,
`apiProfiles`, `apis`, and `models` requirements fail validation until those
providers exist. Optional declarations are allowed so agents can describe future
or fallback behavior.

Example Njord capability:

```json
{
  "name": "ynab-budget-summary",
  "description": "Read YNAB data and summarize the current budget state.",
  "configuration": {
    "required": ["YNAB_ACCESS_TOKEN", "YNAB_BUDGET_ID"],
    "secretRefs": ["YNAB_ACCESS_TOKEN"]
  },
  "requires": {
    "configuration": { "mode": "required" },
    "logs": { "mode": "optional" },
    "storage": { "mode": "optional" },
    "llm": { "mode": "optional" }
  }
}
```

Example non-finance capability:

```json
{
  "name": "document-outline",
  "description": "Build a deterministic outline from local notes.",
  "requires": {
    "storage": { "mode": "required" },
    "tools": {
      "mode": "optional",
      "names": ["filesystem-read"]
    }
  }
}
```

Secrets do not belong in `requires`. Requirement metadata may reference provider,
tool, model, or profile names only. Credentials belong in environment variables,
future Mongoose secret/profile storage, or a configured provider.

## Package Management Boundary

Mongoose package management installs, updates, discovers, and records agents so
the runtime can find manifests and entrypoints. Package metadata supports the
runtime contract, but it does not define what an agent is allowed to access.
Runtime access is defined by the manifest `requires` declarations and the
provider descriptors passed in `MONGOOSE_RUNTIME_CONTEXT`.

## Runtime Errors

Mongoose-side runtime failures use this shape:

```json
{
  "contractVersion": 1,
  "code": "mongoose.missing_required_configuration",
  "message": "Human readable message.",
  "details": {}
}
```

The CLI prints the message and error code for human operators. Details are
redacted before output and logging.

Current runtime error codes:

- `mongoose.agent_not_installed`
- `mongoose.entrypoint_missing`
- `mongoose.missing_required_configuration`
- `mongoose.llm_profile_missing`
- `mongoose.llm_profile_invalid`
- `mongoose.llm_secret_missing`
- `mongoose.llm_invoke_failed`
- `mongoose.provider_unavailable`
- `mongoose.incompatible_runtime_contract`

## Compatibility

Agents can declare a required runtime contract in manifest compatibility
metadata:

```json
{
  "compatibility": {
    "mongooseRuntimeContract": 1
  }
}
```

If the required value is newer than the CLI supports, Mongoose fails before
launching the agent and reports `mongoose.incompatible_runtime_contract`.
