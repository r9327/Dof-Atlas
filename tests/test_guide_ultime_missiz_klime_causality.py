from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


BASE = Path(__file__).resolve().parents[1] / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeMissizKlimeCausalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = load_manual_chapter(BASE / "level_191_200_v22.json")
        cls.stages = {
            str(stage.get("id") or ""): stage
            for stage in payload.get("stages", [])
            if isinstance(stage, dict)
        }

    def test_missiz_single_pass_locks_erazal_dialogue_before_exit(self) -> None:
        stage = self.stages["L197-02"]
        route = [str(row.get("do") or "") for row in stage.get("route", []) if isinstance(row, dict)]
        rendered = "\n".join(route)

        self.assertIn("À glacer le sang", rendered)
        self.assertIn("La dernière carte", rendered)
        self.assertIn("Chaud et Froid", rendered)
        self.assertIn("Plan d'Invasion", rendered)
        self.assertIn("Larme de Missiz Frizz", rendered)
        self.assertIn("NE PAS SORTIR", rendered)
        self.assertIn("Erazal", rendered)

        boss_index = next(i for i, text in enumerate(route) if "Faire UN Missiz" in text)
        dialogue_index = next(i for i, text in enumerate(route) if "en savoir plus au sujet d'Erazal" in text)
        returns_index = next(i for i, text in enumerate(route) if "Rendre le Plan d'Invasion" in text)
        self.assertLess(boss_index, dialogue_index)
        self.assertLess(dialogue_index, returns_index)

        exits = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("Dialogue Missiz au sujet d'Erazal effectué AVANT", exits)
        self.assertIn("sans second Missiz", exits)

    def test_ddg_klime_merge_requires_dragon_noir_to_be_at_exact_klime_gate(self) -> None:
        stage = self.stages["L200-DDG1"]
        progress = "\n".join(str(value) for value in stage.get("progress_also", []))

        self.assertIn("Dazak", progress)
        self.assertIn("très vieille peau de crocodaille", progress)
        self.assertIn("exactement à son objectif Klime", progress)
        self.assertIn("Le simple fait que Le dragon noir soit actif ne suffit jamais", progress)
        self.assertIn("futur Klime de Le dragon noir reste alors un rerun causal", progress)


if __name__ == "__main__":
    unittest.main()
