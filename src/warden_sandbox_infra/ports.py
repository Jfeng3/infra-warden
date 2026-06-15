from __future__ import annotations

from typing import Protocol

from .models import SandboxRunResult, Task


class TaskStore(Protocol):
    async def poll_claimable_task(self) -> Task | None: ...

    async def claim_task(self, task_id: str, worker_id: str, lease_ttl_seconds: int) -> bool: ...

    async def renew_task_lease(self, task_id: str, worker_id: str, lease_ttl_seconds: int) -> bool: ...

    async def complete_task(self, task_id: str, result: str, worker_id: str) -> None: ...

    async def fail_task(self, task_id: str, error: str, worker_id: str) -> None: ...


class SandboxRuntime(Protocol):
    async def run_task(
        self,
        *,
        command: str,
        env: dict[str, str],
        cwd: str | None,
        timeout_seconds: int,
        task_id: str,
        worker_id: str,
    ) -> SandboxRunResult: ...
