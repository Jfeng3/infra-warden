from __future__ import annotations

import asyncio
import json
import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from shlex import quote
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
    codex_auth_path: str | None = None
    vercel_auth_path: str | None = None
    vercel_project_path: str | None = None

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
        codex_auth = _read_codex_auth(self.codex_auth_path) if self.codex_auth_path else None
        vercel_auth = _read_vercel_auth(self.vercel_auth_path) if self.vercel_auth_path else None
        vercel_project = _read_vercel_project(self.vercel_project_path) if self.vercel_project_path else None
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
            if codex_auth is not None:
                await _upload_codex_auth(sandbox, codex_auth)
            if vercel_auth is not None:
                await _upload_vercel_auth(sandbox, vercel_auth)
            if vercel_project is not None:
                await _upload_vercel_project(sandbox, vercel_project, cwd)
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


def _read_codex_auth(path: str) -> bytes:
    auth_path = Path(path)
    try:
        data = auth_path.read_bytes()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Codex auth file not found: {auth_path}") from exc
    try:
        parsed = json.loads(data)
        tokens = parsed["tokens"]
        if not tokens.get("access_token") or not tokens.get("refresh_token"):
            raise ValueError("missing OAuth tokens")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Codex auth file is invalid: {auth_path}") from exc
    return data


def _read_vercel_auth(path: str) -> bytes:
    data, parsed, auth_path = _read_json_file(path, "Vercel auth")
    if not isinstance(parsed.get("token"), str) or not parsed["token"].strip():
        raise RuntimeError(f"Vercel auth file is invalid: {auth_path}")
    return data


def _read_vercel_project(path: str) -> bytes:
    data, parsed, project_path = _read_json_file(path, "Vercel project")
    required = ("orgId", "projectId")
    if any(not isinstance(parsed.get(key), str) or not parsed[key].strip() for key in required):
        raise RuntimeError(f"Vercel project file is invalid: {project_path}")
    return data


def _read_json_file(path: str, label: str) -> tuple[bytes, dict[str, Any], Path]:
    file_path = Path(path)
    try:
        data = file_path.read_bytes()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} file not found: {file_path}") from exc
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} file is invalid: {file_path}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} file is invalid: {file_path}")
    return data, parsed, file_path


async def _upload_codex_auth(sandbox: Any, data: bytes) -> None:
    directory = "/home/user/.codex"
    destination = f"{directory}/auth.json"
    await sandbox.files.make_dir(directory, user="user")
    await sandbox.files.write(destination, data, user="user")
    await sandbox.commands.run(
        f"chmod 700 {directory} && chmod 600 {destination}",
        user="user",
        timeout=30,
    )


async def _upload_vercel_auth(sandbox: Any, data: bytes) -> None:
    directory = "/home/user/.local/share/com.vercel.cli"
    destination = f"{directory}/auth.json"
    await sandbox.files.make_dir(directory, user="user")
    await sandbox.files.write(destination, data, user="user")
    await sandbox.commands.run(
        f"chmod 700 {quote(directory)} && chmod 600 {quote(destination)}",
        user="user",
        timeout=30,
    )


async def _upload_vercel_project(sandbox: Any, data: bytes, cwd: str | None) -> None:
    repo_root = PurePosixPath(cwd or "/workspace/warden")
    directory = str(repo_root / ".vercel")
    destination = f"{directory}/project.json"
    await sandbox.files.make_dir(directory, user="user")
    await sandbox.files.write(destination, data, user="user")
    await sandbox.commands.run(
        f"chmod 700 {quote(directory)} && chmod 600 {quote(destination)}",
        user="user",
        timeout=30,
    )


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
