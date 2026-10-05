from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.achievement_catalog_policy import ALIGNMENT_GUIDE_IDS
from app.modules.encyclopedia.services.memory_bound_achievement_progress_service import (
    AchievementProgressService,
)


class _GuideProvider:
    def __init__(self) -> None:
        self.summary_calls: list[str] = []
        self.detail_calls: list[str] = []

    def get_summary_by_id(self, guide_id: str):
        self.summary_calls.append(str(guide_id))
        return SimpleNamespace(
            required_steps=(
                SimpleNamespace(step_type="quest", entity_id=100 + len(self.summary_calls)),
                SimpleNamespace(step_type="info", entity_id=None),
            )
        )

    def get_by_id(self, guide_id: str):
        self.detail_calls.append(str(guide_id))
        raise AssertionError("alignment progress must not materialize a rich Guide detail")


class MemoryBoundAchievementProgressTests(unittest.TestCase):
    def test_alignment_progress_uses_compact_guide_summaries(self) -> None:
        provider = _GuideProvider()

        result = AchievementProgressService._alignment_main_quest_ids(provider)

        self.assertEqual(set(ALIGNMENT_GUIDE_IDS), set(result))
        self.assertEqual(set(ALIGNMENT_GUIDE_IDS.values()), set(provider.summary_calls))
        self.assertEqual([], provider.detail_calls)
        self.assertTrue(all(len(quest_ids) == 1 for quest_ids in result.values()))


if __name__ == "__main__":
    unittest.main()
