# Task Runtime Adapters

This document defines the adapter contract for `openclaw-task-runtime`.

The runtime stays generic. Each skill provides only a thin `task_resume.py` adapter that knows how to safely resume that skill's phases.

## Execution path

```text
heartbeat -> task_runtime_watch.py -> task_runtime_resume.py -> skill adapter
```

## When you need an adapter

You need an adapter when:

- a task wants auto-resume
- recovery logic depends on skill-specific artifacts or phases
- only part of the task is safe to replay

## Required task-card fields

For resumable work, populate at least:

- `task_type`
- `phase`
- `artifacts`
- `allow_auto_resume`
- `safe_to_retry`
- `stale_after_minutes`
- `max_retries`
- `resume_adapter`

## Adapter command shape

The runtime will invoke adapters like this:

```bash
python3 <adapter> --task-id <task_id> [--timeout-seconds 180]
```

## Adapter responsibilities

An adapter should:

1. load the task card
2. inspect `phase` and `artifacts`
3. resume only safe/idempotent phases
4. call existing skill logic or scripts
5. write back updated `status`, `phase`, `artifacts`, and `last_checkpoint_at`
6. return JSON on stdout when possible

## Adapter boundaries

### Good adapter behavior

- resume report rendering from an already-generated normalized JSON
- resume summary generation from saved intermediate artifacts
- resume validation from a stored candidate set

### Bad adapter behavior

- blindly replay the entire task
- auto-repeat irreversible side effects
- bypass `safe_to_retry`
- invent a second scheduler inside the adapter

## Recommended phase split

Use simple phases so recovery points are obvious:

1. `plan`
2. `collect`
3. `analyze`
4. `render`
5. `deliver`

Most auto-resume work should happen in `collect`, `analyze`, or `render`.
`deliver` should usually be guarded.

## Template

Use `templates/task_resume.py` as a starting point.
