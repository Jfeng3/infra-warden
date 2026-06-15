from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


TaskStatus = Literal["pending", "running", "done", "failed"]


@dataclass(frozen=True)
class Task:
    id: str
    instruction: str
    status: TaskStatus
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    workflow_progress: dict[str, Any] | None = None
    worker_id: str | None = None
    lease_expires_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Task":
        return cls(
            id=str(row["id"]),
            instruction=str(row.get("instruction") or ""),
            status=row.get("status", "pending"),
            result=row.get("result"),
            error=row.get("error"),
            metadata=row.get("metadata"),
            workflow_progress=row.get("workflow_progress"),
            worker_id=row.get("worker_id"),
            lease_expires_at=row.get("lease_expires_at"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
        )


@dataclass(frozen=True)
class SandboxRunResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    sandbox_id: str | None = None
