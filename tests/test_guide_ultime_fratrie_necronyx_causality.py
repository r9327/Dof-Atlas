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


class GuideUltimeFratrieNecronyxCausalityTests(unittest.TestCase):
    def test_fratrie_is_started_at_kankreblath_then_closed_during_existing_saharach_route(self) -> None:
        astrub = load_manual_chapter(MANUAL / "astrub_v5.json")
        level70 = load_manual_chapter(MANUAL / "level_70_100_v10.json")

        astrub03 = _stage(astrub, "AST-03")
        astrub15 = _stage(astrub, "AST-15")
        level7000 = _stage(level70, "L70-00")
        saharach = _stage(level70, "L70-08")

        self.assertIn("Mieux vaut ne pas se fier à la première impression", astrub03.get("quests", []))
        self.assertIn("Aventure miniature", astrub15.get("quests", []))
        self.assertIn("Croquette Magique", _texts(astrub15, "route"))
        self.assertIn("À plus dans l'muldobus", level7000.get("quests", []))

        expected_fratrie = {
            "Ne tirez pas sur le messager",
            "À la rescousse des magypus",
            "Dernier contact",
            "La voix des morts",
            "Le fléau de Burin",
            "Le gang des Toxines",
            "Sombres desseins",
        }
        self.assertTrue(expected_fratrie.issubset(set(saharach.get("quests", []))))
        hard_exit = _texts(saharach, "hard_exit")
        self.assertIn("Le fléau de Burin", hard_exit)
        self.assertIn("Sombres desseins", hard_exit)

    def test_faire_le_mort_is_closed_during_sidimote_before_bonta95(self) -> None:
        level70 = load_manual_chapter(MANUAL / "level_70_100_v10.json")
        bonta = load_manual_chapter(MANUAL / "bonta_1_100_v17.json")

        sidimote = _stage(level70, "L70-10H")
        bonta95 = _stage(bonta, "BNT-45")

        self.assertIn("Le mort dort", sidimote.get("quests", []))
        self.assertIn("Faire le mort", sidimote.get("quests", []))
        self.assertIn("L'accès à la Cathédrale", _texts(sidimote, "route"))
        self.assertIn("Faire le mort", _texts(sidimote, "hard_exit"))

        preparation = json.dumps(bonta95.get("preparation", []), ensure_ascii=False)
        self.assertIn("Artefact Pandawushu Vent", preparation)
        self.assertIn("Artefact Pandawushu Eau", preparation)
        self.assertIn("Artefact Pandawushu Feu", preparation)
        self.assertIn("Artefact Pandawushu Roc", preparation)
        self.assertIn("Faire le mort", preparation)
        self.assertIn("Faire le mort", str(bonta95.get("entry") or ""))

    def test_level200_reuses_early_divine_access_then_builds_necronyx_and_shares_bethel_solar(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        merydique = _stage(payload, "P200-10")
        bethel = _stage(payload, "L200-15E1")
        solar = _stage(payload, "L200-15E6")

        self.assertIn("La colère des dieux", merydique.get("quests", []))
        expected_before_bethel = {
            "L'arme fatale",
            "Les coeurs livides",
            "Craquements de coeur",
            "La guerre des Marches",
            "La quête sous l'eau",
            "Le jour des assassins",
            "Le piège se referme",
        }
        self.assertTrue(expected_before_bethel.issubset(set(bethel.get("quests", []))))
        self.assertNotIn("La colère des dieux", bethel.get("quests", []))
        self.assertIn("Les coeurs livides", solar.get("quests", []))

        bethel_take = _texts(bethel, "take")
        bethel_route = _texts(bethel, "route")
        bethel_exit = _texts(bethel, "hard_exit")
        solar_route = _texts(solar, "route")
        solar_exit = _texts(solar, "hard_exit")

        self.assertIn("déjà réellement terminée depuis P200-10", bethel_take)
        self.assertIn("Nécronyx permanent", bethel_route)
        self.assertIn("Raval le Terrible", bethel_route)
        self.assertIn("La Fratrie des Oubliés", bethel_exit)
        self.assertIn("Dieu Sram", solar_route)
        self.assertIn("L'armée des morts", solar_exit)
        self.assertIn("aucun troisième passage Bethel/Solar", solar_route)

    def test_causal_repairs_do_not_increase_macro_stage_count(self) -> None:
        manifest = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = manifest["canonical"]["chapters"]
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters), 267)
        self.assertEqual(next(row for row in chapters if row["id"] == "astrub")["stage_count"], 16)
        self.assertEqual(next(row for row in chapters if row["id"] == "level_70_100")["stage_count"], 17)
        self.assertEqual(next(row for row in chapters if row["id"] == "level_191_200")["stage_count"], 62)


if __name__ == "__main__":
    unittest.main()
