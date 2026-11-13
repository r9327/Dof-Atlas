"""Offline Craft leveling suggestions: no missing editorial JSON and no invented XP."""
from __future__ import annotations

from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.craft_preload import build_local_leveling_suggestions


class OfflineLevelingTests(unittest.TestCase):
    def test_base_is_not_a_profession(self):
        self.assertIsNone(build_local_leveling_suggestions("Base"))
        self.assertIsNone(build_local_leveling_suggestions("Inconnu"))

    def test_harvest_resources_exist_without_json_or_sqlite(self):
        guide = build_local_leveling_suggestions(
            "Mineur", database_path=Path("/absent/craft.sqlite")
        )
        self.assertEqual(guide["source"], "atlas-local")
        self.assertEqual(guide["kind"], "harvest")
        self.assertEqual(guide["entries"][0]["craft"]["name"], "Fer")
        self.assertEqual(guide["entries"][0]["level_range"], "Étape 1")

    def test_craft_requires_a_real_catalogue(self):
        self.assertIsNone(build_local_leveling_suggestions(
            "Forgeron", database_path=Path("/absent/craft.sqlite")
        ))

    def test_craft_suggests_only_recipes_unlocked_at_current_level(self):
        with tempfile.TemporaryDirectory() as root:
            database = Path(root) / "craft.sqlite"
            with closing(sqlite3.connect(database)) as con:
                con.executescript("""
                    CREATE TABLE recipes (
                        id INTEGER PRIMARY KEY, level INTEGER,
                        job_name TEXT, result_name_fr TEXT
                    );
                    CREATE TABLE recipe_ingredients (
                        id INTEGER PRIMARY KEY, recipe_id INTEGER
                    );
                    INSERT INTO recipes VALUES
                        (1, 1, 'Forgeron', 'Épée novice'),
                        (2, 20, 'Forgeron', 'Épée moyenne'),
                        (3, 40, 'Forgeron', 'Épée forte'),
                        (4, 60, 'Tailleur', 'Coiffe test'),
                        (5, 80, 'Forgeron', 'Sans ingrédients');
                    INSERT INTO recipe_ingredients VALUES
                        (1, 1), (2, 2), (3, 3), (4, 4);
                """)
            guide = build_local_leveling_suggestions(
                "Forgeron", database_path=database
            )
        self.assertEqual([e["level_range"] for e in guide["entries"]],
                         ["Niv. 1+", "Niv. 20+", "Niv. 40+"])
        self.assertEqual([e["craft"]["name"] for e in guide["entries"]],
                         ["Épée novice", "Épée moyenne", "Épée forte"])
        self.assertTrue(all(e["craft"]["quantity"] == 1 for e in guide["entries"]))
        self.assertEqual(guide["kind"], "craft")


if __name__ == "__main__":
    unittest.main()
