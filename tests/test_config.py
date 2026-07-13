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

    def test_e2b_config_expands_codex_auth_path(self) -> None:
        config = load_config(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "secret",
                "WARDEN_WORKER_COMMAND": "warden worker-task",
                "WARDEN_SANDBOX_RUNTIME": "e2b",
                "WARDEN_CODEX_AUTH_PATH": "/secure/codex-auth.json",
            }
        )

        self.assertEqual(config.codex_auth_path, "/secure/codex-auth.json")

    def test_required_supabase_credentials_are_forwarded_even_with_custom_env_list(self) -> None:
        config = load_config(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "secret",
                "WARDEN_WORKER_COMMAND": "warden worker-task",
                "WARDEN_SANDBOX_RUNTIME": "e2b",
                "WARDEN_SANDBOX_ENV": "POSTHOG_API_KEY",
            }
        )

        self.assertEqual(
            config.forwarded_env_names,
            ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "POSTHOG_API_KEY"),
        )


if __name__ == "__main__":
    unittest.main()
