from __future__ import annotations

import unittest

from warden_sandbox_infra.models import (
    TASK_LEASE_SELECT,
    TASK_SANDBOX_INPUTS_SELECT,
    TaskLease,
    TaskSandboxInputs,
)
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

    def test_parses_warden_schema_v2_sandbox_destinations(self) -> None:
        inputs = TaskSandboxInputs.from_value(
            {
                "schema_version": 2,
                "client_slug": "inkwarden",
                "client_runtime_key": "inkwarden",
                "client_runtime_dir": "/host/runtime-config/inkwarden",
                "client_runtime_destination": ".warden-inputs/clients/inkwarden",
                "workflow_config_path": "/host/runtime-config/inkwarden/workflow.json",
                "roadmap_path": "/host/runtime-config/inkwarden/assets/roadmap.json",
                "private_source_file": "/host/private-inputs/inkwarden/source.txt",
                "private_source_destination": ".warden-inputs/private/inkwarden/source.txt",
            }
        )

        self.assertIsNotNone(inputs)
        assert inputs is not None
        self.assertEqual(inputs.schema_version, 2)
        self.assertEqual(inputs.client_runtime_destination, ".warden-inputs/clients/inkwarden")
        self.assertEqual(inputs.private_source_destination, ".warden-inputs/private/inkwarden/source.txt")

    async def test_reads_only_the_sandbox_input_projection_after_claim(self) -> None:
        store = RecordingSupabaseTaskStore("https://example.supabase.co", "secret")

        with self.assertRaisesRegex(Exception, "Task does not exist"):
            await store.get_task_sandbox_inputs("task-1")

        self.assertEqual(
            store.select_params,
            [{"select": TASK_SANDBOX_INPUTS_SELECT, "id": "eq.task-1", "limit": "1"}],
        )


if __name__ == "__main__":
    unittest.main()
