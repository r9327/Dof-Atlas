from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeDdgNebuleuxExitCausalityTests(unittest.TestCase):
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

    def test_comte_exit_consumes_all_post_boss_interactions_before_leaving(self) -> None:
        stage = self.by_id["L200-DDG3"]
        self.assertEqual(stage["dungeon"]["pass"], "ddg_totem_sarmer_single_pass")
        text = self._route_text(stage)

        for token in (
            "NE PAS SORTIR",
            "montre enchantée",
            "socle du Dofus des Glaces",
            "Liquide de la Clepsydre",
            "Djaul",
            "Jiva",
            "Mille et un jours, un destin",
            "Le Dofus des Glaces",
        ):
            self.assertIn(token, text)

        self.assertLess(text.index("montre enchantée"), text.index("socle du Dofus des Glaces"))
        self.assertLess(text.index("socle du Dofus des Glaces"), text.index("Djaul"))
        self.assertLess(text.index("Djaul"), text.index("Mille et un jours, un destin"))

        hard_exit = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("Aucun second Comte", hard_exit)
        self.assertIn("Dialogue Djaul", hard_exit)

    def test_vortex_exit_talks_to_vortex_before_tessie_without_rerun(self) -> None:
        stage = self.by_id["L200-NEB5"]
        self.assertEqual(stage["dungeon"]["pass"], "nebuleux_two_quests_plus_sarmer_single_pass")
        text = self._route_text(stage)

        for token in (
            "parler obligatoirement au Vortex",
            "puits des âmes",
            "Tessie Oude",
            "SANS refaire Vortex",
            "Elvis Irr",
            "second éclat de destin brisé",
        ):
            self.assertIn(token, text)

        self.assertLess(text.index("parler obligatoirement au Vortex"), text.index("Tessie Oude"))
        self.assertLess(text.index("puits des âmes"), text.index("Tessie Oude"))

        hard_exit = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("Aucun rerun Vortex", hard_exit)
        self.assertIn("Un seul Œil de Vortex", hard_exit)

    def test_canonical_stage_count_is_unchanged(self) -> None:
        self.assertEqual(self.chapter["stage_count"], 62)
        self.assertEqual(len(self.chapter["stages"]), 62)


if __name__ == "__main__":
    unittest.main()
