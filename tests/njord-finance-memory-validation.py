"""Validate Njord finance review writes loop-aware memory through Mongoose."""

from __future__ import annotations

from datetime import datetime, timezone
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
AGENT_ROOT = REPO_ROOT / "agents" / "njord"
TEST_LOCAL_APP_DATA = REPO_ROOT / ".test-localappdata-njord-finance-memory"


def remove_tree(path: Path) -> None:
    def handle_error(function, failing_path, _exc_info):
        os.chmod(failing_path, stat.S_IWRITE)
        function(failing_path)

    if path.exists():
        shutil.rmtree(path, onerror=handle_error)


def run_mongoose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(MONGOOSE_CLI), *args],
        cwd=REPO_ROOT,
        env={**os.environ, "LOCALAPPDATA": str(TEST_LOCAL_APP_DATA)},
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

spec = importlib.util.spec_from_file_location("mongoose_cli_for_njord_memory", MONGOOSE_CLI)
assert_true(spec is not None and spec.loader is not None, "Could not load mongoose.py.")
mongoose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mongoose)

context = mongoose.runtime_context(
    mode="run",
    agent={
        "commandName": "Njord",
        "displayName": "Njord",
        "version": "0.1.0",
        "sourcePath": str(AGENT_ROOT),
        "manifestPath": str(AGENT_ROOT / "agent.json"),
    },
    capability={"name": "finance-review", "llm": {"mode": "none"}},
    agent_args=["finance-review"],
)
context_path = mongoose.write_runtime_context(context)
os.environ["MONGOOSE_RUNTIME_CONTEXT"] = str(context_path)

if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from decision_contract import validate_llm_decision  # noqa: E402
from finance_review import build_finance_review_from_snapshot  # noqa: E402
from llm_runtime import LlmDecisionResult  # noqa: E402
from snapshot import build_snapshot  # noqa: E402


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
    scheduled_transactions=[],
    fetched_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
)


def structured_backend(*, request, fact_packet):
    decision = {
        "recommendation": "Review negative cash flow before planning any budget changes.",
        "rationale": "The deterministic risk packet shows net cash flow pressure.",
        "confidence": 0.73,
        "assumptions": ["The current snapshot is representative enough for a review."],
        "risks": ["Scheduled transaction data is missing."],
        "requires_user_approval": True,
    }
    validation = validate_llm_decision(decision, fact_packet)
    return LlmDecisionResult(validation.ok, decision=decision, validation=validation, profile="fixture-llm")


result = build_finance_review_from_snapshot(
    snapshot,
    request="review my finances",
    decision_backend=structured_backend,
)
assert_true(result.ok, "Finance review failed.")
assert_true(result.memory_status == "stored", f"Finance review did not store memory: {result.memory_status}")
assert_true(result.memory_record is not None, "Stored memory record metadata was not returned.")

records = json.loads(
    run_mongoose(
        "memory",
        "list",
        "--agent",
        "Njord",
        "--capability",
        "finance-review",
        "--record-type",
        "loop_aware_memory_record",
        "--status",
        "completed",
        "--json",
    ).stdout
)
assert_true(len(records) == 1, "Expected one stored Njord finance loop memory record.")
record = records[0]
assert_true(record["recordId"] == result.memory_record["recordId"], "Stored memory id did not match result metadata.")
assert_true(record["facts"]["replaySafe"] is True, "Stored finance memory is not replay-safe.")
assert_true(record["decision"]["source"] == "llm", "Stored finance memory did not record LLM decision source.")
assert_true(record["validation"]["status"] == "valid", "Stored finance memory did not record valid decision status.")
assert_true(record["userDecision"]["status"] == "informational", "Stored finance memory should be informational.")
assert_true("YNAB_ACCESS_TOKEN" not in json.dumps(record), "Stored finance memory leaked a config secret key.")

context_payload = json.loads(
    run_mongoose(
        "memory",
        "context",
        "--agent",
        "Njord",
        "--capability",
        "finance-review",
        "--subject",
        "negative cash flow",
        "--json",
    ).stdout
)
assert_true(context_payload["fallback"]["used"] is False, "Prompt context did not find finance memory.")
assert_true(context_payload["records"][0]["source"]["recordId"] == record["recordId"], "Prompt context lost provenance.")
assert_true(context_payload["guardrails"]["canApproveActions"] is False, "Prompt context can approve actions.")
assert_true(context_payload["guardrails"]["canMutateState"] is False, "Prompt context can mutate state.")

print("Njord finance memory validation passed.")
