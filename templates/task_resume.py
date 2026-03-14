#!/usr/bin/env python3
"""Template adapter for openclaw-task-runtime.

Copy this file into your skill, then implement the safe resumable phases.
Example destination:

    ~/.openclaw/workspace/skills/<your-skill>/scripts/task_resume.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def discover_workspace(start: Path) -> Path | None:
    for base in [start, *start.parents]:
        if (base / "AGENTS.md").exists():
            return base
    return None


explicit = os.environ.get("OPENCLAW_WORKSPACE")
WORKSPACE = Path(explicit).expanduser().resolve() if explicit else discover_workspace(Path(__file__).resolve().parent)
if WORKSPACE is None:
    raise RuntimeError("Unable to detect OpenClaw workspace. Set OPENCLAW_WORKSPACE.")

SCRIPTS_DIR = WORKSPACE / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_runtime import append_history, load_card, now_iso, save_card  # noqa: E402


def resume_render(card: dict) -> dict:
    artifacts = card.get("artifacts") if isinstance(card.get("artifacts"), dict) else {}
    normalized_input = artifacts.get("normalized_input")
    if not normalized_input:
        raise RuntimeError("missing artifacts.normalized_input")

    # TODO: replace this block with your own rendering or recovery logic.
    # Example pattern:
    #   result = subprocess.run([...], capture_output=True, text=True, check=False)
    #   parse JSON stdout
    #   update artifacts with output paths

    artifacts["result_path"] = str(normalized_input)
    card["artifacts"] = artifacts
    card["phase"] = "render_complete"
    card["status"] = "done"
    card["last_checkpoint_at"] = now_iso()
    card["updated_at"] = card["last_checkpoint_at"]
    append_history(card, "template-render-resumed", phase=card.get("phase"), status=card.get("status"))
    save_card(card)
    return {
        "task_id": card.get("id"),
        "action": "resume_render",
        "ok": True,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Template task-runtime adapter")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    try:
        card = load_card(args.task_id)
        phase = str(card.get("phase") or "")
        if phase in {"render", "render_report", "finalize"}:
            result = resume_render(card)
        else:
            raise RuntimeError(f"no safe resume handler for phase: {phase}")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
