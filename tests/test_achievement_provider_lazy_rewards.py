from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from threading import current_thread

from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider
from app.quest_catalog import QuestCatalog


def _doduda(*rows: dict[str, object]) -> dict[str, object]:
    return {"references": {"RefIds": [{"data": row} for row in rows]}}


class AchievementProviderLazyRewardTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> None:
        (root / "languages").mkdir(parents=True)
        (root / "languages" / "fr.json").write_text(
            json.dumps({"entries": {"1": "Succès test", "2": "Objet test"}}),
            encoding="utf-8",
        )
        payloads = {
            "achievements.json": _doduda(
                {
                    "id": 10,
                    "nameId": 1,
                    "descriptionId": -1,
                    "categoryId": 8,
                    "level": 1,
                    "points": 5,
                    "order": 0,
                    "objectiveIds": [],
                    "rewardIds": [100],
                }
            ),
            "achievement_categories.json": _doduda(
                {"id": 8, "nameId": 1, "parentId": 0, "order": 0, "achievementIds": [10]}
            ),
            "achievement_objectives.json": _doduda(),
            "quests.json": _doduda(),
            "monsters.json": _doduda(),
            "dungeons.json": _doduda(),
            "achievement_rewards.json": _doduda(
                {
                    "id": 100,
                    "achievementId": 10,
                    "itemsReward": [200],
                    "itemsQuantityReward": [2],
                }
            ),
            "items.json": _doduda({"id": 200, "nameId": 2}),
            "spells.json": _doduda(),
            "titles.json": _doduda(),
            "emoticons.json": _doduda(),
            "ornaments.json": _doduda(),
            "alterations.json": _doduda(),
        }
        for name, payload in payloads.items():
            (root / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_catalog_stays_light_and_detail_rewards_are_on_demand(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_fixture(root)
            quest_provider = QuestProvider(catalog=QuestCatalog([]), data_dir=root)
            provider = AchievementProvider(data_dir=root, quest_provider=quest_provider)

            retained = provider.load_retained()
            self.assertEqual(len(retained), 1)
            light = provider.get_by_id(10)
            self.assertIsNotNone(light)
            assert light is not None
            self.assertEqual([reward.kind for reward in light.rewards], ["achievement_points"])
            self.assertFalse(provider.detail_sources_ready)

            with self.assertRaises(RuntimeError):
                provider.get_detail_by_id(10)

            provider.load_all()
            self.assertTrue(provider.detail_sources_ready)
            detail = provider.get_detail_by_id(10)
            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertEqual([reward.kind for reward in detail.rewards], ["achievement_points", "item"])
            self.assertEqual(detail.rewards[1].name, "Objet test")
            self.assertEqual(detail.rewards[1].quantity, 2)
            self.assertEqual(provider.last_detail_thread_name, current_thread().name)

            still_light = provider.get_by_id(10)
            self.assertIsNotNone(still_light)
            assert still_light is not None
            self.assertEqual([reward.kind for reward in still_light.rewards], ["achievement_points"])
            self.assertIs(provider.get_detail_by_id(10), detail)


if __name__ == "__main__":
    unittest.main()
