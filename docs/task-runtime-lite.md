# Task Recovery Layer Lite

`openclaw-task-runtime` is a small durable recovery layer for OpenClaw workspaces.

It provides:

- run cards (`data/task-runs/*.json`)
- checkpoints
- heartbeat-based stale detection
- safe auto-resume via adapters
- watchdog signals that make silent stalls visible (`alerts`, `recoveries`, `needs_attention`)

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

1. a run card exists
2. `allow_auto_resume = true`
3. the task has `resume_adapter` (or explicit `resume_command`)
4. the current phase is safe to retry

## Core run-card fields

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
- `watchdog` (internal dedupe state for stale / recovery notifications)

## Heartbeat wiring

The installer appends or refreshes this section in `HEARTBEAT.md`:

````md
## Task Recovery Check
Run:

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime_watch.py --auto-resume
```

If it reports any `alerts`, `recoveries`, or `needs_attention`, summarize them briefly.
Treat them as:
- `alerts`: a task went silent / stale
- `recoveries`: watchdog auto-resume moved the task forward
- `needs_attention`: watchdog could not safely recover it or retries are exhausted
If it reports no actionable signals, move on without mentioning it.
````

## Watchdog signal semantics

The watchdog report intentionally separates three user-facing buckets:

- `alerts`: new “this task went silent” signals for the current watchdog pass
- `recoveries`: successful auto-resume signals for the current watchdog pass
- `needs_attention`: fresh escalations that now need a human

For manual debugging, the report also includes `active_needs_attention`, which shows current unresolved attention items without spamming the same escalation every heartbeat.

## Minimal commands

### Create a run card

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

## Boundary

OpenClaw itself should remain the platform scheduler, including cron, sessions, and background tasks.
This layer exists to keep business recovery state, checkpoints, and safe resume paths auditable.
