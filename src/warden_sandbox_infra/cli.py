from __future__ import annotations

import argparse
import asyncio
import os

from .config import load_config
from .controller import SandboxController
from .models import SandboxRunResult
from .runtimes import E2BSandboxRuntime, LocalCommandRuntime
from .supabase_store import SupabaseTaskStore


DEFAULT_E2B_SMOKE_COMMAND = """set -eu
node --version
npm --version
test -f /workspace/warden/package.json
printf 'warden_template=ready\\n'
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Warden tasks in sandbox workers.")
    parser.add_argument(
        "command",
        choices=["run", "run-once", "run-task", "smoke-e2b"],
        help="Run forever, poll once, run an explicit task, or validate the E2B template.",
    )
    parser.add_argument("--task-id", help="Task ID required by run-task.")
    args = parser.parse_args()
    if args.command == "smoke-e2b":
        result = asyncio.run(_smoke_e2b())
        _print_sandbox_result(result)
        if result.exit_code != 0:
            raise SystemExit(result.exit_code)
        return
    if args.command == "run-task" and not args.task_id:
        parser.error("run-task requires --task-id")
    asyncio.run(_run(args.command, task_id=args.task_id))


async def _run(command: str, task_id: str | None = None) -> None:
    config = load_config()
    store = SupabaseTaskStore(config.supabase_url, config.supabase_key)
    runtime = _build_runtime(config)
    controller = SandboxController(config, store, runtime)

    async with store:
        if command == "run-task":
            assert task_id is not None
            result = await controller.run_task(task_id)
            print(result)
        elif command == "run-once":
            result = await controller.run_once()
            print(result)
        else:
            await controller.run_forever()


async def _smoke_e2b(env=os.environ) -> SandboxRunResult:
    template = env.get("E2B_TEMPLATE") or env.get("WARDEN_E2B_TEMPLATE")
    if not template:
        raise ValueError("E2B_TEMPLATE or WARDEN_E2B_TEMPLATE must be set")

    runtime = E2BSandboxRuntime(
        template=template,
        sandbox_timeout_seconds=_positive_int_env(env, "WARDEN_SANDBOX_TIMEOUT_SECONDS", 300),
    )
    return await runtime.run_task(
        command=env.get("WARDEN_E2B_SMOKE_COMMAND", DEFAULT_E2B_SMOKE_COMMAND),
        env={"WARDEN_SANDBOX_SMOKE": "1"},
        cwd=None,
        timeout_seconds=_positive_int_env(env, "WARDEN_COMMAND_TIMEOUT_SECONDS", 60),
        task_id="smoke-test",
        worker_id=env.get("WARDEN_WORKER_ID", "smoke-test"),
    )


def _positive_int_env(env, name: str, default: int) -> int:
    raw = env.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero for smoke-e2b")
    return value


def _print_sandbox_result(result: SandboxRunResult) -> None:
    if result.sandbox_id:
        print(f"sandbox_id={result.sandbox_id}")
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")
    if result.error:
        print(f"error={result.error}")


def _build_runtime(config):
    if config.runtime == "local":
        return LocalCommandRuntime()
    if not config.e2b_template:
        raise ValueError("E2B_TEMPLATE or WARDEN_E2B_TEMPLATE must be set for E2B runtime")
    return E2BSandboxRuntime(
        template=config.e2b_template,
        sandbox_timeout_seconds=config.sandbox_timeout_seconds,
    )
