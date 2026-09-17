from dataclasses import replace
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from warden_sandbox_infra.models import TaskSandboxInputs
from warden_sandbox_infra.task_inputs import prepare_sandbox_uploads


class PrivateDocumentUploadTests(unittest.TestCase):
    def test_private_uploads_are_hash_pinned_and_client_scoped(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime-config" / "client-a"
            private = root / "private-inputs" / "client-a"
            runtime.mkdir(parents=True)
            private.mkdir(parents=True)
            for name in ("workflow.json", "roadmap.json"):
                (runtime / name).write_text("{}")
            document = private / "standard.md"
            document.write_text("Private reference text")
            digest = hashlib.sha256(document.read_bytes()).hexdigest()
            raw = dict(schema_version=2, client_slug="client-a", client_runtime_key="client-a",
                       client_runtime_dir=str(runtime), client_runtime_destination=".warden-inputs/clients/client-a",
                       workflow_config_path=str(runtime / "workflow.json"), roadmap_path=str(runtime / "roadmap.json"),
                       private_evidence_files=[str(document)], private_evidence_hashes={str(document): digest})
            inputs = TaskSandboxInputs.from_value(raw)

            def prepare(value):
                return prepare_sandbox_uploads(value, client_runtime_root=str(runtime.parent),
                                               private_source_roots=(str(private.parent),), sandbox_repo_root="/workspace/warden")

            bundle = prepare(inputs)
            self.assertEqual(len(bundle.uploads), 3)
            self.assertEqual(bundle.uploads[-1].destination_path, "/workspace/warden/.warden-inputs/private/client-a/standard.md")
            self.assertEqual(bundle.uploads[-1].mode, 0o600)
            with self.assertRaisesRegex(ValueError, "hash"):
                prepare(replace(inputs, private_evidence_hashes={}))
            document.write_text("Changed after task creation")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                prepare(inputs)
            document.write_text("Private reference text")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                prepare(replace(inputs, private_evidence_files=(str(document), str(document))))
            sibling = private.parent / "client-b"
            sibling.mkdir()
            other = sibling / "other.md"
            other.write_text("Sibling private source")
            with self.assertRaisesRegex(ValueError, "selected client"):
                prepare(replace(inputs, private_evidence_files=(str(other),)))
            linked = private / "linked.md"
            linked.symlink_to(document)
            with self.assertRaisesRegex(ValueError, "symlink"):
                prepare(replace(inputs, private_evidence_files=(str(linked),)))
            with self.assertRaisesRegex(ValueError, "256"):
                TaskSandboxInputs.from_value({**raw, "private_evidence_files": [str(document)] * 257})
            with self.assertRaisesRegex(ValueError, "object"):
                TaskSandboxInputs.from_value({**raw, "private_evidence_hashes": []})

    def test_large_selected_corpus_uploads_without_weakening_hash_checks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime-config" / "client-a"
            private = root / "private-inputs" / "client-a"
            runtime.mkdir(parents=True)
            private.mkdir(parents=True)
            for name in ("workflow.json", "roadmap.json"):
                (runtime / name).write_text("{}")
            paths = []
            hashes = {}
            for i in range(226):
                source = private / f"document-{i}.txt"
                source.write_text(f"Synthetic selected source {i}")
                paths.append(str(source))
                hashes[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
            inputs = TaskSandboxInputs.from_value(dict(schema_version=2, client_slug="client-a", client_runtime_key="client-a",
                client_runtime_dir=str(runtime), client_runtime_destination=".warden-inputs/clients/client-a",
                workflow_config_path=str(runtime / "workflow.json"), roadmap_path=str(runtime / "roadmap.json"),
                private_evidence_files=paths, private_evidence_hashes=hashes))
            bundle = prepare_sandbox_uploads(inputs, client_runtime_root=str(runtime.parent),
                private_source_roots=(str(private.parent),), sandbox_repo_root="/workspace/warden")
            self.assertEqual(len(bundle.uploads), 228)
            self.assertEqual(len({u.destination_path for u in bundle.uploads}), 228)
            with self.assertRaisesRegex(ValueError, "256"):
                prepare_sandbox_uploads(replace(inputs, private_evidence_files=tuple(paths + paths[:31])),
                    client_runtime_root=str(runtime.parent), private_source_roots=(str(private.parent),), sandbox_repo_root="/workspace/warden")
