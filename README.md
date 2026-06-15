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
- Docs are updated when repo contracts or runtime behavior change.
