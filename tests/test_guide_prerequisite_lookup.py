from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.services import guide_path_profiles
from app.modules.encyclopedia.services.guide_path_profiles import GuidePathResolver


class GuidePrerequisiteLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        directory = self.root / "encyclopedia" / "quests"
        directory.mkdir(parents=True)
        (directory / "source_mapping.json").write_text(
            json.dumps({"quests": {
                "1": {"quest_id": 1, "name": "La quête de l'aube"},
                "2": {"quest_id": 2, "name": "Légende oubliée"},
                "3": {"quest_id": 3, "name": "Épreuve"},
                "99": {"quest_id": 99, "name": "Quête inconnue"},
            }}),
            encoding="utf-8",
        )
        quests = [
            SimpleNamespace(id=qid, name=name)
            for qid, name in (
                (1, "La quête de l'aube"),
                (2, "Légende oubliée"),
                (3, "Épreuve"),
            )
        ]
        catalog = SimpleNamespace(quests=quests, by_id={q.id: q for q in quests})
        quest_provider = SimpleNamespace(get_catalog=lambda: catalog)
        achievement_provider = SimpleNamespace(load_all=lambda: [])
        with patch.object(guide_path_profiles, "DATA_DIR", self.root):
            self.resolver = GuidePathResolver(quest_provider, achievement_provider)

    def test_exact_loose_and_prefixed_text_keep_same_quest_ids(self) -> None:
        resolver = self.resolver
        self.assertEqual(resolver._quest_ids_from_prerequisite_text("La quête de l'aube"), {1})
        self.assertEqual(resolver._quest_ids_from_prerequisite_text("La quête de l’aube"), {1})
        self.assertEqual(resolver._quest_ids_from_prerequisite_text(
            "Avoir terminé La quête de l'aube"
        ), {1})
        self.assertEqual(resolver._quest_ids_from_prerequisite_text(
            "Avoir terminé Légende oubliée"
        ), {2})
        self.assertEqual(resolver._quest_ids_from_prerequisite_text("quêtes inconnues"), set())
        self.assertEqual(resolver._quest_ids_from_prerequisite_text(""), set())

    def test_lookup_does_not_resort_source_names_on_every_fallback(self) -> None:
        class FrozenItems(dict):
            def items(self):
                raise AssertionError("Resorting the source mapping on each lookup is forbidden")

        resolver = self.resolver
        self.assertEqual(
            [len(key) for key, _ids in resolver._prerequisite_name_candidates],
            sorted([len(key) for key, _ids in resolver._prerequisite_name_candidates], reverse=True),
        )
        resolver.quest_source_name_to_ids = FrozenItems(resolver.quest_source_name_to_ids)
        for _ in range(20):
            self.assertEqual(
                resolver._quest_ids_from_prerequisite_text("Avoir terminé La quête de l'aube"),
                {1},
            )
        self.assertEqual(resolver._quest_ids_from_prerequisite_text("Terminer Épreuve"), set())


if __name__ == "__main__":
    unittest.main()
