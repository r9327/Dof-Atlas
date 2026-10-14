from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.modules.encyclopedia.achievement_catalog_policy import (
    ALIGNMENT_GUIDE_IDS,
    ALIGNMENT_ORDER_QUEST_IDS,
)
from app.modules.encyclopedia.providers.memory_bound_guide_provider import (
    MemoryBoundGuideProvider,
)
from app.modules.encyclopedia.services import (
    AchievementProgressService as ExportedAchievementProgressService,
)
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
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


def _real_compact_alignment_provider(quest_ids_by_side: dict[str, tuple[int, ...]]):
    """Use the real metadata-only Guide constructor and compact progress index.

    Bypassing disk loading here isolates the exact contract consumed by
    achievement sync; a get_by_id spy forbids any rich-Guide hydration.
    """
    provider = object.__new__(MemoryBoundGuideProvider)
    provider._loaded = True
    provider._by_id = {}
    provider._progress_quest_ids_by_guide = {}
    provider.get_by_id = Mock(
        side_effect=AssertionError("compact alignment sync loaded rich Guide detail")
    )
    for side, guide_id in ALIGNMENT_GUIDE_IDS.items():
        quest_ids = quest_ids_by_side.get(side, ())
        row = {
            "id": guide_id,
            "title": f"Alignement {side}",
            "category": "alignement",
            "progress_quest_ids": list(quest_ids),
        }
        summary = provider._summary_from_compact_row(row)
        assert summary.required_steps == ()
        provider._by_id[guide_id] = summary
        provider._progress_quest_ids_by_guide[guide_id] = (
            provider._progress_quest_ids_from_row(row)
        )
    return provider


class _AlignmentAchievementProvider:
    def load_retained(self):
        return [
            SimpleNamespace(id=610, category_name="Quêtes", objectives=()),
            SimpleNamespace(id=620, category_name="Quêtes", objectives=()),
        ]

    def progress_objectives_for(self, achievement_id: int):
        if int(achievement_id) == 610:
            return ((611, "Critère Pa", "Pa >= 1", "", ()),)
        if int(achievement_id) == 620:
            return ((621, "Critère Pr", "", "Rang 1", ()),)
        return ()


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

    def test_exported_service_reads_real_compact_guide_index_without_details(self) -> None:
        self.assertIs(ExportedAchievementProgressService, AchievementProgressService)
        first_quest_ids = {
            side: next(iter(orders.values()))[0]
            for side, orders in ALIGNMENT_ORDER_QUEST_IDS.items()
        }
        provider = _real_compact_alignment_provider(
            {side: (quest_id, quest_id) for side, quest_id in first_quest_ids.items()}
        )

        result = ExportedAchievementProgressService._alignment_main_quest_ids(provider)

        self.assertEqual(
            {side: (quest_id,) for side, quest_id in first_quest_ids.items()},
            result,
        )
        self.assertEqual(0, provider.get_by_id.call_count)

    def test_alignment_pa_pr_follow_check_and_uncheck_for_both_sides(self) -> None:
        for side, orders in ALIGNMENT_ORDER_QUEST_IDS.items():
            with self.subTest(side=side), tempfile.TemporaryDirectory() as directory:
                order_name, quest_ids = next(iter(orders.items()))
                guide_provider = _real_compact_alignment_provider(
                    {side: (quest_ids[0],)}
                )
                character_key = "character:alignment"
                quest_progress = QuestProgressService(
                    Path(directory) / "quest_progress.json"
                )
                service = ExportedAchievementProgressService(
                    Path(directory) / "achievement_progress.json"
                )
                achievement_provider = _AlignmentAchievementProvider()
                service.set_alignment_order_choice(character_key, side, order_name)

                quest_progress.set_quest_completed(character_key, quest_ids[0], True)
                self.assertTrue(
                    service.sync_from_quest_progress(
                        character_key, achievement_provider, quest_progress, guide_provider
                    )
                )
                self.assertTrue(service.is_objective_completed(character_key, 610, 611))
                self.assertTrue(service.is_objective_completed(character_key, 620, 621))
                self.assertTrue(service.is_achievement_completed(character_key, 610))
                self.assertTrue(service.is_achievement_completed(character_key, 620))

                quest_progress.set_quest_completed(character_key, quest_ids[0], False)
                self.assertTrue(
                    service.sync_from_quest_progress(
                        character_key, achievement_provider, quest_progress, guide_provider
                    )
                )
                self.assertFalse(service.is_objective_completed(character_key, 610, 611))
                self.assertFalse(service.is_objective_completed(character_key, 620, 621))
                self.assertFalse(service.is_achievement_completed(character_key, 610))
                self.assertFalse(service.is_achievement_completed(character_key, 620))
                self.assertEqual(0, guide_provider.get_by_id.call_count)

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
