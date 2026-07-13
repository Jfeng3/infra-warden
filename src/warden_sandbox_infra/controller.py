from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from .config import ControllerConfig
from .lease_keeper import LeaseKeeper
from .models import SandboxRunResult, TaskLease
from .ports import SandboxRuntime, TaskStore
from .supabase_store import LeaseLostError


RunStatus = Literal["idle", "not_claimed", "completed", "failed", "lost_lease"]


@dataclass(frozen=True)
class RunOnceResult:
    status: RunStatus
    task_id: str | None = None
    message: str | None = None


class SandboxController:
    def __init__(self, config: ControllerConfig, store: TaskStore, runtime: SandboxRuntime) -> None:
        self.config = config
        self.store = store
        self.runtime = runtime

    async def run_once(self) -> RunOnceResult:
        task = await self.store.poll_claimable_task(self.config.worker_id)
        if task is None:
            return RunOnceResult(status="idle")

        return await self._run_task(task)

    async def run_task(self, task_id: str) -> RunOnceResult:
        """Claim and execute one explicit task without polling another queue item."""
        return await self._run_task(TaskLease(id=task_id, status="pending"))

    async def _run_task(self, task: TaskLease) -> RunOnceResult:

        claimed = await self.store.claim_task(
            task.id,
            self.config.worker_id,
            self.config.lease_ttl_seconds,
        )
        if not claimed:
            return RunOnceResult(status="not_claimed", task_id=task.id)

        env = self.config.worker_env(task.id)
        try:
            async with LeaseKeeper(
                store=self.store,
                task_id=task.id,
                worker_id=self.config.worker_id,
                lease_ttl_seconds=self.config.lease_ttl_seconds,
                renew_interval_seconds=self.config.lease_renew_interval_seconds,
            ):
                result = await self.runtime.run_task(
                    command=self.config.worker_command,
                    env=env,
                    cwd=self.config.command_cwd,
                    timeout_seconds=self.config.command_timeout_seconds,
                    task_id=task.id,
                    worker_id=self.config.worker_id,
                )
        except LeaseLostError as exc:
            return RunOnceResult(status="lost_lease", task_id=task.id, message=str(exc))
        except Exception as exc:
            await self._fail_if_owned(task.id, str(exc))
            return RunOnceResult(status="failed", task_id=task.id, message=str(exc))

        if result.exit_code == 0:
            await self.store.complete_task(task.id, _result_text(result), self.config.worker_id)
            return RunOnceResult(status="completed", task_id=task.id)

        message = result.error or f"worker command exited with code {result.exit_code}"
        if result.stderr:
            message = f"{message}\n{result.stderr.strip()}"
        await self.store.fail_task(task.id, message, self.config.worker_id)
        return RunOnceResult(status="failed", task_id=task.id, message=message)

    async def run_forever(self) -> None:
        active: dict[str, asyncio.Task[RunOnceResult]] = {}
        try:
            while True:
                finished = [task_id for task_id, run in active.items() if run.done()]
                for task_id in finished:
                    run = active.pop(task_id)
                    run.result()

                while len(active) < self.config.max_concurrent_tasks:
                    task = await self.store.poll_claimable_task(self.config.worker_id)
                    if task is None or task.id in active:
                        break
                    active[task.id] = asyncio.create_task(self._run_task(task))
                    # Let the task claim its lease before polling for another row.
                    await asyncio.sleep(0)

                if active:
                    await asyncio.wait(
                        active.values(),
                        timeout=self.config.poll_interval_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                else:
                    await asyncio.sleep(self.config.poll_interval_seconds)
        finally:
            for run in active.values():
                run.cancel()
            await asyncio.gather(*active.values(), return_exceptions=True)

    async def _fail_if_owned(self, task_id: str, message: str) -> None:
        with suppress(LeaseLostError):
            await self.store.fail_task(task_id, message, self.config.worker_id)


def _result_text(result: SandboxRunResult) -> str:
    text = result.stdout.strip()
    if result.stderr.strip():
        text = f"{text}\n\nSTDERR:\n{result.stderr.strip()}".strip()
    return text or "(worker completed with no output)"
