# Warden Sandbox Infra Interview Questions

Date: 2026-06-16

## Questions

1. This repo keeps Warden business logic in `../warden` and only collaborates through `task_id + Supabase API contract`. How would you preserve that boundary while preventing task-state semantics from drifting between infra and app?

   Engineering focus: Architecture, separation of concerns, contract design.

   Code areas: `ports.py`, `models.py`, `supabase_store.py`.

2. `SupabaseTaskStore.claim_task()` supports `pending`, legacy `running` tasks with no lease, and expired `running` tasks. When multiple workers race to claim the same task, how would you prove the claim flow is safe? What database constraints or RPC would make it stronger?

   Engineering focus: Distributed systems, concurrency, data consistency.

   Code areas: `SupabaseTaskStore.claim_task()`, Supabase `warden_tasks` contract.

3. `SandboxController.run_once()` starts the sandbox runtime and lease renewal concurrently. Analyze what should happen if lease renewal fails, the sandbox succeeds, or the final Supabase terminal write fails. How would you improve recoverability?

   Engineering focus: Reliability, failure modes, async orchestration.

   Code areas: `SandboxController.run_once()`, `_renew_until_done()`, terminal task writes.

4. The repo has both `LocalCommandRuntime` and `E2BSandboxRuntime`. How would you design the runtime abstraction so local tests and E2B production runs have consistent timeout, cancellation, cleanup, `stdout`, `stderr`, and `error` semantics?

   Engineering focus: Interface design, adapter pattern, runtime abstraction.

   Code areas: `SandboxRuntime`, `LocalCommandRuntime`, `E2BSandboxRuntime`, `SandboxRunResult`.

5. In production, a task keeps cycling between `running` and being re-claimed. What signals would you inspect first, and what observability would you add, such as structured logs, metrics, sandbox metadata, Supabase task snapshots, or error taxonomy?

   Engineering focus: Observability, production debugging, SRE.

   Code areas: controller logs, Supabase task fields, E2B sandbox metadata.

6. `make check` currently runs `compileall` and `unittest`; tests cover completed tasks, failed commands, idle queue, and lost lease cancellation. What tests would you add for confidence around Supabase REST queries, lease TTL and renewal intervals, timeout handling, secret forwarding, and E2B failure paths?

   Engineering focus: Testing strategy, verification, CI.

   Code areas: `tests/test_controller.py`, `tests/test_config.py`, `Makefile`.

## Short Answer Themes

- Keep infra responsible for execution lifecycle, not product workflow lifecycle.
- Use narrow models, narrow `select` fields, and command-style store APIs.
- Make task claiming atomic at the database boundary.
- Treat lease renewal, sandbox execution, and terminal writes as separate failure domains.
- Keep runtime behavior consistent through a small, explicit `SandboxRuntime` contract.
- Add observability before production debugging depends on guessing.
- Use tests to lock down queue semantics, failure paths, and field-level contracts.
