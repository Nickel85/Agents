"""Validate Njord's Mongoose-managed LLM subprocess boundary."""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NJORD_ROOT = REPO_ROOT / "agents" / "njord"
FIXTURE_PROVIDER = REPO_ROOT / "tests" / "fixtures" / "llm-provider-fixture.py"
sys.path.insert(0, str(NJORD_ROOT))

from llm_runtime import synthesize_chat_response  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


original_invoke = os.environ.get("MONGOOSE_LLM_INVOKE")
original_timeout = os.environ.get("NJORD_LLM_TIMEOUT_SECONDS")
try:
    os.environ["MONGOOSE_LLM_INVOKE"] = f'"{sys.executable}" "{FIXTURE_PROVIDER}" --mode echo'
    os.environ.pop("NJORD_LLM_TIMEOUT_SECONDS", None)
    emoji_result = synthesize_chat_response(
        request="What should I do with my budget today?",
        capability="ynab-budget-summary",
        deterministic_output="Category: 🐶 Dogs\nAvailable to assign: $42.00",
    )
    assert_true(emoji_result.ok, f"Emoji prompt did not invoke cleanly: {emoji_result.diagnostic}")
    assert_true(emoji_result.text == "saw emoji", "Emoji-containing deterministic output was not sent to the LLM fixture.")
    assert_true(emoji_result.profile == "fixture", "Fixture profile was not preserved.")

    os.environ["MONGOOSE_LLM_INVOKE"] = f'"{sys.executable}" "{FIXTURE_PROVIDER}" --mode sleep'
    os.environ["NJORD_LLM_TIMEOUT_SECONDS"] = "0.1"
    timeout_result = synthesize_chat_response(
        request="What should I do with my budget today?",
        capability="ynab-budget-summary",
        deterministic_output="Budget facts are available.",
    )
    assert_true(not timeout_result.ok, "Slow LLM fixture unexpectedly succeeded.")
    assert_true("timed out" in timeout_result.diagnostic, "Slow LLM fixture did not return a timeout diagnostic.")
finally:
    if original_invoke is None:
        os.environ.pop("MONGOOSE_LLM_INVOKE", None)
    else:
        os.environ["MONGOOSE_LLM_INVOKE"] = original_invoke
    if original_timeout is None:
        os.environ.pop("NJORD_LLM_TIMEOUT_SECONDS", None)
    else:
        os.environ["NJORD_LLM_TIMEOUT_SECONDS"] = original_timeout

print("Njord LLM runtime validation passed.")
