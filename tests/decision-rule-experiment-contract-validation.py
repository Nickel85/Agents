"""Validate the v0.9 decision/rule/experiment memory contract."""

from __future__ import annotations

from pathlib import Path


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "decision-rule-experiment-memory.md"

assert_true(CONTRACT.exists(), "decision/rule/experiment memory contract is missing.")
text = CONTRACT.read_text(encoding="utf-8")

required_text = [
    "# Decision, Rule, and Experiment Memory Contract v1",
    "`mongoose.memory.v1`",
    "`decision_record`",
    "`rule_record`",
    "`experiment_record`",
    "domain",
    "target",
    "evidenceRefs",
    "relatedMemoryRefs",
    "review",
    "userDecision",
    "extensions",
    "requiresApproval",
    "approvalBoundary",
    "ruleId",
    "experimentId",
    "plannedStart",
    "plannedEnd",
    "successCriteria",
    "`proposed`",
    "`approved`",
    "`active`",
    "`paused`",
    "`rejected`",
    "`expired`",
    "`reviewed`",
    "`superseded`",
    "`disabled`",
    "`completed`",
    "queryability by domain, target, date range, status, review due date",
    "loop_aware_memory_record",
    "Execution Traces",
    "prompt-context summaries",
]
for item in required_text:
    assert_true(item in text, f"decision/rule/experiment contract is missing required text: {item}")

for forbidden_claim in [
    "silently approve a future action",
    "separate database",
    "replace loop-aware memory",
]:
    assert_true(forbidden_claim in text, f"contract must explicitly reject: {forbidden_claim}")

for redaction_text in [
    "Secret values",
    "raw provider payloads",
    "buyer addresses",
    "access tokens",
    "unnecessary PII",
]:
    assert_true(redaction_text in text, f"contract missing redaction boundary: {redaction_text}")

print("Decision/rule/experiment memory contract validation passed.")
