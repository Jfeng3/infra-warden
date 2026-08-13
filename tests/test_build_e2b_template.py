from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_e2b_template.py"
SPEC = importlib.util.spec_from_file_location("build_e2b_template", SCRIPT_PATH)
assert SPEC and SPEC.loader
build_e2b_template = importlib.util.module_from_spec(SPEC)
with patch.dict(
    sys.modules,
    {"e2b": SimpleNamespace(Template=object, default_build_logger=lambda: None)},
):
    SPEC.loader.exec_module(build_e2b_template)


class BuildE2BTemplateTests(unittest.TestCase):
    def test_export_excludes_all_client_delivery_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            (source / "package.json").write_text("{}")
            client_file = source / "client-delivery" / "client-a" / "workflow.json"
            client_file.parent.mkdir(parents=True)
            client_file.write_text('{"client":"a"}')
            client_output = source / "landing" / "public" / "clients" / "client-a" / "post.html"
            client_output.parent.mkdir(parents=True)
            client_output.write_text("client output")
            source_file = source / "src" / "index.ts"
            source_file.parent.mkdir()
            source_file.write_text("export {};\n")
            subprocess.run(["git", "add", "."], cwd=source, check=True)

            build_e2b_template._export_tracked_source(source, destination)

            self.assertTrue((destination / "package.json").is_file())
            self.assertTrue((destination / "src" / "index.ts").is_file())
            self.assertFalse((destination / "client-delivery").exists())
            self.assertFalse((destination / "landing" / "public" / "clients").exists())


if __name__ == "__main__":
    unittest.main()
