from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


BASE = Path(__file__).resolve().parents[1] / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeGrolloumCausalityTests(unittest.TestCase):
    def test_first_grolloum_is_shared_bonta90_and_au_fion_du_trou(self) -> None:
        payload = load_manual_chapter(BASE / "level_181_190_v15.json")
        stages = {
            str(stage.get("id") or ""): stage
            for stage in payload.get("stages", [])
            if isinstance(stage, dict)
        }
        stage = stages["L190-08"]
        rendered = str(stage)

        self.assertIn("Au fion du trou", rendered)
        self.assertIn("Grolloum", rendered)
        self.assertIn("Bonta 90", rendered)
        self.assertIn("Gobiling", rendered)
        self.assertIn("La machine à démonter le temps", rendered)
        self.assertIn("niveau 200", rendered)

        before = "\n".join(str(value) for value in stage.get("before_leaving", []))
        self.assertIn("Bonta 90 terminé", before)
        self.assertIn("Au fion du trou terminé", before)

    def test_second_grolloum_is_causal_for_machine_after_chaud_et_froid(self) -> None:
        payload = load_manual_chapter(BASE / "level_191_200_v22.json")
        stages = {
            str(stage.get("id") or ""): stage
            for stage in payload.get("stages", [])
            if isinstance(stage, dict)
        }
        stage = stages["L200-DDG2"]
        rendered = str(stage)

        self.assertIn("La machine à démonter le temps", rendered)
        self.assertIn("Chaud et Froid", rendered)
        self.assertIn("Grolloum", rendered)
        self.assertIn("Pierre d'Autre Temps", rendered)
        self.assertIn("second", rendered.lower())
        self.assertIn("causal", rendered.lower())

        exits = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("Grolloum global second passage causal", exits)


if __name__ == "__main__":
    unittest.main()
