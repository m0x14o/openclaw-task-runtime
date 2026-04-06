# Quickstart

If you only want the shortest path, copy one of these into your own OpenClaw.

## One-line install

> Install and enable https://github.com/m0x14o/openclaw-task-runtime in the current OpenClaw workspace: clone it into `repos/openclaw-task-runtime`, run `python3 install.py`, wire the task recovery check into `HEARTBEAT.md`, and confirm it is ready.

## One-line skill integration

> Connect the `<skill-name>` skill to https://github.com/m0x14o/openclaw-task-runtime in the current OpenClaw workspace: create a `task_resume.py` adapter from the installed template, add run cards and checkpoints for long-running phases, enable heartbeat-based auto-resume only for safe phases, update the skill docs with the minimal usage, and then show me exactly how to use it.

## One-line temporary long task

> Run this as a resumable long task under openclaw-task-runtime in the current OpenClaw workspace. If no skill exists yet, scaffold a temporary adapter under `tmp/task-runtime/<task-slug>/task_resume.py`, create a run card, checkpoint the safe phases, enable heartbeat auto-resume, and at minimum leave me either a final result, a partial result, or a clear block report: <replace this with your task>
