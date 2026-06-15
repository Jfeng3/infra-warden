from __future__ import annotations

import argparse
import asyncio

from .config import load_config
from .controller import SandboxController
from .runtimes import E2BSandboxRuntime, LocalCommandRuntime
from .supabase_store import SupabaseTaskStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Warden tasks in sandbox workers.")
    parser.add_argument("command", choices=["run", "run-once"], help="Run forever or process one task.")
    args = parser.parse_args()
    asyncio.run(_run(args.command))


async def _run(command: str) -> None:
    config = load_config()
    store = SupabaseTaskStore(config.supabase_url, config.supabase_key)
    runtime = _build_runtime(config)
    controller = SandboxController(config, store, runtime)

    async with store:
        if command == "run-once":
            result = await controller.run_once()
            print(result)
        else:
            await controller.run_forever()


def _build_runtime(config):
    if config.runtime == "local":
        return LocalCommandRuntime()
    if not config.e2b_template:
        raise ValueError("E2B_TEMPLATE or WARDEN_E2B_TEMPLATE must be set for E2B runtime")
    return E2BSandboxRuntime(
        template=config.e2b_template,
        sandbox_timeout_seconds=config.sandbox_timeout_seconds,
    )
