from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from .models import SandboxRunResult


class LocalCommandRuntime:
    async def run_task(
        self,
        *,
        command: str,
        env: dict[str, str],
        cwd: str | None,
        timeout_seconds: int,
        task_id: str,
        worker_id: str,
    ) -> SandboxRunResult:
        del task_id, worker_id
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            env={**os.environ, **env},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            wait = process.communicate()
            if timeout_seconds > 0:
                stdout, stderr = await asyncio.wait_for(wait, timeout=timeout_seconds)
            else:
                stdout, stderr = await wait
        except asyncio.TimeoutError:
            await _kill_process(process)
            return SandboxRunResult(
                exit_code=124,
                stderr=f"worker command timed out after {timeout_seconds} seconds",
                error="timeout",
            )
        except asyncio.CancelledError:
            await _kill_process(process)
            raise

        return SandboxRunResult(
            exit_code=process.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )


@dataclass(frozen=True)
class E2BSandboxRuntime:
    template: str
    sandbox_timeout_seconds: int

    async def run_task(
        self,
        *,
        command: str,
        env: dict[str, str],
        cwd: str | None,
        timeout_seconds: int,
        task_id: str,
        worker_id: str,
    ) -> SandboxRunResult:
        try:
            from e2b import AsyncSandbox
        except ImportError as exc:
            raise RuntimeError("Install the e2b package to use WARDEN_SANDBOX_RUNTIME=e2b") from exc

        sandbox = await AsyncSandbox.create(
            template=self.template,
            timeout=self.sandbox_timeout_seconds,
            envs=env,
            metadata={"task_id": task_id, "worker_id": worker_id},
        )
        sandbox_id = _sandbox_id(sandbox)
        try:
            result = await sandbox.commands.run(
                command,
                cwd=cwd,
                envs=env,
                timeout=timeout_seconds,
            )
            return SandboxRunResult(
                exit_code=int(_attr(result, "exit_code", "exitCode", default=0)),
                stdout=str(_attr(result, "stdout", default="")),
                stderr=str(_attr(result, "stderr", default="")),
                error=_optional_str(_attr(result, "error", default=None)),
                sandbox_id=sandbox_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return SandboxRunResult(
                exit_code=int(_attr(exc, "exit_code", "exitCode", default=1)),
                stdout=str(_attr(exc, "stdout", default="")),
                stderr=str(_attr(exc, "stderr", default="")),
                error=str(exc),
                sandbox_id=sandbox_id,
            )
        finally:
            with suppress(Exception):
                await sandbox.kill()


async def _kill_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.kill()
    with suppress(Exception):
        await process.wait()


def _sandbox_id(sandbox: Any) -> str | None:
    value = _attr(sandbox, "sandbox_id", "sandboxId", default=None)
    return _optional_str(value)


def _attr(obj: Any, *names: str, default: Any) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
