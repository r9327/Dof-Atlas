from __future__ import annotations

import json
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


class GuideUltimeIvoireSylarghExitCausalityTests(unittest.TestCase):
    def test_sylargh_exit_interaction_is_mandatory_before_leaving(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        stage = _stage(payload, "L200-15")

        route_rows = stage.get("route", []) or []
        route = _texts(stage, "route")
        exits = _texts(stage, "hard_exit")

        self.assertIn("Il est temps de mourir", stage.get("quests", []))
        self.assertIn("Faire un seul Transporteur", route)
        self.assertIn("Nékoléreux instable", route)
        self.assertIn("détruire le brikoléreux", route)
        self.assertIn("NE PAS SORTIR", route)
        self.assertIn("L'explosion tue automatiquement le personnage", route)
        self.assertIn("Après résurrection", route)
        self.assertIn("parler à Agonie", route)

        boss_index = next(
            index
            for index, row in enumerate(route_rows)
            if isinstance(row, dict) and "vaincre Sylargh" in str(row.get("do") or "")
        )
        exit_interaction_index = next(
            index
            for index, row in enumerate(route_rows)
            if isinstance(row, dict) and "Nékoléreux instable" in str(row.get("do") or "")
        )
        agonie_index = next(
            index
            for index, row in enumerate(route_rows)
            if isinstance(row, dict) and "parler à Agonie" in str(row.get("do") or "")
        )
        self.assertLess(boss_index, exit_interaction_index)
        self.assertLess(exit_interaction_index, agonie_index)

        self.assertIn("brikoléreux détruit AVANT toute sortie", exits)
        self.assertIn("aucun second Transporteur", exits)

    def test_final_ivoire_route_keeps_single_sylargh_for_this_thread(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        stage = _stage(payload, "L200-15")

        route = _texts(stage, "route")
        self.assertIn("Faire un seul Transporteur", route)
        self.assertIn("Aucun second Sylargh ne doit être nécessaire", route)
        self.assertIn("Hyrkul", route)
        self.assertIn("Dofus Ivoire", route)

    def test_sylargh_repair_preserves_canonical_stage_count(self) -> None:
        manifest = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = manifest["canonical"]["chapters"]
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters), 267)
        self.assertEqual(next(row for row in chapters if row["id"] == "level_191_200")["stage_count"], 62)

        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        self.assertEqual(len(payload.get("stages", [])), 62)


if __name__ == "__main__":
    unittest.main()
