# Copy-paste prompts for your OpenClaw

## 1) Install

> Install and enable https://github.com/m0x14o/openclaw-task-runtime in the current OpenClaw workspace: clone it into `repos/openclaw-task-runtime`, run `python3 install.py`, wire the task recovery check into `HEARTBEAT.md`, and confirm it is ready.

## 2) Connect an existing skill

> Connect the `<skill-name>` skill to https://github.com/m0x14o/openclaw-task-runtime in the current OpenClaw workspace: create a `task_resume.py` adapter from the installed template, add run cards and checkpoints for long-running phases, enable heartbeat-based auto-resume only for safe phases, update the skill docs with the minimal usage, and then show me exactly how to use it.

## 3) Run a temporary long task

> Run this as a resumable long task under openclaw-task-runtime in the current OpenClaw workspace. If no skill exists yet, scaffold a temporary adapter under `tmp/task-runtime/<task-slug>/task_resume.py`, create a run card, checkpoint the safe phases, enable heartbeat auto-resume, and at minimum leave me either a final result, a partial result, or a clear block report: <replace this with your task>
