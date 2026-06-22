# Loop-Aware Memory Record Contract v1

Loop-aware memory records are the v0.9 bridge between capability execution and
shared memory. They let Mongoose remember enough context from a capability run
to support prompt context, audit/replay, decision logs, and future traces
without implementing the full shared Loop Runtime.

This contract is intentionally narrow. Capabilities remain first-class and own
their domain behavior. Mongoose provides the shared memory shape and storage
surface so later sessions can ask what was attempted, what evidence was used,
what was recommended or decided, and what happened next.

## Boundary

v0.9 loop-aware memory records:

- describe capability work after or during existing capability execution.
- preserve agent and capability identity.
- store references to facts, tools, state, decisions, and outputs.
- include durable user-facing narration events.
- distinguish transient activity indicators from durable evidence.
- remain safe for prompt-context retrieval.

v0.9 loop-aware memory records do not:

- execute arbitrary loop definitions.
- replace capability-specific audit or decision records.
- implement shared Execution Traces.
- expose hidden chain-of-thought, raw prompts, raw provider payloads, secrets,
  or unnecessary PII.
- approve actions or mutate state.

The later shared Loop Runtime can use these records as durable references, but
it is tracked separately from v0.9.

## Record Shape

The record type is `loop_aware_memory_record`.

Required fields:

```json
{
  "schemaVersion": 1,
  "recordType": "loop_aware_memory_record",
  "recordId": "memory_loop_20260622_001",
  "agentId": "njord",
  "capabilityId": "finance-review",
  "goal": {
    "request": "Review my budget and recommend what to do with extra cash.",
    "normalizedIntent": "budget_recommendation"
  },
  "loop": {
    "definitionId": "njord.finance_review.v1",
    "phase": "recommendation",
    "status": "completed",
    "exitReason": "recommendation_returned"
  },
  "events": [],
  "provenance": {
    "createdAt": "2026-06-22T10:00:00-04:00",
    "source": "Njord REPL"
  },
  "redaction": {
    "secretsRemoved": true,
    "piiLevel": "minimal"
  }
}
```

Optional fields:

```json
{
  "inputs": {
    "factRefs": ["fact_packet_20260622_001"],
    "memoryRefs": ["preference_rule_123"],
    "evidenceRefs": ["evidence_456"]
  },
  "tools": [
    {
      "provider": "ynab",
      "operation": "read_budget_snapshot",
      "resultRef": "snapshot_789"
    }
  ],
  "state": {
    "readRefs": ["snapshot_789"],
    "updateRefs": []
  },
  "prompts": {
    "templateRef": "njord.finance_review.prompt.v1",
    "llmProfile": "fake-main"
  },
  "decision": {
    "summary": "Prioritize emergency savings before project funding.",
    "confidence": "medium",
    "assumptions": ["No urgent overspending detected"],
    "risks": ["Snapshot may be stale"],
    "validation": "passed"
  },
  "userDecision": {
    "status": "accepted",
    "noteRef": "user_decision_123"
  },
  "outcome": {
    "status": "recorded",
    "stateMutation": false
  },
  "relatedRecordIds": ["decision_proposal_123"]
}
```

Records should store references instead of copying sensitive state. Raw access
tokens, API keys, bearer tokens, raw provider payloads, and unnecessary PII must
not be stored.

## Durable Events

Durable events are audit-friendly narration. They are safe to show to a user
and safe to replay later as a summary of what the capability did.

Suggested durable event kinds:

- `started`
- `state_read`
- `tool_used`
- `fact_found`
- `memory_used`
- `decision_made`
- `validation_passed`
- `validation_failed`
- `recommendation_ready`
- `approval_required`
- `completed`
- `error`

Durable event shape:

```json
{
  "eventId": "event_001",
  "eventKind": "memory_used",
  "visibility": "user",
  "message": "Using your saved preference: emergency fund before project funding.",
  "relatedRefs": ["preference_rule_123"],
  "createdAt": "2026-06-22T10:00:03-04:00",
  "redaction": {
    "secretsRemoved": true,
    "piiLevel": "minimal"
  }
}
```

Durable events should explain observable actions, evidence, decisions, and
boundaries. They must not expose private reasoning traces.

## Transient Activity Indicators

Transient activity indicators are live UI feedback for long-running work. They
are not durable decisions, evidence, or audit events.

Examples:

```text
Thinking.
Thinking..
Thinking...
```

Terminal renderers should cycle one, two, and three dots while waiting for an
LLM response or long-running tool call. The renderer should overwrite the same
terminal line in place so the indicator stays a single live status line and all
previous durable output remains above it. When the next durable event or final
output appears, the transient line should be cleared or replaced cleanly.

Transient indicator shape:

```json
{
  "indicatorKind": "thinking",
  "visibility": "user",
  "messageTemplate": "Thinking{ellipsis}",
  "animation": {
    "kind": "cycling_ellipsis",
    "frames": [".", "..", "..."],
    "overwriteLine": true
  },
  "persist": false
}
```

If a transient indicator is persisted for diagnostics, it should be stored only
as lightweight timing/status metadata. It should not be treated as evidence,
reasoning, or a decision.

## Prompt Context

Prompt-context retrieval may summarize loop-aware memory records when they are
relevant to a new request. Summaries should include provenance and enough
context to explain why a prior record is relevant:

- prior goal or request
- capability id
- evidence or fact references
- decision or recommendation summary
- user decision
- outcome

Prompt context must not treat memory as execution authority. A remembered
preference, prior approval, or prior recommendation cannot approve a new action.

## Versioning

The `schemaVersion` field version-controls the record shape.

- Additive optional fields can remain `schemaVersion: 1`.
- New required fields or changed meanings require a new schema version.
- Readers should preserve unknown fields when possible.
- Old records must remain readable for audit and prompt context.

