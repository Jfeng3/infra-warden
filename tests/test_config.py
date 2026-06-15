from __future__ import annotations

import unittest

from warden_sandbox_infra.config import load_config


class ConfigTests(unittest.TestCase):
    def test_worker_env_is_task_scoped(self) -> None:
        config = load_config(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "secret",
                "WARDEN_WORKER_COMMAND": "warden worker",
                "WARDEN_WORKER_ID": "worker-1",
                "WARDEN_SANDBOX_RUNTIME": "local",
                "WARDEN_SANDBOX_ENV": "SUPABASE_URL,SUPABASE_SERVICE_ROLE_KEY,MISSING",
            }
        )

        env = config.worker_env(
            "task-1",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "secret",
            },
        )

        self.assertEqual(env["WARDEN_TASK_ID"], "task-1")
        self.assertEqual(env["WARDEN_WORKER_ID"], "worker-1")
        self.assertEqual(env["SUPABASE_SERVICE_ROLE_KEY"], "secret")
        self.assertNotIn("MISSING", env)


if __name__ == "__main__":
    unittest.main()
