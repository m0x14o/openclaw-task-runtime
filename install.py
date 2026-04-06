#!/usr/bin/env python3
"""Install openclaw-task-runtime into an existing OpenClaw workspace."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
HEARTBEAT_SECTION_TITLE = "## Task Recovery Check"
HEARTBEAT_BLOCK_TEMPLATE = """## Task Recovery Check
Run:

```bash
python3 {workspace}/scripts/task_runtime_watch.py --auto-resume
```

If it reports any `alerts`, `recoveries`, or `needs_attention`, summarize them briefly.
Treat them as:
- `alerts`: a task went silent / stale
- `recoveries`: watchdog auto-resume moved the task forward
- `needs_attention`: watchdog could not safely recover it or retries are exhausted
If it reports no actionable signals, move on without mentioning it.
"""


SECTION_RE = re.compile(r"(?ms)^## (?:Task Runtime Recovery Check|Task Recovery Check)\n.*?(?=^##\s|\Z)")


def discover_workspace(start: Path) -> Path | None:
    for base in [start, *start.parents]:
        if (base / "AGENTS.md").exists():
            return base
    return None



def resolve_workspace(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("OPENCLAW_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()

    repo_guess = discover_workspace(REPO_ROOT)
    if repo_guess is not None:
        return repo_guess

    cwd_guess = discover_workspace(Path.cwd())
    if cwd_guess is not None:
        return cwd_guess

    raise RuntimeError("Unable to detect OpenClaw workspace. Pass --workspace explicitly.")



def copy_file(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(dst)



def patch_heartbeat(path: Path, *, workspace: Path) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
    else:
        current = "# HEARTBEAT.md\n\n"

    heartbeat_block = HEARTBEAT_BLOCK_TEMPLATE.format(workspace=str(workspace)).rstrip() + "\n"
    if HEARTBEAT_SECTION_TITLE in current:
        updated = SECTION_RE.sub(heartbeat_block + "\n", current, count=1)
    else:
        updated = current.rstrip() + "\n\n" + heartbeat_block + "\n"

    updated = updated.rstrip() + "\n"
    if updated == current:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return True



def main() -> int:
    parser = argparse.ArgumentParser(description="Install openclaw-task-runtime into an OpenClaw workspace")
    parser.add_argument("--workspace")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = resolve_workspace(args.workspace)
    files = {
        REPO_ROOT / "scripts" / "task_runtime.py": workspace / "scripts" / "task_runtime.py",
        REPO_ROOT / "scripts" / "task_runtime_watch.py": workspace / "scripts" / "task_runtime_watch.py",
        REPO_ROOT / "scripts" / "task_runtime_resume.py": workspace / "scripts" / "task_runtime_resume.py",
        REPO_ROOT / "docs" / "task-runtime-lite.md": workspace / "docs" / "openclaw-task-runtime" / "task-runtime-lite.md",
        REPO_ROOT / "docs" / "task-runtime-adapters.md": workspace / "docs" / "openclaw-task-runtime" / "task-runtime-adapters.md",
        REPO_ROOT / "OPENCLAW_ONE_LINER.md": workspace / "docs" / "openclaw-task-runtime" / "OPENCLAW_ONE_LINER.md",
        REPO_ROOT / "templates" / "task_resume.py": workspace / "templates" / "openclaw-task-runtime" / "task_resume.py",
    }

    copied: list[str] = []
    if not args.dry_run:
        for src, dst in files.items():
            copied.append(copy_file(src, dst))
        heartbeat_changed = patch_heartbeat(workspace / "HEARTBEAT.md", workspace=workspace)
    else:
        copied = [str(dst) for dst in files.values()]
        heartbeat_changed = True

    print(
        json.dumps(
            {
                "ok": True,
                "workspace": str(workspace),
                "copied": copied,
                "heartbeat_changed": heartbeat_changed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
