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


class GuideUltimeNimotopiaIvoireCausalityTests(unittest.TestCase):
    def test_nimotopia_success_is_closed_before_level200_ivoire_gate(self) -> None:
        level190 = load_manual_chapter(MANUAL / "level_181_190_v15.json")
        level200 = load_manual_chapter(MANUAL / "level_191_200_v22.json")

        nimotopia = _stage(level190, "L190-09")
        bonheur = _stage(level200, "L200-11")

        expected_nimotopia_quests = {
            "Frais de porc inclus",
            "Nos amies les bêtes",
            "Il a fui, il a tout compris",
            "Shyriiwook",
            "À armes égales",
            "La valse des manuels",
        }
        self.assertTrue(expected_nimotopia_quests.issubset(set(nimotopia.get("quests", []))))
        self.assertIn("La chasse aux chasseurs", nimotopia.get("successes", []))

        requirements = "\n".join(
            str(row.get("requirement") or row)
            for row in bonheur.get("preparation", []) or []
            if isinstance(row, dict)
        )
        self.assertIn("La chasse aux chasseurs", requirements)
        self.assertTrue(
            any(
                bool(row.get("blocking")) and "La chasse aux chasseurs" in str(row.get("requirement") or "")
                for row in bonheur.get("preparation", []) or []
                if isinstance(row, dict)
            )
        )

    def test_nimotopia_order_and_single_razof_are_explicit(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_181_190_v15.json")
        stage = _stage(payload, "L190-09")
        route = _texts(stage, "route")
        exits = _texts(stage, "hard_exit")

        self.assertLess(route.index("Nos amies les bêtes"), route.index("Il a fui, il a tout compris"))
        dungeon = stage.get("dungeon")
        self.assertIsInstance(dungeon, dict)
        self.assertEqual(dungeon.get("name"), "Camp du Comte Razof")
        self.assertEqual(dungeon.get("boss"), "Comte Razof")
        self.assertFalse(bool(dungeon.get("capture_ocre")))

        self.assertIn("tonneau", route.lower())
        self.assertIn("parler au Comte Razof", route)
        self.assertIn("NE PAS SORTIR", route)
        self.assertIn("Aucun second Camp du Comte Razof", exits)

    def test_nimotopia_repair_preserves_canonical_macro_counts(self) -> None:
        manifest = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = manifest["canonical"]["chapters"]

        self.assertEqual(sum(int(row["stage_count"]) for row in chapters), 267)
        self.assertEqual(next(row for row in chapters if row["id"] == "level_181_190")["stage_count"], 24)
        self.assertEqual(next(row for row in chapters if row["id"] == "level_191_200")["stage_count"], 62)

        level190 = load_manual_chapter(MANUAL / "level_181_190_v15.json")
        self.assertEqual(len(level190.get("stages", [])), 24)


if __name__ == "__main__":
    unittest.main()
