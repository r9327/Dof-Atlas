"""Ensure legacy and lazy search share source fields without flattening state."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.services.quest_search_text import quest_search_fields


class QuestSearchFieldsTests(unittest.TestCase):
    def test_fields_keep_raw_values_order_and_require_no_qt(self):
        quest = SimpleNamespace(
            search_text="Quête première",
            steps=(
                SimpleNamespace(name="Étape A", objectives=(SimpleNamespace(text="Parler à Bob"),)),
                SimpleNamespace(name="Étape B", objectives=(SimpleNamespace(text="Voir Astrub"),)),
            ),
            rewards=(SimpleNamespace(name="Cawotte"), SimpleNamespace(name="Ortie")),
        )
        self.assertEqual(
            quest_search_fields(quest, ("Succès 1", "Succès 2")),
            ("Quête première", "Étape A Étape B", "Parler à Bob Voir Astrub",
             "Cawotte Ortie", "Succès 1 Succès 2"),
        )

    def test_empty_optional_fields_match_original_join_semantics(self):
        quest = SimpleNamespace(search_text="Nom", steps=(), rewards=())
        self.assertEqual(quest_search_fields(quest, ()), ("Nom", "", "", "", ""))


if __name__ == "__main__":
    unittest.main()
