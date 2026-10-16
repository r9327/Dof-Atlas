"""Fail-closed preflight for the supplemental installed-binary certification."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.distribution.manifest import ReleaseFile
from app.distribution.release_client import UpdateError
from scripts.windows.certify_public_install import verify_release_inventory


class InstalledCertificationInventoryTests(unittest.TestCase):
    def test_missing_or_wrong_required_source_blocks_even_with_craft_seed(self):
        name = "quest_categories.json"
        pin = {"size": 17, "sha256": "a" * 64}
        lock = {"assets": {name: pin}}
        source = "AtlasApp/_internal/data/cache/dofus_maps/raw/doduda_cli/" + name
        seed = ReleaseFile("AtlasApp/_internal/data/bootstrap/craft_seed.sqlite", 12, "b" * 64)
        for files in ((seed,), (seed, ReleaseFile(source, 17, "c" * 64)),
                      (seed, ReleaseFile(source, 18, "a" * 64))):
            with self.subTest(files=files), patch(
                "scripts.windows.certify_public_install.read_lock", return_value=lock
            ):
                with self.assertRaisesRegex(UpdateError, "Public locked JSON missing/corrupt"):
                    verify_release_inventory(SimpleNamespace(manifest=SimpleNamespace(files=files)), Path("."))

    def test_pinned_json_does_not_replace_required_craft_database(self):
        lock = {"assets": {"quests.json": {"size": 19, "sha256": "d" * 64}}}
        entry = ReleaseFile("AtlasApp/_internal/data/cache/dofus_maps/raw/doduda_cli/quests.json",
                            19, "d" * 64)
        remote = SimpleNamespace(manifest=SimpleNamespace(files=(entry,)))
        with patch("scripts.windows.certify_public_install.read_lock", return_value=lock):
            with self.assertRaisesRegex(UpdateError, "Public Craft seed is missing"):
                verify_release_inventory(remote, Path("."))
            remote.manifest.files += (ReleaseFile(
                "AtlasApp/_internal/data/bootstrap/craft_seed.sqlite", 12, "b" * 64),)
            self.assertEqual(verify_release_inventory(remote, Path(".")), lock)


if __name__ == "__main__":
    unittest.main()
