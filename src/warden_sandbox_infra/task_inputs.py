from __future__ import annotations

from pathlib import Path
import re

from .models import SandboxUpload, SandboxUploadBundle, TaskSandboxInputs


_SAFE_CLIENT_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def prepare_sandbox_uploads(
    inputs: TaskSandboxInputs | None,
    *,
    client_runtime_root: str | None,
    private_source_roots: tuple[str, ...],
) -> SandboxUploadBundle | None:
    if inputs is None:
        return None
    if type(inputs.schema_version) is not int or inputs.schema_version != 1:
        raise ValueError(f"unsupported sandbox_inputs schema_version: {inputs.schema_version}")
    if not isinstance(inputs.client_slug, str) or not _SAFE_CLIENT_SLUG.fullmatch(inputs.client_slug):
        raise ValueError("sandbox_inputs client_slug must be safe kebab-case")
    if not isinstance(inputs.client_runtime_key, str) or not _SAFE_CLIENT_SLUG.fullmatch(inputs.client_runtime_key):
        raise ValueError("sandbox_inputs client_runtime_key must be safe kebab-case")
    if not client_runtime_root:
        raise ValueError("WARDEN_CLIENT_RUNTIME_ROOT is required for client task inputs")

    runtime_root = _existing_directory(client_runtime_root, "client runtime root")
    client_dir = _existing_directory(inputs.client_runtime_dir, "client runtime directory")
    if client_dir.is_symlink():
        raise ValueError(f"client runtime directory must not be a symlink: {client_dir}")
    if client_dir.parent.resolve() != runtime_root.resolve() or client_dir.name != inputs.client_runtime_key:
        raise ValueError("client runtime directory does not match the allowlisted root and client_runtime_key")

    workflow_config = _existing_file(inputs.workflow_config_path, "workflow config")
    roadmap = _existing_file(inputs.roadmap_path, "roadmap")
    for label, file_path in (("workflow config", workflow_config), ("roadmap", roadmap)):
        if not _inside(file_path, client_dir):
            raise ValueError(f"{label} must live inside the selected client runtime directory")

    uploads: list[SandboxUpload] = []
    for file_path in sorted(client_dir.rglob("*")):
        if file_path.is_symlink():
            raise ValueError(f"client runtime package must not contain symlinks: {file_path}")
        if file_path.is_file():
            uploads.append(_upload(file_path))

    if inputs.private_source_file:
        private_file = _existing_file(inputs.private_source_file, "private source file")
        if private_file.suffix.lower() not in {".md", ".txt"}:
            raise ValueError("private source file must be Markdown or text")
        if _inside(private_file, client_dir):
            raise ValueError("private source file must live outside the client runtime package")
        allowed_roots = [_existing_directory(root, "private source root") for root in private_source_roots]
        if not any(_inside(private_file, root) for root in allowed_roots):
            raise ValueError("private source file is outside WARDEN_PRIVATE_SOURCE_ROOTS")
        uploads.append(_upload(private_file))

    return SandboxUploadBundle(tuple(uploads))


def _existing_directory(value: str, label: str) -> Path:
    path = _absolute_path(value, label)
    if not path.is_dir():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def _existing_file(value: str, label: str) -> Path:
    path = _absolute_path(value, label)
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def _absolute_path(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path: {value}")
    return path


def _inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _upload(path: Path) -> SandboxUpload:
    absolute = str(path.resolve())
    return SandboxUpload(source_path=absolute, destination_path=absolute, mode=0o600)
