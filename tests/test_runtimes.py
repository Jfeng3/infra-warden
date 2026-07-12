from __future__ import annotations

from dataclasses import dataclass
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from warden_sandbox_infra.runtimes import E2BSandboxRuntime


@dataclass
class FakeCommandResult:
    exit_code: int = 0
    stdout: str = "ready\n"
    stderr: str = ""
    error: str | None = None


class FakeCommands:
    def __init__(self, result: FakeCommandResult | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def run(self, command: str, **kwargs: object) -> FakeCommandResult:
        self.calls.append({"command": command, **kwargs})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeSandbox:
    def __init__(self, result: FakeCommandResult | Exception) -> None:
        self.sandbox_id = "sandbox-123"
        self.commands = FakeCommands(result)
        self.killed = False

    async def kill(self) -> None:
        self.killed = True


class FakeAsyncSandbox:
    sandbox = FakeSandbox(FakeCommandResult())
    create_calls: list[dict[str, object]] = []

    @classmethod
    async def create(cls, **kwargs: object) -> FakeSandbox:
        cls.create_calls.append(kwargs)
        return cls.sandbox


class E2BRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeAsyncSandbox.sandbox = FakeSandbox(FakeCommandResult())
        FakeAsyncSandbox.create_calls = []

    async def test_creates_runs_and_kills_task_sandbox(self) -> None:
        runtime = E2BSandboxRuntime(template="warden:v1", sandbox_timeout_seconds=600)

        with patch.dict(sys.modules, {"e2b": SimpleNamespace(AsyncSandbox=FakeAsyncSandbox)}):
            result = await runtime.run_task(
                command="npm run warden -- worker-task",
                env={"WARDEN_TASK_ID": "task-1"},
                cwd="/workspace/warden",
                timeout_seconds=300,
                task_id="task-1",
                worker_id="worker-1",
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.sandbox_id, "sandbox-123")
        self.assertEqual(
            FakeAsyncSandbox.create_calls,
            [{
                "template": "warden:v1",
                "timeout": 600,
                "envs": {"WARDEN_TASK_ID": "task-1"},
                "metadata": {"task_id": "task-1", "worker_id": "worker-1"},
            }],
        )
        self.assertEqual(
            FakeAsyncSandbox.sandbox.commands.calls,
            [{
                "command": "npm run warden -- worker-task",
                "cwd": "/workspace/warden",
                "envs": {"WARDEN_TASK_ID": "task-1"},
                "timeout": 300,
            }],
        )
        self.assertTrue(FakeAsyncSandbox.sandbox.killed)

    async def test_returns_command_failure_and_still_kills_sandbox(self) -> None:
        failure = RuntimeError("command connection failed")
        failure.exit_code = 17
        failure.stderr = "worker crashed"
        FakeAsyncSandbox.sandbox = FakeSandbox(failure)
        runtime = E2BSandboxRuntime(template="warden:v1", sandbox_timeout_seconds=600)

        with patch.dict(sys.modules, {"e2b": SimpleNamespace(AsyncSandbox=FakeAsyncSandbox)}):
            result = await runtime.run_task(
                command="false",
                env={},
                cwd=None,
                timeout_seconds=60,
                task_id="task-1",
                worker_id="worker-1",
            )

        self.assertEqual(result.exit_code, 17)
        self.assertEqual(result.stderr, "worker crashed")
        self.assertEqual(result.error, "command connection failed")
        self.assertTrue(FakeAsyncSandbox.sandbox.killed)


if __name__ == "__main__":
    unittest.main()
