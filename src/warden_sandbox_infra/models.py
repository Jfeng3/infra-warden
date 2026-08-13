from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


TaskStatus = Literal["pending", "running", "done", "failed"]
TASK_LEASE_COLUMNS = (
    "id",
    "status",
    "worker_id",
    "lease_expires_at",
    "started_at",
    "completed_at",
    "result",
    "error",
)
TASK_LEASE_SELECT = ",".join(TASK_LEASE_COLUMNS)
TASK_SANDBOX_INPUTS_SELECT = "sandbox_inputs:metadata->sandbox_inputs"


@dataclass(frozen=True)
class TaskLease:
    id: str
    status: TaskStatus
    worker_id: str | None = None
    lease_expires_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    result: str | None = None
    error: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TaskLease":
        return cls(
            id=str(row["id"]),
            status=row.get("status", "pending"),
            worker_id=row.get("worker_id"),
            lease_expires_at=row.get("lease_expires_at"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            result=row.get("result"),
            error=row.get("error"),
        )


@dataclass(frozen=True)
class TaskSandboxInputs:
    schema_version: int
    client_slug: str
    client_runtime_key: str
    client_runtime_dir: str
    workflow_config_path: str
    roadmap_path: str
    private_source_file: str = ""

    @classmethod
    def from_value(cls, value: Any) -> "TaskSandboxInputs | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("task metadata.sandbox_inputs must be an object")
        return cls(
            schema_version=value.get("schema_version"),
            client_slug=value.get("client_slug"),
            client_runtime_key=value.get("client_runtime_key"),
            client_runtime_dir=value.get("client_runtime_dir"),
            workflow_config_path=value.get("workflow_config_path"),
            roadmap_path=value.get("roadmap_path"),
            private_source_file=value.get("private_source_file", ""),
        )


@dataclass(frozen=True)
class SandboxUpload:
    source_path: str
    destination_path: str
    mode: int = 0o600


@dataclass(frozen=True)
class SandboxUploadBundle:
    uploads: tuple[SandboxUpload, ...]


@dataclass(frozen=True)
class SandboxRunResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    sandbox_id: str | None = None
