"""Natural-language request routing for Njord."""

from __future__ import annotations

import json
from dataclasses import dataclass

from llm_runtime import llm_invoke_command, parse_json_object, run_llm_invoke


@dataclass(frozen=True)
class Route:
    capability: str
    reason: str


CAPABILITIES = [
    {
        "name": "config-status",
        "description": "Show local YNAB configuration status without printing secrets.",
        "taskTypes": ["configuration", "setup", "credential-status"],
    },
    {
        "name": "finance-review",
        "description": "Run read-only finance review loops for cash flow forecasting and financial risk.",
        "taskTypes": ["finance-review", "cash-flow-forecast", "financial-risk", "review"],
    },
    {
        "name": "brief",
        "description": "Produce a weekly-style financial brief with observations, review items, and next actions.",
        "taskTypes": ["brief", "financial-brief", "weekly-brief"],
    },
    {
        "name": "ynab-spending-review",
        "description": "Review income, outflows, net cash flow, categories, and transactions for a period.",
        "taskTypes": ["spending-review", "cash-flow", "transactions"],
    },
    {
        "name": "ynab-budget-summary",
        "description": "Summarize the current YNAB budget state and review flags.",
        "taskTypes": ["budget-summary", "finance", "budget", "ynab"],
    },
    {
        "name": "hello-world",
        "description": "Verify the local agent runtime and optional YNAB connection path.",
        "taskTypes": ["diagnostic", "connection-test", "greeting"],
    },
]


def build_selection_prompt(request: str) -> str:
    return "\n".join(
        [
            "Njord needs to select one installed capability for the user request.",
            "Use only the availableCapabilities list. Do not invent an installed capability.",
            "Return only JSON with this shape:",
            '{"capability":"capability-name","reason":"short reason","confidence":0.0}',
            "",
            "Selection input:",
            json.dumps(
                {
                    "request": request,
                    "availableCapabilities": CAPABILITIES,
                },
                indent=2,
                sort_keys=True,
            ),
        ]
    )


def llm_route_request(request: str) -> Route | None:
    command = llm_invoke_command()
    if not command:
        return None
    invoked, output, _diagnostic = run_llm_invoke(
        command,
        prompt=build_selection_prompt(request),
        system_prompt=(
            "You select Njord capabilities. Return strict JSON only and choose only an available capability."
        ),
    )
    if not invoked or not output:
        return None

    outer_payload = parse_json_object(output)
    if outer_payload is None:
        return None
    response = outer_payload.get("response", {}) if isinstance(outer_payload.get("response", {}), dict) else {}
    content = str(response.get("content", "")).strip()
    decision = parse_json_object(content)
    if decision is None:
        return None

    capability = str(decision.get("capability", "")).strip()
    known = {item["name"] for item in CAPABILITIES}
    if capability not in known:
        return None
    reason = str(decision.get("reason", "")).strip() or "Selected by the configured LLM."
    return Route(capability=capability, reason=reason)


def route_request(request: str) -> Route:
    llm_route = llm_route_request(request)
    if llm_route is not None:
        return llm_route

    normalized = request.lower()

    finance_review_terms = (
        "finance review",
        "financial review",
        "review my finances",
        "review my money",
        "risk score",
        "financial risk",
        "cash flow forecast",
        "cashflow forecast",
    )
    config_terms = (
        "config",
        "configuration",
        "credential",
        "credentials",
        "setup",
    )
    brief_terms = (
        "brief",
        "briefing",
        "weekly",
        "cfo-style",
        "cfo style",
        "financial brief",
    )
    budget_terms = (
        "budget",
        "financial",
        "finances",
        "money",
        "ynab",
        "latest",
        "summary",
        "cash",
        "account",
        "attention",
        "review",
        "flag",
        "flags",
    )
    spending_terms = (
        "spending",
        "spend",
        "spent",
        "transaction",
        "transactions",
        "cash flow",
        "cashflow",
        "outflow",
        "outflows",
        "income",
        "current month",
        "this month",
        "previous month",
        "last month",
        "month-to-date",
    )
    greeting_terms = ("hello", "hi", "hey", "test", "connection")

    if any(term in normalized for term in config_terms) and "status" in normalized:
        return Route(
            capability="config-status",
            reason="The request asks for local YNAB configuration status.",
        )

    if any(term in normalized for term in finance_review_terms):
        return Route(
            capability="finance-review",
            reason="The request asks for the interaction-first finance review loop.",
        )

    if any(term in normalized for term in brief_terms):
        return Route(
            capability="brief",
            reason="The request asks for a financial brief.",
        )

    if any(term in normalized for term in spending_terms):
        return Route(
            capability="ynab-spending-review",
            reason="The request asks about spending, transactions, or cash flow.",
        )

    if any(term in normalized for term in budget_terms):
        return Route(
            capability="ynab-budget-summary",
            reason="The request asks about budget or financial information.",
        )

    if any(term in normalized for term in greeting_terms):
        return Route(
            capability="hello-world",
            reason="The request looks like a greeting or connection test.",
        )

    return Route(
        capability="ynab-budget-summary",
        reason="Defaulting to the financial summary capability for Njord.",
    )


