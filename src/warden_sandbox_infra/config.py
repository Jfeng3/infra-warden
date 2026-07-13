from __future__ import annotations

from dataclasses import dataclass
import os
import socket
from typing import Mapping


DEFAULT_LEASE_TTL_SECONDS = 10 * 60
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_SANDBOX_TIMEOUT_SECONDS = 60 * 60
DEFAULT_FORWARDED_ENV = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY")


@dataclass(frozen=True)
class ControllerConfig:
    supabase_url: str
    supabase_key: str
    worker_id: str
    worker_command: str
    runtime: str
    e2b_template: str | None
    command_cwd: str | None
    lease_ttl_seconds: int
    lease_renew_interval_seconds: float
    poll_interval_seconds: float
    sandbox_timeout_seconds: int
    command_timeout_seconds: int
    forwarded_env_names: tuple[str, ...]
    max_concurrent_tasks: int = 20
    codex_auth_path: str | None = None

    def worker_env(self, task_id: str, source_env: Mapping[str, str] = os.environ) -> dict[str, str]:
        env = {
            "WARDEN_TASK_ID": task_id,
            "WARDEN_WORKER_ID": self.worker_id,
        }
        for name in self.forwarded_env_names:
            value = source_env.get(name)
            if value:
                env[name] = value
        return env


def load_config(env: Mapping[str, str] = os.environ) -> ControllerConfig:
    supabase_url = _required(env, "SUPABASE_URL")
    supabase_key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_ANON_KEY")
    if not supabase_key:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY must be set")

    worker_id = env.get("WARDEN_WORKER_ID") or f"local:{socket.gethostname()}:{os.getpid()}"
    worker_command = _required(env, "WARDEN_WORKER_COMMAND")
    runtime = env.get("WARDEN_SANDBOX_RUNTIME", "e2b").strip().lower()
    if runtime not in {"e2b", "local"}:
        raise ValueError("WARDEN_SANDBOX_RUNTIME must be 'e2b' or 'local'")

    lease_ttl = _int_env(env, "WARDEN_LEASE_TTL_SECONDS", DEFAULT_LEASE_TTL_SECONDS)
    renew_default = min(120.0, max(30.0, lease_ttl / 4))
    renew_interval = _float_env(env, "WARDEN_LEASE_RENEW_INTERVAL_SECONDS", renew_default)

    configured_forwarded_env = tuple(
        item.strip()
        for item in env.get("WARDEN_SANDBOX_ENV", ",".join(DEFAULT_FORWARDED_ENV)).split(",")
        if item.strip()
    )
    forwarded_env = tuple(dict.fromkeys((*DEFAULT_FORWARDED_ENV, *configured_forwarded_env)))
    codex_auth_raw = env.get("WARDEN_CODEX_AUTH_PATH", "~/.codex/auth.json").strip()

    return ControllerConfig(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        worker_id=worker_id,
        worker_command=worker_command,
        runtime=runtime,
        e2b_template=env.get("E2B_TEMPLATE") or env.get("WARDEN_E2B_TEMPLATE"),
        command_cwd=env.get("WARDEN_WORKER_CWD"),
        lease_ttl_seconds=lease_ttl,
        lease_renew_interval_seconds=renew_interval,
        poll_interval_seconds=_float_env(env, "WARDEN_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS),
        sandbox_timeout_seconds=_int_env(env, "WARDEN_SANDBOX_TIMEOUT_SECONDS", DEFAULT_SANDBOX_TIMEOUT_SECONDS),
        command_timeout_seconds=_int_env(env, "WARDEN_COMMAND_TIMEOUT_SECONDS", 0),
        forwarded_env_names=forwarded_env,
        max_concurrent_tasks=max(1, _int_env(env, "WARDEN_MAX_CONCURRENT_TASKS", 20)),
        codex_auth_path=os.path.expanduser(codex_auth_raw) if runtime == "e2b" and codex_auth_raw else None,
    )


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise ValueError(f"{name} must be set")
    return value


def _int_env(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _float_env(env: Mapping[str, str], name: str, default: float) -> float:
    value = env.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
