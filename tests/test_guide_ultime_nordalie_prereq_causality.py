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


class GuideUltimeNordaliePrerequisiteCausalityTests(unittest.TestCase):
    def test_allumer_le_feu_is_really_closed_on_the_shared_meulou(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_100_120_v9.json")
        stage = _stage(payload, "L100-03")

        self.assertIn("Allumer le feu", stage.get("quests", []))
        route = _texts(stage, "route")
        exits = _texts(stage, "hard_exit")
        self.assertIn("Allumer le feu", route)
        self.assertIn("six os", route)
        self.assertIn("Hurlements de rire fermé", exits)
        self.assertIn("Un seul Meulou", exits)

    def test_malediction_is_really_closed_before_level200(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_120_150_v21.json")
        stage = _stage(payload, "L120-21M")

        self.assertIn("Malédiction !", stage.get("quests", []))
        self.assertIn("Malédiction ! terminée", _texts(stage, "before_leaving"))
        self.assertIn("L'âme de glace", _texts(stage, "hard_exit"))

    def test_nordalie_closes_tal_kasha_and_la_garde_before_four_missions(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        stage = _stage(payload, "L200-10")

        self.assertIn("La garde meurt mais ne se rend pas", stage.get("quests", []))
        self.assertEqual((stage.get("dungeon") or {}).get("name"), "Chambre de Tal Kasha")

        route_rows = stage.get("route", []) or []
        route = _texts(stage, "route")
        exits = _texts(stage, "hard_exit")

        # GPS values for modern Nordalie must not be frozen by this causal test:
        # the route data may only carry coordinates that were independently
        # re-verified against current DPLN/local data. What matters here is the
        # exact prerequisite/action ordering that prevents a Tal Kasha rerun.
        self.assertIn("10/10", route)
        self.assertIn("Rendre La garde meurt mais ne se rend pas", route)
        self.assertIn("Poiskaille fantôme", route)
        self.assertIn("Faire l'unique Tal Kasha", route)
        self.assertIn("Hem le Maudit", route)
        self.assertIn("AVANT de quitter la salle de sortie", route)
        self.assertIn("Le bonheur est dans le spray", route)
        self.assertIn("Une voix de crystal", route)
        self.assertIn("Le mort dans l'âme", route)
        self.assertIn("Le guerrier noir", route)

        la_garde_index = next(
            index
            for index, row in enumerate(route_rows)
            if isinstance(row, dict) and "Rendre La garde meurt mais ne se rend pas" in str(row.get("do") or "")
        )
        tal_kasha_index = next(
            index
            for index, row in enumerate(route_rows)
            if isinstance(row, dict) and "Faire l'unique Tal Kasha" in str(row.get("do") or "")
        )
        missions_index = next(
            index
            for index, row in enumerate(route_rows)
            if isinstance(row, dict) and "ouvre les quatre missions" in str(row.get("do") or "")
        )
        self.assertLess(la_garde_index, missions_index)
        self.assertLess(tal_kasha_index, missions_index)

        requirements = [
            row
            for row in stage.get("preparation", []) or []
            if isinstance(row, dict) and row.get("requirement")
        ]
        self.assertTrue(any("Malédiction !" in str(row["requirement"]) and row.get("blocking") for row in requirements))
        self.assertTrue(any("Allumer le feu" in str(row["requirement"]) and row.get("blocking") for row in requirements))
        self.assertIn("Tal Kasha terminé", exits)
        self.assertIn("Hem le Maudit", exits)
        self.assertIn("Les trois démonstrations du destin terminées", exits)

    def test_late_nordalie_stage_no_longer_repeats_tal_kasha(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        stage = _stage(payload, "L200-14")

        self.assertIsNone(stage.get("dungeon"))
        route = _texts(stage, "route")
        exits = _texts(stage, "hard_exit")

        self.assertIn("placer le fil de Dardondakal", route)
        self.assertIn("Affronter Hyrkul", route)
        self.assertIn("Nordalie se termine ici", route)
        self.assertIn("aucun Tal Kasha ici", route)
        self.assertIn("Aucun Tal Kasha après l'ouverture des quatre missions", exits)

    def test_nordalie_repair_preserves_canonical_stage_count(self) -> None:
        manifest = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = manifest["canonical"]["chapters"]
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters), 267)
        self.assertEqual(next(row for row in chapters if row["id"] == "level_191_200")["stage_count"], 62)
        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        self.assertEqual(len(payload.get("stages", [])), 62)


if __name__ == "__main__":
    unittest.main()
