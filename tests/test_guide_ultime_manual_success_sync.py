from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import GuideUltimeManualRuntimeService


class _AchievementProvider:
    def load_all(self):
        return [
            SimpleNamespace(id=101, name="Duo"),
            SimpleNamespace(id=202, name="L'arbre qui cache la forêt"),
        ]


class GuideUltimeManualSuccessSyncTests(unittest.TestCase):
    def test_authored_success_names_resolve_to_local_achievement_ids(self):
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.achievement_provider = _AchievementProvider()
        card = {"manual_success_names": ["L'arbre qui cache la forêt"]}
        self.assertEqual(service.card_success_ids(card), (202,))

    def test_manual_success_names_are_deduplicated_after_normalization(self):
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.achievement_provider = _AchievementProvider()
        card = {"manual_success_names": ["Duo", "duo"]}
        self.assertEqual(service.card_success_ids(card), (101,))


if __name__ == "__main__":
    unittest.main()
