#!/usr/bin/env python3
"""Generic resume dispatcher for task-runtime adapters.

Each task card may declare a `resume_adapter` path. This dispatcher loads the
card, resolves the adapter command, and passes `--task-id` through so the
adapter can recover the specific phase safely.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from task_runtime import WORKSPACE, load_card, append_history, save_card, resolve_workspace_path


def resolve_adapter_command(adapter: str, *, task_id: str, timeout_seconds: int) -> list[str]:
    adapter = str(Path(resolve_workspace_path(adapter) or adapter).expanduser())
    if adapter.endswith(".py"):
        return ["python3", adapter, "--task-id", task_id, "--timeout-seconds", str(timeout_seconds)]
    return [adapter, "--task-id", task_id, "--timeout-seconds", str(timeout_seconds)]



def parse_child_output(stdout: str) -> Any:
    payload = stdout.strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw_stdout": payload}



def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch a task card to its configured resume adapter")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    try:
        card = load_card(args.task_id)
        adapter = card.get("resume_adapter") or card.get("meta", {}).get("resume_adapter")
        if not adapter:
            raise RuntimeError("task has no resume_adapter configured")
        command = resolve_adapter_command(str(adapter), task_id=str(card.get("id")), timeout_seconds=args.timeout_seconds)
        proc = subprocess.run(
            command,
            cwd=str(WORKSPACE),
            text=True,
            capture_output=True,
            timeout=args.timeout_seconds,
            check=False,
        )
        child_result = parse_child_output(proc.stdout)
        latest = load_card(args.task_id)
        if proc.returncode == 0:
            append_history(
                latest,
                "resume-dispatched",
                phase=latest.get("phase"),
                status=latest.get("status"),
                message=str(adapter),
                extra={"adapter": adapter},
            )
            save_card(latest)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "task_id": args.task_id,
                        "adapter": adapter,
                        "command": command,
                        "result": child_result,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        latest["last_resume_error"] = proc.stderr.strip() or proc.stdout.strip() or f"return code {proc.returncode}"
        append_history(
            latest,
            "resume-dispatch-failed",
            phase=latest.get("phase"),
            status=latest.get("status"),
            message=latest["last_resume_error"],
            extra={"adapter": adapter},
        )
        save_card(latest)
        print(
            json.dumps(
                {
                    "ok": False,
                    "task_id": args.task_id,
                    "adapter": adapter,
                    "command": command,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                    "returncode": proc.returncode,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
