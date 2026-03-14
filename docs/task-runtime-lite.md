# Task Runtime Lite

`openclaw-task-runtime` is a small durable execution layer for OpenClaw workspaces.

It provides:

- task cards (`data/task-runs/*.json`)
- checkpoints
- heartbeat-based stale detection
- safe auto-resume via adapters

## Installation shape

This project is designed to be installed **into an existing OpenClaw workspace**.

After `python3 install.py`, the important pieces land in:

- `<workspace>/scripts/task_runtime.py`
- `<workspace>/scripts/task_runtime_watch.py`
- `<workspace>/scripts/task_runtime_resume.py`
- `<workspace>/docs/openclaw-task-runtime/`
- `<workspace>/templates/openclaw-task-runtime/`

## Auto-enable behavior

Heartbeat runs the watchdog globally, but a task is only auto-managed when all of these are true:

1. a task card exists
2. `allow_auto_resume = true`
3. the task has `resume_adapter` (or explicit `resume_command`)
4. the current phase is safe to retry

## Core task-card fields

- `id`
- `task_type`
- `title`
- `mode`
- `status`
- `phase`
- `last_checkpoint_at`
- `retry_count`
- `max_retries`
- `allow_auto_resume`
- `safe_to_retry`
- `resume_adapter`
- `resume_command`
- `artifacts`

## Heartbeat wiring

The installer appends this section to `HEARTBEAT.md` if it is not already present:

````md
## Task Runtime Recovery Check
Run:

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime_watch.py --auto-resume
```

If it reports any `resumed` tasks or `needs_attention` tasks, summarize them briefly.
If it reports no stale tasks, move on without mentioning it.
````

## Minimal commands

### Create a task card

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime.py create \
  --task-type my-long-task \
  --title "My long-running task" \
  --mode overnight \
  --phase collect \
  --resume-adapter ~/.openclaw/workspace/skills/my-skill/scripts/task_resume.py \
  --allow-auto-resume \
  --stale-after-minutes 30 \
  --max-retries 2
```

### Write a checkpoint

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime.py checkpoint <task_id> \
  --phase render \
  --artifact normalized_input=/tmp/job-normalized.json \
  --message "ready to resume rendering"
```

### List stale resumable tasks

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime.py stale --require-resume-command
```

### Run the watchdog manually

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime_watch.py --auto-resume
```
