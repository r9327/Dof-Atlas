from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


BASE = Path(__file__).resolve().parents[1] / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeAbyssalExitCausalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = load_manual_chapter(BASE / "level_181_190_v15.json")
        cls.stages = {
            str(stage.get("id") or ""): stage
            for stage in payload.get("stages", [])
            if isinstance(stage, dict)
        }

    def test_meno_closes_piege_de_crystal_before_exit(self) -> None:
        stage = self.stages["L190-10B"]
        route = "\n".join(str(row.get("do") or "") for row in stage.get("route", []) if isinstance(row, dict))
        self.assertIn("Piège de crystal", route)
        self.assertIn("NE PAS SORTIR", route)
        self.assertIn("Capitaine Meno", route)
        self.assertIn("Son nom est Personne", route)
        exits = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("AVANT sortie", exits)
        self.assertIn("aucun rerun Abyssal", exits)

    def test_dantinea_dialogue_is_required_before_exit(self) -> None:
        stage = self.stages["L190-10C"]
        route = "\n".join(str(row.get("do") or "") for row in stage.get("route", []) if isinstance(row, dict))
        self.assertIn("NE PAS SORTIR", route)
        self.assertIn("Dame Askina", route)
        self.assertIn("Rançon nage", route)
        exits = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("Dialogue Dantinéa", exits)
        self.assertIn("Un seul Dantinéa", exits)

    def test_koutoulou_post_boss_sequence_is_complete(self) -> None:
        stage = self.stages["L190-10E"]
        route = [str(row.get("do") or "") for row in stage.get("route", []) if isinstance(row, dict)]
        rendered = "\n".join(route)
        self.assertIn("Larve de Koutoulou", rendered)
        self.assertIn("Capitaine Skaille", rendered)
        self.assertIn("Prêtre en jaune", rendered)
        self.assertIn("Pollie Perkine", rendered)
        self.assertIn("Reine Viktorie", rendered)
        post = next(text for text in route if "NE PAS QUITTER" in text)
        self.assertLess(post.index("Capitaine Skaille"), post.index("Prêtre en jaune"))
        self.assertLess(post.index("Prêtre en jaune"), post.index("Pollie Perkine"))
        exits = "\n".join(str(value) for value in stage.get("hard_exit", []))
        self.assertIn("L'appel de Koutoulou fermés sans second Temple", exits)


if __name__ == "__main__":
    unittest.main()
