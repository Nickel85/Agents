"""Command runner for the Njord agent."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


AGENT_ROOT = Path(__file__).resolve().parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from config import ConfigFileError, config_status_lines, current_config_snapshot
from finance_review import load_finance_review
from llm_runtime import narrate_finance_response, synthesize_chat_response
from router import route_request
from session import ResponseEvent, run_repl
from terminal import should_use_color, style_output
from ynab_api import YnabClient, choose_plan


COMMAND_NAMES = {
    "hello-world",
    "ynab-budget-summary",
    "brief",
    "ynab-spending-review",
    "finance-review",
    "config",
    "ask",
}


def configure_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_module(module_name: str, module_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module at {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_hello_world(name: str) -> str:
    module_path = AGENT_ROOT / "capabilities" / "hello-world" / "hello_world.py"
    module = load_module("njord_hello_world", module_path)
    return module.run(name)


def run_hello_world_with_status(name: str) -> tuple[bool, str]:
    module_path = AGENT_ROOT / "capabilities" / "hello-world" / "hello_world.py"
    module = load_module("njord_hello_world", module_path)
    return module.run_with_status(name)


def run_ynab_budget_summary() -> tuple[bool, str]:
    module_path = (
        AGENT_ROOT
        / "capabilities"
        / "ynab-budget-summary"
        / "ynab_budget_summary.py"
    )
    module = load_module("njord_ynab_budget_summary", module_path)
    return module.load_latest_summary()


def run_ynab_spending_review(
    period: str = "current-month",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[bool, str]:
    module_path = (
        AGENT_ROOT
        / "capabilities"
        / "ynab-spending-review"
        / "ynab_spending_review.py"
    )
    module = load_module("njord_ynab_spending_review", module_path)
    try:
        start = module.parse_cli_date(start_date, "--from")
        end = module.parse_cli_date(end_date, "--to")
    except ValueError as exc:
        return False, str(exc)
    return module.load_spending_review(period, start=start, end=end)


def run_brief() -> tuple[bool, str]:
    module_path = AGENT_ROOT / "capabilities" / "brief" / "brief.py"
    module = load_module("njord_manual_brief", module_path)
    return module.load_manual_brief()


def run_finance_review() -> tuple[bool, str]:
    return load_finance_review()


def run_finance_review_for_request(request: str) -> tuple[bool, str]:
    return load_finance_review(request=request)


def run_config_status() -> tuple[bool, str]:
    try:
        snapshot = current_config_snapshot()
    except ConfigFileError as exc:
        return (
            False,
            "\n".join(
                [
                    "Njord configuration status",
                    str(exc),
                    "",
                    "Next steps",
                    "- Fix the JSON file or remove it and use the repository .env file for development.",
                    "- Run: Njord config status",
                ]
            ),
        )

    token = snapshot["token"]
    budget_id = snapshot["budget_id"]
    extra_lines: list[str] = ["", "Validation"]

    if not token:
        extra_lines.extend(
            [
                "- YNAB access token is missing.",
                "- Add YNAB_ACCESS_TOKEN to the preferred config file or repo .env file.",
            ]
        )
        return (
            False,
            "\n".join(
                config_status_lines(
                    token=token,
                    budget_id=budget_id,
                    token_source=snapshot["token_source"],
                    budget_source=snapshot["budget_source"],
                    config_path=snapshot["config_path"],
                    extra_lines=extra_lines,
                )
            ),
        )

    client = YnabClient(token)
    plans_result = client.list_plans()
    if not plans_result.ok:
        extra_lines.append(f"- Token validation failed: {plans_result.message}")
        return (
            False,
            "\n".join(
                config_status_lines(
                    token=token,
                    budget_id=budget_id,
                    token_source=snapshot["token_source"],
                    budget_source=snapshot["budget_source"],
                    config_path=snapshot["config_path"],
                    extra_lines=extra_lines,
                )
            ),
        )

    if not budget_id:
        extra_lines.extend(
            [
                f"- YNAB token is valid. Found {len(plans_result.items)} plan(s).",
                "- YNAB budget/plan ID is missing.",
                "- Add YNAB_BUDGET_ID to select the plan Njord should summarize.",
            ]
        )
        return (
            False,
            "\n".join(
                config_status_lines(
                    token=token,
                    budget_id=budget_id,
                    token_source=snapshot["token_source"],
                    budget_source=snapshot["budget_source"],
                    config_path=snapshot["config_path"],
                    extra_lines=extra_lines,
                )
            ),
        )

    selected_plan = choose_plan(plans_result.items, budget_id)
    if selected_plan is None:
        extra_lines.extend(
            [
                f"- YNAB token is valid. Found {len(plans_result.items)} plan(s).",
                "- Configured YNAB_BUDGET_ID did not match any returned plan.",
            ]
        )
        return (
            False,
            "\n".join(
                config_status_lines(
                    token=token,
                    budget_id=budget_id,
                    token_source=snapshot["token_source"],
                    budget_source=snapshot["budget_source"],
                    config_path=snapshot["config_path"],
                    extra_lines=extra_lines,
                )
            ),
        )

    extra_lines.extend(
        [
            f"- YNAB token is valid. Found {len(plans_result.items)} plan(s).",
            "- Configured budget/plan ID matches an available YNAB plan.",
        ]
    )
    return (
        True,
        "\n".join(
            config_status_lines(
                token=token,
                budget_id=budget_id,
                token_source=snapshot["token_source"],
                budget_source=snapshot["budget_source"],
                config_path=snapshot["config_path"],
                extra_lines=extra_lines,
            )
        ),
    )


def answer_request(request: str) -> tuple[bool, str]:
    route = route_request(request)
    ok, output = run_routed_capability(route.capability, request)
    if not ok and output.startswith("I do not know"):
        return False, output

    response = f"Request: {request}\nCapability: {route.capability}\nReason: {route.reason}\n\n{output}"
    if ok and route.capability in {"brief", "ynab-spending-review", "ynab-budget-summary", "finance-review"}:
        narration = narrate_finance_response(
            request=request,
            capability=route.capability,
            deterministic_output=output,
        )
        if narration.ok:
            profile = f" ({narration.profile})" if narration.profile else ""
            response = f"{response}\n\nLLM narration{profile}\n{narration.text}"
        elif narration.diagnostic:
            response = f"{response}\n\nLLM narration unavailable\n{narration.diagnostic}"

    return ok, response


def run_routed_capability(capability: str, request: str) -> tuple[bool, str]:
    if capability == "hello-world":
        return run_hello_world_with_status("Njord")
    if capability == "brief":
        return run_brief()
    if capability == "ynab-spending-review":
        return run_ynab_spending_review()
    if capability == "ynab-budget-summary":
        return run_ynab_budget_summary()
    if capability == "finance-review":
        return run_finance_review_for_request(request)
    if capability == "config-status":
        return run_config_status()
    return False, f"I do not know how to run capability: {capability}"


def answer_chat_request(request: str) -> tuple[bool, str]:
    route = route_request(request)
    ok, output = run_routed_capability(route.capability, request)
    if not ok and output.startswith("I do not know"):
        return False, output

    if route.capability == "config-status":
        return ok, chat_fallback_response(
            request=request,
            capability=route.capability,
            reason=route.reason,
            deterministic_output=output,
            diagnostic="Configuration status is deterministic and does not need LLM synthesis.",
        )

    if route.capability == "hello-world":
        return ok, output

    chat = synthesize_chat_response(
        request=request,
        capability=route.capability,
        deterministic_output=output,
    )
    if chat.ok:
        profile = f" ({chat.profile})" if chat.profile else ""
        return ok, f"{chat.text}\n\nLLM profile{profile}"

    return ok, chat_fallback_response(
        request=request,
        capability=route.capability,
        reason=route.reason,
        deterministic_output=output,
        diagnostic=chat.diagnostic,
    )


def answer_chat_events(request: str):
    yield ResponseEvent("status", "Reading your request...")
    route = route_request(request)
    yield ResponseEvent("status", f"Selected capability: {route.capability}")
    yield ResponseEvent("status", f"Routing reason: {route.reason}")
    yield ResponseEvent("status", "Running deterministic finance checks...")
    ok, output = run_routed_capability(route.capability, request)

    if not ok and output.startswith("I do not know"):
        yield ResponseEvent("error", output)
        yield ResponseEvent("done")
        return

    if route.capability == "config-status":
        yield ResponseEvent("status", "Rendering configuration status without LLM synthesis.")
        yield ResponseEvent(
            "text",
            chat_fallback_response(
                request=request,
                capability=route.capability,
                reason=route.reason,
                deterministic_output=output,
                diagnostic="Configuration status is deterministic and does not need LLM synthesis.",
            ),
        )
        yield ResponseEvent("done")
        return

    if route.capability == "hello-world":
        yield ResponseEvent("status", "Rendering deterministic response.")
        yield ResponseEvent("text" if ok else "error", output)
        yield ResponseEvent("done")
        return

    yield ResponseEvent("status", "Preparing safe read-only facts for the LLM...")
    yield ResponseEvent("status", "Asking the configured LLM to synthesize a conversational response...")
    chat = synthesize_chat_response(
        request=request,
        capability=route.capability,
        deterministic_output=output,
    )
    if chat.ok:
        profile = f" ({chat.profile})" if chat.profile else ""
        yield ResponseEvent("status", f"LLM response received{profile}.")
        yield ResponseEvent("text", f"{chat.text}\n\nLLM profile{profile}")
        yield ResponseEvent("done")
        return

    if chat.diagnostic:
        yield ResponseEvent("warning", f"LLM synthesis unavailable: {chat.diagnostic}")
    yield ResponseEvent("status", "Falling back to deterministic finance output.")
    yield ResponseEvent(
        "text" if ok else "error",
        chat_fallback_response(
            request=request,
            capability=route.capability,
            reason=route.reason,
            deterministic_output=output,
            diagnostic=chat.diagnostic,
        ),
    )
    yield ResponseEvent("done")


def chat_fallback_response(
    *,
    request: str,
    capability: str,
    reason: str,
    deterministic_output: str,
    diagnostic: str,
) -> str:
    lines = [
        "I pulled the relevant finance capability, but I could not synthesize a live LLM response.",
        f"Reason: {diagnostic}",
        "",
        f"Capability used: {capability}",
        f"Why: {reason}",
        "",
        "Finance metrics and source output:",
        deterministic_output,
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Njord agent capabilities."
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color in human-readable output.",
    )
    subparsers = parser.add_subparsers(
        dest="capability",
        required=False,
        help="Capability to run.",
    )

    hello_world = subparsers.add_parser(
        "hello-world",
        help="Run the hello world capability.",
    )
    hello_world.add_argument(
        "--name",
        default="there",
        help="Optional name or context to include in the greeting.",
    )

    subparsers.add_parser(
        "ynab-budget-summary",
        help="Summarize the latest available YNAB budget state.",
    )

    brief = subparsers.add_parser(
        "brief",
        help="Produce a manual weekly-style financial brief.",
    )
    brief.add_argument(
        "request",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )

    spending_review = subparsers.add_parser(
        "ynab-spending-review",
        help="Review YNAB spending for a month or explicit date range.",
    )
    spending_review.add_argument(
        "--period",
        choices=("current-month", "previous-month"),
        default="current-month",
        help="Named period to review when --from and --to are not provided.",
    )

    subparsers.add_parser(
        "finance-review",
        help="Run the read-only interaction-first finance review loops.",
    )
    spending_review.add_argument(
        "--from",
        dest="start_date",
        help="Start date for a custom review range, in YYYY-MM-DD format.",
    )
    spending_review.add_argument(
        "--to",
        dest="end_date",
        help="End date for a custom review range, in YYYY-MM-DD format.",
    )
    spending_review.add_argument(
        "request",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )

    config = subparsers.add_parser(
        "config",
        help="Inspect Njord local configuration.",
    )
    config_subparsers = config.add_subparsers(
        dest="config_command",
        required=True,
        help="Configuration command to run.",
    )
    config_subparsers.add_parser(
        "status",
        help="Show YNAB configuration status without printing secrets.",
    )

    ask = subparsers.add_parser(
        "ask",
        help="Route a natural-language request to the right capability.",
    )
    ask.add_argument(
        "request",
        nargs=argparse.REMAINDER,
        help="Natural-language request for the Njord agent.",
    )

    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv

    command_index = 0
    while command_index < len(argv) and argv[command_index] == "--no-color":
        command_index += 1

    if command_index >= len(argv):
        return argv

    if argv[command_index] not in COMMAND_NAMES and not argv[command_index].startswith("-"):
        return [*argv[:command_index], "ask", *argv[command_index:]]

    return argv


def main() -> None:
    configure_output()
    parser = build_parser()
    args = parser.parse_args(normalize_argv(sys.argv[1:]))
    color_enabled = should_use_color(args.no_color)

    if args.capability is None:
        raise SystemExit(
            run_repl(
                input_stream=sys.stdin,
                output_stream=sys.stdout,
                color_enabled=color_enabled,
                answer_events=answer_chat_events,
            )
        )

    if args.capability == "hello-world":
        ok, output = run_hello_world_with_status(args.name)
        print(style_output(output, color_enabled))
        if not ok:
            sys.exit(1)
        return

    if args.capability == "ynab-budget-summary":
        ok, output = run_ynab_budget_summary()
        print(style_output(output, color_enabled))
        if not ok:
            sys.exit(1)
        return

    if args.capability == "brief":
        ok, output = run_brief()
        print(style_output(output, color_enabled))
        if not ok:
            sys.exit(1)
        return

    if args.capability == "ynab-spending-review":
        ok, output = run_ynab_spending_review(
            args.period,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(style_output(output, color_enabled))
        if not ok:
            sys.exit(1)
        return

    if args.capability == "finance-review":
        ok, output = run_finance_review()
        print(style_output(output, color_enabled))
        if not ok:
            sys.exit(1)
        return

    if args.capability == "config":
        if args.config_command == "status":
            ok, output = run_config_status()
            print(style_output(output, color_enabled))
            if not ok:
                sys.exit(1)
            return

    if args.capability == "ask":
        request = " ".join(args.request).strip()
        if not request:
            parser.error("ask requires a natural-language request.")

        ok, output = answer_request(request)
        print(style_output(output, color_enabled))
        if not ok:
            sys.exit(1)
        return

    parser.error(f"Unknown capability: {args.capability}")


if __name__ == "__main__":
    main()

