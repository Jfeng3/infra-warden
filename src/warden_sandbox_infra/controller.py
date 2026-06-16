from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from .config import ControllerConfig
from .models import SandboxRunResult
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
        task = await self.store.poll_claimable_task()
        if task is None:
            return RunOnceResult(status="idle")

        claimed = await self.store.claim_task(
            task.id,
            self.config.worker_id,
            self.config.lease_ttl_seconds,
        )
        if not claimed:
            return RunOnceResult(status="not_claimed", task_id=task.id)

        env = self.config.worker_env(task.id)
        run_task = asyncio.create_task(
            self.runtime.run_task(
                command=self.config.worker_command,
                env=env,
                cwd=self.config.command_cwd,
                timeout_seconds=self.config.command_timeout_seconds,
                task_id=task.id,
                worker_id=self.config.worker_id,
            )
        )
        stop_renewing = asyncio.Event()
        renew_task = asyncio.create_task(self._renew_until_done(task.id, stop_renewing))

        try:
            done, _ = await asyncio.wait(
                {run_task, renew_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if renew_task in done:
                renew_task.result()

            result = await run_task
        except LeaseLostError as exc:
            run_task.cancel()
            with suppress(asyncio.CancelledError):
                await run_task
            return RunOnceResult(status="lost_lease", task_id=task.id, message=str(exc))
        except Exception as exc:
            await self._fail_if_owned(task.id, str(exc))
            return RunOnceResult(status="failed", task_id=task.id, message=str(exc))
        finally:
            stop_renewing.set()
            if not renew_task.done():
                renew_task.cancel()
                with suppress(asyncio.CancelledError):
                    await renew_task

        if result.exit_code == 0:
            await self.store.complete_task(task.id, _result_text(result), self.config.worker_id)
            return RunOnceResult(status="completed", task_id=task.id)

        message = result.error or f"worker command exited with code {result.exit_code}"
        if result.stderr:
            message = f"{message}\n{result.stderr.strip()}"
        await self.store.fail_task(task.id, message, self.config.worker_id)
        return RunOnceResult(status="failed", task_id=task.id, message=message)

    async def run_forever(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self.config.poll_interval_seconds)

    async def _renew_until_done(self, task_id: str, stop: asyncio.Event) -> None:
        while not stop.is_set():
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.config.lease_renew_interval_seconds)
                break
            ok = await self.store.renew_task_lease(
                task_id,
                self.config.worker_id,
                self.config.lease_ttl_seconds,
            )
            if not ok:
                raise LeaseLostError(f"Task {task_id} lease is no longer owned by {self.config.worker_id}")

    async def _fail_if_owned(self, task_id: str, message: str) -> None:
        with suppress(LeaseLostError):
            await self.store.fail_task(task_id, message, self.config.worker_id)


def _result_text(result: SandboxRunResult) -> str:
    text = result.stdout.strip()
    if result.stderr.strip():
        text = f"{text}\n\nSTDERR:\n{result.stderr.strip()}".strip()
    return text or "(worker completed with no output)"
