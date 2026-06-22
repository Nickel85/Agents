"""Validate the local Mongoose memory provider MVP."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


REPO_ROOT = Path(__file__).resolve().parents[1]
MONGOOSE_CLI = REPO_ROOT / "mongoose" / "mongoose.py"
TEST_LOCAL_APP_DATA = REPO_ROOT / ".test-localappdata-mongoose-memory"


def remove_tree(path: Path) -> None:
    def handle_error(function, failing_path, _exc_info):
        os.chmod(failing_path, stat.S_IWRITE)
        function(failing_path)

    if path.exists():
        shutil.rmtree(path, onerror=handle_error)


def run_mongoose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LOCALAPPDATA": str(TEST_LOCAL_APP_DATA)}
    result = subprocess.run(
        [sys.executable, str(MONGOOSE_CLI), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"mongoose {' '.join(args)} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result


remove_tree(TEST_LOCAL_APP_DATA)
TEST_LOCAL_APP_DATA.mkdir(parents=True)
os.environ["LOCALAPPDATA"] = str(TEST_LOCAL_APP_DATA)

spec = importlib.util.spec_from_file_location("mongoose_cli_memory", MONGOOSE_CLI)
assert_true(spec is not None and spec.loader is not None, "Could not load mongoose.py.")
mongoose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mongoose)

state = json.loads(run_mongoose("state", "--init", "--json").stdout)
memory_path = Path(state["memory"])
assert_true(memory_path.is_dir(), "mongoose state --init did not create the memory directory.")

record = {
    "recordType": "loop_aware_memory_record",
    "agentId": "njord",
    "capabilityId": "finance-review",
    "goal": {"request": "Review budget token=secret-token"},
    "loop": {"status": "completed"},
    "decision": {"summary": "Use emergency fund preference", "confidence": 0.82},
    "outcome": {"status": "accepted", "summary": "User accepted the recommendation."},
    "events": [
        {
            "eventKind": "memory_used",
            "message": "Applied prior preference.",
            "createdAt": "2026-06-21T00:00:00Z",
        }
    ],
    "YNAB_ACCESS_TOKEN": "secret-token",
}
append = run_mongoose("memory", "append", "--record-json", json.dumps(record), "--json")
stored = json.loads(append.stdout)
stored_text = json.dumps(stored, sort_keys=True)
assert_true(stored["recordType"] == "loop_aware_memory_record", "Stored recordType changed.")
assert_true(stored["schemaVersion"] == 1, "Default schemaVersion was not applied.")
assert_true(stored["recordId"].startswith("memory_"), "Record id was not generated.")
assert_true(stored["redaction"]["secretsRemoved"] is True, "Redaction marker was not set.")
assert_true("secret-token" not in stored_text, "Memory append leaked a secret value.")
assert_true(stored["YNAB_ACCESS_TOKEN"] == "[redacted]", "Secret-like memory field was not redacted.")
assert_true("token=[redacted]" in stored_text, "Secret-like text in memory content was not redacted.")

list_result = run_mongoose(
    "memory",
    "list",
    "--agent",
    "njord",
    "--capability",
    "finance-review",
    "--record-type",
    "loop_aware_memory_record",
    "--status",
    "completed",
    "--json",
)
listed = json.loads(list_result.stdout)
assert_true(len(listed) == 1, "Filtered memory list did not return exactly one record.")
assert_true(listed[0]["recordId"] == stored["recordId"], "Filtered memory list returned the wrong record.")

subject_result = run_mongoose("memory", "list", "--subject", "emergency fund", "--json")
subject_matches = json.loads(subject_result.stdout)
assert_true(len(subject_matches) == 1, "Subject search did not find the expected memory record.")

outcome_result = run_mongoose("memory", "list", "--outcome", "accepted", "--min-confidence", "0.8", "--json")
outcome_matches = json.loads(outcome_result.stdout)
assert_true(len(outcome_matches) == 1, "Outcome/confidence filters did not find the expected memory record.")

show_result = run_mongoose("memory", "show", stored["recordId"], "--json")
shown = json.loads(show_result.stdout)
assert_true(shown["recordId"] == stored["recordId"], "Memory show returned the wrong record.")

commerce_record = {
    "recordType": "decision_proposal",
    "agentId": "etsy",
    "capabilityId": "ad-review",
    "createdAt": "2026-06-21T01:00:00Z",
    "subject": "seasonal listing",
    "decision": {
        "summary": "Do not rerun buyer shipment promo for 123 Main Street; token=commerce-secret",
        "confidence": 0.91,
    },
    "userDecision": {"status": "rejected", "summary": "User rejected the promo."},
    "outcome": {"status": "deferred", "summary": "No campaign was launched."},
    "buyerEmail": "buyer@example.com",
    "buyerAddress": "123 Main Street",
}
commerce_append = run_mongoose("memory", "append", "--record-json", json.dumps(commerce_record), "--json")
commerce_stored = json.loads(commerce_append.stdout)
context_result = run_mongoose(
    "memory",
    "context",
    "--agent",
    "etsy",
    "--capability",
    "ad-review",
    "--subject",
    "seasonal",
    "--outcome",
    "deferred",
    "--min-confidence",
    "0.9",
    "--json",
)
context = json.loads(context_result.stdout)
context_text = json.dumps(context, sort_keys=True)
assert_true(context["interface"] == "mongoose.prompt-context.v1", "Prompt context interface changed.")
assert_true(context["fallback"]["used"] is False, "Prompt context incorrectly used fallback.")
assert_true(context["records"][0]["recordId"] == commerce_stored["recordId"], "Prompt context returned the wrong record.")
assert_true(context["records"][0]["source"]["recordId"] == commerce_stored["recordId"], "Prompt context lost provenance.")
assert_true(context["guardrails"]["canApproveActions"] is False, "Prompt context can approve actions.")
assert_true(context["guardrails"]["canMutateState"] is False, "Prompt context can mutate state.")
assert_true("commerce-secret" not in context_text, "Prompt context leaked a secret.")
assert_true("buyer@example.com" not in context_text, "Prompt context leaked a buyer email.")
assert_true("123 Main Street" not in context_text, "Prompt context leaked a buyer address.")
assert_true("[redacted-address]" in context_text, "Prompt context did not redact an address-like phrase.")

empty_context = json.loads(run_mongoose("memory", "context", "--subject", "does-not-exist", "--json").stdout)
assert_true(empty_context["fallback"]["used"] is True, "Prompt context did not return deterministic fallback.")
assert_true(empty_context["records"] == [], "Fallback prompt context should not include records.")

records_file = memory_path / "records.jsonl"
assert_true(records_file.is_file(), "Memory JSONL file was not created.")
assert_true("secret-token" not in records_file.read_text(encoding="utf-8"), "Memory JSONL leaked a secret value.")

providers = mongoose.runtime_provider_descriptors(
    {"commandName": "Njord", "llm": {"mode": "none"}},
    {"name": "finance-review", "llm": {"mode": "none"}},
)
memory_provider = providers["memory"]
assert_true(memory_provider["available"] is True, "Memory provider was not available.")
assert_true(memory_provider["interface"] == "mongoose.memory.v1", "Memory provider interface changed.")
assert_true(memory_provider["recordsPath"] == str(records_file), "Memory provider recordsPath was wrong.")
assert_true(memory_provider["appendCommand"][-3:] == ["memory", "append", "--json"], "Memory appendCommand was wrong.")
assert_true(memory_provider["listCommand"][-3:] == ["memory", "list", "--json"], "Memory listCommand was wrong.")
assert_true(memory_provider["contextCommand"][-3:] == ["memory", "context", "--json"], "Memory contextCommand was wrong.")

print("Mongoose memory validation passed.")
