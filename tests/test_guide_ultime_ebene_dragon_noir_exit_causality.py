from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeEbeneDragonNoirExitCausalityTests(unittest.TestCase):
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

    def test_dragon_noir_restores_nimbos_bible_then_closes_skin_and_klime(self) -> None:
        stage = self.by_id["L200-15E4"]
        text = self._route_text(stage)

        for token in (
            "PREMIER Dazak",
            "Totem de la colère",
            "La bible des rancunes",
            "20 Morceaux de Brikoléreux",
            "6000 pods libres",
            "SANS refaire le donjon",
            "Plénie/Maire Cantile/Banquier",
            "De Brikke et de Brokke",
            "très vieille peau de crocodaille",
            "Ludrune l'Aveugle",
            "Barbarbe de Ludrune",
            "UN Klime",
            "Sac en peau de crocodaille",
            "Tressa",
            "La vengeance du dernier empereur",
        ):
            self.assertIn(token, text)

        self.assertLess(text.index("PREMIER Dazak"), text.index("La bible des rancunes"))
        self.assertLess(text.index("La bible des rancunes"), text.index("Plénie/Maire Cantile/Banquier"))
        self.assertLess(text.index("Plénie/Maire Cantile/Banquier"), text.index("SECONDE fois"))
        self.assertLess(text.index("très vieille peau de crocodaille"), text.index("UN Klime"))
        self.assertLess(text.index("UN Klime"), text.index("Tressa"))

    def test_dragon_noir_models_primary_dazak_conditional_rerun_and_single_klime(self) -> None:
        stage = self.by_id["L200-15E4"]
        dungeons = [row for row in stage.get("dungeons", []) if isinstance(row, dict)]
        self.assertEqual(
            [(row.get("name"), row.get("pass")) for row in dungeons],
            [
                ("Brasserie du roi Dazak", "nimbos_bible_totem_primary"),
                ("Brasserie du roi Dazak", "ebene_rerun_only_if_skin_blocked"),
                ("Salons privés de Klime", "unique_for_ebene_dragon_noir"),
            ],
        )

        hard_exit = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("Bible fermée", hard_exit)
        self.assertIn("Second Dazak causal uniquement si", hard_exit)
        self.assertIn("sinon il est interdit", hard_exit)
        self.assertIn("Aucun troisième Dazak", hard_exit)
        self.assertIn("Dialogue Klime post-boss", hard_exit)

    def test_canonical_stage_count_is_unchanged(self) -> None:
        self.assertEqual(self.chapter["stage_count"], 62)
        self.assertEqual(len(self.chapter["stages"]), 62)


if __name__ == "__main__":
    unittest.main()
