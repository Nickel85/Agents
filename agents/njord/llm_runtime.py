"""Mongoose-managed LLM narration helpers for Njord."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from decision_contract import DecisionValidationResult, validate_llm_decision
from fact_packet import FinanceFactPacket


MAX_CONTEXT_CHARS = 5000
DEFAULT_LLM_TIMEOUT_SECONDS = 45.0


@dataclass(frozen=True)
class LlmNarration:
    ok: bool
    text: str = ""
    profile: str = ""
    diagnostic: str = ""


@dataclass(frozen=True)
class LlmDecisionResult:
    ok: bool
    decision: dict | None = None
    validation: DecisionValidationResult | None = None
    profile: str = ""
    diagnostic: str = ""


def _runtime_context() -> dict:
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


def _invoke_command_from_context() -> list[str]:
    context = _runtime_context()
    llm = context.get("providers", {}).get("llm", {}) if isinstance(context.get("providers", {}), dict) else {}
    command = llm.get("invokeCommand", []) if isinstance(llm, dict) else []
    if isinstance(command, list) and all(isinstance(item, str) and item for item in command):
        return command
    return []


def _fallback_invoke_command() -> list[str]:
    explicit = os.environ.get("MONGOOSE_LLM_INVOKE", "").strip()
    if explicit:
        return shlex.split(explicit)
    return []


def llm_invoke_command() -> list[str]:
    return _invoke_command_from_context() or _fallback_invoke_command()


def llm_timeout_seconds() -> float:
    raw_timeout = os.environ.get("NJORD_LLM_TIMEOUT_SECONDS", "").strip()
    if not raw_timeout:
        return DEFAULT_LLM_TIMEOUT_SECONDS
    try:
        return max(float(raw_timeout), 0.1)
    except ValueError:
        return DEFAULT_LLM_TIMEOUT_SECONDS


def run_llm_invoke(command: list[str], *, prompt: str, system_prompt: str) -> tuple[bool, str, str]:
    timeout = llm_timeout_seconds()
    try:
        completed = subprocess.run(
            [*command, "--system", system_prompt],
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return False, "", f"Mongoose LLM invocation timed out after {timeout:g} seconds."
    except OSError as exc:
        return False, "", f"Mongoose LLM invocation could not start: {exc}"
    except UnicodeError as exc:
        return False, "", f"Mongoose LLM invocation failed while encoding text: {exc}"
    return True, completed.stdout.strip(), completed.stderr.strip()


def redact_for_prompt(text: str) -> str:
    redacted_lines: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in ("access token", "api key", "authorization", "secret", "password")):
            redacted_lines.append("[redacted secret-bearing line]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)[:MAX_CONTEXT_CHARS]


def build_narration_prompt(*, request: str, capability: str, deterministic_output: str) -> str:
    context = redact_for_prompt(deterministic_output)
    return "\n".join(
        [
            "You are Njord, a read-only budgeting assistant.",
            "Explain the deterministic finance facts below in concise, practical language.",
            "Do not invent balances, transactions, or budget changes.",
            "Do not recommend or claim that any YNAB write has happened.",
            "",
            f"User request: {request}",
            f"Deterministic capability: {capability}",
            "",
            "Deterministic output:",
            context,
        ]
    )


def build_chat_prompt(*, request: str, capability: str, deterministic_output: str) -> str:
    context = redact_for_prompt(deterministic_output)
    return "\n".join(
        [
            "You are Njord, an interactive personal-finance assistant.",
            "Answer like a conversational assistant, not a command-line report.",
            "Use the YNAB-backed capability output and finance metrics below as your source of truth.",
            "Lead with the answer the user probably wants, then cite the most relevant metrics.",
            "Keep it concise, practical, and specific.",
            "If data is missing or a connection failed, say what is missing and what the user should do next.",
            "Do not invent balances, transactions, categories, income, outflows, or budget changes.",
            "Do not claim that any YNAB write has happened.",
            "Budget-changing requests can only result in read-only analysis or a future draft plan.",
            "",
            f"User message: {request}",
            f"Selected capability: {capability}",
            "",
            "Capability output and metrics:",
            context,
        ]
    )


def build_decision_prompt(*, request: str, fact_packet: FinanceFactPacket) -> str:
    return "\n".join(
        [
            "You are Njord, a read-only budgeting assistant.",
            "Use only the deterministic fact packet below.",
            "Return only a JSON object with these exact fields:",
            "- recommendation: string",
            "- rationale: string",
            "- confidence: number from 0.0 to 1.0",
            "- assumptions: array of strings",
            "- risks: array of strings",
            "- requires_user_approval: boolean",
            "",
            "Rules:",
            "- Do not invent balances, transactions, or budget changes.",
            "- Do not calculate balances; use provided facts only.",
            "- Do not claim any YNAB write happened.",
            "- Do not approve cash floor violations.",
            "- Budget-changing recommendations must require user approval.",
            "",
            f"User request: {request}",
            f"Capability: {fact_packet.capability}",
            "",
            "Fact packet:",
            fact_packet.to_prompt_context(),
        ]
    )


def parse_json_object(text: str) -> dict | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def narrate_finance_response(*, request: str, capability: str, deterministic_output: str) -> LlmNarration:
    command = llm_invoke_command()
    if not command:
        return LlmNarration(False, diagnostic="No Mongoose LLM invocation command is available.")

    prompt = build_narration_prompt(
        request=request,
        capability=capability,
        deterministic_output=deterministic_output,
    )
    system_prompt = (
        "You narrate read-only finance analysis from deterministic facts. "
        "Keep generated text separate from facts and never propose unapproved writes."
    )
    invoked, output, diagnostic_output = run_llm_invoke(command, prompt=prompt, system_prompt=system_prompt)
    if not invoked:
        return LlmNarration(False, diagnostic=diagnostic_output)
    if not output:
        diagnostic = diagnostic_output or "Mongoose LLM invocation returned no output."
        return LlmNarration(False, diagnostic=diagnostic)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return LlmNarration(False, diagnostic="Mongoose LLM invocation returned invalid JSON.")

    if not isinstance(payload, dict) or not payload.get("ok"):
        message = str(payload.get("message", "") if isinstance(payload, dict) else "").strip()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict) and error.get("message"):
            message = str(error.get("message"))
        return LlmNarration(False, diagnostic=message or "Mongoose LLM invocation failed.")

    response = payload.get("response", {}) if isinstance(payload.get("response", {}), dict) else {}
    text = str(response.get("content", "")).strip()
    if not text:
        return LlmNarration(False, diagnostic="Mongoose LLM invocation returned an empty response.")
    return LlmNarration(True, text=text, profile=str(payload.get("profile", "")))


def synthesize_chat_response(*, request: str, capability: str, deterministic_output: str) -> LlmNarration:
    command = llm_invoke_command()
    if not command:
        return LlmNarration(False, diagnostic="No Mongoose LLM invocation command is available.")

    prompt = build_chat_prompt(
        request=request,
        capability=capability,
        deterministic_output=deterministic_output,
    )
    system_prompt = (
        "You are an interactive read-only finance assistant. "
        "Use capability facts and metrics only; never invent data or claim writes."
    )
    invoked, output, diagnostic_output = run_llm_invoke(command, prompt=prompt, system_prompt=system_prompt)
    if not invoked:
        return LlmNarration(False, diagnostic=diagnostic_output)
    if not output:
        diagnostic = diagnostic_output or "Mongoose LLM invocation returned no output."
        return LlmNarration(False, diagnostic=diagnostic)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return LlmNarration(False, diagnostic="Mongoose LLM invocation returned invalid JSON.")

    if not isinstance(payload, dict) or not payload.get("ok"):
        message = str(payload.get("message", "") if isinstance(payload, dict) else "").strip()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict) and error.get("message"):
            message = str(error.get("message"))
        return LlmNarration(False, diagnostic=message or "Mongoose LLM invocation failed.")

    response = payload.get("response", {}) if isinstance(payload.get("response", {}), dict) else {}
    text = str(response.get("content", "")).strip()
    if not text:
        return LlmNarration(False, diagnostic="Mongoose LLM invocation returned an empty response.")
    return LlmNarration(True, text=text, profile=str(payload.get("profile", "")))


def invoke_finance_decision(*, request: str, fact_packet: FinanceFactPacket) -> LlmDecisionResult:
    command = llm_invoke_command()
    if not command:
        return LlmDecisionResult(False, diagnostic="No Mongoose LLM invocation command is available.")

    prompt = build_decision_prompt(request=request, fact_packet=fact_packet)
    system_prompt = (
        "You produce strict JSON finance decisions from validated deterministic facts. "
        "Return only JSON and never claim that state changed."
    )
    invoked, output, diagnostic_output = run_llm_invoke(command, prompt=prompt, system_prompt=system_prompt)
    if not invoked:
        return LlmDecisionResult(False, diagnostic=diagnostic_output)
    if not output:
        diagnostic = diagnostic_output or "Mongoose LLM invocation returned no output."
        return LlmDecisionResult(False, diagnostic=diagnostic)
    outer_payload = parse_json_object(output)
    if outer_payload is None:
        return LlmDecisionResult(False, diagnostic="Mongoose LLM invocation returned invalid JSON.")
    if not outer_payload.get("ok"):
        message = str(outer_payload.get("message", "")).strip()
        error = outer_payload.get("error", {}) if isinstance(outer_payload.get("error", {}), dict) else {}
        if error.get("message"):
            message = str(error.get("message"))
        return LlmDecisionResult(False, diagnostic=message or "Mongoose LLM invocation failed.")

    response = outer_payload.get("response", {}) if isinstance(outer_payload.get("response", {}), dict) else {}
    content = str(response.get("content", "")).strip()
    decision = parse_json_object(content)
    if decision is None:
        return LlmDecisionResult(
            False,
            profile=str(outer_payload.get("profile", "")),
            diagnostic="LLM response did not contain a structured finance decision JSON object.",
        )
    validation = validate_llm_decision(decision, fact_packet)
    return LlmDecisionResult(
        validation.ok,
        decision=decision,
        validation=validation,
        profile=str(outer_payload.get("profile", "")),
        diagnostic="" if validation.ok else validation.summary(),
    )
