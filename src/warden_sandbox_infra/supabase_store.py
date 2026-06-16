from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .models import TASK_LEASE_SELECT, TaskLease


class SupabaseError(RuntimeError):
    pass


class LeaseLostError(RuntimeError):
    pass


@dataclass
class SupabaseTaskStore:
    supabase_url: str
    supabase_key: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        base_url = self.supabase_url.rstrip("/")
        self._table_url = f"{base_url}/rest/v1/warden_tasks"
        self._client = httpx.AsyncClient(timeout=self.timeout_seconds)

    async def __aenter__(self) -> "SupabaseTaskStore":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def poll_claimable_task(self) -> TaskLease | None:
        pending = await self._select_one(
            {
                "select": TASK_LEASE_SELECT,
                "status": "eq.pending",
                "order": "created_at.asc",
                "limit": "1",
            }
        )
        if pending:
            return TaskLease.from_row(pending)

        legacy_running = await self._select_one(
            {
                "select": TASK_LEASE_SELECT,
                "status": "eq.running",
                "lease_expires_at": "is.null",
                "order": "started_at.asc",
                "limit": "1",
            }
        )
        if legacy_running:
            return TaskLease.from_row(legacy_running)

        expired_running = await self._select_one(
            {
                "select": TASK_LEASE_SELECT,
                "status": "eq.running",
                "lease_expires_at": f"lt.{_now_iso()}",
                "order": "lease_expires_at.asc",
                "limit": "1",
            }
        )
        return TaskLease.from_row(expired_running) if expired_running else None

    async def claim_task(self, task_id: str, worker_id: str, lease_ttl_seconds: int) -> bool:
        now = _now_iso()
        pending_update = {
            "status": "running",
            "worker_id": worker_id,
            "lease_expires_at": _lease_expiry_iso(lease_ttl_seconds),
            "started_at": now,
            "completed_at": None,
            "error": None,
        }
        rows = await self._patch(
            {"id": f"eq.{task_id}", "status": "eq.pending", "select": "id"},
            pending_update,
        )
        if rows:
            return True

        reclaim_update = {
            "status": "running",
            "worker_id": worker_id,
            "lease_expires_at": _lease_expiry_iso(lease_ttl_seconds),
            "completed_at": None,
            "error": None,
        }
        rows = await self._patch(
            {
                "id": f"eq.{task_id}",
                "status": "eq.running",
                "lease_expires_at": "is.null",
                "select": "id",
            },
            reclaim_update,
        )
        if rows:
            return True

        rows = await self._patch(
            {
                "id": f"eq.{task_id}",
                "status": "eq.running",
                "lease_expires_at": f"lt.{now}",
                "select": "id",
            },
            reclaim_update,
        )
        return bool(rows)

    async def renew_task_lease(self, task_id: str, worker_id: str, lease_ttl_seconds: int) -> bool:
        rows = await self._patch(
            {
                "id": f"eq.{task_id}",
                "status": "eq.running",
                "worker_id": f"eq.{worker_id}",
                "select": "id",
            },
            {"lease_expires_at": _lease_expiry_iso(lease_ttl_seconds)},
        )
        return bool(rows)

    async def complete_task(self, task_id: str, result: str, worker_id: str) -> None:
        rows = await self._patch(
            {"id": f"eq.{task_id}", "worker_id": f"eq.{worker_id}", "select": "id"},
            {
                "status": "done",
                "result": result,
                "completed_at": _now_iso(),
                "lease_expires_at": None,
            },
        )
        if not rows:
            raise LeaseLostError(f"Task {task_id} is not owned by worker {worker_id}")

    async def fail_task(self, task_id: str, error: str, worker_id: str) -> None:
        rows = await self._patch(
            {"id": f"eq.{task_id}", "worker_id": f"eq.{worker_id}", "select": "id"},
            {
                "status": "failed",
                "error": error,
                "completed_at": _now_iso(),
                "lease_expires_at": None,
            },
        )
        if not rows:
            raise LeaseLostError(f"Task {task_id} is not owned by worker {worker_id}")

    async def _select_one(self, params: dict[str, str]) -> dict[str, Any] | None:
        rows = await self._request("GET", params=params)
        if not isinstance(rows, list):
            raise SupabaseError("Expected Supabase select response to be a list")
        return rows[0] if rows else None

    async def _patch(self, params: dict[str, str], payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = await self._request("PATCH", params=params, json=payload, prefer="return=representation")
        if not isinstance(rows, list):
            raise SupabaseError("Expected Supabase update response to be a list")
        return rows

    async def _request(
        self,
        method: str,
        *,
        params: dict[str, str],
        json: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
        }
        if prefer:
            headers["Prefer"] = prefer
        response = await self._client.request(
            method,
            self._table_url,
            params=params,
            json=json,
            headers=headers,
        )
        if response.status_code >= 400:
            raise SupabaseError(f"Supabase {method} failed with {response.status_code}: {response.text}")
        if not response.content:
            return None
        return response.json()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _lease_expiry_iso(lease_ttl_seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=lease_ttl_seconds)).isoformat().replace("+00:00", "Z")
