# Portfolio

Portfolio is a v0.9 reference capability for memory-backed investment thesis
management. It is separate from Njord budgeting and from Mongoose platform
implementation work.

The capability tracks durable thesis claims, related positions, evidence,
confidence changes, invalidation checks, and review prompts. It frames output as
research organization, not financial advice or trading execution.

## Examples

```powershell
Portfolio create-thesis ai-infra --claim "AI infrastructure demand will compound over the next decade." --horizon "10 years" --assumption "Data center capex remains durable" --invalidation "Hyperscaler capex contracts for two consecutive years" --confidence 0.72
Portfolio add-position ai-infra NVDA --relationship aligned --intended-allocation 12 --actual-exposure 14 --rationale "Compute platform exposure"
Portfolio add-evidence ai-infra --source "Company transcript" --stance supports --summary "Management raised data-center demand outlook." --confidence-impact 0.04
Portfolio review-thesis ai-infra
Portfolio list-theses
Portfolio archive-thesis ai-infra
```

When launched through Mongoose, Portfolio uses `mongoose.memory.v1` to append
records for thesis creation, updates, evidence, and review summaries. It can
also request prompt context from prior memory records. Without Mongoose memory,
it still stores deterministic local JSON under its runtime storage path or a
repo-local fallback for development.

## Guardrails

- No automatic trading or brokerage execution.
- No personalized financial advice.
- Keep source attribution and evidence timestamps visible.
- Separate user-authored thesis claims from inferred risks.
- Flag missing or stale evidence instead of pretending monitoring is complete.
