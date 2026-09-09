from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
GUARDRAILS = (ROOT / "DEVELOPMENT_GUARDRAILS.md").read_text(encoding="utf-8")
FINAL = (ROOT / "tools" / "build_guide_ultime_final.py").read_text(encoding="utf-8")
GPS = (ROOT / "tools" / "build_guide_ultime_gps_route.py").read_text(encoding="utf-8")


class GuideUltimeLegacySourceContractTests(unittest.TestCase):
    def test_manual_manifest_is_the_declared_source_of_truth(self) -> None:
        self.assertIn("data/routes/guide_ultime_manual/manifest_v1.json", GUARDRAILS)
        self.assertEqual(MANIFEST["guide_id"], "guide_ultime_manual")
        self.assertIn("canonical", MANIFEST)

    def test_manifest_keeps_current_canonical_route(self) -> None:
        chapters = {row["id"]: row for row in MANIFEST["canonical"]["chapters"]}
        self.assertEqual(chapters["level_120_150"]["file"], "level_120_150_v21.json")
        self.assertEqual(chapters["level_191_200"]["file"], "level_191_200_v22.json")
        self.assertEqual(chapters["level_200_plus"]["file"], "level_200_plus_v11.json")
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters.values()), 267)

    def test_legacy_builders_write_only_generated_artifacts(self) -> None:
        self.assertIn('ARTIFACTS = ROOT / "artifacts"', FINAL)
        self.assertIn('OUT_GUIDE = ARTIFACTS / "guide_ultime_final.json"', FINAL)
        self.assertIn('ARTIFACTS = ROOT / "artifacts"', GPS)
        self.assertIn('GUIDE_PATH = ARTIFACTS / "guide_ultime_final.json"', GPS)
        self.assertIn('OUT = ARTIFACTS / "guide_ultime_gps_route.json"', GPS)

    def test_legacy_gps_builder_does_not_target_manual_canonical_files(self) -> None:
        self.assertNotIn('guide_ultime_manual/manifest_v1.json', GPS)
        self.assertNotIn('data/routes/guide_ultime_manual', GPS)

    def test_legacy_final_builder_does_not_replace_manual_manifest(self) -> None:
        self.assertNotIn('guide_ultime_manual/manifest_v1.json', FINAL)
        self.assertNotIn('data/routes/guide_ultime_manual', FINAL)


if __name__ == "__main__":
    unittest.main()
