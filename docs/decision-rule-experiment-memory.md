# Decision, Rule, and Experiment Memory Contract v1

This contract defines shared Mongoose memory record shapes for domain decisions,
rules, and experiments. It is v0.9 substrate for later UI review, metrics,
preference learning, policy-gated auto-approval, and domain audit flows.

These records are stored through the shared `mongoose.memory.v1` provider from
#164. They are not a separate persistence system. They are also not full
Execution Traces and not the complete `loop_aware_memory_record` envelope from
#170.

Loop-aware memory records may reference these records when a capability run
creates, updates, reviews, or applies one. Future execution traces may reference
both, but traces should not replace domain decision records.

## Record Types

Supported v1 record types:

- `decision_record`
- `rule_record`
- `experiment_record`

All record types share these common fields:

```json
{
  "schemaVersion": 1,
  "recordType": "decision_record",
  "recordId": "memory_...",
  "domain": "finance",
  "agentId": "Njord",
  "capabilityId": "finance-review",
  "target": {
    "type": "budget-category",
    "id": "category-123",
    "label": "Dining"
  },
  "status": "proposed",
  "summary": "Short user-facing summary.",
  "rationale": "Why this exists, using replay-safe evidence.",
  "evidenceRefs": ["memory_...", "fact_packet_id"],
  "relatedMemoryRefs": ["memory_..."],
  "outcome": {
    "status": "unknown",
    "summary": ""
  },
  "review": {
    "dueAt": "2026-07-01T00:00:00Z",
    "window": "30d"
  },
  "userDecision": {
    "status": "informational",
    "decidedAt": "",
    "summary": ""
  },
  "audit": {
    "createdAt": "2026-06-22T00:00:00Z",
    "updatedAt": "2026-06-22T00:00:00Z",
    "supersedes": "",
    "supersededBy": ""
  },
  "redaction": {
    "secretsRemoved": true,
    "piiRemoved": true
  },
  "extensions": {}
}
```

## Decision Records

`decision_record` captures a domain proposal or decision outcome. It should be
used for commerce ad choices, finance categorization decisions, budget review
recommendations, fulfillment choices, or similar domain decisions.

Decision-specific fields:

```json
{
  "decision": {
    "kind": "recommendation",
    "proposedAction": "Review dining category funding.",
    "confidence": 0.72,
    "requiresApproval": true,
    "approvalBoundary": "No state mutation is authorized by this record."
  }
}
```

Decision records may be used later for metrics and preference learning, but
future auto-approval thresholds must preserve user intent. A prior accepted
decision can inform ranking or risk scoring; it cannot silently approve a future
action unless a later policy-gated auto-approval framework explicitly allows it.

## Rule Records

`rule_record` captures a reusable preference, policy, or domain rule. It should
be used for finance categorization rules, commerce campaign constraints,
portfolio review criteria, or fulfillment preferences.

Rule-specific fields:

```json
{
  "rule": {
    "ruleId": "finance-dining-review-threshold",
    "condition": "Dining category balance is negative.",
    "effect": "Prompt user to review before planning budget moves.",
    "scope": "Njord finance reviews",
    "enabled": true
  }
}
```

Rule records should include enough source context to explain whether they were
user-authored, inferred from repeated decisions, imported from a domain system,
or created by a capability recommendation.

## Experiment Records

`experiment_record` captures a time-bounded plan with explicit evaluation
criteria. It should be used for commerce bundle/deal/ad tests, portfolio thesis
review windows, budgeting experiments, or fulfillment workflow trials.

Experiment-specific fields:

```json
{
  "experiment": {
    "experimentId": "etsy-summer-bundle-test",
    "hypothesis": "Bundling related items will improve average order value.",
    "plannedStart": "2026-07-01T00:00:00Z",
    "plannedEnd": "2026-07-31T00:00:00Z",
    "duration": "30d",
    "successCriteria": ["Average order value increases by 10%."],
    "evaluationWindow": "7d-after-end"
  }
}
```

Experiment records must separate hypothesis, plan, observed outcome, and later
interpretation so review surfaces can show what was believed before results
were known.

## Lifecycle States

Allowed lifecycle states:

- `proposed`
- `approved`
- `active`
- `paused`
- `rejected`
- `expired`
- `reviewed`
- `superseded`
- `disabled`
- `completed`
- `informational`

State transitions should be append-only. A later record may supersede an earlier
record by setting `audit.supersedes` and the older record may be linked with
`audit.supersededBy`. Implementations should not rewrite prior decision history.

## Query Needs

Shared memory queries should support these dimensions when the fields exist:

- `domain`
- `agentId`
- `capabilityId`
- `target.type`
- `target.id`
- `createdAt` or `audit.createdAt` date range
- `status`
- `review.dueAt`
- `rule.ruleId`
- `experiment.experimentId`
- `outcome.status`

The v0.9 CLI memory filters cover the common subset by agent, capability,
subject text, date range, status, confidence, and outcome. Domain-specific
capabilities may apply additional filtering after retrieving memory records.

## Redaction and Storage

Decision, rule, and experiment records are stored through `mongoose.memory.v1`.
Secret values, raw provider payloads, buyer addresses, access tokens, and
unnecessary PII must be removed before records are written or before prompt
context is generated.

Domain-specific details belong under `extensions`, but extensions must follow
the same redaction, audit, and replay-safety rules as common fields.

## Relationship to Loop-Aware Memory and Traces

`loop_aware_memory_record` captures what a capability run attempted, what
evidence it used, what it decided, and what happened next. It may reference a
`decision_record`, `rule_record`, or `experiment_record` in
`relatedMemoryRefs`.

Execution Traces are future runtime envelopes for decisions, tool usage, state
references, validation, exit criteria, and outcomes. They may reference these
records, but should not copy sensitive or domain-heavy payloads.

## Validation Expectations

Validation should cover:

- JSON shape for `decision_record`, `rule_record`, and `experiment_record`.
- accepted lifecycle states and append-only supersession links.
- redaction of secrets, raw tokens, buyer addresses, and unnecessary PII.
- queryability by domain, target, date range, status, review due date,
  `ruleId`, `experimentId`, and outcome.
- loop-aware memory references to domain decision/rule/experiment records.
- prompt-context summaries that include provenance and guardrails.
- no domain-specific write automation, execution, or auto-approval authority.

## Non-Goals

- Do not implement commerce, finance, fulfillment, ad, or budgeting write
  automation in this contract.
- Do not treat a past accepted decision as future approval.
- Do not silently approve a future action from prior memory or outcomes.
- Do not create a separate database beside shared Mongoose memory.
- Do not replace loop-aware memory records or future Execution Traces.
