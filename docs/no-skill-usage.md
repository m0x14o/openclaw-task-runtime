# No-skill usage

You do **not** need a formal OpenClaw skill before using `openclaw-task-runtime`.

That is the most common beginner misunderstanding.

## Key idea

`resume_adapter` is just a script path.

It does **not** have to live under `skills/`.

So you have two modes:

1. **Skill mode**
   - use `skills/<skill>/scripts/task_resume.py`
   - best for repeated, reusable workflows

2. **Ad-hoc mode**
   - use `tmp/task-runtime/<task-slug>/task_resume.py`
   - best for one-off long tasks that still need checkpointing and auto-resume

## Recommended path for beginners

Start in ad-hoc mode first.

If the task repeats, then promote it into a proper skill.

## One-line prompt for ad-hoc mode

Send this to your own OpenClaw:

> Install and enable https://github.com/m0x14o/openclaw-task-runtime in the current OpenClaw workspace: clone it into `repos/openclaw-task-runtime`, run `python3 install.py`, wire the task recovery check into `HEARTBEAT.md`, and if no skill exists for this task, create a temporary resume adapter under `tmp/task-runtime/<task-slug>/task_resume.py`, create a run card, checkpoint safe phases, and run this job under the recovery layer so it can resume automatically.

## Minimal ad-hoc example

### 1. Copy the template

```bash
mkdir -p ~/.openclaw/workspace/tmp/task-runtime/my-task
cp ~/.openclaw/workspace/templates/openclaw-task-runtime/task_resume.py \
  ~/.openclaw/workspace/tmp/task-runtime/my-task/task_resume.py
```

### 2. Create a run card that points to that temporary adapter

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime.py create \
  --task-type ad-hoc-task \
  --title "My one-off long task" \
  --mode overnight \
  --phase render \
  --resume-adapter ~/.openclaw/workspace/tmp/task-runtime/my-task/task_resume.py \
  --allow-auto-resume \
  --stale-after-minutes 30 \
  --max-retries 2
```

### 3. Later, if the task becomes stable and reusable

Move the adapter into a real skill:

```text
skills/<your-skill>/scripts/task_resume.py
```

That is all. The recovery layer stays the same.
