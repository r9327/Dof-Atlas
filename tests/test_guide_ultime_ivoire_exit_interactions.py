from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"


def _stage(payload: dict, stage_id: str) -> dict:
    return next(stage for stage in payload.get("stages", []) if stage.get("id") == stage_id)


def _texts(stage: dict, field: str) -> str:
    rows = stage.get(field, []) or []
    return "\n".join(
        str(row.get("do") or row.get("action") or row) if isinstance(row, dict) else str(row)
        for row in rows
    )


class GuideUltimeIvoireExitInteractionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")

    def test_tal_kasha_requires_hem_before_exit(self) -> None:
        stage = _stage(self.payload, "L200-10")
        route = _texts(stage, "route")
        self.assertIn("Faire l'unique Tal Kasha", route)
        self.assertIn("Hem le Maudit", route)
        self.assertIn("AVANT de quitter la salle de sortie", route)

    def test_anerice_requires_both_exit_dialogues(self) -> None:
        stage = _stage(self.payload, "L200-12")
        route = _texts(stage, "route")
        self.assertIn("Anerice", route)
        self.assertIn("Funestaro", route)
        self.assertIn("avant sortie", route)

    def test_nileza_and_meno_dialogues_are_mandatory_before_exit(self) -> None:
        stage = _stage(self.payload, "L200-13")
        route = _texts(stage, "route")
        exits = _texts(stage, "hard_exit")

        self.assertIn("parler à Nileza", route)
        self.assertIn("AVANT de quitter sa salle de sortie", route)
        self.assertIn("Son nom est Personne", route)
        self.assertIn("parler au Capitaine Meno", route)
        self.assertIn("Pichon kloune", route)
        self.assertIn("SANS refaire le donjon", route)
        self.assertIn("Dialogue Nileza de salle de sortie", exits)
        self.assertIn("Dialogue Meno de salle de sortie", exits)
        self.assertIn("sans troisième Meno", exits)

    def test_sylargh_requires_brikolereux_before_exit(self) -> None:
        stage = _stage(self.payload, "L200-15")
        route = _texts(stage, "route")
        exits = _texts(stage, "hard_exit")

        self.assertIn("Nékoléreux instable", route)
        self.assertIn("détruire le brikoléreux", route)
        self.assertIn("NE PAS SORTIR", route)
        self.assertIn("Après résurrection", route)
        self.assertIn("aucun second Transporteur", exits)


if __name__ == "__main__":
    unittest.main()
