#!/usr/bin/env python3
"""Heartbeat helper for inspecting and auto-resuming stale task cards."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from task_runtime import (
    WORKSPACE,
    append_history,
    build_resume_command,
    list_cards,
    load_card,
    make_result,
    now_iso,
    save_card,
    seconds_since_checkpoint,
    shell_to_argv,
    stale_due,
    task_path,
)


def summarize_problem(card: dict[str, Any]) -> str:
    age = seconds_since_checkpoint(card)
    age_text = f"{age}s" if age is not None else "unknown"
    return (
        f"{card.get('task_type')}:{card.get('id')}"
        f" phase={card.get('phase')} status={card.get('status')} age={age_text}"
    )



def attempt_resume(card: dict[str, Any], *, timeout_seconds: int, dry_run: bool) -> dict[str, Any]:
    task_id = str(card.get("id"))
    command_text = card.get("resume_command") or ""
    command_argv = card.get("resume_command_argv") or shell_to_argv(command_text)
    if not command_argv and card.get("resume_adapter"):
        command_text, command_argv = build_resume_command(
            task_id,
            resume_command=command_text,
            resume_adapter=card.get("resume_adapter"),
        )
        card["resume_command"] = command_text
        card["resume_command_argv"] = command_argv
    if not command_argv:
        return {
            "task_id": task_id,
            "ok": False,
            "action": "skip",
            "reason": "missing resume command",
        }

    retry_count = int(card.get("retry_count") or 0) + 1
    attempt_at = now_iso()
    card["retry_count"] = retry_count
    card["last_resume_attempt_at"] = attempt_at
    card["updated_at"] = attempt_at

    if dry_run:
        append_history(card, "auto-resume-dry-run", phase=card.get("phase"), status=card.get("status"), message=command_text)
        save_card(card)
        return {
            "task_id": task_id,
            "ok": True,
            "action": "dry-run",
            "command": command_text,
            "retry_count": retry_count,
        }

    save_card(card)

    try:
        proc = subprocess.run(
            command_argv,
            cwd=str(WORKSPACE),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:
        latest = load_card(task_id)
        latest["retry_count"] = retry_count
        latest["last_resume_attempt_at"] = attempt_at
        latest["updated_at"] = latest.get("updated_at") or attempt_at
        latest["last_resume_error"] = str(exc)
        append_history(latest, "auto-resume-error", phase=latest.get("phase"), status=latest.get("status"), message=str(exc))
        save_card(latest)
        return {
            "task_id": task_id,
            "ok": False,
            "action": "error",
            "error": str(exc),
            "retry_count": retry_count,
        }

    result: dict[str, Any] = {
        "task_id": task_id,
        "ok": proc.returncode == 0,
        "action": "resume",
        "command": command_text,
        "returncode": proc.returncode,
        "retry_count": retry_count,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    latest = load_card(task_id)
    latest["retry_count"] = retry_count
    latest["last_resume_attempt_at"] = attempt_at
    if proc.returncode == 0:
        append_history(latest, "auto-resume-triggered", phase=latest.get("phase"), status=latest.get("status"), message=command_text)
    else:
        latest["last_resume_error"] = proc.stderr.strip() or proc.stdout.strip() or f"return code {proc.returncode}"
        append_history(latest, "auto-resume-failed", phase=latest.get("phase"), status=latest.get("status"), message=latest["last_resume_error"])
    save_card(latest)
    return result



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect task cards and optionally auto-resume stale safe tasks")
    parser.add_argument("--task-type")
    parser.add_argument("--auto-resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    return parser



def main() -> int:
    args = build_parser().parse_args()
    running = list_cards(task_type=args.task_type, status="running")
    stale_cards = [card for card in running if stale_due(card)]
    report: dict[str, Any] = {
        "checked_at": now_iso(),
        "running_count": len(running),
        "stale_count": len(stale_cards),
        "running": [make_result(card, task_path(str(card.get("id")))) for card in running],
        "stale": [make_result(card, task_path(str(card.get("id")))) for card in stale_cards],
        "resumed": [],
        "skipped": [],
        "needs_attention": [],
    }

    if args.auto_resume:
        for card in stale_cards:
            max_retries = int(card.get("max_retries") or 0)
            retry_count = int(card.get("retry_count") or 0)
            if retry_count >= max_retries:
                report["needs_attention"].append(
                    {
                        "task_id": card.get("id"),
                        "reason": "max retries reached",
                        "summary": summarize_problem(card),
                    }
                )
                continue
            if not card.get("safe_to_retry"):
                report["needs_attention"].append(
                    {
                        "task_id": card.get("id"),
                        "reason": "task marked unsafe to auto-retry",
                        "summary": summarize_problem(card),
                    }
                )
                continue
            if not (card.get("resume_command_argv") or card.get("resume_adapter")):
                report["needs_attention"].append(
                    {
                        "task_id": card.get("id"),
                        "reason": "stale but no resume command or adapter configured",
                        "summary": summarize_problem(card),
                    }
                )
                continue
            report["resumed"].append(
                attempt_resume(card, timeout_seconds=args.timeout_seconds, dry_run=args.dry_run)
            )
    else:
        for card in stale_cards:
            report["skipped"].append(
                {
                    "task_id": card.get("id"),
                    "reason": "stale candidate found; auto-resume not requested",
                    "summary": summarize_problem(card),
                }
            )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
