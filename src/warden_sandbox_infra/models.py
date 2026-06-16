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
class SandboxRunResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    sandbox_id: str | None = None
