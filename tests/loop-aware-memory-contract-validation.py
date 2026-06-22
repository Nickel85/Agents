"""Validate the v0.9 loop-aware memory contract documentation."""

from __future__ import annotations

from pathlib import Path


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "loop-aware-memory.md"


text = CONTRACT.read_text(encoding="utf-8")
normalized_text = " ".join(text.lower().split())

for required_text in (
    "# Loop-Aware Memory Record Contract v1",
    "`loop_aware_memory_record`",
    '"schemaVersion": 1',
    '"recordType": "loop_aware_memory_record"',
    '"agentId": "njord"',
    '"capabilityId": "finance-review"',
    "Durable Events",
    "`memory_used`",
    "`decision_made`",
    "`approval_required`",
    "Transient Activity Indicators",
    "Thinking.",
    "Thinking..",
    "Thinking...",
    '"overwriteLine": true',
    "same\nterminal line in place",
    "Prompt Context",
    "Versioning",
):
    assert_true(
        required_text in text,
        f"loop-aware memory contract is missing required text: {required_text}",
    )

for forbidden_claim in (
    "execute arbitrary loop definitions",
    "approve actions or mutate state",
):
    assert_true(
        forbidden_claim in text,
        f"loop-aware memory contract must explicitly reject: {forbidden_claim}",
    )

for secret_text in (
    "raw access tokens",
    "API keys",
    "bearer tokens",
    "raw provider payloads",
    "private reasoning traces",
):
    assert_true(
        secret_text.lower() in normalized_text,
        f"loop-aware memory contract must mention redaction boundary: {secret_text}",
    )

print("Loop-aware memory contract validation passed.")
