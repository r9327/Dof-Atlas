from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"


def _stage(payload: dict, stage_id: str) -> dict:
    return next(stage for stage in payload.get("stages", []) if stage.get("id") == stage_id)


def _text(stage: dict, field: str) -> str:
    return json.dumps(stage.get(field, []), ensure_ascii=False)


class GuideUltimeMerydiqueCausalityTests(unittest.TestCase):
    def test_divine_access_and_merydique_chain_are_closed_before_reminiscence_totems(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        self.assertEqual(payload["stage_count"], 62)
        self.assertEqual(payload["stage_count"], len(payload["stages"]))

        ids = [str(stage.get("id") or "") for stage in payload["stages"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLess(ids.index("P200-10"), ids.index("P200-15"))

        merydique = _stage(payload, "P200-10")
        self.assertIn("La colère des dieux", merydique.get("quests", []))
        self.assertIn("Un pouvoir mérydique", merydique.get("quests", []))
        self.assertIn("Mort et renouveau", merydique.get("quests", []))

        route = _text(merydique, "route")
        hard_exit = _text(merydique, "hard_exit")
        preparation = _text(merydique, "preparation")

        self.assertIn("La colère des dieux", route)
        self.assertIn("AVANT l'étape qui exige l'accès au Domaine des dieux", route)
        self.assertIn("Alchimiste niveau 40 personnel", preparation)
        self.assertIn("Potion de Bivoak", preparation)

        kimbo = route.index("Canopée du Kimbo")
        chene = route.index("Clairière du Chêne Mou")
        ougah = route.index("Temple du Grand Ougah")
        arbre = route.index("Arbre des vagabonds")
        self.assertLess(kimbo, chene)
        self.assertLess(chene, ougah)
        self.assertLess(ougah, arbre)

        self.assertGreaterEqual(route.count("Bourgeon parasite"), 4)
        self.assertGreaterEqual(route.count("Idole Mérydique"), 4)
        self.assertGreaterEqual(route.count("NE PAS SORTIR"), 3)
        self.assertIn("Mort et renouveau réellement terminés", hard_exit)

        totems = _stage(payload, "P200-15")
        totem_text = json.dumps(totems, ensure_ascii=False)
        self.assertIn("Un héritage tourmenté", totem_text)
        self.assertIn("Mort et renouveau", totem_text)

    def test_trapamorts_reuses_divine_access_without_restarting_la_colere(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        merydique = _stage(payload, "P200-10")
        trapamorts = _stage(payload, "L200-15E1")

        self.assertIn("La colère des dieux", merydique.get("quests", []))
        self.assertNotIn("La colère des dieux", trapamorts.get("quests", []))
        self.assertIn("L'arme fatale", trapamorts.get("quests", []))
        self.assertIn("Les coeurs livides", trapamorts.get("quests", []))

        take = _text(trapamorts, "take")
        route = _text(trapamorts, "route")
        hard_exit = _text(trapamorts, "hard_exit")
        self.assertIn("déjà réellement terminée depuis P200-10", take)
        self.assertIn("Réutiliser l'accès ouvert plus tôt", route)
        self.assertIn("aucun doublon de quête ou d'accès", hard_exit)

    def test_merydique_repair_keeps_canonical_macro_count(self) -> None:
        manifest = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = manifest["canonical"]["chapters"]
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters), 267)
        level200 = next(row for row in chapters if row["id"] == "level_191_200")
        self.assertEqual(level200["file"], "level_191_200_v22.json")
        self.assertEqual(level200["stage_count"], 62)


if __name__ == "__main__":
    unittest.main()
