from __future__ import annotations

import unittest
from unittest.mock import patch

from app.quest_source_index import QuestSourceError
from tools.audit_guide_ultime_manual_final_coverage import load_provider_achievements
from tools.audit_guide_ultime_manual_prerequisites import load_provider_quests


class GuideUltimeCatalogFailureTests(unittest.TestCase):
    def test_quest_source_failure_becomes_explicit_unavailable_catalog(self) -> None:
        with patch(
            "tools.audit_guide_ultime_manual_prerequisites.QuestProvider",
            side_effect=QuestSourceError("catalogue absent"),
        ):
            self.assertEqual(load_provider_quests(), [])

    def test_achievement_source_failure_becomes_explicit_unavailable_catalog(self) -> None:
        with patch(
            "tools.audit_guide_ultime_manual_final_coverage.AchievementProvider",
            side_effect=QuestSourceError("catalogue absent"),
        ):
            self.assertEqual(load_provider_achievements(), [])

    def test_os_failure_never_fabricates_catalog_data(self) -> None:
        with patch(
            "tools.audit_guide_ultime_manual_final_coverage.AchievementProvider",
            side_effect=OSError("fixture inaccessible"),
        ):
            self.assertEqual(load_provider_achievements(), [])


if __name__ == "__main__":
    unittest.main()
