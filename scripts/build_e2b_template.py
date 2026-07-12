#!/usr/bin/env python3
"""Build a Warden E2B template from the committed Warden source tree."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from e2b import Template, default_build_logger


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WARDEN_REPO = REPO_ROOT.parent / "warden"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name",
        default=os.environ.get("E2B_TEMPLATE", "warden"),
        help="E2B template name or name:tag (default: E2B_TEMPLATE or warden)",
    )
    parser.add_argument(
        "--warden-repo",
        type=Path,
        default=Path(os.environ.get("WARDEN_REPO_PATH", DEFAULT_WARDEN_REPO)),
        help="Path to the Warden git checkout",
    )
    parser.add_argument("--cpu-count", type=int, default=2)
    parser.add_argument("--memory-mb", type=int, default=4096)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    source = args.warden_repo.resolve()
    _require_source_files(source)
    revision = _git(source, "rev-parse", "--short", "HEAD").decode().strip()
    if _git(source, "status", "--porcelain").strip():
        print("warning: template includes modifications to tracked Warden files")

    with tempfile.TemporaryDirectory(prefix="warden-e2b-template-") as temp_dir:
        context = Path(temp_dir)
        _export_tracked_source(source, context)
        template = (
            Template(file_context_path=context)
            .from_node_image("22")
            .copy(".", "/workspace/warden", user="user")
            .run_cmd("chown -R user:user /workspace/warden", user="root")
            .set_workdir("/workspace/warden")
            .run_cmd("HUSKY=0 npm ci")
            .run_cmd("npm run build")
            .run_cmd("test -f package.json && test -f dist/cli.js && node --version && npm --version")
        )
        build = Template.build(
            template,
            args.name,
            cpu_count=args.cpu_count,
            memory_mb=args.memory_mb,
            skip_cache=args.no_cache,
            on_build_logs=default_build_logger(),
        )

    print(f"built template={args.name} warden_revision={revision} build={build}")


def _require_source_files(source: Path) -> None:
    for relative in (".git", "package.json", "package-lock.json"):
        if not (source / relative).exists():
            raise SystemExit(f"Warden source is missing {relative}: {source}")


def _export_tracked_source(source: Path, destination: Path) -> None:
    tracked = _git(source, "ls-files", "-z").decode().split("\0")
    for relative in filter(None, tracked):
        source_path = source / relative
        if not source_path.exists() and not source_path.is_symlink():
            continue
        if source_path.is_dir() and not source_path.is_symlink():
            continue  # Gitlink/submodule; not part of the Warden runtime source.
        destination_path = destination / relative
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            destination_path.symlink_to(os.readlink(source_path))
        else:
            shutil.copy2(source_path, destination_path)


def _git(source: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=source,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


if __name__ == "__main__":
    main()
