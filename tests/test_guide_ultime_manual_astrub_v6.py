from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualAstrubV6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v5 = load_manual_chapter(MANUAL / "astrub_v5.json")
        cls.v6 = load_manual_chapter(MANUAL / "astrub_v6.json")
        cls.v5_by_id = {str(stage.get("id") or ""): stage for stage in cls.v5["stages"]}
        cls.v6_by_id = {str(stage.get("id") or ""): stage for stage in cls.v6["stages"]}

    def test_v6_preserves_all_sixteen_stable_stage_ids_and_order(self) -> None:
        ids_v5 = [str(stage.get("id") or "") for stage in self.v5["stages"]]
        ids_v6 = [str(stage.get("id") or "") for stage in self.v6["stages"]]
        self.assertEqual(len(ids_v6), 16)
        self.assertEqual(ids_v6, ids_v5)

    def test_v6_does_not_change_player_route_quests_or_locations(self) -> None:
        protected_fields = (
            "title",
            "level",
            "expected_level",
            "duration_min",
            "estimated_duration_min",
            "start",
            "end",
            "entry",
            "exit",
            "quests",
            "quest_sequence",
            "parallel_quests",
            "route",
            "waypoints",
            "instructions",
            "opportunistic",
            "before_leaving_area",
            "before_leave",
            "hard_exit",
            "pause",
            "pause_checkpoint",
        )
        for stage_id, before in self.v5_by_id.items():
            after = self.v6_by_id[stage_id]
            for field in protected_fields:
                self.assertEqual(after.get(field), before.get(field), f"{stage_id}:{field}")

    def test_v6_structures_only_already_authored_preparation_targets(self) -> None:
        expected = {
            "AST-00": {"kamas"},
            "AST-01": {"Lailait", "Goujon"},
            "AST-03": {"Arme de chasse"},
            "AST-05": {
                "Eau potable",
                "Ortie",
                "Sauge",
                "Trèfle à 5 feuilles",
                "Fleur de Pissenlit Diabolique",
                "Pétale de Rose Démoniaque",
                "Pétale de Tournesol Sauvage",
                "Langue d'Épouvanteur",
            },
            "AST-10": {"Fer"},
            "AST-12": {"Ferrite", "Serviette de Plage", "Cuir de Scélérat Strubien", "Planche Contreplaquée"},
            "AST-14": {"Poudre de Perlinpainpain", "Huile de Sésame"},
        }
        for stage_id, names in expected.items():
            preparation = self.v6_by_id[stage_id].get("preparation", []) or []
            actual = {
                "kamas" if isinstance(row, dict) and row.get("kamas") is not None else str(row.get("name") or "")
                for row in preparation
                if isinstance(row, dict)
            }
            self.assertTrue(names.issubset(actual), f"{stage_id}: {sorted(names - actual)}")

    def test_v6_structures_existing_dungeon_and_monster_passes(self) -> None:
        expected_dungeons = {
            "AST-06": "Grange du Tournesol Affamé",
            "AST-07": "Château Ensablé",
            "AST-09": "Donjon Bouftou",
            "AST-15": "Cache de Kankreblath",
        }
        for stage_id, name in expected_dungeons.items():
            dungeon = self.v6_by_id[stage_id].get("dungeon") or {}
            self.assertEqual(dungeon.get("name"), name)
            self.assertTrue(str(dungeon.get("pass") or "").startswith("single_optimized_pass"))

        monsters = self.v6_by_id["AST-13"].get("monsters", []) or []
        milimulou = next(row for row in monsters if isinstance(row, dict) and row.get("name") == "Milimulou")
        self.assertEqual(milimulou.get("quantity"), 5)
        self.assertEqual(milimulou.get("for"), "Bûcherons en détresse")

    def test_rikiki_is_explicitly_kept_in_bank_after_astrub(self) -> None:
        bank = self.v6_by_id["AST-15"].get("bank_items", []) or []
        rikiki = next(row for row in bank if isinstance(row, dict) and row.get("name") == "Baguette Rikiki")
        self.assertEqual(rikiki.get("quantity"), 1)
        self.assertIn("banque", str(rikiki.get("policy") or "").casefold())


if __name__ == "__main__":
    unittest.main()
