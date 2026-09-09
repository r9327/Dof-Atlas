from __future__ import annotations

from pathlib import Path
import unittest

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from tools import validate_guide_ultime_manual_transversals_v15 as validator
from tools import validate_guide_ultime_manual_transversals_v16 as validator_v16


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeFinalTransversalValidatorTests(unittest.TestCase):
    def test_final_manifest_versions_are_pinned(self) -> None:
        expected = {
            "level_51_70": "level_51_70_v4.json",
            "level_70_100": "level_70_100_v10.json",
            "level_100_120": "level_100_120_v9.json",
            "level_120_150": "level_120_150_v21.json",
            "level_150_170": "level_150_170_v21.json",
            "level_171_180": "level_171_180_v13.json",
            "level_181_190": "level_181_190_v15.json",
            "level_191_200": "level_191_200_v22.json",
            "level_200_plus": "level_200_plus_v11.json",
        }
        actual = {chapter_id: filename for chapter_id, filename, _ in validator.EXPECTED_CHAPTERS}
        for chapter_id, filename in expected.items():
            self.assertEqual(actual.get(chapter_id), filename, chapter_id)
        self.assertEqual(validator.EXPECTED_BONTA_FILE, "bonta_1_100_v17.json")
        self.assertEqual(validator.EXPECTED_TEMPORAL_FILE, "temporal_registry_v15.json")
        self.assertEqual(validator.EXPECTED_OCRE_FINAL_FILE, "ocre_final_route_v2.json")

    def test_final_static_transversal_audit_passes_without_catalog(self) -> None:
        report = validator.audit(skip_catalog=True)
        self.assertEqual(report["status"], "STRICT_PASS", report["hard_errors"])
        self.assertEqual(report["hard_error_count"], 0, report["hard_errors"])
        self.assertEqual(report["canonical_chapter_count"], 13)
        self.assertEqual(report["canonical_stage_count"], 267)

    def test_success_and_parallel_quest_semantics_are_locked(self) -> None:
        high = load_manual_chapter(BASE / "level_191_200_v22.json")
        enut_close = next(row for row in high["stages"] if row.get("id") == "L200-ENUT-CLOSE")
        self.assertIn("Le roi et moi", enut_close.get("successes", []))
        self.assertNotIn("Le roi et moi", enut_close.get("quests", []))

        post = load_manual_chapter(BASE / "level_200_plus_v11.json")
        flovoraison = next(row for row in post["stages"] if row.get("id") == "P200-24")
        self.assertIn("Qui nous protège du Protecteur ?", flovoraison.get("quests", []))
        self.assertIn("Flovoraison", flovoraison.get("quests", []))

    def test_validator_is_module_safe(self) -> None:
        source = Path(validator.__file__).read_text(encoding="utf-8")
        self.assertNotIn("sys.path.insert", source)
        self.assertNotIn("import sys", source)

    def test_v16_validator_is_module_safe(self) -> None:
        source = Path(validator_v16.__file__).read_text(encoding="utf-8")
        self.assertIn("from tools import validate_guide_ultime_manual_transversals_v15 as v15", source)
        self.assertNotIn("sys.path.insert", source)
        self.assertNotIn("import sys", source)
        self.assertIs(validator_v16.v15, validator)


if __name__ == "__main__":
    unittest.main()