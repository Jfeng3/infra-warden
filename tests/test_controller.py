from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import unittest

from warden_sandbox_infra.config import ControllerConfig
from warden_sandbox_infra.controller import SandboxController
from warden_sandbox_infra.models import SandboxRunResult, TaskLease
from warden_sandbox_infra.supabase_store import LeaseLostError


def config() -> ControllerConfig:
    return ControllerConfig(
        supabase_url="https://example.supabase.co",
        supabase_key="secret",
        worker_id="worker-1",
        worker_command="warden worker",
        runtime="local",
        e2b_template=None,
        command_cwd=None,
        lease_ttl_seconds=60,
        lease_renew_interval_seconds=0.01,
        poll_interval_seconds=0.01,
        sandbox_timeout_seconds=60,
        command_timeout_seconds=0,
        forwarded_env_names=(),
    )


@dataclass
class FakeStore:
    task: TaskLease | None
    renew_ok: bool = True
    claimed: list[str] = field(default_factory=list)
    renewed: int = 0
    completed: list[tuple[str, str, str]] = field(default_factory=list)
    failed: list[tuple[str, str, str]] = field(default_factory=list)

    async def poll_claimable_task(self) -> TaskLease | None:
        return self.task

    async def claim_task(self, task_id: str, worker_id: str, lease_ttl_seconds: int) -> bool:
        del lease_ttl_seconds
        self.claimed.append(f"{task_id}:{worker_id}")
        return True

    async def renew_task_lease(self, task_id: str, worker_id: str, lease_ttl_seconds: int) -> bool:
        del task_id, worker_id, lease_ttl_seconds
        self.renewed += 1
        return self.renew_ok

    async def complete_task(self, task_id: str, result: str, worker_id: str) -> None:
        self.completed.append((task_id, result, worker_id))

    async def fail_task(self, task_id: str, error: str, worker_id: str) -> None:
        if not self.renew_ok:
            raise LeaseLostError("lost")
        self.failed.append((task_id, error, worker_id))


@dataclass
class FakeRuntime:
    result: SandboxRunResult
    delay_seconds: float = 0
    cancelled: bool = False
    env_seen: dict[str, str] | None = None

    async def run_task(
        self,
        *,
        command: str,
        env: dict[str, str],
        cwd: str | None,
        timeout_seconds: int,
        task_id: str,
        worker_id: str,
    ) -> SandboxRunResult:
        del command, cwd, timeout_seconds, task_id, worker_id
        self.env_seen = env
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            return self.result
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_once_completes_claimed_task(self) -> None:
        store = FakeStore(TaskLease(id="task-1", status="pending"))
        runtime = FakeRuntime(SandboxRunResult(exit_code=0, stdout="done"))
        controller = SandboxController(config(), store, runtime)

        result = await controller.run_once()

        self.assertEqual(result.status, "completed")
        self.assertEqual(store.claimed, ["task-1:worker-1"])
        self.assertEqual(store.completed, [("task-1", "done", "worker-1")])
        self.assertEqual(runtime.env_seen["WARDEN_TASK_ID"], "task-1")

    async def test_run_once_fails_on_nonzero_exit(self) -> None:
        store = FakeStore(TaskLease(id="task-1", status="pending"))
        runtime = FakeRuntime(SandboxRunResult(exit_code=2, stderr="bad"))
        controller = SandboxController(config(), store, runtime)

        result = await controller.run_once()

        self.assertEqual(result.status, "failed")
        self.assertEqual(store.failed[0][0], "task-1")
        self.assertIn("worker command exited with code 2", store.failed[0][1])
        self.assertIn("bad", store.failed[0][1])

    async def test_run_once_returns_idle_when_no_task(self) -> None:
        store = FakeStore(None)
        runtime = FakeRuntime(SandboxRunResult(exit_code=0))
        controller = SandboxController(config(), store, runtime)

        result = await controller.run_once()

        self.assertEqual(result.status, "idle")
        self.assertEqual(store.claimed, [])

    async def test_lost_lease_cancels_runtime_without_terminal_write(self) -> None:
        store = FakeStore(TaskLease(id="task-1", status="pending"), renew_ok=False)
        runtime = FakeRuntime(SandboxRunResult(exit_code=0), delay_seconds=1)
        controller = SandboxController(config(), store, runtime)

        result = await controller.run_once()

        self.assertEqual(result.status, "lost_lease")
        self.assertTrue(runtime.cancelled)
        self.assertEqual(store.completed, [])
        self.assertEqual(store.failed, [])


if __name__ == "__main__":
    unittest.main()
