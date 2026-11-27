"""Stable Quest/Guide release signature and fail-closed compatibility."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.core.file_stamp import source_file_sizes
from app.modules.encyclopedia.services.guide_release_signature import guide_steps_sha256


class ReleaseSignatureTests(unittest.TestCase):
    def test_guide_steps_digest_matches_original_release_shape(self) -> None:
        steps = [
            SimpleNamespace(id="q:1", step_type="quest", entity_id=42, order=1),
            SimpleNamespace(id="q:2", step_type="quest", entity_id=43, order=2),
        ]
        guide = SimpleNamespace(required_steps=steps)
        expected_rows = [("q:1", "quest", "42", 1), ("q:2", "quest", "43", 2)]
        expected = hashlib.sha256(
            json.dumps(expected_rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(guide_steps_sha256(guide), expected)
        self.assertNotEqual(guide_steps_sha256(SimpleNamespace(required_steps=list(reversed(steps)))), expected)
        self.assertEqual(guide_steps_sha256(SimpleNamespace(required_steps=[])), hashlib.sha256(b"[]").hexdigest())

    def test_portable_source_sizes_preserve_strict_and_missing_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "quests.json").write_bytes(b"one")
            sources = (("quests", "quests.json"), ("missing", "missing.json"))
            self.assertEqual(
                source_file_sizes(root, sources),
                {"quests.json": 3, "missing.json": -1},
            )
            with self.assertRaises(FileNotFoundError):
                source_file_sizes(root, sources, allow_missing=False)
            self.assertEqual(
                source_file_sizes(root, (("quests", "quests.json"),), allow_missing=False),
                {"quests.json": 3},
            )

    def test_both_guide_bundle_consumers_share_the_same_step_signer(self) -> None:
        from app.modules.encyclopedia.services import (
            guide_catalog_prebuilt_route, guide_prebuilt_rewards,
        )
        self.assertIs(guide_prebuilt_rewards._steps_sha, guide_steps_sha256)
        self.assertIs(guide_catalog_prebuilt_route._steps_digest, guide_steps_sha256)


if __name__ == "__main__":
    unittest.main()
