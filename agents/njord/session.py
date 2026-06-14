"""Interactive session loop for the Njord agent."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable, TextIO

from terminal import style_output, styled


AnswerCall = Callable[[str], tuple[bool, str]]
AnswerEventsCall = Callable[[str], Iterable["ResponseEvent"]]


@dataclass(frozen=True)
class ResponseEvent:
    kind: str
    text: str = ""


RESPONSE_EVENT_KINDS = {
    "text",
    "text_delta",
    "status",
    "warning",
    "error",
    "prompt",
    "approval_request",
    "done",
    "cancelled",
}
EXIT_COMMANDS = {"exit", "quit"}
PROMPT = "Njord> "


def help_text() -> str:
    return "\n".join(
        [
            "Ask Njord naturally about your budget, spending, cash flow, or financial risk.",
            "",
            "Examples",
            "- Review my finances.",
            "- Give me a financial brief.",
            "- Summarize my current budget.",
            "- Show my current-month spending.",
            "- Check my configuration status.",
            "",
            "Type exit or quit to leave the session.",
            "Budget-changing requests are read-only for now and cannot mutate YNAB from chat.",
        ]
    )


def response_events(ok: bool, output: str) -> list[ResponseEvent]:
    if ok:
        return [ResponseEvent("text", output), ResponseEvent("done")]
    return [ResponseEvent("error", output), ResponseEvent("done")]


def text_delta_events(output: str, *, chunk_size: int = 80) -> list[ResponseEvent]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if not output:
        return [ResponseEvent("done")]
    events = [
        ResponseEvent("text_delta", output[index : index + chunk_size])
        for index in range(0, len(output), chunk_size)
    ]
    events.append(ResponseEvent("done"))
    return events


def handle_input(
    raw_input: str,
    *,
    answer_request: AnswerCall,
) -> tuple[bool, list[ResponseEvent]]:
    request = raw_input.strip()
    if not request:
        return False, []

    normalized = request.lower()
    if normalized in EXIT_COMMANDS:
        return True, [ResponseEvent("done")]

    if normalized in {"help", "what can you do", "what can you do?"}:
        return False, [ResponseEvent("text", help_text()), ResponseEvent("done")]

    if request.startswith("/"):
        return False, [
            ResponseEvent(
                "warning",
                "Njord sessions are conversational now. Ask naturally, for example: Review my finances.",
            ),
            ResponseEvent("done"),
        ]

    return False, response_events(*answer_request(request))


def handle_builtin_input(raw_input: str) -> tuple[bool, list[ResponseEvent], bool]:
    request = raw_input.strip()
    if not request:
        return False, [], True

    normalized = request.lower()
    if normalized in EXIT_COMMANDS:
        return True, [ResponseEvent("done")], True

    if normalized in {"help", "what can you do", "what can you do?"}:
        return False, [ResponseEvent("text", help_text()), ResponseEvent("done")], True

    if request.startswith("/"):
        return False, [
            ResponseEvent(
                "warning",
                "Njord sessions are conversational now. Ask naturally, for example: Review my finances.",
            ),
            ResponseEvent("done"),
        ], True

    return False, [], False


def render_event(event: ResponseEvent, *, color_enabled: bool, output_stream: TextIO) -> None:
    if event.kind not in RESPONSE_EVENT_KINDS:
        raise ValueError(f"Unknown response event kind: {event.kind}")

    if event.kind in {"done", "cancelled"} or not event.text:
        return

    if event.kind == "text_delta":
        output_stream.write(style_output(event.text, color_enabled))
        output_stream.flush()
        return

    if event.kind == "prompt":
        rendered = styled(event.text, "selected", color_enabled)
        output_stream.write(rendered)
        output_stream.flush()
        return

    if event.kind == "status":
        rendered = styled(event.text, "muted", color_enabled)
    elif event.kind == "warning":
        rendered = styled(event.text, "warning", color_enabled)
    elif event.kind == "error":
        rendered = styled(style_output(event.text, color_enabled), "error", color_enabled)
    elif event.kind == "approval_request":
        rendered = styled(style_output(event.text, color_enabled), "warning", color_enabled)
    else:
        rendered = style_output(event.text, color_enabled)
    output_stream.write(f"{rendered}\n")
    output_stream.flush()


def run_repl(
    *,
    input_stream: TextIO,
    output_stream: TextIO,
    color_enabled: bool,
    answer_request: AnswerCall | None = None,
    answer_events: AnswerEventsCall | None = None,
) -> int:
    if answer_request is None and answer_events is None:
        raise ValueError("run_repl requires answer_request or answer_events.")

    while True:
        render_event(ResponseEvent("prompt", PROMPT), color_enabled=color_enabled, output_stream=output_stream)
        raw_input = input_stream.readline()
        if raw_input == "":
            output_stream.write("\n")
            return 0

        should_exit, events, handled = handle_builtin_input(raw_input)
        if not handled:
            request = raw_input.strip()
            if answer_events is not None:
                for event in answer_events(request):
                    render_event(event, color_enabled=color_enabled, output_stream=output_stream)
                continue
            assert answer_request is not None
            should_exit, events = handle_input(
                raw_input,
                answer_request=answer_request,
            )
        for event in events:
            render_event(event, color_enabled=color_enabled, output_stream=output_stream)
        if should_exit:
            return 0
