from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView
from app.quest_catalog import QuestCatalog, build_quest_requirement_name_index


class _Provider:
    def __init__(self) -> None:
        self.calls = 0
        self.rows = [
            SimpleNamespace(id=101, name="Première quête"),
            SimpleNamespace(id=202, name="Deuxième quête"),
            SimpleNamespace(id=303, name="Première quête"),
        ]

    def list_quests(self):
        self.calls += 1
        return list(self.rows)


class QuestDetailRequirementCacheTests(unittest.TestCase):
    def test_catalogue_is_indexed_once_for_multiple_prerequisites(self) -> None:
        provider = QuestProvider(catalog=QuestCatalog(_Provider().rows))
        quest_view = SimpleNamespace(quest_provider=provider)
        guide_view = SimpleNamespace(quest_provider=provider)
        with patch("app.quest_catalog.build_quest_requirement_name_index",
                   wraps=build_quest_requirement_name_index) as build_index:
            first = QuestDetailView._quest_id_from_requirement_line(
                quest_view, "Quête terminée : Première quête",
            )
            second = QuestDetailView._quest_id_from_requirement_line(
                guide_view, "Quête active : Deuxième quête",
            )
            build_index.assert_called_once()

        self.assertEqual(first, 101)
        self.assertEqual(second, 202)

    def test_non_quest_requirement_does_not_build_index(self) -> None:
        provider = _Provider()
        view = SimpleNamespace(quest_provider=provider)

        result = QuestDetailView._quest_id_from_requirement_line(view, "Niveau 100")

        self.assertIsNone(result)
        self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
