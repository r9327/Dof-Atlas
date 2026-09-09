from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


BASE = Path(__file__).resolve().parents[1] / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeIlyzaelleBonta99CausalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = load_manual_chapter(BASE / "level_191_200_v22.json")
        cls.stages = {
            str(stage.get("id") or ""): stage
            for stage in payload.get("stages", [])
            if isinstance(stage, dict)
        }

    def test_bonta99_requires_ilyzaelle_dialogue_before_exit(self) -> None:
        stage = self.stages["L199-04"]
        rendered = "\n".join(
            str(row.get("do") or "")
            for row in stage.get("route", [])
            if isinstance(row, dict)
        )
        self.assertIn("Fée d'hiver", rendered)
        self.assertIn("NE PAS SORTIR", rendered)
        self.assertIn("mission confiée par Jiva", rendered)
        self.assertIn("bénédiction de son Dofus blanc", rendered)

        exits = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("AVANT sortie", exits)
        self.assertIn("Dialogue Ilyzaelle", exits)

    def test_lavis_de_la_mort_is_only_merged_if_already_at_ilyzaelle(self) -> None:
        stage = self.stages["L199-04"]
        rendered = str(stage)
        self.assertIn("L'avis de la Mort", rendered)
        self.assertIn("Feu dévoreur", rendered)
        self.assertIn("NE PAS retarder Bonta99", rendered)
        self.assertIn("futur Ilyzaelle comme rerun causal", rendered)
        self.assertIn("Une dernière volonté", rendered)
        self.assertIn("Les totems de Maïmane", rendered)
        self.assertIn("seul un fil déjà réellement au boss peut être fusionné", rendered)


if __name__ == "__main__":
    unittest.main()
