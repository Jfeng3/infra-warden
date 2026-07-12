from __future__ import annotations

import unittest

from warden_sandbox_infra.models import TASK_LEASE_SELECT, TaskLease
from warden_sandbox_infra.supabase_store import SupabaseTaskStore


class RecordingSupabaseTaskStore(SupabaseTaskStore):
    def __post_init__(self) -> None:
        self.select_params: list[dict[str, str]] = []

    async def _select_one(self, params: dict[str, str]) -> dict[str, object] | None:
        self.select_params.append(params)
        return None


class TaskContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_poll_claimable_task_uses_infra_task_column_whitelist(self) -> None:
        store = RecordingSupabaseTaskStore("https://example.supabase.co", "secret")

        result = await store.poll_claimable_task("e2b-controller-1")

        self.assertIsNone(result)
        self.assertEqual(len(store.select_params), 3)
        for params in store.select_params:
            self.assertEqual(params["select"], TASK_LEASE_SELECT)
            self.assertNotIn("*", params["select"])
            self.assertNotIn("metadata", params["select"])
            self.assertNotIn("workflow_progress", params["select"])
            self.assertNotIn("instruction", params["select"])
            self.assertEqual(params["metadata->>target_worker_id"], "eq.e2b-controller-1")

    def test_task_lease_does_not_expose_app_owned_fields(self) -> None:
        task = TaskLease.from_row(
            {
                "id": "task-1",
                "status": "pending",
                "instruction": "business-owned prompt",
                "metadata": {"owner": "warden-app"},
                "workflow_progress": {"step": "publish"},
            }
        )

        self.assertFalse(hasattr(task, "instruction"))
        self.assertFalse(hasattr(task, "metadata"))
        self.assertFalse(hasattr(task, "workflow_progress"))


if __name__ == "__main__":
    unittest.main()
