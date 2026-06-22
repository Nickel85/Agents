"""Portfolio thesis research agent."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AGENT_ROOT = Path(__file__).resolve().parent
FALLBACK_STATE = AGENT_ROOT / ".local-state"
THESIS_FILE = "theses.json"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip(".-")
    return slug or "thesis"


def runtime_context() -> dict[str, Any]:
    context_path = os.environ.get("MONGOOSE_RUNTIME_CONTEXT", "").strip()
    if not context_path:
        return {}
    path = Path(context_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def provider(name: str) -> dict[str, Any]:
    context = runtime_context()
    providers = context.get("providers", {})
    item = providers.get(name, {}) if isinstance(providers, dict) else {}
    return item if isinstance(item, dict) else {}


def storage_root() -> Path:
    storage = provider("storage")
    path = storage.get("path", "") if storage.get("available") else ""
    if path:
        return Path(str(path))
    return FALLBACK_STATE


def thesis_path() -> Path:
    return storage_root() / THESIS_FILE


def load_state() -> dict[str, Any]:
    path = thesis_path()
    if not path.exists():
        return {"schemaVersion": 1, "theses": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schemaVersion": 1, "theses": {}}
    if not isinstance(payload, dict):
        return {"schemaVersion": 1, "theses": {}}
    theses = payload.get("theses", {})
    if not isinstance(theses, dict):
        theses = {}
    payload["theses"] = theses
    payload.setdefault("schemaVersion", 1)
    return payload


def save_state(state: dict[str, Any]) -> None:
    path = thesis_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def memory_command(name: str) -> list[str]:
    memory = provider("memory")
    if not memory.get("available"):
        return []
    key = f"{name}Command"
    command = memory.get(key, [])
    if isinstance(command, list) and all(isinstance(item, str) and item for item in command):
        return command
    return []


def append_memory(record: dict[str, Any]) -> dict[str, Any] | None:
    command = memory_command("append")
    if not command:
        return None
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(record, sort_keys=True),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=30,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def prompt_context(subject: str, limit: int = 5) -> dict[str, Any]:
    command = memory_command("context")
    if not command:
        return {}
    try:
        completed = subprocess.run(
            [
                *command,
                "--agent",
                "Portfolio",
                "--capability",
                "thesis",
                "--subject",
                subject,
                "--limit",
                str(limit),
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=30,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if completed.returncode != 0:
        return {}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def thesis_memory_record(thesis: dict[str, Any], event_kind: str, summary: str, *, outcome: str = "recorded") -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "recordType": "loop_aware_memory_record",
        "agentId": "Portfolio",
        "capabilityId": "thesis",
        "goal": {
            "request": f"Portfolio thesis {event_kind}: {thesis['id']}",
            "summary": "Maintain durable investment thesis research memory.",
        },
        "loop": {
            "definitionIds": ["portfolio-thesis-management"],
            "status": "completed",
            "exitCriteria": ["record structured thesis state", "preserve research guardrails"],
        },
        "subject": thesis["id"],
        "decision": {
            "summary": summary,
            "confidence": thesis.get("confidence"),
            "source": "user-authored-research",
        },
        "recommendation": {
            "summary": "Review evidence and invalidation criteria before making any portfolio decision.",
            "requiresUserApproval": True,
        },
        "userDecision": {
            "status": "informational",
            "summary": "Portfolio memory records organize research and do not authorize trades.",
        },
        "outcome": {
            "status": outcome,
            "summary": summary,
        },
        "facts": {
            "thesis": {
                "id": thesis["id"],
                "claim": thesis.get("claim", ""),
                "status": thesis.get("status", ""),
                "timeHorizon": thesis.get("timeHorizon", ""),
                "confidence": thesis.get("confidence"),
                "sectors": thesis.get("sectors", []),
                "assumptions": thesis.get("assumptions", []),
                "invalidationCriteria": thesis.get("invalidationCriteria", []),
            },
            "positions": thesis.get("positions", []),
            "evidence": thesis.get("evidence", []),
            "replaySafe": True,
        },
        "events": [
            {
                "eventKind": "started",
                "visibility": "user",
                "message": f"Started portfolio thesis {event_kind}.",
                "createdAt": now_utc_iso(),
            },
            {
                "eventKind": "decision_made",
                "visibility": "user",
                "message": summary,
                "createdAt": now_utc_iso(),
            },
            {
                "eventKind": "completed",
                "visibility": "user",
                "message": "Stored portfolio research memory without trading authority.",
                "createdAt": now_utc_iso(),
            },
        ],
        "redaction": {"secretsRemoved": True, "rawProviderPayloadsRemoved": True},
        "createdAt": now_utc_iso(),
    }


def get_thesis(state: dict[str, Any], thesis_id: str) -> dict[str, Any] | None:
    thesis = state["theses"].get(thesis_id)
    return thesis if isinstance(thesis, dict) else None


def print_lines(lines: list[str]) -> int:
    print("\n".join(lines))
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    state = load_state()
    thesis_id = slugify(args.id)
    if thesis_id in state["theses"]:
        print(f"Thesis already exists: {thesis_id}", file=sys.stderr)
        return 1
    thesis = {
        "id": thesis_id,
        "claim": args.claim,
        "status": "active",
        "timeHorizon": args.horizon or "",
        "assumptions": args.assumption or [],
        "invalidationCriteria": args.invalidation or [],
        "sectors": args.sector or [],
        "relatedAssets": args.asset or [],
        "confidence": args.confidence,
        "notes": args.note or [],
        "positions": [],
        "evidence": [],
        "createdAt": now_utc_iso(),
        "updatedAt": now_utc_iso(),
    }
    state["theses"][thesis_id] = thesis
    save_state(state)
    stored = append_memory(thesis_memory_record(thesis, "created", f"Created thesis: {args.claim}", outcome="created"))
    lines = [f"Created thesis: {thesis_id}", f"Claim: {args.claim}"]
    if stored:
        lines.append(f"Memory record: {stored.get('recordId', '')}")
    return print_lines(lines)


def cmd_list(args: argparse.Namespace) -> int:
    state = load_state()
    theses = sorted(state["theses"].values(), key=lambda item: item.get("id", ""))
    if args.status:
        theses = [item for item in theses if item.get("status") == args.status]
    if not theses:
        return print_lines(["No portfolio theses found."])
    lines = ["Portfolio theses"]
    for thesis in theses:
        confidence = thesis.get("confidence")
        confidence_text = f"; confidence {confidence}" if confidence is not None else ""
        lines.append(f"- {thesis['id']} [{thesis.get('status', '')}{confidence_text}]: {thesis.get('claim', '')}")
    return print_lines(lines)


def cmd_show(args: argparse.Namespace) -> int:
    state = load_state()
    thesis = get_thesis(state, slugify(args.id))
    if thesis is None:
        print(f"Thesis not found: {args.id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(thesis, indent=2, sort_keys=True))
        return 0
    lines = [
        f"Portfolio thesis: {thesis['id']}",
        f"Status: {thesis.get('status', '')}",
        f"Claim: {thesis.get('claim', '')}",
        f"Time horizon: {thesis.get('timeHorizon', '')}",
        f"Confidence: {thesis.get('confidence', '')}",
    ]
    if thesis.get("assumptions"):
        lines.extend(["", "Assumptions", *[f"- {item}" for item in thesis["assumptions"]]])
    if thesis.get("invalidationCriteria"):
        lines.extend(["", "Invalidation criteria", *[f"- {item}" for item in thesis["invalidationCriteria"]]])
    if thesis.get("positions"):
        lines.extend(["", "Positions"])
        for item in thesis["positions"]:
            lines.append(f"- {item['symbol']} ({item['relationship']}): target {item.get('intendedAllocation', '')}%, actual {item.get('actualExposure', '')}%")
    if thesis.get("evidence"):
        lines.extend(["", "Evidence"])
        for item in thesis["evidence"]:
            lines.append(f"- {item['stance']}: {item['summary']} ({item.get('source', '')})")
    return print_lines(lines)


def cmd_update(args: argparse.Namespace) -> int:
    state = load_state()
    thesis = get_thesis(state, slugify(args.id))
    if thesis is None:
        print(f"Thesis not found: {args.id}", file=sys.stderr)
        return 1
    if args.claim:
        thesis["claim"] = args.claim
    if args.horizon:
        thesis["timeHorizon"] = args.horizon
    if args.confidence is not None:
        thesis["confidence"] = args.confidence
    thesis.setdefault("assumptions", []).extend(args.assumption or [])
    thesis.setdefault("invalidationCriteria", []).extend(args.invalidation or [])
    thesis.setdefault("notes", []).extend(args.note or [])
    thesis["updatedAt"] = now_utc_iso()
    save_state(state)
    append_memory(thesis_memory_record(thesis, "updated", f"Updated thesis: {thesis['id']}", outcome="updated"))
    return print_lines([f"Updated thesis: {thesis['id']}"])


def cmd_archive(args: argparse.Namespace) -> int:
    state = load_state()
    thesis = get_thesis(state, slugify(args.id))
    if thesis is None:
        print(f"Thesis not found: {args.id}", file=sys.stderr)
        return 1
    thesis["status"] = "archived"
    thesis["archivedAt"] = now_utc_iso()
    thesis["updatedAt"] = now_utc_iso()
    save_state(state)
    append_memory(thesis_memory_record(thesis, "archived", f"Archived thesis: {thesis['id']}", outcome="archived"))
    return print_lines([f"Archived thesis: {thesis['id']}"])


def cmd_add_position(args: argparse.Namespace) -> int:
    state = load_state()
    thesis = get_thesis(state, slugify(args.id))
    if thesis is None:
        print(f"Thesis not found: {args.id}", file=sys.stderr)
        return 1
    position = {
        "symbol": args.symbol.upper(),
        "relationship": args.relationship,
        "rationale": args.rationale or "",
        "intendedAllocation": args.intended_allocation,
        "actualExposure": args.actual_exposure,
        "riskNotes": args.risk_note or [],
        "createdAt": now_utc_iso(),
    }
    thesis.setdefault("positions", []).append(position)
    thesis["updatedAt"] = now_utc_iso()
    save_state(state)
    append_memory(thesis_memory_record(thesis, "position-added", f"Associated {position['symbol']} as {position['relationship']}.", outcome="position-recorded"))
    return print_lines([f"Added position {position['symbol']} to thesis {thesis['id']}."])


def cmd_add_evidence(args: argparse.Namespace) -> int:
    state = load_state()
    thesis = get_thesis(state, slugify(args.id))
    if thesis is None:
        print(f"Thesis not found: {args.id}", file=sys.stderr)
        return 1
    evidence = {
        "source": args.source,
        "sourceDate": args.source_date or now_utc_iso(),
        "stance": args.stance,
        "summary": args.summary,
        "confidenceImpact": args.confidence_impact,
        "affectedAssets": args.asset or [],
        "createdAt": now_utc_iso(),
    }
    thesis.setdefault("evidence", []).append(evidence)
    if args.confidence_impact is not None and thesis.get("confidence") is not None:
        thesis["confidence"] = max(0.0, min(float(thesis["confidence"]) + args.confidence_impact, 1.0))
    thesis["updatedAt"] = now_utc_iso()
    save_state(state)
    append_memory(thesis_memory_record(thesis, "evidence-added", f"Recorded {args.stance} evidence: {args.summary}", outcome="evidence-recorded"))
    return print_lines([f"Added {args.stance} evidence to thesis {thesis['id']}."])


def deployed_capital_summary(thesis: dict[str, Any]) -> dict[str, Any]:
    positions = thesis.get("positions", [])
    intended = sum(float(item.get("intendedAllocation") or 0) for item in positions)
    actual = sum(float(item.get("actualExposure") or 0) for item in positions)
    return {
        "intendedAllocation": intended,
        "actualExposure": actual,
        "drift": actual - intended,
        "positionCount": len(positions),
    }


def cmd_review(args: argparse.Namespace) -> int:
    state = load_state()
    thesis = get_thesis(state, slugify(args.id))
    if thesis is None:
        print(f"Thesis not found: {args.id}", file=sys.stderr)
        return 1
    capital = deployed_capital_summary(thesis)
    evidence = thesis.get("evidence", [])
    supports = [item for item in evidence if item.get("stance") == "supports"]
    rejects = [item for item in evidence if item.get("stance") == "rejects"]
    context = prompt_context(thesis["id"])
    context_records = context.get("records", []) if isinstance(context.get("records", []), list) else []
    lines = [
        f"Portfolio thesis review: {thesis['id']}",
        "Research-only output; not financial advice or trading execution.",
        "",
        f"Claim: {thesis.get('claim', '')}",
        f"Status: {thesis.get('status', '')}",
        f"Confidence: {thesis.get('confidence', '')}",
        f"Time horizon: {thesis.get('timeHorizon', '')}",
        "",
        "Deployed capital by thesis",
        f"- Intended allocation: {capital['intendedAllocation']:.2f}%",
        f"- Actual exposure: {capital['actualExposure']:.2f}%",
        f"- Drift: {capital['drift']:.2f}%",
        f"- Positions tracked: {capital['positionCount']}",
        "",
        "Evidence health",
        f"- Supports: {len(supports)}",
        f"- Rejects: {len(rejects)}",
        f"- Neutral/watch: {len(evidence) - len(supports) - len(rejects)}",
        "",
        "What would change my mind",
    ]
    invalidation = thesis.get("invalidationCriteria", [])
    lines.extend(f"- {item}" for item in invalidation) if invalidation else lines.append("- No invalidation criteria recorded.")
    lines.extend(["", "Review prompts"])
    if capital["drift"]:
        lines.append("- Review allocation drift before changing exposure.")
    if not evidence:
        lines.append("- Add dated evidence before changing confidence.")
    if rejects:
        lines.append("- Revisit assumptions because rejecting evidence exists.")
    if context_records:
        lines.append(f"- Memory context records considered: {len(context_records)}")
    lines.append("- Any portfolio action requires separate user approval outside this research record.")
    append_memory(thesis_memory_record(thesis, "reviewed", f"Reviewed thesis {thesis['id']} with {len(evidence)} evidence item(s).", outcome="reviewed"))
    return print_lines(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track portfolio investment theses and research memory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-thesis", help="Create an investment thesis.")
    create.add_argument("id")
    create.add_argument("--claim", required=True)
    create.add_argument("--horizon", default="")
    create.add_argument("--assumption", action="append")
    create.add_argument("--invalidation", action="append")
    create.add_argument("--sector", action="append")
    create.add_argument("--asset", action="append")
    create.add_argument("--confidence", type=float)
    create.add_argument("--note", action="append")
    create.set_defaults(handler=cmd_create)

    list_parser = subparsers.add_parser("list-theses", help="List investment theses.")
    list_parser.add_argument("--status", choices=["active", "archived"])
    list_parser.set_defaults(handler=cmd_list)

    show = subparsers.add_parser("show-thesis", help="Show one thesis.")
    show.add_argument("id")
    show.add_argument("--json", action="store_true")
    show.set_defaults(handler=cmd_show)

    update = subparsers.add_parser("update-thesis", help="Update thesis metadata.")
    update.add_argument("id")
    update.add_argument("--claim")
    update.add_argument("--horizon")
    update.add_argument("--confidence", type=float)
    update.add_argument("--assumption", action="append")
    update.add_argument("--invalidation", action="append")
    update.add_argument("--note", action="append")
    update.set_defaults(handler=cmd_update)

    archive = subparsers.add_parser("archive-thesis", help="Archive a thesis.")
    archive.add_argument("id")
    archive.set_defaults(handler=cmd_archive)

    position = subparsers.add_parser("add-position", help="Associate a position or asset with a thesis.")
    position.add_argument("id")
    position.add_argument("symbol")
    position.add_argument("--relationship", required=True, choices=["aligned", "hedge", "watchlist", "rejected", "conflicts-with"])
    position.add_argument("--rationale")
    position.add_argument("--intended-allocation", type=float)
    position.add_argument("--actual-exposure", type=float)
    position.add_argument("--risk-note", action="append")
    position.set_defaults(handler=cmd_add_position)

    evidence = subparsers.add_parser("add-evidence", help="Record evidence for a thesis.")
    evidence.add_argument("id")
    evidence.add_argument("--source", required=True)
    evidence.add_argument("--source-date")
    evidence.add_argument("--stance", required=True, choices=["supports", "rejects", "neutral"])
    evidence.add_argument("--summary", required=True)
    evidence.add_argument("--confidence-impact", type=float)
    evidence.add_argument("--asset", action="append")
    evidence.set_defaults(handler=cmd_add_evidence)

    review = subparsers.add_parser("review-thesis", help="Review thesis health and drift.")
    review.add_argument("id")
    review.set_defaults(handler=cmd_review)

    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
