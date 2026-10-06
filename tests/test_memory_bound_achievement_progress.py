from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
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


class _CompactAchievementProvider:
    def __init__(self) -> None:
        self.achievement = SimpleNamespace(
            id=500,
            category_name="Quêtes",
            objective_ids=(501,),
            objectives=(),
        )

    def load_retained(self):
        return [self.achievement]

    def progress_objectives_for(self, achievement_id: int):
        if int(achievement_id) != 500:
            return ()
        return (
            (
                501,
                "",
                "",
                "",
                (("quest", 10),),
            ),
        )


class _QuestProgress:
    @staticmethod
    def completed_quest_ids(_character_key: str):
        return {10}


class MemoryBoundAchievementProgressTests(unittest.TestCase):
    def test_alignment_progress_uses_compact_guide_summaries(self) -> None:
        provider = _GuideProvider()

        result = AchievementProgressService._alignment_main_quest_ids(provider)

        self.assertEqual(set(ALIGNMENT_GUIDE_IDS), set(result))
        self.assertEqual(set(ALIGNMENT_GUIDE_IDS.values()), set(provider.summary_calls))
        self.assertEqual([], provider.detail_calls)
        self.assertTrue(all(len(quest_ids) == 1 for quest_ids in result.values()))


    def test_compact_objective_contract_preserves_auto_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = AchievementProgressService(
                Path(directory) / "achievement_progress.json"
            )
            provider = _CompactAchievementProvider()

            changed = service.sync_from_quest_progress(
                "character:1",
                provider,
                _QuestProgress(),
            )

            self.assertTrue(changed)
            self.assertTrue(
                service.is_achievement_completed("character:1", 500)
            )
            self.assertTrue(
                service.is_objective_completed("character:1", 500, 501)
            )


if __name__ == "__main__":
    unittest.main()
