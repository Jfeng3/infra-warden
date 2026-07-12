# warden-sandbox-infra

Runs Warden tasks inside isolated E2B sandboxes.

## Project Goal

Claim a Warden task from Supabase, run it in an isolated E2B sandbox, keep its
lease alive, and report success or failure. Warden business logic stays in the
Warden app repo.

## Definition of Done

- Warden business logic stays out of this repo.
- Claiming, leases, timeouts, and failures are deterministic and testable.
- Secrets are read from environment/config, never hardcoded.
- Infra changes include focused tests once the test harness exists.
- `make check` passes.
- Docs are updated when repo contracts or runtime behavior change.

## Commands

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
make check
```

## Make The E2B Sandbox Work

Build a template from Warden's tracked working-tree files. This includes edits
to tracked source files for pre-commit testing, but cannot include `.env`,
`.git`, ignored credentials, generated artifacts, or unrelated untracked files:

```bash
E2B_API_KEY=<key> \
E2B_TEMPLATE=warden:dev \
make build-e2b-template
```

The build defaults to `../warden`, Node 22, 2 CPUs, and 4096 MB. Override the
source with `WARDEN_REPO_PATH`, or invoke the script directly for CPU, memory,
and cache flags.

The resulting template contains a built Warden checkout at
`/workspace/warden`. Before touching the real queue, validate that contract:

```bash
E2B_API_KEY=<key> \
E2B_TEMPLATE=<template-name-or-id> \
make smoke-e2b
```

The smoke command creates a disposable sandbox, checks Node, npm, and
`/workspace/warden/package.json`, prints the sandbox ID and versions, then kills
the sandbox. Override `WARDEN_E2B_SMOKE_COMMAND` if a template uses a different
layout.

## Claimed Task Contract

The controller claims a task before starting E2B. Therefore the command inside
the sandbox must execute exactly `WARDEN_TASK_ID` as the existing
`WARDEN_WORKER_ID`; it must not start another general queue poller.

Warden exposes `worker-task --task-id`, which validates that the task is
`running` and owned by `WARDEN_WORKER_ID`, then directly executes it without
polling. Run one task with:

```bash
WARDEN_SANDBOX_RUNTIME=e2b \
E2B_TEMPLATE=<template> \
WARDEN_WORKER_CWD=/workspace/warden \
WARDEN_WORKER_COMMAND='npm run warden -- worker-task --task-id "$WARDEN_TASK_ID"' \
python3 -m warden_sandbox_infra run-task --task-id <task-id>
```

Use `run-task` for targeted/manual jobs so older unrelated queue entries cannot
be claimed accidentally. `run-once` polls and claims the oldest available task.
Continuous `run` and `run-once` only poll tasks whose
`metadata.target_worker_id` matches `WARDEN_WORKER_ID`, keeping Mac-targeted and
E2B-targeted work isolated.

Forward only credentials the selected Warden provider and workflow need. For
example, an OpenRouter-backed worker may use:

```bash
WARDEN_SANDBOX_ENV=SUPABASE_URL,SUPABASE_ANON_KEY,OPENROUTER_API_KEY,DEFAULT_PROVIDER,DEFAULT_MODEL
```

The default `openai-codex` provider expects local Codex authentication, which is
not baked into the template. Do not copy `~/.codex/auth.json` into an image;
configure a sandbox-suitable provider credential instead.

Use `WARDEN_SANDBOX_RUNTIME=local` for local command execution during
development.
