# AGENTS.md

Codex entrypoint for `warden-sandbox-infra`.

This repo owns sandbox infrastructure for the Warden app. The Warden app lives
next to this repo at:

- Relative path: `../warden`
- Absolute path: `/Users/jie/Codes/warden`

When working from `/Users/jie/Codes/warden-org`, `../warden` resolves through
the symlink:

```text
/Users/jie/Codes/warden-org/warden -> /Users/jie/Codes/warden
```

## Required Rule Reads

Before making infrastructure changes, read:

- `CLAUDE.md` in this repo
- `../warden/AGENTS.md`

For changes touching queue, task claiming, workers, leases, or Supabase task
state, also read:

- `../warden/src/data_model/db.ts`
- `../warden/src/data_model/types.ts`
- `../warden/src/runner.ts`
- `../warden/supabase/migrations/`
- `../warden/docs/plans/2026-06-15-supabase-db-simplification-for-e2b.md`

For changes touching artifacts, storage, files, or sandbox file transfer, also
read:

- `../warden/docs/plans/2026-06-15-e2b-artifact-storage-migration.md`
- `../warden/.claude/rules/data-flow.md`
- `../warden/.claude/rules/pipeline-flow.md`

## Repo Boundary

- This repo owns E2B/controller infrastructure, sandbox startup, task polling,
  task claiming, lease renewal, worker environment injection, and infra tests.
- Warden owns business logic, workflow steps, pipeline state, publishing rules,
  Supabase schema, dashboard behavior, and artifact semantics.
- Connect the two repos through `task_id` and the Supabase API contract.
- Do not move Warden business logic into this repo.
- Do not edit files under `../warden` from this repo unless the user explicitly
  asks for a cross-repo change.

## Standing Constraints

- Do not edit `.env`.
- Do not commit or push unless the user explicitly asks.
- Do not add dependencies without a clear justification.
- Do not store secrets in this repo.
- Keep infra code deterministic and testable.
