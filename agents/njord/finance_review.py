"""Interaction-first Njord finance review capability."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import ConfigFileError, current_config_snapshot
from decision_contract import validate_llm_decision
from fact_packet import (
    FinanceFactPacket,
    build_cash_flow_fact_packet,
    build_financial_risk_fact_packet,
)
from loop_contract import get_contract
from llm_runtime import LlmDecisionResult, invoke_finance_decision
from review import review_snapshot
from snapshot import FinancialSnapshot, load_snapshot
from spending import review_spending
from ynab_api import YnabClient, choose_plan, format_currency, list_plans


@dataclass(frozen=True)
class FinanceReviewResult:
    ok: bool
    output: str
    fact_packets: list[FinanceFactPacket]
    audit_record: dict[str, Any] | None = None
    memory_record: dict[str, Any] | None = None
    memory_status: str = "skipped"


def fallback_decision_payload() -> dict[str, Any]:
    return {
        "recommendation": "Review the deterministic finance facts before requesting a budget change.",
        "rationale": "The finance review is read-only and uses validated fact packets.",
        "confidence": 0.8,
        "assumptions": [
            "The loaded YNAB snapshot is the current source of truth.",
            "Missing scheduled transaction data lowers forecast confidence.",
        ],
        "risks": [
            "Short review periods can make cash flow look worse than the full month.",
            "No budget changes are executed from this review.",
        ],
        "requires_user_approval": True,
    }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def runtime_context() -> dict[str, Any]:
    context_path = os.environ.get("MONGOOSE_RUNTIME_CONTEXT", "").strip()
    if not context_path:
        return {}
    path = Path(context_path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def memory_append_command() -> list[str]:
    context = runtime_context()
    providers = context.get("providers", {})
    memory = providers.get("memory", {}) if isinstance(providers, dict) else {}
    if not isinstance(memory, dict) or not memory.get("available"):
        return []
    command = memory.get("appendCommand", [])
    if isinstance(command, list) and all(isinstance(item, str) and item for item in command):
        return command
    return []


def append_memory_record(record: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str]:
    command = memory_append_command()
    if not command:
        return False, None, "No Mongoose memory append command is available."
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(record, sort_keys=True),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=30,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, None, f"Could not append Mongoose memory record: {exc}"
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or completed.stdout.strip() or "Mongoose memory append failed."
        return False, None, diagnostic
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return True, None, "Mongoose memory append succeeded without JSON output."
    return True, payload if isinstance(payload, dict) else None, ""


def confidence_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))
    text = str(value).strip().lower()
    if text == "high":
        return 0.85
    if text == "medium":
        return 0.65
    if text == "low":
        return 0.35
    try:
        return max(0.0, min(float(text), 1.0))
    except ValueError:
        return None


def llm_decision_summary(result: LlmDecisionResult, fallback_decision: dict[str, Any]) -> dict[str, Any]:
    if result.ok and result.decision:
        decision = result.decision
        return {
            "source": "llm",
            "summary": str(decision.get("recommendation", "")).strip(),
            "rationale": str(decision.get("rationale", "")).strip(),
            "confidence": confidence_value(decision.get("confidence")),
            "requiresUserApproval": bool(decision.get("requires_user_approval", True)),
            "assumptions": decision.get("assumptions", []),
            "risks": decision.get("risks", []),
        }
    return {
        "source": "deterministic_fallback",
        "summary": str(fallback_decision.get("recommendation", "")).strip(),
        "rationale": str(fallback_decision.get("rationale", "")).strip(),
        "confidence": confidence_value(fallback_decision.get("confidence")),
        "requiresUserApproval": bool(fallback_decision.get("requires_user_approval", True)),
        "assumptions": fallback_decision.get("assumptions", []),
        "risks": fallback_decision.get("risks", []),
    }


def build_finance_audit_record(
    *,
    snapshot: FinancialSnapshot,
    request: str,
    fact_packets: list[FinanceFactPacket],
    llm_decision: LlmDecisionResult,
    fallback_validation_summary: str,
) -> dict[str, Any]:
    risk_packet = fact_packets[-1]
    decision = llm_decision_summary(llm_decision, fallback_decision_payload())
    validation_status = "valid" if llm_decision.ok else "unavailable"
    if llm_decision.validation is not None and not llm_decision.validation.ok:
        validation_status = "invalid"
    event_time = now_utc_iso()
    fact_packet_refs = [
        {
            "packetId": packet.packet_id,
            "capability": packet.capability,
            "confidence": packet.confidence,
            "sourceSnapshotIds": packet.source_snapshot_ids,
            "generatedFacts": packet.generated_facts,
            "missingData": packet.missing_data,
            "staleData": packet.stale_data,
        }
        for packet in fact_packets
    ]
    return {
        "schemaVersion": 1,
        "recordType": "loop_aware_memory_record",
        "agentId": "Njord",
        "capabilityId": "finance-review",
        "goal": {
            "request": request,
            "summary": "Run read-only finance review loops and produce replay-safe recommendations.",
        },
        "loop": {
            "definitionIds": ["cash-flow-forecasting", "financial-risk"],
            "status": "completed",
            "exitCriteria": [
                "fact packets generated",
                "LLM decision attempted or deterministic fallback recorded",
                "decision contract validation status recorded",
                "read-only guardrails preserved",
            ],
        },
        "stateReads": [
            {
                "provider": "YNAB",
                "planId": snapshot.metadata.plan_id,
                "planName": snapshot.metadata.plan_name,
                "snapshotId": fact_packets[0].source_snapshot_ids[0] if fact_packets else "",
                "fetchedAt": snapshot.metadata.fetched_at,
            }
        ],
        "tools": [
            {"name": "YNAB read API", "mode": "read-only"},
            {"name": "Mongoose LLM provider", "mode": "optional", "profile": llm_decision.profile},
        ],
        "facts": {
            "factPackets": fact_packet_refs,
            "replaySafe": True,
        },
        "decision": decision,
        "recommendation": {
            "summary": decision["summary"],
            "requiresUserApproval": decision["requiresUserApproval"],
        },
        "validation": {
            "status": validation_status,
            "fallbackValidation": fallback_validation_summary,
            "llmValidation": llm_decision.validation.summary() if llm_decision.validation else llm_decision.diagnostic,
        },
        "userDecision": {
            "status": "informational",
            "summary": "No budget-changing action was requested or approved by this read-only review.",
        },
        "outcome": {
            "status": "completed",
            "summary": f"Risk band {risk_packet.generated_facts.get('risk_band')} with score {risk_packet.generated_facts.get('risk_score')}.",
        },
        "confidence": decision["confidence"],
        "events": [
            {
                "eventKind": "started",
                "visibility": "user",
                "message": "Started a read-only finance review.",
                "createdAt": event_time,
            },
            {
                "eventKind": "state_read",
                "visibility": "user",
                "message": "Read the selected YNAB snapshot without write access.",
                "createdAt": event_time,
            },
            {
                "eventKind": "fact_found",
                "visibility": "user",
                "message": "Generated cash-flow and financial-risk fact packets.",
                "references": [packet.packet_id for packet in fact_packets],
                "createdAt": event_time,
            },
            {
                "eventKind": "decision_made",
                "visibility": "user",
                "message": decision["summary"],
                "createdAt": event_time,
            },
            {
                "eventKind": "validation_passed" if validation_status == "valid" else "validation_failed",
                "visibility": "user",
                "message": llm_decision.validation.summary() if llm_decision.validation else llm_decision.diagnostic,
                "createdAt": event_time,
            },
            {
                "eventKind": "completed",
                "visibility": "user",
                "message": "Completed the finance review without mutating YNAB.",
                "createdAt": event_time,
            },
        ],
        "trace": {"futureExecutionTraceId": ""},
        "redaction": {"secretsRemoved": True, "rawProviderPayloadsRemoved": True},
        "createdAt": event_time,
    }


def build_finance_review_from_snapshot(
    snapshot: FinancialSnapshot,
    *,
    request: str = "Review my finances.",
    decision_backend=invoke_finance_decision,
    memory_appender=append_memory_record,
) -> FinanceReviewResult:
    spending = review_spending(snapshot)
    review_summary = review_snapshot(snapshot)
    review_flags = [flag.to_dict() for flag in review_summary.flags]
    cash_flow = build_cash_flow_fact_packet(snapshot, spending)
    risk = build_financial_risk_fact_packet(
        snapshot,
        spending,
        review_flags,
        cash_flow_packet=cash_flow,
    )
    validation = validate_llm_decision(fallback_decision_payload(), risk)
    llm_decision = decision_backend(request=request, fact_packet=risk)
    lines = [
        "Njord finance review",
        f"Plan: {snapshot.metadata.plan_name}",
        f"Snapshot: {snapshot.metadata.fetched_at}",
        "",
        "Loop contract",
        f"- {get_contract('cash-flow-forecasting').name}: calculate_only; LLM role: none.",
        f"- {get_contract('financial-risk').name}: score_and_explain; LLM role: explain only.",
        "",
        "Cash Flow Forecasting",
        f"- Current cash: {cash_flow.generated_facts['current_cash_display']}",
        f"- Income: {cash_flow.generated_facts['income_display']}",
        f"- Outflows: {cash_flow.generated_facts['outflows_display']}",
        f"- Net cash flow: {cash_flow.generated_facts['net_cash_flow_display']}",
        (
            "- Estimated daily net cash flow: "
            f"{cash_flow.generated_facts['estimated_daily_net_cash_flow_display']}"
        ),
        f"- Cash floor breach date: {cash_flow.generated_facts['cash_floor_breach_date'] or 'not detected'}",
        f"- Forecast confidence: {cash_flow.confidence}",
        "",
        "Financial Risk",
        f"- Risk score: {risk.generated_facts['risk_score']} ({risk.generated_facts['risk_band']})",
        f"- High-severity flags: {risk.generated_facts['high_flag_count']}",
        f"- Medium-severity flags: {risk.generated_facts['medium_flag_count']}",
        "- Top risks:",
    ]
    lines.extend(f"  - {item}" for item in risk.generated_facts["top_risks"])
    lines.extend(
        [
            "- Mitigation actions:",
            *[f"  - {item}" for item in risk.generated_facts["mitigation_actions"]],
            "",
            "Fact packets",
            f"- {cash_flow.packet_id}: {cash_flow.capability}; confidence {cash_flow.confidence}",
            f"- {risk.packet_id}: {risk.capability}; confidence {risk.confidence}",
            "",
            "LLM decision validation",
            f"- Deterministic fallback: {validation.summary()}",
        ]
    )
    lines.extend(format_llm_decision_lines(llm_decision))
    lines.extend(
        [
            "",
            "Guardrails",
            "- This review is read-only.",
            "- Natural-language requests cannot mutate YNAB before guarded write execution exists.",
            "- LLM output may explain or rank validated facts, but cannot calculate balances or approve writes.",
            "",
            "Next actions",
            "- Ask Njord follow-up questions in the REPL.",
            "- Use future guarded planning only after reviewing these facts.",
        ]
    )
    if cash_flow.missing_data or risk.missing_data:
        missing = sorted(set(cash_flow.missing_data + risk.missing_data))
        lines.extend(["", "Missing or weak data"])
        lines.extend(f"- {item}" for item in missing)

    audit_record = build_finance_audit_record(
        snapshot=snapshot,
        request=request,
        fact_packets=[cash_flow, risk],
        llm_decision=llm_decision,
        fallback_validation_summary=validation.summary(),
    )
    memory_ok, memory_record, memory_diagnostic = memory_appender(audit_record)
    memory_status = "stored" if memory_ok else f"skipped: {memory_diagnostic}"

    return FinanceReviewResult(
        True,
        "\n".join(lines),
        [cash_flow, risk],
        audit_record=audit_record,
        memory_record=memory_record,
        memory_status=memory_status,
    )


def format_llm_decision_lines(result: LlmDecisionResult) -> list[str]:
    profile = f" ({result.profile})" if result.profile else ""
    if not result.ok:
        diagnostic = result.diagnostic or "Configured LLM backend did not return a valid decision."
        return [f"- LLM decision unavailable{profile}: {diagnostic}"]

    decision = result.decision or {}
    lines = [
        f"- LLM decision{profile}: {result.validation.summary() if result.validation else 'valid'}",
        f"  - Recommendation: {decision.get('recommendation', '')}",
        f"  - Rationale: {decision.get('rationale', '')}",
        f"  - Confidence: {decision.get('confidence', '')}",
        f"  - Requires user approval: {decision.get('requires_user_approval', '')}",
        "  - Assumptions:",
    ]
    lines.extend(f"    - {item}" for item in decision.get("assumptions", []))
    lines.append("  - Risks:")
    lines.extend(f"    - {item}" for item in decision.get("risks", []))
    return lines


def load_finance_review(*, request: str = "Review my finances.") -> tuple[bool, str]:
    try:
        config = current_config_snapshot()
    except ConfigFileError as exc:
        return (
            False,
            "\n".join(
                [
                    str(exc),
                    "Run 'Njord config status' after fixing the configuration file.",
                ]
            ),
        )

    if not config["token"]:
        return (
            False,
            "YNAB_ACCESS_TOKEN is not configured. Run 'Njord config status' for setup details.",
        )
    if not config["budget_id"]:
        return (
            False,
            "YNAB_BUDGET_ID is not configured. Run 'Njord config status' to validate available plans.",
        )

    plans_result = list_plans()
    if not plans_result.ok:
        return False, plans_result.message
    selected_plan = choose_plan(plans_result.items, config["budget_id"])
    if selected_plan is None:
        return False, "No YNAB plan could be selected."
    selected_id = selected_plan.get("id", "")
    name = selected_plan.get("name") or selected_id or "selected YNAB plan"

    snapshot_result = load_snapshot(YnabClient(config["token"]), selected_id, name)
    if not snapshot_result.ok or snapshot_result.snapshot is None:
        return (
            False,
            "\n".join(
                [
                    "Njord finance review",
                    f"Plan: {name}",
                    "",
                    "Connection status: connected to YNAB plan list.",
                    f"Snapshot status: {snapshot_result.message}",
                    "The finance review needs a full read-only snapshot before it can build fact packets.",
                ]
            ),
        )
    result = build_finance_review_from_snapshot(snapshot_result.snapshot, request=request)
    return result.ok, result.output


def summarize_fact_packet(packet: FinanceFactPacket) -> dict[str, Any]:
    return {
        "packet_id": packet.packet_id,
        "capability": packet.capability,
        "confidence": packet.confidence,
        "source_snapshot_ids": packet.source_snapshot_ids,
        "generated_facts": packet.generated_facts,
    }
