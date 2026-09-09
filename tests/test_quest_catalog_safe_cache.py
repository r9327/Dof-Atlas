from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.quest_catalog as quest_catalog
from app.quest_catalog import (
    QuestAchievementSeries,
    QuestCatalog,
    QuestObjective,
    QuestRecord,
    QuestReward,
    QuestSolutionBlock,
    QuestStep,
)


class QuestCatalogSafeCacheTests(unittest.TestCase):
    def test_cache_round_trip_preserves_nested_catalog_without_pickle(self) -> None:
        reward = QuestReward("Kama test", 12, "img.png", item_id=9, kind="item")
        objective = QuestObjective(7, "Parler au PNJ", 1, map_label="[1,2]", zone="Astrub")
        step = QuestStep(3, "Étape", "Description", [objective], [reward])
        record = QuestRecord(
            id=42,
            name="Quête test",
            category="Test",
            level_min=10,
            level_max=20,
            start_criterion="PL>9",
            zones=["Astrub"],
            achievements=["Succès test"],
            prerequisites=["Niveau 10+"],
            info=["Aucun combat détecté"],
            steps=[step],
            source_solution_steps=[step],
            solution_blocks=[QuestSolutionBlock(1, "text", content="Bonjour")],
            source_info={"status": "ok"},
            rewards=[reward],
        )
        catalog = QuestCatalog(
            [record],
            Path("data/raw"),
            ["warning"],
            achievement_series=(QuestAchievementSeries(5, "Série", "Astrub", 1, (42,)),),
        )

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "catalog.json.gz"
            legacy_path = Path(tmp) / "catalog.pkl"
            legacy_path.write_bytes(b"legacy-pickle-never-read")
            signature = (("source", "fake", 1, 2),)
            with (
                patch.object(quest_catalog, "QUEST_CATALOG_CACHE_PATH", cache_path),
                patch.object(quest_catalog, "QUEST_CATALOG_LEGACY_CACHE_PATH", legacy_path),
                patch.object(quest_catalog, "_is_default_quest_data_dir", return_value=True),
                patch.object(quest_catalog, "quest_catalog_cache_signature", return_value=signature),
            ):
                quest_catalog.write_quest_catalog_cache(catalog)
                loaded = quest_catalog.read_quest_catalog_cache()

            self.assertFalse(legacy_path.exists())
            self.assertIsInstance(loaded, QuestCatalog)
            self.assertEqual(loaded.quests[0].name, "Quête test")
            self.assertEqual(loaded.quests[0].steps[0].objectives[0].zone, "Astrub")
            self.assertEqual(loaded.achievement_series[0].quest_ids, (42,))

    def test_module_does_not_import_or_deserialize_pickle(self) -> None:
        source = inspect.getsource(quest_catalog)
        self.assertNotIn("import pickle", source)
        self.assertNotIn("pickle.loads", source)
        self.assertNotIn("pickle.dumps", source)


if __name__ == "__main__":
    unittest.main()
