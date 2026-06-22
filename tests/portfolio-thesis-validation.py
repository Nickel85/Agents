"""Validate the Portfolio v0.9 memory-backed thesis capability."""

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
PORTFOLIO_AGENT = REPO_ROOT / "agents" / "portfolio" / "agent.py"
PORTFOLIO_MANIFEST = REPO_ROOT / "agents" / "portfolio" / "agent.json"
TEST_LOCAL_APP_DATA = REPO_ROOT / ".test-localappdata-portfolio-thesis"


def remove_tree(path: Path) -> None:
    def handle_error(function, failing_path, _exc_info):
        os.chmod(failing_path, stat.S_IWRITE)
        function(failing_path)

    if path.exists():
        shutil.rmtree(path, onerror=handle_error)


def run_command(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env={**os.environ, "LOCALAPPDATA": str(TEST_LOCAL_APP_DATA)},
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"{' '.join(command)} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result


def run_mongoose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command([sys.executable, str(MONGOOSE_CLI), *args], check=check)


def run_portfolio(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command([sys.executable, str(PORTFOLIO_AGENT), *args], check=check)


remove_tree(TEST_LOCAL_APP_DATA)
TEST_LOCAL_APP_DATA.mkdir(parents=True)
os.environ["LOCALAPPDATA"] = str(TEST_LOCAL_APP_DATA)

spec = importlib.util.spec_from_file_location("mongoose_cli_for_portfolio", MONGOOSE_CLI)
assert_true(spec is not None and spec.loader is not None, "Could not load mongoose.py.")
mongoose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mongoose)

manifest = json.loads(PORTFOLIO_MANIFEST.read_text(encoding="utf-8"))
mongoose.validate_manifest(manifest, PORTFOLIO_MANIFEST)
context = mongoose.runtime_context(
    mode="run",
    agent={
        "commandName": "Portfolio",
        "displayName": "Portfolio",
        "version": "0.1.0",
        "sourcePath": str(PORTFOLIO_AGENT.parent),
        "manifestPath": str(PORTFOLIO_MANIFEST),
    },
    capability=manifest["capabilities"][0],
    agent_args=["thesis"],
)
context_path = mongoose.write_runtime_context(context)
os.environ["MONGOOSE_RUNTIME_CONTEXT"] = str(context_path)

create = run_portfolio(
    "create-thesis",
    "ai-infra",
    "--claim",
    "AI infrastructure demand will compound over the next decade.",
    "--horizon",
    "10 years",
    "--assumption",
    "Data center capex remains durable.",
    "--invalidation",
    "Hyperscaler capex contracts for two consecutive years.",
    "--sector",
    "Semiconductors",
    "--asset",
    "NVDA",
    "--confidence",
    "0.72",
)
assert_true("Created thesis: ai-infra" in create.stdout, "Portfolio did not create the thesis.")
assert_true("Memory record:" in create.stdout, "Portfolio did not report a memory record.")

run_portfolio(
    "add-position",
    "ai-infra",
    "NVDA",
    "--relationship",
    "aligned",
    "--intended-allocation",
    "12",
    "--actual-exposure",
    "14",
    "--rationale",
    "Compute platform exposure.",
)
run_portfolio(
    "add-position",
    "ai-infra",
    "XLK",
    "--relationship",
    "hedge",
    "--intended-allocation",
    "5",
    "--actual-exposure",
    "4",
    "--rationale",
    "Broader technology exposure.",
)
run_portfolio(
    "add-evidence",
    "ai-infra",
    "--source",
    "Company transcript",
    "--source-date",
    "2026-06-01",
    "--stance",
    "supports",
    "--summary",
    "Management raised data-center demand outlook.",
    "--confidence-impact",
    "0.04",
    "--asset",
    "NVDA",
)

shown = json.loads(run_portfolio("show-thesis", "ai-infra", "--json").stdout)
assert_true(shown["id"] == "ai-infra", "Stored thesis id changed.")
assert_true(len(shown["positions"]) == 2, "Position association was not stored.")
assert_true(shown["positions"][0]["relationship"] == "aligned", "Position relationship was not stored.")
assert_true(len(shown["evidence"]) == 1, "Evidence item was not stored.")
assert_true(shown["evidence"][0]["stance"] == "supports", "Evidence stance was not stored.")
assert_true(abs(shown["confidence"] - 0.76) < 0.0001, "Confidence impact was not applied.")

review = run_portfolio("review-thesis", "ai-infra")
assert_true("Portfolio thesis review: ai-infra" in review.stdout, "Review did not render heading.")
assert_true("Research-only output; not financial advice or trading execution." in review.stdout, "Review lost research-only guardrail.")
assert_true("Intended allocation: 17.00%" in review.stdout, "Review did not summarize intended allocation.")
assert_true("Actual exposure: 18.00%" in review.stdout, "Review did not summarize actual exposure.")
assert_true("Drift: 1.00%" in review.stdout, "Review did not calculate thesis drift.")
assert_true("What would change my mind" in review.stdout, "Review did not surface invalidation checks.")
assert_true("Any portfolio action requires separate user approval" in review.stdout, "Review lost approval boundary.")

records = json.loads(
    run_mongoose(
        "memory",
        "list",
        "--agent",
        "Portfolio",
        "--capability",
        "thesis",
        "--record-type",
        "loop_aware_memory_record",
        "--subject",
        "ai-infra",
        "--json",
    ).stdout
)
assert_true(len(records) >= 4, "Portfolio did not append thesis memory records.")
assert_true(all(record["agentId"] == "Portfolio" for record in records), "Portfolio memory lost agent identity.")
assert_true(all(record["capabilityId"] == "thesis" for record in records), "Portfolio memory lost capability identity.")
assert_true(any(record["outcome"]["status"] == "reviewed" for record in records), "Review memory record was not stored.")
records_text = json.dumps(records).lower()
for forbidden_claim in ("trade executed", "order placed", "brokerage execution completed"):
    assert_true(forbidden_claim not in records_text, f"Portfolio memory implied execution: {forbidden_claim}.")

context_payload = json.loads(
    run_mongoose(
        "memory",
        "context",
        "--agent",
        "Portfolio",
        "--capability",
        "thesis",
        "--subject",
        "ai-infra",
        "--json",
    ).stdout
)
assert_true(context_payload["fallback"]["used"] is False, "Portfolio prompt context did not find thesis memory.")
assert_true(context_payload["records"], "Portfolio prompt context returned no records.")
assert_true(context_payload["guardrails"]["canApproveActions"] is False, "Portfolio context can approve actions.")
assert_true(context_payload["guardrails"]["canMutateState"] is False, "Portfolio context can mutate state.")

archive = run_portfolio("archive-thesis", "ai-infra")
assert_true("Archived thesis: ai-infra" in archive.stdout, "Portfolio did not archive thesis.")
active_list = run_portfolio("list-theses", "--status", "active")
assert_true("No portfolio theses found." in active_list.stdout, "Archived thesis still appeared as active.")
archived_list = run_portfolio("list-theses", "--status", "archived")
assert_true("ai-infra [archived" in archived_list.stdout, "Archived thesis was not listed.")

print("Portfolio thesis validation passed.")
