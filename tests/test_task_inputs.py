from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from warden_sandbox_infra.models import TaskSandboxInputs
from warden_sandbox_infra.task_inputs import prepare_sandbox_uploads


class TaskInputTests(unittest.TestCase):
    def test_packages_one_client_and_one_selected_private_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime_root = root / "runtime-config"
            client_dir = runtime_root / "client-a"
            private_root = root / "private-inputs"
            workflow = client_dir / "workflow.json"
            roadmap = client_dir / "assets" / "roadmap.json"
            voice = client_dir / "voice.md"
            private = private_root / "client-a" / "source.txt"
            sibling = runtime_root / "client-b" / "workflow.json"
            roadmap.parent.mkdir(parents=True)
            private.parent.mkdir(parents=True)
            sibling.parent.mkdir(parents=True)
            workflow.write_text("{}")
            roadmap.write_text("{}")
            voice.write_text("voice")
            private.write_text("private")
            sibling.write_text("{}")

            bundle = prepare_sandbox_uploads(
                TaskSandboxInputs(
                    schema_version=2,
                    client_slug="client-a",
                    client_runtime_key="client-a",
                    client_runtime_dir=str(client_dir),
                    client_runtime_destination=".warden-inputs/clients/client-a",
                    workflow_config_path=str(workflow),
                    roadmap_path=str(roadmap),
                    private_source_file=str(private),
                    private_source_destination=".warden-inputs/private/client-a/source.txt",
                ),
                client_runtime_root=str(runtime_root),
                private_source_roots=(str(private_root),),
                sandbox_repo_root="/workspace/warden",
            )

            assert bundle is not None
            uploaded = {item.source_path for item in bundle.uploads}
            self.assertEqual(uploaded, {str(path.resolve()) for path in (workflow, roadmap, voice, private)})
            self.assertNotIn(str(sibling.resolve()), uploaded)
            destinations = {item.source_path: item.destination_path for item in bundle.uploads}
            self.assertEqual(
                destinations[str(workflow.resolve())],
                "/workspace/warden/.warden-inputs/clients/client-a/workflow.json",
            )
            self.assertEqual(
                destinations[str(roadmap.resolve())],
                "/workspace/warden/.warden-inputs/clients/client-a/assets/roadmap.json",
            )
            self.assertEqual(
                destinations[str(voice.resolve())],
                "/workspace/warden/.warden-inputs/clients/client-a/voice.md",
            )
            self.assertEqual(
                destinations[str(private.resolve())],
                "/workspace/warden/.warden-inputs/private/client-a/source.txt",
            )
            self.assertTrue(all(item.mode == 0o600 for item in bundle.uploads))

    def test_rejects_private_file_outside_allowlist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime_root = root / "runtime-config"
            client_dir = runtime_root / "client-a"
            allowed = root / "allowed"
            outside = root / "outside" / "source.txt"
            workflow = client_dir / "workflow.json"
            roadmap = client_dir / "roadmap.json"
            client_dir.mkdir(parents=True)
            allowed.mkdir()
            outside.parent.mkdir()
            workflow.write_text("{}")
            roadmap.write_text("{}")
            outside.write_text("private")

            with self.assertRaisesRegex(ValueError, "outside WARDEN_PRIVATE_SOURCE_ROOTS"):
                prepare_sandbox_uploads(
                    TaskSandboxInputs(
                        schema_version=2,
                        client_slug="client-a",
                        client_runtime_key="client-a",
                        client_runtime_dir=str(client_dir),
                        client_runtime_destination=".warden-inputs/clients/client-a",
                        workflow_config_path=str(workflow),
                        roadmap_path=str(roadmap),
                        private_source_file=str(outside),
                        private_source_destination=".warden-inputs/private/client-a/source.txt",
                    ),
                    client_runtime_root=str(runtime_root),
                    private_source_roots=(str(allowed),),
                    sandbox_repo_root="/workspace/warden",
                )

    def test_rejects_cross_client_runtime_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime_root = root / "runtime-config"
            client_dir = runtime_root / "client-b"
            workflow = client_dir / "workflow.json"
            roadmap = client_dir / "roadmap.json"
            client_dir.mkdir(parents=True)
            workflow.write_text("{}")
            roadmap.write_text("{}")

            with self.assertRaisesRegex(ValueError, "does not match"):
                prepare_sandbox_uploads(
                    TaskSandboxInputs(
                        schema_version=2,
                        client_slug="client-a",
                        client_runtime_key="client-a",
                        client_runtime_dir=str(client_dir),
                        client_runtime_destination=".warden-inputs/clients/client-a",
                        workflow_config_path=str(workflow),
                        roadmap_path=str(roadmap),
                    ),
                    client_runtime_root=str(runtime_root),
                    private_source_roots=(),
                    sandbox_repo_root="/workspace/warden",
                )

    def test_rejects_task_controlled_destination_outside_fixed_layout(self) -> None:
        with TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime-config"
            client_dir = runtime_root / "client-a"
            workflow = client_dir / "workflow.json"
            roadmap = client_dir / "roadmap.json"
            client_dir.mkdir(parents=True)
            workflow.write_text("{}")
            roadmap.write_text("{}")

            with self.assertRaisesRegex(ValueError, "client_runtime_destination must be"):
                prepare_sandbox_uploads(
                    TaskSandboxInputs(
                        schema_version=2,
                        client_slug="client-a",
                        client_runtime_key="client-a",
                        client_runtime_dir=str(client_dir),
                        client_runtime_destination="src/client-a",
                        workflow_config_path=str(workflow),
                        roadmap_path=str(roadmap),
                    ),
                    client_runtime_root=str(runtime_root),
                    private_source_roots=(),
                    sandbox_repo_root="/workspace/warden",
                )


if __name__ == "__main__":
    unittest.main()
