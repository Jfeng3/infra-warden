from __future__ import annotations

import asyncio
from dataclasses import dataclass
import unittest

from warden_sandbox_infra.lease_keeper import LeaseKeeper
from warden_sandbox_infra.supabase_store import LeaseLostError


@dataclass
class RenewalStore:
    renew_ok: bool = True
    renewed: int = 0

    async def renew_task_lease(self, task_id: str, worker_id: str, lease_ttl_seconds: int) -> bool:
        self.asserted_call = (task_id, worker_id, lease_ttl_seconds)
        self.renewed += 1
        return self.renew_ok


class LeaseKeeperTests(unittest.IsolatedAsyncioTestCase):
    async def test_starts_renewing_on_enter_and_stops_on_exit(self) -> None:
        store = RenewalStore()

        async with LeaseKeeper(store, "task-1", "worker-1", 600, 0.005):
            await asyncio.sleep(0.02)

        renewals_after_exit = store.renewed
        await asyncio.sleep(0.02)

        self.assertGreaterEqual(renewals_after_exit, 1)
        self.assertEqual(store.asserted_call, ("task-1", "worker-1", 600))
        self.assertEqual(store.renewed, renewals_after_exit)

    async def test_lost_lease_cancels_the_context_body(self) -> None:
        store = RenewalStore(renew_ok=False)
        body_cancelled = False

        with self.assertRaisesRegex(LeaseLostError, "no longer owned"):
            async with LeaseKeeper(store, "task-1", "worker-1", 600, 0.005):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    body_cancelled = True
                    raise

        self.assertTrue(body_cancelled)
        self.assertEqual(store.renewed, 1)


if __name__ == "__main__":
    unittest.main()
