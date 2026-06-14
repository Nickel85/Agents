"""Validate the Njord REPL session contract."""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NJORD_ROOT = REPO_ROOT / "agents" / "njord"
NJORD_AGENT = NJORD_ROOT / "agent.py"
MONGOOSE_CLI = REPO_ROOT / "mongoose" / "mongoose.py"
TEST_LOCAL_APP_DATA = REPO_ROOT / ".test-localappdata-mongoose"
sys.path.insert(0, str(NJORD_ROOT))

import agent as njord_agent  # noqa: E402
from session import ResponseEvent, handle_input, render_event, run_repl, text_delta_events  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def remove_tree(path: Path) -> None:
    def handle_error(function, failing_path, _exc_info):
        os.chmod(failing_path, stat.S_IWRITE)
        function(failing_path)

    if path.exists():
        shutil.rmtree(path, onerror=handle_error)


def ok_output(text: str):
    return lambda: (True, text)


def run_mongoose(*args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "LOCALAPPDATA": str(TEST_LOCAL_APP_DATA),
        **(extra_env or {}),
    }
    return subprocess.run(
        [sys.executable, str(MONGOOSE_CLI), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def run_session(script: str, answer=None) -> tuple[int, str, list[str]]:
    calls: list[str] = []

    def answer_request(request: str) -> tuple[bool, str]:
        calls.append(request)
        if answer is not None:
            return answer(request)
        return True, f"routed: {request}"

    output = io.StringIO()
    code = run_repl(
        input_stream=io.StringIO(script),
        output_stream=output,
        color_enabled=False,
        answer_request=answer_request,
    )
    return code, output.getvalue(), calls


def run_event_session(script: str, answer_events) -> tuple[int, str]:
    output = io.StringIO()
    code = run_repl(
        input_stream=io.StringIO(script),
        output_stream=output,
        color_enabled=False,
        answer_events=answer_events,
    )
    return code, output.getvalue()


for exit_command in ("exit", "quit"):
    exit_code, output, routed = run_session(f"{exit_command}\n")
    assert_true(exit_code == 0, f"{exit_command} did not exit cleanly.")
    assert_true("Njord> " in output, f"{exit_command} did not render the prompt.")
    assert_true(routed == [], f"{exit_command} was unexpectedly routed.")

exit_code, output, routed = run_session("help\nexit\n")
assert_true(exit_code == 0, "help session did not exit cleanly.")
for phrase in ("Review my finances", "Give me a financial brief", "Summarize my current budget", "exit or quit"):
    assert_true(phrase in output, f"{phrase} was missing from conversational help.")
assert_true(routed == [], "help was unexpectedly routed.")

exit_code, output, routed = run_session("/unknown\nexit\n")
assert_true(exit_code == 0, "Slash-prefixed input session did not exit cleanly.")
assert_true("Njord sessions are conversational now" in output, "Slash-prefixed input did not explain conversational use.")
assert_true(routed == [], "Slash-prefixed input was unexpectedly routed.")

exit_code, output, routed = run_session(
    "check my configuration status\ngive me a financial brief\nreview my finances\nsummarize my current budget\nshow my current-month spending\nexit\n"
)
assert_true(exit_code == 0, "Conversational finance session did not exit cleanly.")
assert_true(
    routed == [
        "check my configuration status",
        "give me a financial brief",
        "review my finances",
        "summarize my current budget",
        "show my current-month spending",
    ],
    "Conversational prompts were not routed in order.",
)

exit_code, output, routed = run_session("summarize my current budget\nexit\n")
assert_true(exit_code == 0, "Natural-language session did not exit cleanly.")
assert_true(routed == ["summarize my current budget"], "Natural-language prompt was not routed exactly once.")
assert_true("routed: summarize my current budget" in output, "Natural-language response was not rendered.")


def fixture_answer_events(request: str):
    yield ResponseEvent("status", f"Routing request: {request}")
    yield ResponseEvent("status", "Running deterministic finance checks...")
    yield ResponseEvent("status", "Asking the configured LLM to synthesize a conversational response...")
    yield ResponseEvent("text", "final answer")
    yield ResponseEvent("done")


exit_code, output = run_event_session("summarize my current budget\nexit\n", fixture_answer_events)
assert_true(exit_code == 0, "Event-driven session did not exit cleanly.")
assert_true(
    output.index("Routing request: summarize my current budget") < output.index("final answer"),
    "Event-driven session did not render progress before the final answer.",
)
for phrase in (
    "Running deterministic finance checks...",
    "Asking the configured LLM to synthesize a conversational response...",
):
    assert_true(phrase in output, f"{phrase} was missing from event-driven REPL output.")

should_exit, events = handle_input(
    "/missing",
    answer_request=lambda request: (_ for _ in ()).throw(AssertionError("unexpected route")),
)
assert_true(not should_exit, "Slash-prefixed input should not exit the session.")
assert_true(events[0].kind == "warning", "Slash-prefixed input should produce a warning event.")

delta_events = text_delta_events("abcdef", chunk_size=2)
assert_true([event.kind for event in delta_events] == ["text_delta", "text_delta", "text_delta", "done"], "Text delta events were not ordered.")
delta_output = io.StringIO()
for event in delta_events:
    render_event(event, color_enabled=False, output_stream=delta_output)
assert_true(delta_output.getvalue() == "abcdef", "Text delta renderer did not preserve streamed text.")
try:
    render_event(ResponseEvent("not-real", "x"), color_enabled=False, output_stream=io.StringIO())
    raise AssertionError("Unknown event kind did not fail.")
except ValueError:
    pass

process = subprocess.run(
    [sys.executable, str(NJORD_AGENT), "--no-color"],
    input="exit\n",
    text=True,
    capture_output=True,
    timeout=10,
)
assert_true(process.returncode == 0, f"Njord no-arg REPL failed: {process.stdout}{process.stderr}")
assert_true("Njord> " in process.stdout, "Njord no-arg REPL did not render the prompt.")

process = subprocess.run(
    [sys.executable, str(NJORD_AGENT), "--no-color", "this is a free-form request"],
    text=True,
    capture_output=True,
    timeout=10,
)
assert_true(process.returncode != 2, f"Free-form launcher-style request hit argparse: {process.stderr}")
assert_true("Request: this is a free-form request" in process.stdout, "Free-form request did not route through ask.")

remove_tree(TEST_LOCAL_APP_DATA)
fake_profile = run_mongoose("llm", "add", "fake-main", "--provider", "fake", "--model", "fake-chat", "--default")
assert_true(fake_profile.returncode == 0, f"fake LLM profile setup failed: {fake_profile.stdout}{fake_profile.stderr}")
invoke = f'"{sys.executable}" "{MONGOOSE_CLI}" llm invoke --json'
original_summary = njord_agent.run_ynab_budget_summary
original_finance_review = njord_agent.run_finance_review_for_request
original_localappdata = os.environ.get("LOCALAPPDATA")
original_invoke = os.environ.get("MONGOOSE_LLM_INVOKE")
try:
    os.environ["LOCALAPPDATA"] = str(TEST_LOCAL_APP_DATA)
    os.environ["MONGOOSE_LLM_INVOKE"] = invoke
    njord_agent.run_ynab_budget_summary = lambda: (True, "Budget facts\nAvailable to assign: $42.00")
    njord_agent.run_finance_review_for_request = lambda request: (True, "Njord finance review\nRisk score: 42")
    ok, narrated = njord_agent.answer_request("summarize my budget")
    assert_true(ok, "Njord finance answer did not succeed with fixture summary.")
    assert_true("LLM narration (fake-main)" in narrated, "Njord did not label fake-provider LLM narration.")
    assert_true("Fake LLM narration" in narrated, "Njord did not include fake-provider LLM response.")
    assert_true("Available to assign: $42.00" in narrated, "Njord dropped deterministic finance facts.")

    ok, review_answer = njord_agent.answer_request("review my finances")
    assert_true(ok, "Njord finance review answer did not succeed with fixture review.")
    assert_true("Capability: finance-review" in review_answer, "Finance review request did not route to finance-review.")
    assert_true("LLM narration (fake-main)" in review_answer, "Finance review answer did not use configured LLM narration.")

    ok, chat_answer = njord_agent.answer_chat_request("review my finances")
    assert_true(ok, "Njord chat finance review did not succeed with fixture review.")
    assert_true("Fake LLM narration" in chat_answer, "Chat finance review did not synthesize with configured LLM.")
    assert_true("LLM profile (fake-main)" in chat_answer, "Chat finance review did not label the configured LLM profile.")
    assert_true("Capability: finance-review" not in chat_answer, "Chat finance review exposed command-style capability metadata.")

    chat_events = list(njord_agent.answer_chat_events("review my finances"))
    event_text = "\n".join(event.text for event in chat_events)
    assert_true([event.kind for event in chat_events[:5]] == ["status", "status", "status", "status", "status"], "Chat events did not start with progress status.")
    assert_true("Selected capability: finance-review" in event_text, "Chat events did not show selected capability.")
    assert_true("Running deterministic finance checks..." in event_text, "Chat events did not show deterministic work.")
    assert_true("Asking the configured LLM" in event_text, "Chat events did not show LLM synthesis work.")
    assert_true("LLM response received (fake-main)." in event_text, "Chat events did not show LLM completion.")
    assert_true(chat_events[-1].kind == "done", "Chat events did not end with done.")

    output = io.StringIO()
    repl_code = run_repl(
        input_stream=io.StringIO("review my finances\nexit\n"),
        output_stream=output,
        color_enabled=False,
        answer_events=njord_agent.answer_chat_events,
    )
    assert_true(repl_code == 0, "LLM-backed conversational REPL session did not exit cleanly.")
    repl_output = output.getvalue()
    assert_true("Fake LLM narration" in repl_output, "REPL conversation did not use the configured LLM backend.")
    assert_true("LLM profile (fake-main)" in repl_output, "REPL conversation did not label the configured LLM profile.")
    assert_true("Capability: finance-review" not in repl_output, "REPL conversation exposed command-style capability metadata.")
    assert_true("Selected capability: finance-review" in repl_output, "REPL conversation did not show routing progress.")
    assert_true("Asking the configured LLM" in repl_output, "REPL conversation did not show LLM progress.")
finally:
    njord_agent.run_ynab_budget_summary = original_summary
    njord_agent.run_finance_review_for_request = original_finance_review
    if original_localappdata is None:
        os.environ.pop("LOCALAPPDATA", None)
    else:
        os.environ["LOCALAPPDATA"] = original_localappdata
    if original_invoke is None:
        os.environ.pop("MONGOOSE_LLM_INVOKE", None)
    else:
        os.environ["MONGOOSE_LLM_INVOKE"] = original_invoke

print("Njord REPL validation passed.")
