# Njord

## Purpose

Njord is an agent for understanding and improving personal finances. It starts as an accountant for YNAB budget data: summarizing balances, spending, cash flow, category activity, and financial changes over time.

Over time, this agent should grow from reporting what happened into explaining why it happened and recommending what to do next.

Njord is also the first concrete agent use case for Mongoose. Its job is to
prove that a locally installed agent can deliver useful, deterministic
workflows before Mongoose generalizes the package, runtime, scheduling, and
provider interfaces for other agents.

## Behavior

Njord should be:

- Accurate before clever.
- Clear about assumptions, missing data, and uncertainty.
- Conservative with recommendations that affect money.
- Respectful of privacy and careful with credentials.
- Practical, using plain-language summaries and specific numbers.

The agent should separate observations from recommendations. It should not make irreversible financial decisions, move money, or modify a budget unless that capability is explicitly added and approved.

## Dependencies

- YNAB account access.
- YNAB API token or OAuth access token.
- Selected YNAB budget or plan ID.
- Secure local configuration for secrets.
- A runtime capable of making HTTPS requests to the YNAB API.

YNAB API documentation: [https://api.ynab.com/](https://api.ynab.com/)

## Local Configuration

Preferred setup for normal installed use is a user-local JSON file:

```text
%LOCALAPPDATA%\Agents\Njord\config.json
```

Create the folder if needed, then add:

```json
{
  "YNAB_ACCESS_TOKEN": "your-token",
  "YNAB_BUDGET_ID": "your-budget-or-plan-id"
}
```

Check the configuration without printing secrets:

```powershell
Njord
```

Then ask naturally:

```text
Njord> Check my configuration status.
```

For automation or direct checks:

```powershell
Njord config status
```

For direct repository development, `.env` is still supported. Store local development secrets in a `.env` file at the repository root. This file is ignored by Git.

Start by copying `.env.example` to `.env`, then fill in:

```env
YNAB_ACCESS_TOKEN=
YNAB_BUDGET_ID=
```

Configuration precedence is:

1. Current process environment variables.
2. `%LOCALAPPDATA%\Agents\Njord\config.json`.
3. Repository root `.env`.

Never commit the real `.env` file or paste the YNAB access token into documentation, logs, examples, or prompts.

## YNAB Read Layer

Njord reads YNAB data through [ynab_api.py](ynab_api.py). Capabilities should use that shared module instead of making raw HTTP requests directly.

The read layer provides:

- one authenticated read-only client for the YNAB API.
- helpers for plans/budgets, accounts, categories, months, transactions, and scheduled transactions.
- deterministic plan selection when `YNAB_BUDGET_ID` is configured.
- consistent milliunit currency formatting and ISO date parsing.
- structured, user-facing errors for missing tokens, rejected tokens, HTTP failures, malformed JSON, URL failures, and timeouts.
- token-safe error handling that avoids printing access tokens or authorization details.

The current YNAB API uses `plans` as the primary resource name. Njord still accepts budget-oriented language in configuration and user-facing text because users commonly think in terms of budgets.

## Normalized Snapshot

Njord converts raw YNAB read responses into the domain model in [snapshot.py](snapshot.py). Capabilities should use that snapshot model instead of traversing raw YNAB payloads directly.

The snapshot includes:

- selected plan metadata, source timestamp, and included resources.
- accounts and on-budget balance helpers.
- category groups and flat categories with budgeted, activity, and balance amounts.
- months for cash-flow and period analysis.
- transactions and scheduled transactions for spending review and upcoming obligation analysis.
- serialization through typed fields only, so access tokens and raw payload secrets are not persisted.

## Spending Review

Njord derives period spending reviews from the normalized snapshot in
[spending.py](spending.py). Reviews can cover the current month, previous month,
or an explicit date range.

The current review output includes:

- income.
- outflows.
- net cash flow.
- transaction count.
- previous-period comparison when enough data exists.
- top spending categories.
- notable transactions.

The review is factual read intelligence. It stays separate from recommendations
so the manual brief MVP can reuse the data without implying automatic budget
changes.

## Recommendations

Njord derives conservative recommendations from review-needed flags and
spending reviews in [recommendations.py](recommendations.py). Recommendations
are advice only; they do not modify YNAB data.

Each recommendation separates:

- facts.
- interpretation.
- recommended review or action.
- expected impact.
- confidence.
- risks and tradeoffs.
- supporting evidence.

Recommendations are included only when deterministic evidence is available, so
the manual brief MVP can reuse them without requiring an LLM.

## AI Capability Loops

Njord's AI-backed finance work is structured as capability loops instead of
free-form chat. Each loop separates deterministic services, structured fact
packets, optional LLM judgment, validation, recommendations, audit metadata,
and any later approval/state update boundary.

The v0.8 loops are:

- Cash Flow Forecasting: calculate-only forecast from balances, transactions,
  and scheduled data.
- Financial Risk: deterministic risk score with explain-only LLM behavior.

The loop contract, dependency map, and milestone sequencing gates are documented
in [ai-loop-roadmap.md](ai-loop-roadmap.md).

## Finance Review

The interaction-first finance review is available inside the REPL:

```powershell
Njord
Njord> Review my finances.
```

For automation or Mongoose dispatch:

```powershell
python agents\njord\agent.py finance-review
mongoose run Njord finance-review
```

The review composes cash-flow forecasting and financial-risk loops, builds fact
packets and finance metrics, asks the configured Mongoose LLM backend for
structured judgment when available, validates that LLM decision contract, and
keeps all behavior read-only. In the REPL, Njord uses those capability outputs
as source material for a conversational answer instead of exposing the user to
the raw command report. Natural-language requests can ask for a finance review,
but they cannot mutate YNAB before guarded planning and write execution exist.

When Njord is launched by Mongoose with the v0.9 memory provider, each finance
review appends a `loop_aware_memory_record` through `mongoose.memory.v1`. The
record keeps replay-safe fact packet summaries, validation status,
user-facing loop events, and an informational decision outcome so future prompt
context can remember prior reviews without granting approval or write
authority.

If no Mongoose LLM profile is configured, or if the backend does not return
valid structured JSON, Njord keeps the deterministic review visible and reports
that the LLM decision was unavailable.

## Manual Financial Brief

The main manual workflow is:

```powershell
Njord
```

Then ask naturally:

```text
Njord> Give me a financial brief.
```

For automation or direct repository development:

```powershell
python agents\njord\agent.py brief
```

The brief combines balances, current-month spending highlights, review-needed
items, and conservative suggested next actions. It is read-only, deterministic,
and does not require Mongoose scheduling, event subscriptions, or LLM narration.

## Review-Needed Detection

Njord derives review-needed flags from the normalized snapshot in
[review.py](review.py). These flags are attention prompts, not recommendations
or approvals to change YNAB data.

The current rules flag:

- negative category balances.
- categories with spending but little or no assigned budget coverage.
- category activity that is materially above the assigned budget.
- uncategorized transactions.
- unusually large outflow transactions.
- scheduled transactions whose next date appears stale.

Each flag includes the rule that triggered it, the affected category or
transaction, severity, confidence, a neutral explanation, and supporting
evidence for later briefs or recommendations to reuse.

## Install

Install Njord as the user-local `Njord` command without administrator privileges.

Preferred Mongoose runtime flow:

```powershell
mongoose install Njord
```

If Mongoose is not installed yet, build and install it from the repository root:

```text
.\build-mongoose.cmd
.\install-mongoose.cmd
```

Legacy direct installer:

From the repository root:

```text
.\install.cmd Njord
```

All agents use `.\install.cmd <agent-install-name>`. Njord's install name is `Njord`. If an agent does not exist, the installer prints the available agent names.

The installer discovers this agent from [agent.json](agent.json):

```json
{
  "commandName": "Njord",
  "displayName": "Njord",
  "entrypointPath": "agent.py",
  "example": "Get me my latest budget",
  "description": "Personal finance agent for YNAB budget analysis and financial summaries."
}
```

The installer creates:

```text
%LOCALAPPDATA%\Agents\bin\Njord.cmd
```

It also adds that folder to the current user's `PATH`. Open a new terminal after installing.

Then run:

```powershell
Njord
```

Validate YNAB setup first:

```text
Njord> Check my configuration status.
```

Inside the session, enter a natural-language request:

```powershell
Njord> Get me my latest budget
```

If the current terminal cannot find `Njord` yet, open a new terminal or call the launcher directly:

```powershell
& "$env:LOCALAPPDATA\Agents\bin\Njord.cmd"
```

For installer internals, update notes, and uninstall instructions, see [../../install/README.md](../../install/README.md).

## Capabilities

| Capability | Description |
| --- | --- |
| `hello-world` | Run a simple Python greeting capability to verify the agent runtime pattern works. |
| `brief` | Produce a weekly-style financial brief with observations, spending highlights, review items, and suggested next actions. |
| `finance-review` | Run read-only AI capability loops for cash-flow forecasting and financial risk. |
| `ynab-budget-summary` | Read YNAB budget data and summarize current financial position, review-needed flags, spending, category activity, and notable changes. |
| `ynab-spending-review` | Review current month, previous month, or date-range spending with income, outflows, cash flow, top categories, and notable transactions. |

## Usage

Ask this agent for budget summaries, spending reviews, category analysis, cash-flow snapshots, or questions about where money is going.

Example requests:

- "Summarize my budget this month."
- "Show me my biggest spending categories."
- "What changed since last month?"
- "Are there categories I should review?"
- "Give me a CFO-style weekly financial brief."
- "Review my finances."
- "Show my cash flow forecast and risk score."

## Run The Agent

Run the interactive session through `agent.py`.

From the repository root:

```powershell
python agents\njord\agent.py
```

The REPL prompt is `Njord>`. It is conversational: ask naturally for budget
summaries, financial briefs, spending reviews, finance reviews, risk checks,
configuration status, or follow-up questions. Type `exit` or `quit` to leave
the session.

Finance-oriented REPL interactions select the relevant Njord capability,
collect YNAB-backed metrics, and then use the configured Mongoose LLM backend
to synthesize a ChatGPT-style response from those facts when a profile is
available. If the LLM backend is missing or unreachable, Njord still shows the
capability output and explains the missing synthesis step. One-shot commands
remain available for automation and explicit capability testing.

For scripts, tests, and Mongoose dispatch, one-shot commands remain available:

```powershell
python agents\njord\agent.py ask "Hey Njord, get me my latest budget."
```

You can also call capabilities directly:

```powershell
python agents\njord\agent.py hello-world
```

With a custom name:

```powershell
python agents\njord\agent.py hello-world --name "Njord"
```

Latest budget summary:

```powershell
python agents\njord\agent.py ynab-budget-summary
```

Manual financial brief:

```powershell
python agents\njord\agent.py brief
```

Finance review:

```powershell
python agents\njord\agent.py finance-review
```

Current month spending review:

```powershell
python agents\njord\agent.py ynab-spending-review
```

Previous month spending review:

```powershell
python agents\njord\agent.py ynab-spending-review --period previous-month
```

Explicit date range spending review:

```powershell
python agents\njord\agent.py ynab-spending-review --from 2026-05-01 --to 2026-05-31
```

Configuration status:

```powershell
python agents\njord\agent.py config status
```

After running the user-local installer, you can call this agent from any new terminal:

```powershell
Njord
```

The `hello-world` capability also tests the YNAB API connection by loading `YNAB_ACCESS_TOKEN` through the shared configuration stack and calling the YNAB plans endpoint.

If the token is configured correctly, the command reports that the connection succeeded and shows how many plans were found. It does not print the token.

To see available options:

```powershell
python agents\njord\agent.py --help
```

## Run The Sample Capability Directly

The `hello-world` capability is the first executable Python capability for this agent.

From the repository root, run:

```powershell
python agents\njord\capabilities\hello-world\hello_world.py
```

With a custom name:

```powershell
python agents\njord\capabilities\hello-world\hello_world.py --name "Njord"
```

Expected output:

```text
Hello, Njord.
Njord is ready to review your financial life.
YNAB connection succeeded. Found <count> plan(s).
```

In VS Code, open a terminal from the repository root before running the command.

## Internal Structure

- `agent.py`: Command-line entrypoint.
- `agent.json`: Install metadata discovered by the root installer. Its `commandName` is globally unique; its `entrypointPath` is relative to this directory.
- `brief.py`: Composes the manual financial brief from snapshot, spending, review, and recommendation outputs.
- `decision_contract.py`: Validates structured LLM decisions against finance loop guardrails.
- `fact_packet.py`: Builds deterministic prompt-safe finance fact packets.
- `finance_review.py`: Composes cash-flow and risk loops for the REPL finance review.
- `loop_contract.py`: Defines the AI capability loop contract and v0.8 loop registry.
- `router.py`: Routes natural-language requests to capabilities.
- `config.py`: Loads local environment values from `.env`.
- `review.py`: Detects categories and transactions that deserve human review.
- `recommendations.py`: Produces evidence-backed recommended reviews and actions.
- `spending.py`: Calculates period spending reviews from normalized transactions.
- `snapshot.py`: Normalized financial snapshot model for Njord analysis features.
- `write-safety.md`: Safety model for future YNAB write plans, approvals,
  audit records, and reconciliation.
- `ynab_api.py`: Shared read-only YNAB API client and normalization helpers.
- `capabilities/`: Capability implementations and documentation.

## Roadmap

Njord is moving toward budget maintenance in deliberate layers. The target flow
is:

```text
Read YNAB state
-> detect new money, overspending, underfunding, and category pressure
-> draft a money-movement or allocation plan
-> explain evidence, rationale, risk, and expected impact
-> require explicit approval
-> execute only approved writes
-> reconcile the result
-> retain outcomes for future preference learning
```

Milestone progression:

1. Read-only accountant and analyst mode: summarize financials from YNAB and
   identify patterns, anomalies, budget pressure, and review items.
2. Advisor mode: provide recommendations and tradeoffs without implying that
   Njord can change the budget.
3. Guarded planner mode: draft structured budget-maintenance plans for moving
   money between categories or allocating new money, including before/after
   values, rationale, risk, and source evidence.
4. Approval mode: let the user approve, reject, edit, defer, or expire a plan
   before any write operation is eligible to run.
5. Guarded operator mode: execute only approved, non-expired, policy-compliant
   YNAB write plans and create durable audit records.
6. Reconciliation mode: compare intended changes with current YNAB state and
   flag success, partial success, drift, or unknown status.
7. Preference-learning mode: measure approval, edit, rejection, and reversal
   rates so future recommendations can better match the user's budgeting style.

Scope boundary:

- In scope: YNAB budget reads, budget pressure detection, new-money allocation
  plans, category money-movement plans, approval records, guarded writes,
  reconciliation, audit records, and preference-learning inputs.
- Out of scope: unrelated Mongoose package-manager work, commerce
  integrations, non-Njord agents, broad UI host work, and auto-approval before
  proposal history and reconciliation data exist.

## Notes

This agent should begin as read-only. Any future capability that writes to YNAB
must be documented separately, require explicit confirmation, and prefer draft
recommendations over automatic changes. Natural-language requests must not
directly mutate YNAB; they should produce plans that pass through policy,
approval, execution, reconciliation, and audit steps.

The write safety contract is documented in
[write-safety.md](write-safety.md). Later budget-maintenance issues must
preserve that contract.

