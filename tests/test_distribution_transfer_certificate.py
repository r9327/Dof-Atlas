"""Transfer gate: fail-closed runtime inventory, static imports and private files."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.windows.certify_app_export import TransferCertificationError, certify
from scripts.windows.export_app_repository import export, selected_runtime_path


class TransferCertificateTests(unittest.TestCase):
    def fixture(self, root: Path, *, missing_import: bool = False):
        source = root / "source"
        source.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=source, check=True)
        files = {
            "main.py": "from app.core.runtime import start\n",
            "launch.py": "import main\n",
            "app/__init__.py": "",
            "app/core/__init__.py": "",
            "app/core/runtime.py": ("from app.modules.encyclopedia.tools import audit\n"
                                    if missing_import else "def start(): pass\n"),
            "app/modules/encyclopedia/tools/audit.py": "SECRET = 'dev-only'\n",
            "local_dofus_data/__init__.py": "",
            "data/encyclopedia/guides/catalog.json": '{"ok":true}\n',
            "data/large_file_contracts.json": '{"dev":true}\n',
            "data/network/protocol_research/backlog_v1.json": '{"private":true}\n',
            "data/local/zaaps.json": '{"zaaps": []}\\n',
            "data/local/client_profiles.json": '{"private": true}\\n',
            "data/images/misc/dofus_atlas_logo.png": "PNG",
            "tests/test_export.py": "pass\n",
            "tools/graphify.py": "pass\n",
            "tools/atlas_doctor.py": "pass\n",
        }
        for name, value in files.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=source, check=True)
        destination = root / "app-only"
        export(source, destination, "a" * 40)
        return source, destination

    def test_export_certifies_without_developer_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = self.fixture(Path(tmp))
            report = certify(source, destination, "a" * 40, check_checkout=False)
            self.assertEqual(report["status"], "PASS")
            self.assertGreaterEqual(report["static_import_edges"], 1)
            for name in ("tools/graphify.py", "tools/atlas_doctor.py",
                         "app/modules/encyclopedia/tools/audit.py",
                         "data/network/protocol_research/backlog_v1.json",
                         "data/large_file_contracts.json", "data/local/client_profiles.json"):
                self.assertFalse((destination / name).exists(), name)

    def test_tampering_or_unexpected_files_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = self.fixture(Path(tmp))
            target = destination / "app/core/runtime.py"
            target.write_text("tampered\n")
            with self.assertRaises(TransferCertificationError):
                certify(source, destination, "a" * 40, check_checkout=False)
            target.write_text((source / "app/core/runtime.py").read_text())
            bad = destination / "tools/graphify.py"
            bad.parent.mkdir(parents=True)
            bad.write_text("leaked")
            with self.assertRaises(TransferCertificationError):
                certify(source, destination, "a" * 40, check_checkout=False)

    def test_runtime_cannot_import_excluded_dev_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = self.fixture(Path(tmp), missing_import=True)
            with self.assertRaisesRegex(TransferCertificationError, "excluded"):
                certify(source, destination, "a" * 40, check_checkout=False)

    def test_fails_before_mutating_destination_on_lfs_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = self.fixture(Path(tmp))
            marker = destination / "README.md"
            marker.write_text("keep")
            icon = source / "data/images/misc/dofus_atlas_logo.png"
            icon.write_text("version https://git-lfs.github.com/spec/v1\n")
            with self.assertRaises(RuntimeError):
                export(source, destination, "b" * 40)
            self.assertTrue((destination / "app/core/runtime.py").exists())
            self.assertEqual(marker.read_text(), "keep")

    def test_allowlist_denies_research_and_unknown_resources(self):
        for name in ("app/modules/encyclopedia/tools/audit.py",
                     "data/network/protocol_research/backlog_v1.json",
                     "data/large_file_contracts.json", "data/local/quest_progress.json",
                     "tools/graphify.py", "data/images/archive/unused.png"):
            self.assertFalse(selected_runtime_path(name), name)


if __name__ == "__main__":
    unittest.main()
