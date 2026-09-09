from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeEbeneSolarCausalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chapter = load_manual_chapter(BASE / "level_191_200_v22.json")
        cls.by_id = {
            str(row.get("id") or ""): row
            for row in cls.chapter.get("stages", [])
            if isinstance(row, dict)
        }

    @staticmethod
    def _route_text(stage: dict) -> str:
        return "\n".join(
            str(row.get("do") or "")
            for row in stage.get("route", [])
            if isinstance(row, dict)
        )

    def test_solar_route_is_in_player_execution_order(self) -> None:
        stage = self.by_id["L200-15E6"]
        text = self._route_text(stage)

        for token in (
            "20 Âmes de Calciné",
            "drop ne fonctionne pas dans la Tour de Solar",
            "sort Nécronyx",
            "Tour de Solar",
            "impérativement sur Solar avant le coup fatal",
            "NE PAS SORTIR",
            "coeur livide",
            "Dieu Sram",
            "La Voix des Douze",
            "Volkaragnar",
            "Crocoburio",
            "Dofus Ébène sur son socle",
        ):
            self.assertIn(token, text)

        self.assertLess(text.index("20 Âmes de Calciné"), text.index("Faire UN Solar"))
        self.assertLess(text.index("sort Nécronyx"), text.index("Faire UN Solar"))
        self.assertLess(text.index("impérativement sur Solar avant le coup fatal"), text.index("NE PAS SORTIR"))
        self.assertLess(text.index("NE PAS SORTIR"), text.index("La Voix des Douze"))
        self.assertLess(text.index("La Voix des Douze"), text.index("Volkaragnar"))

    def test_solar_keeps_single_ebene_dungeon_and_post_boss_contract(self) -> None:
        stage = self.by_id["L200-15E6"]
        self.assertEqual(stage["dungeon"]["name"], "Tour de Solar")
        self.assertEqual(stage["dungeon"]["pass"], "unique_for_ebene_final")

        hard_exit = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("20 Âmes de Calciné", hard_exit)
        self.assertIn("Solar vaincu avec Nécronyx", hard_exit)
        self.assertIn("Coeur livide de Solar", hard_exit)
        self.assertIn("sans Bethel/Solar supplémentaire", hard_exit)
        self.assertIn("Dofus Ébène", hard_exit)

    def test_canonical_stage_count_is_unchanged(self) -> None:
        self.assertEqual(self.chapter["stage_count"], 62)
        self.assertEqual(len(self.chapter["stages"]), 62)


if __name__ == "__main__":
    unittest.main()
