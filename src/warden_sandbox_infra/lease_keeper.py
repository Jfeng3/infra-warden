from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import TracebackType

from .ports import TaskStore
from .supabase_store import LeaseLostError


@dataclass
class LeaseKeeper:
    """Renew one claimed task lease while its owning controller coroutine runs."""

    store: TaskStore
    task_id: str
    worker_id: str
    lease_ttl_seconds: int
    renew_interval_seconds: float
    _stop: asyncio.Event = field(init=False, default_factory=asyncio.Event)
    _renew_task: asyncio.Task[None] | None = field(init=False, default=None)
    _owner_task: asyncio.Task[object] | None = field(init=False, default=None)
    _renew_error: Exception | None = field(init=False, default=None)

    async def __aenter__(self) -> LeaseKeeper:
        owner = asyncio.current_task()
        if owner is None:
            raise RuntimeError("LeaseKeeper must run inside an asyncio task")
        self._owner_task = owner
        self._renew_task = asyncio.create_task(
            self._renew_until_stopped(),
            name=f"lease:{self.task_id}",
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc, traceback
        self._stop.set()
        if self._renew_task is not None:
            await self._renew_task
        if self._renew_error is not None:
            raise self._renew_error
        return False

    async def _renew_until_stopped(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=self.renew_interval_seconds,
                    )
                    break
                except asyncio.TimeoutError:
                    pass

                renewed = await self.store.renew_task_lease(
                    self.task_id,
                    self.worker_id,
                    self.lease_ttl_seconds,
                )
                if not renewed:
                    raise LeaseLostError(
                        f"Task {self.task_id} lease is no longer owned by {self.worker_id}"
                    )
        except Exception as error:
            self._renew_error = error
            if self._owner_task is not None and not self._owner_task.done():
                self._owner_task.cancel()
