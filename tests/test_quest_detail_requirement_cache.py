from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView


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
        provider = _Provider()
        view = SimpleNamespace(quest_provider=provider)

        first = QuestDetailView._quest_id_from_requirement_line(
            view,
            "Quête terminée : Première quête",
        )
        second = QuestDetailView._quest_id_from_requirement_line(
            view,
            "Quête active : Deuxième quête",
        )

        self.assertEqual(first, 101)
        self.assertEqual(second, 202)
        self.assertEqual(provider.calls, 1)

    def test_non_quest_requirement_does_not_build_index(self) -> None:
        provider = _Provider()
        view = SimpleNamespace(quest_provider=provider)

        result = QuestDetailView._quest_id_from_requirement_line(view, "Niveau 100")

        self.assertIsNone(result)
        self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
