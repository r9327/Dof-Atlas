"""Canonical Guide reward projections: same output, no user progress and safe fallback."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.services import guide_prebuilt_rewards as prebuilt
from app.modules.encyclopedia.services.guide_quest_view_model import guide_rewards


class GuideRewardIndexTests(unittest.TestCase):
    def _fixture(self):
        guide = SimpleNamespace(
            id="alignement_bonta", category="alignements", reward_item=None,
            context_entities=[], parts=[],
            required_steps=[
                SimpleNamespace(step_type="quest", entity_id=2),
                SimpleNamespace(step_type="quest", entity_id=1),
                SimpleNamespace(step_type="quest", entity_id=2),
            ],
        )
        def reward(kind, name, quantity, image_path=""):
            return SimpleNamespace(kind=kind, name=name, quantity=quantity, image_path=image_path)
        quests = SimpleNamespace(by_id={
            1: SimpleNamespace(rewards=[reward("kamas", "Kamas", 100)], source_info={}),
            2: SimpleNamespace(rewards=[reward("item", "Cristal", 2, "data/images/cristal.png")], source_info={}),
        })
        achievements = SimpleNamespace(get_by_id=lambda _id: None)
        return guide, quests, achievements

    def test_rewards_exactly_equal_to_original_with_quest_order_and_deduplication(self):
        guide, quests, achievements = self._fixture()
        ids = (2, 1)
        expected = guide_rewards(
            guide, achievements,
            (quests.by_id[qid] for qid in ids),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "rewards.json"
            with patch.object(prebuilt, "_guide_sha", return_value="source-guide-sha"), patch.object(
                prebuilt, "_source_sizes", return_value={"quests.json": 1234}
            ):
                summary = prebuilt.write_bundle(
                    [guide], quests, achievements, output, source_sha="a" * 40,
                )
                self.assertEqual(summary["guides"], 1)
                cached = prebuilt.cached_rewards(guide, path=output)
                self.assertEqual(cached, expected)
                self.assertEqual(
                    [x["quantity"] for x in json.loads(output.read_text())["guides"][guide.id]["rewards"]
                     if x["kind"] == "kamas"], [100],
                )
                self.assertNotIn("character:", output.read_text())
                self.assertNotIn("quest_progress", output.read_text())

    def test_bad_source_and_corruption_fall_back_instead_of_hiding_rewards(self):
        guide, quests, achievements = self._fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rewards.json"
            with patch.object(prebuilt, "_guide_sha", return_value="abc"), patch.object(
                prebuilt, "_source_sizes", return_value={"quests.json": 7}
            ):
                prebuilt.write_bundle([guide], quests, achievements, path, source_sha="b" * 40)
                payload = json.loads(path.read_text())
                payload["quest_source_sizes"]["quests.json"] = 8
                path.write_text(json.dumps(payload))
                self.assertIsNone(prebuilt.cached_rewards(guide, path=path))
                path.write_text("not json")
                self.assertIsNone(prebuilt.cached_rewards(guide, path=path))
                self.assertIsNone(prebuilt.cached_rewards(guide, path=path.with_name("missing.json")))
                with self.assertRaises(ValueError):
                    prebuilt.write_bundle([guide], quests, achievements, path, source_sha="bad")

    def test_portable_asset_paths_and_no_external_absolute_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = prebuilt.ROOT_DIR / "data/images/misc/logo.png"
            encoded = prebuilt._encode_path(str(local))
            self.assertTrue(encoded.startswith("@atlas-root/"))
            self.assertEqual(prebuilt._decode_path(encoded), str(local))
            with self.assertRaises(ValueError):
                prebuilt._decode_path("@atlas-root/../../escape.png")
            with self.assertRaises(ValueError):
                prebuilt._encode_path(str(Path(tmp) / "foreign.png"))

    def test_unbundled_developer_does_not_trust_unknown_release(self):
        guide, _, _ = self._fixture()
        with patch.dict("os.environ", {"DOFUS_ATLAS_PREBUILT_REWARDS_FILE": ""}):
            self.assertIsNone(prebuilt.cached_rewards(guide))


if __name__ == "__main__":
    unittest.main()
