# openclaw-task-runtime

[中文说明](./README.zh-CN.md) | [One-line prompt](./OPENCLAW_ONE_LINER.md)

A lightweight durable task runtime for OpenClaw.

It adds four missing pieces for long-running work:

- durable task cards (`data/task-runs/*.json`)
- checkpoints
- heartbeat-based stale detection
- safe auto-resume through skill adapters

This is **not** a business skill. It is a **workspace-level runtime** that any skill can plug into.

## What problem this solves

OpenClaw is great at doing work, but long jobs can still get messy:

- a run stalls overnight
- an agent loses momentum after a timeout
- report rendering fails after the expensive part already finished
- a task needs resumable phases instead of one giant black box

`openclaw-task-runtime` gives OpenClaw a small durable execution layer without introducing a heavy workflow platform.

## What this is not

- not a plugin system replacement
- not a queue
- not a generic DAG engine
- not a business-specific skill

Think of it as **LangGraph/Inngest-lite for OpenClaw workspaces**.

## One-line usage

Send this **single message** to your own OpenClaw:

> Install and enable https://github.com/m0x14o/openclaw-task-runtime in the current OpenClaw workspace: clone it into `repos/openclaw-task-runtime`, run `python3 install.py`, wire the task runtime recovery check into `HEARTBEAT.md`, and then show me the minimal `task card + resume_adapter` pattern for my next long-running task.

If your OpenClaw can run shell commands in its own workspace, that is enough.

## Manual install

Clone this repo into your OpenClaw workspace, typically:

```bash
git clone https://github.com/m0x14o/openclaw-task-runtime ~/.openclaw/workspace/repos/openclaw-task-runtime
cd ~/.openclaw/workspace/repos/openclaw-task-runtime
python3 install.py
```

The installer will:

- copy runtime scripts into `<workspace>/scripts/`
- copy docs into `<workspace>/docs/openclaw-task-runtime/`
- copy an adapter template into `<workspace>/templates/openclaw-task-runtime/`
- append an idempotent Task Runtime Recovery Check section to `<workspace>/HEARTBEAT.md`

## How it works

```text
heartbeat -> task_runtime_watch.py -> task_runtime_resume.py -> skill adapter
```

### Core files

- `scripts/task_runtime.py` — task card / run-state manager
- `scripts/task_runtime_watch.py` — heartbeat watchdog for stale resumable tasks
- `scripts/task_runtime_resume.py` — generic dispatcher for per-skill adapters
- `templates/task_resume.py` — adapter template for your own skill

## When to use it

Use this runtime for tasks that are:

- longer than ~10 minutes
- multi-phase
- resumable from file/state checkpoints
- okay to auto-retry in some phases

Examples:

- overnight research
- report generation
- batch analysis
- code analysis + tests + summary
- multi-step diagnostics that can checkpoint safely

## When **not** to auto-resume

Do **not** auto-retry irreversible side effects unless you add your own safety gate:

- sending external messages
- publishing
- deployments
- restarts
- browser confirmation clicks
- deleting data

## Minimal integration pattern

### 1. Create a task card

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime.py create \
  --task-type my-long-task \
  --title "My long-running job" \
  --mode overnight \
  --phase collect \
  --resume-adapter ~/.openclaw/workspace/skills/my-skill/scripts/task_resume.py \
  --allow-auto-resume \
  --stale-after-minutes 30 \
  --max-retries 2
```

### 2. Write checkpoints between phases

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime.py checkpoint <task_id> \
  --phase render \
  --artifact normalized_input=/tmp/job-normalized.json \
  --message "ready to render final report"
```

### 3. Implement a skill adapter

Copy the template:

```bash
cp ~/.openclaw/workspace/templates/openclaw-task-runtime/task_resume.py \
  ~/.openclaw/workspace/skills/my-skill/scripts/task_resume.py
```

Then teach that adapter how to safely recover the resumable phases for your skill.

## Adapter contract

Your adapter must:

1. accept `--task-id` and optional `--timeout-seconds`
2. load the task card
3. resume only safe/idempotent phases
4. update `status`, `phase`, `artifacts`, and `last_checkpoint_at`
5. return JSON on stdout when possible

See `docs/task-runtime-adapters.md` for the full contract.

## Design principles

This project intentionally borrows ideas from:

- LangGraph — durable/stateful task flow
- Inngest — step/run state + flow control
- Temporal — workflow discipline and replay mindset

But it stays intentionally small so it can live inside a normal OpenClaw workspace.

## Repository layout

```text
.
├── docs/
├── scripts/
├── templates/
├── install.py
└── README.md
```

## License

MIT
