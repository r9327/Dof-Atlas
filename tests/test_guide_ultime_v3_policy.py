from __future__ import annotations

import unittest

from app.quest_catalog import normalize_text
from tools.build_guide_ultime_final import MANDATORY_REPEATABLES
from tools.build_guide_ultime_gps_route import acquisition_options, source_recommendation


class GuideUltimeV3AcquisitionPolicyTests(unittest.TestCase):
    def test_hdv_is_recommended_and_craft_stays_optional(self):
        options = acquisition_options("bank|hdv|craft|farm")
        modes = [row["mode"] for row in options]
        self.assertEqual(modes[:4], ["BANQUE", "HDV", "CRAFT", "FARM_DROP"])
        self.assertEqual(
            source_recommendation("hdv|craft"),
            "HDV — recommandé pour optimiser le temps",
        )
        craft = next(row for row in options if row["mode"] == "CRAFT")
        self.assertTrue(craft["optional_when_hdv_available"])
        self.assertFalse(craft["requires_job_level"])

    def test_craft_only_source_does_not_infer_hard_job_gate(self):
        craft = next(
            row for row in acquisition_options("craft")
            if row["mode"] == "CRAFT"
        )
        self.assertFalse(craft["requires_job_level"])

    def test_fight_club_is_one_completion_not_140_week_thread(self):
        meta = MANDATORY_REPEATABLES[normalize_text("Fight club")]
        self.assertEqual(meta["runtime_policy"], "complete_once_for_success")
        self.assertIsNone(meta["counter"])


if __name__ == "__main__":
    unittest.main()
