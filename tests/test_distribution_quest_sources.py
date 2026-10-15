"""Windows distributions must contain the real, pinned Quest source dataset."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.quest_catalog import QUEST_CATALOG_SOURCE_FILES
from app.distribution.release_client import UpdateError
from scripts.windows.materialize_quest_sources import (
    REQUIRED_SOURCE_NAMES, QuestSourceBundleError, load_lock,
    materialize_bundle, verify_bundle,
)
from scripts.windows.probe_public_release import verify_public_quest_sources


class QuestSourceDistributionTests(unittest.TestCase):
    def sample(self):
        data = b'{"references":{"RefIds":[{"data":{"id":1}}]}}'
        entry = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        files = {
            name: {**entry, "asset": name.removeprefix("languages/")}
            for name in sorted(REQUIRED_SOURCE_NAMES)
        }
        return data, {"schema_version": 1, "repository": "dofusdude/dofus3-main",
                      "release_tag": "3.7.10.10", "files": files}

    def test_lock_has_every_runtime_quest_dependency(self):
        self.assertEqual(REQUIRED_SOURCE_NAMES,
                         frozenset(relative for _name, relative in QUEST_CATALOG_SOURCE_FILES))
        lock = load_lock()
        self.assertEqual(lock["release_tag"], "3.7.10.10")
        self.assertEqual(set(lock["files"]), REQUIRED_SOURCE_NAMES)
        self.assertGreater(sum(f["size"] for f in lock["files"].values()), 100_000_000)
        self.assertTrue(all(len(f["sha256"]) == 64 for f in lock["files"].values()))

    def test_missing_quest_categories_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            _data, lock = self.sample()
            with self.assertRaisesRegex(QuestSourceBundleError, "Missing/invalid"):
                verify_bundle(Path(directory), lock)

    def test_materialization_downloads_all_pinned_assets_and_reuses_them(self):
        with tempfile.TemporaryDirectory() as directory:
            data, lock = self.sample()
            fetched = []
            def opener(request, *, timeout):
                fetched.append(request.full_url)
                self.assertEqual(timeout, 90)
                self.assertTrue(request.full_url.startswith(
                    "https://github.com/dofusdude/dofus3-main/releases/download/3.7.10.10/"))
                return io.BytesIO(data)
            root = Path(directory)
            self.assertEqual(materialize_bundle(root, lock, opener=opener), 21)
            self.assertEqual(len(fetched), 21)
            self.assertEqual(verify_bundle(root, lock), 21)
            self.assertTrue((root / "languages" / "fr.json").is_file())
            self.assertTrue((root / "quest_categories.json").is_file())
            self.assertEqual(materialize_bundle(root, lock, opener=opener), 21)
            self.assertEqual(len(fetched), 21)

    def test_upstream_hash_mismatch_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            _data, lock = self.sample()
            with self.assertRaisesRegex(QuestSourceBundleError, "SHA-256/size mismatch"):
                materialize_bundle(Path(directory), lock,
                                   opener=lambda request, timeout: io.BytesIO(b"invalid"))
            self.assertFalse((Path(directory) / "quest_categories.json").is_file())

    def test_existing_tampered_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data, lock = self.sample()
            root = Path(directory)
            materialize_bundle(root, lock, opener=lambda req, timeout: io.BytesIO(data))
            (root / "quest_categories.json").write_text("changed")
            with self.assertRaisesRegex(QuestSourceBundleError, "quest_categories.json"):
                verify_bundle(root, lock)

    def test_disallow_symlinked_source_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "real"
            target.mkdir()
            link = root / "linked"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("This runner does not permit symlinks")
            _data, lock = self.sample()
            with self.assertRaisesRegex(QuestSourceBundleError, "symlink"):
                materialize_bundle(link, lock, opener=lambda req, timeout: io.BytesIO(b""))

    def test_installed_package_probe_failure_blocks_e2e_pass(self):
        with patch("scripts.windows.probe_public_release.subprocess.run",
                   return_value=Mock(returncode=3, stderr="missing quest source")):
            with self.assertRaisesRegex(UpdateError, "Quest sources"):
                verify_public_quest_sources(Path("AtlasApp.exe"), env={})

    def test_installed_package_probe_passes_only_on_zero(self):
        with patch("scripts.windows.probe_public_release.subprocess.run",
                   return_value=Mock(returncode=0, stderr="")) as runner:
            verify_public_quest_sources(Path("AtlasApp.exe"), env={})
            self.assertEqual(runner.call_args.args[0][-1], "--atlas-package-smoke")

    def test_workflow_materializes_and_certifies_before_publication(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/atlas-windows-distribution.yml").read_text(
                        encoding="utf-8")
        self.assertLess(workflow.index("Materialize pinned Quest sources"),
                        workflow.index("Compile application bundle with QtWebEngine"))
        self.assertLess(workflow.index("Verify mandatory Quest JSON survived"),
                        workflow.index("Package ZIP, manifest and launcher"))
        self.assertIn("Execute frozen Quest catalogue worker", workflow)
        self.assertIn("quest_sources_lock.json", workflow)


if __name__ == "__main__":
    unittest.main()
