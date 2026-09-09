from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


class GuideUltimeManualRouteHookTests(unittest.TestCase):
    def test_route_hook_expands_prerequisites_preparation_quests_and_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transversal = {
                "schema_version": 1,
                "stages": [
                    {
                        "id": "BNT-01",
                        "entry": "Rang précédent terminé.",
                        "quests": ["Quête Bonta"],
                        "preparation": [{"name": "Ressource Bonta", "quantity": 2}],
                        "take": ["Prendre Quête Bonta."],
                        "route": [{"area": "Bonta", "do": "Faire les vraies actions Bonta."}],
                        "before_leaving": ["Quête Bonta terminée."],
                    }
                ],
            }
            chapter = {
                "schema_version": 1,
                "depends_on": ["bonta.json"],
                "stages": [
                    {
                        "id": "MAIN-01",
                        "route_hooks": ["BNT-01"],
                        "quests": ["Quête principale"],
                        "route": [{"area": "Route principale", "do": "Continuer la route principale."}],
                    }
                ],
            }
            (root / "bonta.json").write_text(json.dumps(transversal, ensure_ascii=False), encoding="utf-8")
            (root / "chapter.json").write_text(json.dumps(chapter, ensure_ascii=False), encoding="utf-8")

            resolved = load_manual_chapter(root / "chapter.json")
            stage = resolved["stages"][0]

            self.assertIn("Quête Bonta", stage["quests"])
            self.assertIn("Quête principale", stage["quests"])
            self.assertEqual(stage["entry"], "Rang précédent terminé.")
            self.assertTrue(any(row.get("name") == "Ressource Bonta" for row in stage["preparation"]))
            self.assertIn("Prendre Quête Bonta.", stage["take"])
            self.assertTrue(any(row.get("do") == "Faire les vraies actions Bonta." for row in stage["route"]))
            self.assertIn("Quête Bonta terminée.", stage["before_leaving"])

    def test_transversal_text_reference_is_expanded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bonta.json").write_text(
                json.dumps({"stages": [{"id": "BNT-22", "quests": ["Rang 51"]}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "chapter.json").write_text(
                json.dumps(
                    {
                        "depends_on": ["bonta.json"],
                        "stages": [{"id": "MAIN", "transversal": "BNT-22 from bonta.json", "quests": ["Main"]}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            resolved = load_manual_chapter(root / "chapter.json")
            self.assertEqual(resolved["stages"][0]["quests"], ["Rang 51", "Main"])

    def test_transversal_routes_field_is_a_valid_stage_hook_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bonta.json").write_text(
                json.dumps({"stages": [{"id": "BNT-36", "quests": ["Rang 80"]}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "chapter.json").write_text(
                json.dumps(
                    {
                        "transversal_routes": ["bonta.json"],
                        "stages": [{"id": "MAIN", "route_hooks": ["BNT-36"], "quests": ["Main"]}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            resolved = load_manual_chapter(root / "chapter.json")
            self.assertEqual(resolved["stages"][0]["quests"], ["Rang 80", "Main"])

    def test_route_file_hook_is_preserved_for_specialized_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bonta_order_rank80_v1.json").write_text(
                json.dumps({"schema_version": 1, "options": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "chapter.json").write_text(
                json.dumps(
                    {
                        "stages": [
                            {
                                "id": "MAIN",
                                "route_hooks": ["bonta_order_rank80_v1"],
                                "quests": ["Main"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            resolved = load_manual_chapter(root / "chapter.json")
            stage = resolved["stages"][0]
            self.assertEqual(stage["quests"], ["Main"])
            self.assertEqual(stage["route_hooks"], ["bonta_order_rank80_v1"])

    def test_unresolved_explicit_hook_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "chapter.json").write_text(
                json.dumps({"stages": [{"id": "MAIN", "route_hooks": ["BNT-99"]}]}),
                encoding="utf-8",
            )
            with self.assertRaises(KeyError):
                load_manual_chapter(root / "chapter.json")


if __name__ == "__main__":
    unittest.main()
