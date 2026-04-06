#!/usr/bin/env python3
"""Heartbeat helper for inspecting and auto-resuming stale run cards.

The watchdog emits three high-signal buckets for heartbeat summarization:
- alerts: a task went silent / stale this round
- recoveries: auto-resume moved the task forward this round
- needs_attention: a fresh human-facing escalation this round

`active_needs_attention` is also included for manual inspection without
repeating the same user-facing escalation every heartbeat.
"""

from __future__ import annotations

import argparse
import json
import subprocess
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


def human_age(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return f"{seconds}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m" if rem == 0 else f"{minutes}m{rem}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"



def task_ref(card: dict[str, Any]) -> str:
    return f"{card.get('task_type')}:{card.get('id')}"



def summarize_problem(card: dict[str, Any]) -> str:
    age = seconds_since_checkpoint(card)
    return (
        f"{task_ref(card)}"
        f" phase={card.get('phase')} status={card.get('status')} age={human_age(age)}"
    )



def ensure_watchdog(card: dict[str, Any]) -> dict[str, Any]:
    watchdog = card.get("watchdog")
    if isinstance(watchdog, dict):
        return watchdog
    watchdog = {}
    card["watchdog"] = watchdog
    return watchdog



def notice_fingerprint(card: dict[str, Any], *, kind: str, reason: str = "") -> str:
    payload = {
        "kind": kind,
        "reason": reason,
        "status": card.get("status"),
        "phase": card.get("phase"),
        "last_checkpoint_at": card.get("last_checkpoint_at"),
        "retry_count": int(card.get("retry_count") or 0),
        "max_retries": int(card.get("max_retries") or 0),
        "last_resume_attempt_at": card.get("last_resume_attempt_at"),
        "last_resume_error": card.get("last_resume_error"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)



def record_notice(
    card: dict[str, Any],
    *,
    slot: str,
    fingerprint: str,
    event: str,
    message: str,
    persist: bool,
) -> bool:
    watchdog = ensure_watchdog(card)
    if watchdog.get(slot) == fingerprint:
        return False
    if not persist:
        return True
    watchdog[slot] = fingerprint
    watchdog[f"{slot}_at"] = now_iso()
    append_history(card, event, phase=card.get("phase"), status=card.get("status"), message=message)
    save_card(card)
    return True



def build_alert(card: dict[str, Any]) -> dict[str, Any]:
    age = seconds_since_checkpoint(card)
    return {
        "task_id": card.get("id"),
        "task_type": card.get("task_type"),
        "kind": "silent",
        "summary": summarize_problem(card),
        "message": (
            f"{task_ref(card)} went silent for {human_age(age)} "
            f"at phase={card.get('phase')}; watchdog is checking recovery."
        ),
    }



def build_attention(card: dict[str, Any], *, reason: str, detail: str = "") -> dict[str, Any]:
    item: dict[str, Any] = {
        "task_id": card.get("id"),
        "task_type": card.get("task_type"),
        "reason": reason,
        "summary": summarize_problem(card),
        "message": f"{task_ref(card)} needs attention: {reason}.",
    }
    if detail:
        item["detail"] = detail
        item["message"] = f"{item['message']} {detail}"
    return item



def build_recovery(before: dict[str, Any], after: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    outcome = f"status={after.get('status')} phase={after.get('phase')}"
    return {
        "task_id": after.get("id"),
        "task_type": after.get("task_type"),
        "retry_count": attempt.get("retry_count"),
        "summary": summarize_problem(after),
        "message": f"{task_ref(before)} auto-resume ran successfully; now {outcome}.",
    }



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



def maybe_emit_stale_alert(card: dict[str, Any], *, persist: bool) -> dict[str, Any] | None:
    alert = build_alert(card)
    should_emit = record_notice(
        card,
        slot="last_stale_notice",
        fingerprint=notice_fingerprint(card, kind="stale"),
        event="watchdog-stale-alerted",
        message=alert["message"],
        persist=persist,
    )
    if not should_emit:
        return None
    return alert



def maybe_emit_attention(
    card: dict[str, Any],
    *,
    reason: str,
    detail: str = "",
    persist: bool,
) -> dict[str, Any] | None:
    item = build_attention(card, reason=reason, detail=detail)
    should_emit = record_notice(
        card,
        slot="last_attention_notice",
        fingerprint=notice_fingerprint(card, kind="attention", reason=reason),
        event="watchdog-needs-attention",
        message=item["message"],
        persist=persist,
    )
    if not should_emit:
        return None
    return item



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect run cards and optionally auto-resume stale safe tasks")
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
        "alerts": [],
        "recoveries": [],
        "resumed": [],
        "skipped": [],
        "needs_attention": [],
        "active_needs_attention": [],
    }

    persist_notices = not args.dry_run

    if args.auto_resume:
        for card in stale_cards:
            alert = maybe_emit_stale_alert(card, persist=persist_notices)
            if alert is not None:
                report["alerts"].append(alert)

            max_retries = int(card.get("max_retries") or 0)
            retry_count = int(card.get("retry_count") or 0)
            if retry_count >= max_retries:
                active = build_attention(card, reason="max retries reached")
                report["active_needs_attention"].append(active)
                notice = maybe_emit_attention(card, reason="max retries reached", persist=persist_notices)
                if notice is not None:
                    report["needs_attention"].append(notice)
                continue
            if not card.get("safe_to_retry"):
                active = build_attention(card, reason="task marked unsafe to auto-retry")
                report["active_needs_attention"].append(active)
                notice = maybe_emit_attention(card, reason="task marked unsafe to auto-retry", persist=persist_notices)
                if notice is not None:
                    report["needs_attention"].append(notice)
                continue
            if not (card.get("resume_command_argv") or card.get("resume_adapter")):
                active = build_attention(card, reason="stale but no resume command or adapter configured")
                report["active_needs_attention"].append(active)
                notice = maybe_emit_attention(card, reason="stale but no resume command or adapter configured", persist=persist_notices)
                if notice is not None:
                    report["needs_attention"].append(notice)
                continue

            before = dict(card)
            result = attempt_resume(card, timeout_seconds=args.timeout_seconds, dry_run=args.dry_run)
            report["resumed"].append(result)

            if result.get("ok"):
                if result.get("action") != "dry-run":
                    latest = load_card(str(card.get("id")))
                    report["recoveries"].append(build_recovery(before, latest, result))
                continue

            final_retry_count = int(result.get("retry_count") or 0)
            if final_retry_count >= max_retries:
                latest = load_card(str(card.get("id")))
                detail = latest.get("last_resume_error") or result.get("error") or result.get("stderr") or result.get("stdout") or "resume failed"
                active = build_attention(latest, reason="auto-resume failed and retries are exhausted", detail=detail)
                report["active_needs_attention"].append(active)
                notice = maybe_emit_attention(
                    latest,
                    reason="auto-resume failed and retries are exhausted",
                    detail=detail,
                    persist=persist_notices,
                )
                if notice is not None:
                    report["needs_attention"].append(notice)
    else:
        for card in stale_cards:
            alert = maybe_emit_stale_alert(card, persist=False)
            if alert is not None:
                report["alerts"].append(alert)
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
