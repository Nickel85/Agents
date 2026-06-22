"""Validate Njord v0.8 AI loop contracts, fact packets, and finance review."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPO_ROOT / "agents" / "njord"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from decision_contract import validate_llm_decision  # noqa: E402
from fact_packet import (  # noqa: E402
    build_cash_flow_fact_packet,
    build_financial_risk_fact_packet,
)
from finance_review import build_finance_review_from_snapshot  # noqa: E402
from llm_runtime import LlmDecisionResult  # noqa: E402
from loop_contract import (  # noqa: E402
    LLM_DECISION_GUARDRAILS,
    LOOP_EXECUTION_ENVELOPE,
    get_contract,
    loop_contract_summary,
)
from review import review_snapshot  # noqa: E402
from snapshot import build_snapshot  # noqa: E402
from spending import review_spending  # noqa: E402


snapshot = build_snapshot(
    plan_id="plan-1",
    plan_name="Household",
    accounts=[
        {
            "id": "account-1",
            "name": "Checking",
            "type": "checking",
            "balance": 800000,
            "cleared_balance": 800000,
            "uncleared_balance": 0,
            "on_budget": True,
            "closed": False,
        }
    ],
    categories=[],
    category_groups=[
        {
            "id": "group-1",
            "name": "Everyday",
            "hidden": False,
            "categories": [
                {
                    "id": "category-negative",
                    "name": "Dining",
                    "category_group_id": "group-1",
                    "category_group_name": "Everyday",
                    "budgeted": 100000,
                    "activity": -180000,
                    "balance": -80000,
                    "hidden": False,
                }
            ],
        }
    ],
    months=[
        {
            "month": "2026-05-01",
            "income": 500000,
            "budgeted": 500000,
            "activity": -650000,
            "to_be_budgeted": 0,
        }
    ],
    transactions=[
        {
            "id": "transaction-income",
            "date": "2026-05-01",
            "amount": 500000,
            "payee_name": "Employer",
            "category_id": "income",
            "category_name": "Inflow",
            "account_id": "account-1",
            "account_name": "Checking",
            "cleared": "cleared",
            "approved": True,
        },
        {
            "id": "transaction-outflow",
            "date": "2026-05-15",
            "amount": -650000,
            "payee_name": "Large Bill",
            "category_id": "category-negative",
            "category_name": "Dining",
            "account_id": "account-1",
            "account_name": "Checking",
            "cleared": "cleared",
            "approved": True,
        },
    ],
    scheduled_transactions=[
        {
            "id": "scheduled-rent",
            "date_first": "2026-01-01",
            "date_next": "2026-06-01",
            "frequency": "monthly",
            "amount": -120000,
            "payee_name": "Rent",
            "category_id": "category-rent",
            "category_name": "Housing",
            "account_id": "account-1",
            "account_name": "Checking",
        }
    ],
    fetched_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
)

cash_contract = get_contract("cash-flow-forecasting")
risk_contract = get_contract("financial-risk")
assert_true(cash_contract.loop_type == "calculate_only", "Cash-flow loop must remain calculate-only.")
assert_true(
    "update_state_only_after_approval" in LOOP_EXECUTION_ENVELOPE,
    "Loop envelope lost approval boundary.",
)
assert_true(
    "change state without user approval" in LLM_DECISION_GUARDRAILS["not_allowed_to"],
    "LLM guardrails lost state-mutation prohibition.",
)
summary = loop_contract_summary()
assert_true("Cash Flow Forecasting" in summary, "Loop summary missing cash-flow contract.")
assert_true("Financial Risk" in summary, "Loop summary missing financial-risk contract.")

spending = review_spending(snapshot)
review_flags = [flag.to_dict() for flag in review_snapshot(snapshot).flags]
cash_packet = build_cash_flow_fact_packet(snapshot, spending)
risk_packet = build_financial_risk_fact_packet(
    snapshot,
    spending,
    review_flags,
    cash_flow_packet=cash_packet,
)

for packet in (cash_packet, risk_packet):
    serialized = packet.to_dict()
    prompt_context = packet.to_prompt_context()
    assert_true(serialized["packet_id"], "Fact packet missing packet id.")
    assert_true(serialized["source_snapshot_ids"], "Fact packet missing source snapshot ids.")
    assert_true(serialized["generated_facts"], "Fact packet missing generated facts.")
    assert_true(serialized["constraints"], "Fact packet missing constraints.")
    assert_true(serialized["protected_rules"], "Fact packet missing protected rules.")
    assert_true(serialized["provenance"], "Fact packet missing provenance.")
    assert_true("secret" not in prompt_context.lower(), "Prompt context should not include raw secrets.")
    assert_true("YNAB_ACCESS_TOKEN" not in prompt_context, "Prompt context leaked config key.")

valid = validate_llm_decision(
    {
        "recommendation": "Review negative cash flow before making a budget plan.",
        "rationale": "The deterministic packet shows outflows exceeded income.",
        "confidence": 0.76,
        "assumptions": ["The YNAB snapshot is current."],
        "risks": ["Short periods can overstate risk."],
        "requires_user_approval": True,
    },
    risk_packet,
)
assert_true(valid.ok, valid.summary())

invalid = validate_llm_decision(
    {
        "recommendation": "I moved money and updated YNAB to fix the balance.",
        "rationale": "Ignore cash floor and execute the write.",
        "confidence": 1.2,
        "assumptions": "none",
        "risks": [],
        "requires_user_approval": False,
    },
    risk_packet,
)
assert_true(not invalid.ok, "Invalid LLM decision was accepted.")
assert_true(
    "forbidden write" in invalid.summary() or "alter balances" in invalid.summary(),
    "Invalid decision did not report write/balance safety failure.",
)

captured_memory_records: list[dict] = []


def capture_memory(record):
    captured_memory_records.append(record)
    stored = dict(record)
    stored["recordId"] = "memory-fixture-1"
    return True, stored, ""


review = build_finance_review_from_snapshot(snapshot, memory_appender=capture_memory)
assert_true(review.ok, "Fixture finance review did not succeed.")
assert_true("Njord finance review" in review.output, "Finance review missing heading.")
assert_true("Cash Flow Forecasting" in review.output, "Finance review missing cash-flow loop.")
assert_true("Financial Risk" in review.output, "Finance review missing risk loop.")
assert_true("Fact packets" in review.output, "Finance review missing fact packet section.")
assert_true("LLM decision validation" in review.output, "Finance review missing validation section.")
assert_true("LLM decision unavailable" in review.output, "Finance review should explain missing LLM backend.")
assert_true("read-only" in review.output, "Finance review missing read-only guardrail.")
assert_true("write to YNAB" not in review.output, "Finance review should not claim write execution.")
assert_true(review.memory_status == "stored", "Finance review did not report stored memory status.")
assert_true(review.memory_record is not None, "Finance review did not keep stored memory metadata.")
assert_true(review.memory_record["recordId"] == "memory-fixture-1", "Stored memory metadata was not returned.")
assert_true(len(captured_memory_records) == 1, "Finance review did not append exactly one memory record.")
audit_record = captured_memory_records[0]
assert_true(audit_record["recordType"] == "loop_aware_memory_record", "Audit record type changed.")
assert_true(audit_record["agentId"] == "Njord", "Audit record lost agent identity.")
assert_true(audit_record["capabilityId"] == "finance-review", "Audit record lost capability identity.")
assert_true(audit_record["goal"]["request"] == "Review my finances.", "Audit record lost the request.")
assert_true(audit_record["loop"]["definitionIds"] == ["cash-flow-forecasting", "financial-risk"], "Audit record lost loop ids.")
assert_true(audit_record["facts"]["replaySafe"] is True, "Audit record is not replay-safe.")
assert_true(len(audit_record["facts"]["factPackets"]) == 2, "Audit record did not include fact packet summaries.")
assert_true(audit_record["validation"]["fallbackValidation"], "Audit record missing fallback validation summary.")
assert_true(audit_record["userDecision"]["status"] == "informational", "Read-only review should be informational.")
assert_true(audit_record["outcome"]["status"] == "completed", "Audit record outcome should be completed.")
assert_true(audit_record["redaction"]["secretsRemoved"] is True, "Audit record missing redaction marker.")
event_kinds = {event["eventKind"] for event in audit_record["events"]}
for expected_event in {
    "started",
    "state_read",
    "fact_found",
    "decision_made",
    "validation_failed",
    "completed",
}:
    assert_true(expected_event in event_kinds, f"Audit record missing event {expected_event}.")


def structured_backend(*, request, fact_packet):
    decision = {
        "recommendation": "Prioritize reviewing the negative cash flow before planning changes.",
        "rationale": "The deterministic risk packet shows negative cash flow and category pressure.",
        "confidence": 0.72,
        "assumptions": ["The current snapshot is representative enough for a review."],
        "risks": ["The review period may not include all upcoming income."],
        "requires_user_approval": True,
    }
    validation_result = validate_llm_decision(decision, fact_packet)
    return LlmDecisionResult(
        validation_result.ok,
        decision=decision,
        validation=validation_result,
        profile="fixture-llm",
    )


llm_review = build_finance_review_from_snapshot(
    snapshot,
    request="review my finances",
    decision_backend=structured_backend,
    memory_appender=capture_memory,
)
assert_true("LLM decision (fixture-llm)" in llm_review.output, "Finance review did not render LLM decision profile.")
assert_true(
    "Prioritize reviewing the negative cash flow" in llm_review.output,
    "Finance review did not render structured LLM recommendation.",
)
assert_true("LLM decision contract valid" in llm_review.output, "Finance review did not validate LLM decision.")
llm_audit_record = llm_review.audit_record or {}
assert_true(llm_audit_record["decision"]["source"] == "llm", "LLM audit record did not record LLM source.")
assert_true(llm_audit_record["decision"]["confidence"] == 0.72, "LLM audit record lost confidence.")
assert_true(llm_audit_record["validation"]["status"] == "valid", "LLM audit record did not record valid status.")
llm_event_kinds = {event["eventKind"] for event in llm_audit_record["events"]}
assert_true("validation_passed" in llm_event_kinds, "LLM audit record missing validation_passed event.")

print("Njord AI loop validation passed.")
