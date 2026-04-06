#!/usr/bin/env python3
"""Lightweight run-card state manager for long-running OpenClaw work.

This keeps durable run cards in data/task-runs so heartbeat checks can
inspect progress, detect stale runs, and trigger safe resume commands.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def discover_workspace(start: Path) -> Path | None:
    for base in [start, *start.parents]:
        if (base / "AGENTS.md").exists():
            return base
    return None



def resolve_workspace() -> Path:
    explicit = os.environ.get("OPENCLAW_WORKSPACE")
    if explicit:
        return Path(explicit).expanduser().resolve()

    here = Path(__file__).resolve()
    by_script = discover_workspace(here.parent)
    if by_script is not None:
        return by_script

    by_cwd = discover_workspace(Path.cwd())
    if by_cwd is not None:
        return by_cwd

    raise RuntimeError(
        "Unable to detect OpenClaw workspace. Set OPENCLAW_WORKSPACE or install these scripts inside <workspace>/scripts/."
    )



def resolve_workspace_path(value: str | None) -> str | None:
    if not value:
        return None
    expanded = Path(os.path.expandvars(os.path.expanduser(value.strip())))
    if expanded.is_absolute():
        return str(expanded)
    return str((resolve_workspace() / expanded).resolve())


WORKSPACE = resolve_workspace()
TASK_RUNS_DIR = WORKSPACE / "data" / "task-runs"
DEFAULT_RESUME_RUNNER = WORKSPACE / "scripts" / "task_runtime_resume.py"


def now_shanghai() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    return datetime.now()


def now_iso() -> str:
    return now_shanghai().isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def sanitize_task_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if not cleaned:
        raise ValueError("task id is empty after sanitization")
    return cleaned.lower()


def default_task_id(task_type: str) -> str:
    stamp = now_shanghai().strftime("%Y%m%d-%H%M%S")
    return sanitize_task_id(f"{task_type}-{stamp}")


def ensure_dir() -> None:
    TASK_RUNS_DIR.mkdir(parents=True, exist_ok=True)


def task_path(task_id: str) -> Path:
    return TASK_RUNS_DIR / f"{sanitize_task_id(task_id)}.json"


def parse_kv_pairs(values: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise ValueError(f"expected key=value, got: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"empty key in: {item}")
        result[key] = value.strip()
    return result



def shell_to_argv(command: str | None) -> list[str]:
    if not command:
        return []
    argv = shlex.split(command)
    return [os.path.expandvars(os.path.expanduser(part)) for part in argv]



def normalize_resume_adapter(adapter: str | None) -> str | None:
    return resolve_workspace_path(adapter)



def build_resume_command(task_id: str, *, resume_command: str | None, resume_adapter: str | None) -> tuple[str | None, list[str]]:
    explicit = (resume_command or "").strip()
    if explicit:
        return explicit, shell_to_argv(explicit)
    adapter = normalize_resume_adapter(resume_adapter)
    if not adapter:
        return None, []
    command = f"python3 {DEFAULT_RESUME_RUNNER} --task-id {sanitize_task_id(task_id)}"
    return command, shell_to_argv(command)


@dataclass
class TaskSummary:
    id: str
    task_type: str
    title: str
    mode: str
    status: str
    phase: str
    updated_at: str | None
    retry_count: int
    max_retries: int
    allow_auto_resume: bool
    stale_after_minutes: int
    seconds_since_checkpoint: int | None


class TaskRuntimeError(Exception):
    pass



def load_card(task_id: str) -> dict[str, Any]:
    path = task_path(task_id)
    if not path.exists():
        raise TaskRuntimeError(f"task not found: {task_id}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TaskRuntimeError(f"invalid task file: {path}")
    return data



def save_card(card: dict[str, Any]) -> Path:
    ensure_dir()
    path = task_path(str(card["id"]))
    with path.open("w", encoding="utf-8") as handle:
        json.dump(card, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path



def history_entry(event: str, *, phase: str | None = None, status: str | None = None, message: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "at": now_iso(),
        "event": event,
    }
    if phase:
        entry["phase"] = phase
    if status:
        entry["status"] = status
    if message:
        entry["message"] = message
    if extra:
        entry["extra"] = extra
    return entry



def append_history(card: dict[str, Any], event: str, *, phase: str | None = None, status: str | None = None, message: str = "", extra: dict[str, Any] | None = None) -> None:
    items = card.setdefault("history", [])
    if not isinstance(items, list):
        items = []
        card["history"] = items
    items.append(history_entry(event, phase=phase, status=status, message=message, extra=extra))
    if len(items) > 80:
        del items[:-80]



def seconds_since_checkpoint(card: dict[str, Any]) -> int | None:
    checkpoint_at = parse_iso(card.get("last_checkpoint_at") or card.get("updated_at"))
    if checkpoint_at is None:
        return None
    delta = now_shanghai() - checkpoint_at
    return max(0, int(delta.total_seconds()))



def stale_due(card: dict[str, Any]) -> bool:
    if card.get("status") != "running":
        return False
    if not card.get("allow_auto_resume"):
        return False
    stale_after = int(card.get("stale_after_minutes") or 0)
    if stale_after <= 0:
        return False
    age = seconds_since_checkpoint(card)
    if age is None:
        return False
    if age < stale_after * 60:
        return False
    retries = int(card.get("retry_count") or 0)
    max_retries = int(card.get("max_retries") or 0)
    return retries < max_retries



def summarize(card: dict[str, Any]) -> TaskSummary:
    return TaskSummary(
        id=str(card.get("id", "")),
        task_type=str(card.get("task_type", "")),
        title=str(card.get("title", "")),
        mode=str(card.get("mode", "")),
        status=str(card.get("status", "")),
        phase=str(card.get("phase", "")),
        updated_at=card.get("updated_at"),
        retry_count=int(card.get("retry_count") or 0),
        max_retries=int(card.get("max_retries") or 0),
        allow_auto_resume=bool(card.get("allow_auto_resume")),
        stale_after_minutes=int(card.get("stale_after_minutes") or 0),
        seconds_since_checkpoint=seconds_since_checkpoint(card),
    )



def list_cards(*, task_type: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    ensure_dir()
    cards: list[dict[str, Any]] = []
    for path in sorted(TASK_RUNS_DIR.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                card = json.load(handle)
            if not isinstance(card, dict):
                continue
        except Exception:
            continue
        if task_type and str(card.get("task_type")) != task_type:
            continue
        if status and str(card.get("status")) != status:
            continue
        cards.append(card)
    cards.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return cards



def make_result(card: dict[str, Any], path: Path) -> dict[str, Any]:
    summary = summarize(card)
    return {
        "task_id": summary.id,
        "task_path": str(path),
        "task_type": summary.task_type,
        "title": summary.title,
        "mode": summary.mode,
        "status": summary.status,
        "phase": summary.phase,
        "retry_count": summary.retry_count,
        "max_retries": summary.max_retries,
        "allow_auto_resume": summary.allow_auto_resume,
        "stale_after_minutes": summary.stale_after_minutes,
        "seconds_since_checkpoint": summary.seconds_since_checkpoint,
        "artifacts": deepcopy(card.get("artifacts") or {}),
        "resume_command": card.get("resume_command"),
        "resume_adapter": card.get("resume_adapter"),
        "watchdog": deepcopy(card.get("watchdog") or {}),
    }



def cmd_create(args: argparse.Namespace) -> dict[str, Any]:
    task_id = sanitize_task_id(args.task_id) if args.task_id else default_task_id(args.task_type)
    artifacts = parse_kv_pairs(args.artifact)
    meta = parse_kv_pairs(args.meta)
    checkpoint_time = now_iso()
    resume_adapter = normalize_resume_adapter(args.resume_adapter)
    resume_command, resume_command_argv = build_resume_command(
        task_id,
        resume_command=args.resume_command,
        resume_adapter=resume_adapter,
    )
    card: dict[str, Any] = {
        "id": task_id,
        "task_type": args.task_type,
        "title": args.title,
        "mode": args.mode,
        "owner_skill": args.owner_skill,
        "status": args.status,
        "phase": args.phase,
        "created_at": checkpoint_time,
        "updated_at": checkpoint_time,
        "last_checkpoint_at": checkpoint_time if args.status == "running" else None,
        "allow_auto_resume": args.allow_auto_resume,
        "safe_to_retry": args.safe_to_retry,
        "stale_after_minutes": args.stale_after_minutes,
        "retry_count": 0,
        "max_retries": args.max_retries,
        "resume_adapter": resume_adapter,
        "resume_command": resume_command,
        "resume_command_argv": resume_command_argv,
        "artifacts": artifacts,
        "notes": args.notes,
        "meta": meta,
        "history": [],
    }
    append_history(card, "created", phase=args.phase, status=args.status, message=args.notes or "task created")
    path = save_card(card)
    return {"ok": True, "action": "create", "task": make_result(card, path)}



def apply_common_updates(card: dict[str, Any], args: argparse.Namespace) -> None:
    changed = False
    resume_changed = False
    if getattr(args, "phase", None):
        card["phase"] = args.phase
        changed = True
    if getattr(args, "status", None):
        card["status"] = args.status
        changed = True
    if getattr(args, "title", None):
        card["title"] = args.title
        changed = True
    if getattr(args, "allow_auto_resume", None) is not None:
        card["allow_auto_resume"] = args.allow_auto_resume
        changed = True
    if getattr(args, "safe_to_retry", None) is not None:
        card["safe_to_retry"] = args.safe_to_retry
        changed = True
    if getattr(args, "resume_adapter", None):
        card["resume_adapter"] = normalize_resume_adapter(args.resume_adapter)
        resume_changed = True
        changed = True
    if getattr(args, "resume_command", None):
        card["resume_command"] = args.resume_command
        resume_changed = True
        changed = True
    if resume_changed:
        command, argv = build_resume_command(
            str(card.get("id")),
            resume_command=card.get("resume_command"),
            resume_adapter=card.get("resume_adapter"),
        )
        card["resume_command"] = command
        card["resume_command_argv"] = argv
    if getattr(args, "stale_after_minutes", None) is not None:
        card["stale_after_minutes"] = args.stale_after_minutes
        changed = True
    if getattr(args, "max_retries", None) is not None:
        card["max_retries"] = args.max_retries
        changed = True
    if getattr(args, "notes", None):
        card["notes"] = args.notes
        changed = True
    artifact_updates = parse_kv_pairs(getattr(args, "artifact", None))
    if artifact_updates:
        card.setdefault("artifacts", {}).update(artifact_updates)
        changed = True
    meta_updates = parse_kv_pairs(getattr(args, "meta", None))
    if meta_updates:
        card.setdefault("meta", {}).update(meta_updates)
        changed = True
    if changed:
        card["updated_at"] = now_iso()



def update_card(task_id: str, args: argparse.Namespace, *, event: str, checkpoint: bool = False) -> dict[str, Any]:
    card = load_card(task_id)
    apply_common_updates(card, args)
    if checkpoint:
        card["last_checkpoint_at"] = now_iso()
        card["updated_at"] = card["last_checkpoint_at"]
        if not getattr(args, "status", None):
            card["status"] = "running"
    append_history(
        card,
        event,
        phase=card.get("phase"),
        status=card.get("status"),
        message=args.message or "",
    )
    path = save_card(card)
    return {"ok": True, "action": event, "task": make_result(card, path)}



def cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    cards = list_cards(task_type=args.task_type, status=args.status)
    summaries = [make_result(card, task_path(str(card.get("id")))) for card in cards]
    if args.only_stale:
        summaries = [item for item in summaries if stale_due(load_card(item["task_id"]))]
    return {"ok": True, "action": "list", "count": len(summaries), "tasks": summaries}



def cmd_inspect(args: argparse.Namespace) -> dict[str, Any]:
    card = load_card(args.task_id)
    return {"ok": True, "action": "inspect", "task": card, "task_path": str(task_path(args.task_id))}



def cmd_mark_retry(args: argparse.Namespace) -> dict[str, Any]:
    card = load_card(args.task_id)
    card["retry_count"] = int(card.get("retry_count") or 0) + 1
    card["last_resume_attempt_at"] = now_iso()
    card["updated_at"] = card["last_resume_attempt_at"]
    if args.error:
        card["last_resume_error"] = args.error
    append_history(
        card,
        "resume-attempt",
        phase=card.get("phase"),
        status=card.get("status"),
        message=args.message or args.error or "resume attempt recorded",
    )
    path = save_card(card)
    return {"ok": True, "action": "mark-retry", "task": make_result(card, path)}



def cmd_stale(args: argparse.Namespace) -> dict[str, Any]:
    cards = list_cards(task_type=args.task_type, status="running")
    stale_cards = []
    for card in cards:
        if args.require_resume_command and not (card.get("resume_command_argv") or card.get("resume_adapter")):
            continue
        if stale_due(card):
            stale_cards.append(make_result(card, task_path(str(card.get("id")))))
    return {"ok": True, "action": "stale", "count": len(stale_cards), "tasks": stale_cards}



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage durable run cards for long-running work")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a new run card")
    create.add_argument("--task-id")
    create.add_argument("--task-type", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--mode", default="full")
    create.add_argument("--owner-skill", default="")
    create.add_argument("--status", default="running")
    create.add_argument("--phase", default="planning")
    create.add_argument("--artifact", action="append", default=[])
    create.add_argument("--meta", action="append", default=[])
    create.add_argument("--notes", default="")
    create.add_argument("--resume-command")
    create.add_argument("--resume-adapter")
    create.add_argument("--stale-after-minutes", type=int, default=30)
    create.add_argument("--max-retries", type=int, default=2)
    create.add_argument("--safe-to-retry", action=argparse.BooleanOptionalAction, default=True)
    create.add_argument("--allow-auto-resume", action=argparse.BooleanOptionalAction, default=False)
    create.set_defaults(func=cmd_create)

    checkpoint = sub.add_parser("checkpoint", help="Update progress and refresh checkpoint time")
    checkpoint.add_argument("task_id")
    checkpoint.add_argument("--phase")
    checkpoint.add_argument("--status")
    checkpoint.add_argument("--title")
    checkpoint.add_argument("--artifact", action="append", default=[])
    checkpoint.add_argument("--meta", action="append", default=[])
    checkpoint.add_argument("--notes")
    checkpoint.add_argument("--message", default="checkpoint")
    checkpoint.add_argument("--resume-command")
    checkpoint.add_argument("--resume-adapter")
    checkpoint.add_argument("--stale-after-minutes", type=int)
    checkpoint.add_argument("--max-retries", type=int)
    checkpoint.add_argument("--safe-to-retry", action=argparse.BooleanOptionalAction, default=None)
    checkpoint.add_argument("--allow-auto-resume", action=argparse.BooleanOptionalAction, default=None)
    checkpoint.set_defaults(func=lambda args: update_card(args.task_id, args, event="checkpoint", checkpoint=True))

    update = sub.add_parser("update", help="Update task metadata without touching checkpoint")
    update.add_argument("task_id")
    update.add_argument("--phase")
    update.add_argument("--status")
    update.add_argument("--title")
    update.add_argument("--artifact", action="append", default=[])
    update.add_argument("--meta", action="append", default=[])
    update.add_argument("--notes")
    update.add_argument("--message", default="update")
    update.add_argument("--resume-command")
    update.add_argument("--resume-adapter")
    update.add_argument("--stale-after-minutes", type=int)
    update.add_argument("--max-retries", type=int)
    update.add_argument("--safe-to-retry", action=argparse.BooleanOptionalAction, default=None)
    update.add_argument("--allow-auto-resume", action=argparse.BooleanOptionalAction, default=None)
    update.set_defaults(func=lambda args: update_card(args.task_id, args, event="update", checkpoint=False))

    complete = sub.add_parser("complete", help="Mark a task as done")
    complete.add_argument("task_id")
    complete.add_argument("--phase")
    complete.add_argument("--artifact", action="append", default=[])
    complete.add_argument("--meta", action="append", default=[])
    complete.add_argument("--notes")
    complete.add_argument("--message", default="task completed")
    complete.add_argument("--status", default="done")
    complete.add_argument("--safe-to-retry", action=argparse.BooleanOptionalAction, default=False)
    complete.add_argument("--allow-auto-resume", action=argparse.BooleanOptionalAction, default=False)
    complete.set_defaults(func=lambda args: update_card(args.task_id, args, event="complete", checkpoint=False))

    block = sub.add_parser("block", help="Mark a task as blocked")
    block.add_argument("task_id")
    block.add_argument("--phase")
    block.add_argument("--artifact", action="append", default=[])
    block.add_argument("--meta", action="append", default=[])
    block.add_argument("--notes")
    block.add_argument("--message", default="task blocked")
    block.add_argument("--status", default="blocked")
    block.add_argument("--safe-to-retry", action=argparse.BooleanOptionalAction, default=False)
    block.add_argument("--allow-auto-resume", action=argparse.BooleanOptionalAction, default=False)
    block.set_defaults(func=lambda args: update_card(args.task_id, args, event="blocked", checkpoint=False))

    fail = sub.add_parser("fail", help="Mark a task as failed")
    fail.add_argument("task_id")
    fail.add_argument("--phase")
    fail.add_argument("--artifact", action="append", default=[])
    fail.add_argument("--meta", action="append", default=[])
    fail.add_argument("--notes")
    fail.add_argument("--message", default="task failed")
    fail.add_argument("--status", default="failed")
    fail.add_argument("--safe-to-retry", action=argparse.BooleanOptionalAction, default=False)
    fail.add_argument("--allow-auto-resume", action=argparse.BooleanOptionalAction, default=False)
    fail.set_defaults(func=lambda args: update_card(args.task_id, args, event="failed", checkpoint=False))

    inspect = sub.add_parser("inspect", help="Show full run card")
    inspect.add_argument("task_id")
    inspect.set_defaults(func=cmd_inspect)

    list_cmd = sub.add_parser("list", help="List run cards")
    list_cmd.add_argument("--task-type")
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--only-stale", action="store_true")
    list_cmd.set_defaults(func=cmd_list)

    stale = sub.add_parser("stale", help="List stale auto-resume candidates")
    stale.add_argument("--task-type")
    stale.add_argument("--require-resume-command", action="store_true")
    stale.set_defaults(func=cmd_stale)

    mark_retry = sub.add_parser("mark-retry", help="Record an auto-resume attempt")
    mark_retry.add_argument("task_id")
    mark_retry.add_argument("--message")
    mark_retry.add_argument("--error")
    mark_retry.set_defaults(func=cmd_mark_retry)

    return parser



def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.func(args)
    except (TaskRuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
