from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_warden_task.py"
SPEC = importlib.util.spec_from_file_location("run_warden_task", SCRIPT_PATH)
assert SPEC and SPEC.loader
run_warden_task = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_warden_task)


class RunWardenTaskScriptTests(unittest.TestCase):
    def test_build_env_loads_reviewed_warden_values_and_overrides_ad_hoc_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            infra_env = root / "infra.env"
            warden_env = root / "warden.env"
            infra_env.write_text(
                "E2B_API_KEY=e2b-secret\n"
                "E2B_TEMPLATE=2026-07-18-bmi-blog\n"
                "SUPABASE_URL=https://example.supabase.co\n"
                "SUPABASE_ANON_KEY=anon-secret\n"
            )
            warden_env.write_text(
                "SUPABASE_SERVICE_ROLE_KEY=service-secret\n"
                "POSTHOG_API_KEY=posthog-secret\n"
                "POSTHOG_HOST=https://posthog.example\n"
                "DATAFORSEO_LOGIN=data-login\n"
                "STRIPE_SECRET_KEY=must-not-cross-boundary\n"
            )

            env = run_warden_task.build_controller_env(
                {
                    "WARDEN_SANDBOX_ENV": "POSTHOG_API_KEY",
                    "WARDEN_WORKER_COMMAND": "npm run warden -- worker-task --task-id '$WARDEN_TASK_ID",
                },
                infra_env,
                warden_env,
            )

        self.assertEqual(env["POSTHOG_API_KEY"], "posthog-secret")
        self.assertEqual(env["DATAFORSEO_LOGIN"], "data-login")
        self.assertEqual(env["SUPABASE_SERVICE_ROLE_KEY"], "service-secret")
        self.assertNotIn("STRIPE_SECRET_KEY", env)
        self.assertIn("POSTHOG_API_KEY", env["WARDEN_SANDBOX_ENV"].split(","))
        self.assertIn("DATAFORSEO_LOGIN", env["WARDEN_SANDBOX_ENV"].split(","))
        self.assertEqual(env["WARDEN_SANDBOX_RUNTIME"], "e2b")
        self.assertEqual(env["WARDEN_WORKER_COMMAND"], run_warden_task.CANONICAL_WORKER_COMMAND)

    def test_explicit_host_value_wins_over_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            infra_env = root / "infra.env"
            warden_env = root / "warden.env"
            infra_env.write_text("E2B_API_KEY=file-value\n")
            warden_env.write_text("POSTHOG_API_KEY=file-value\n")

            env = run_warden_task.build_controller_env(
                {"E2B_API_KEY": "host-value"},
                infra_env,
                warden_env,
            )

        self.assertEqual(env["E2B_API_KEY"], "host-value")

    def test_dotenv_parser_keeps_json_backslashes_and_quoted_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text(
                'GOOGLE_SERVICE_ACCOUNT_KEY={"private_key":"line\\nline"}\n'
                'RESEND_FROM_EMAIL="InkWarden <hello@example.com>"\n'
                "PLAIN=value # comment\n"
            )

            values = run_warden_task._read_env_file(path)

        self.assertEqual(values["GOOGLE_SERVICE_ACCOUNT_KEY"], '{"private_key":"line\\nline"}')
        self.assertEqual(values["RESEND_FROM_EMAIL"], "InkWarden <hello@example.com>")
        self.assertEqual(values["PLAIN"], "value")


if __name__ == "__main__":
    unittest.main()
