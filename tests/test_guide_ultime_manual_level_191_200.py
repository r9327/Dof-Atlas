from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualLevel191200Tests(unittest.TestCase):
    def test_bonta_1_100_v11_has_all_ranks_and_merge_hooks(self) -> None:
        resolved = load_manual_chapter(BASE / "bonta_1_100_v11.json")
        self.assertEqual(resolved["quest_range"], [1, 100])
        self.assertEqual(resolved["stage_count"], 49)
        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}
        self.assertIn("À glacer le sang", by_id["BNT-46"]["quests"])
        self.assertEqual(by_id["BNT-46"]["dungeon"]["name"], "Forgefroide de Missiz Frizz")
        self.assertIn("Fée d'hiver", by_id["BNT-48"]["quests"])
        self.assertIn("L'exorciste", by_id["BNT-48"]["quests"])
        self.assertIn("bonta_order_rank100_v1.json", json.dumps(by_id["BNT-48"], ensure_ascii=False))

    def test_order100_keeps_exactly_one_persisted_order(self) -> None:
        payload = json.loads((BASE / "bonta_order_rank100_v1.json").read_text(encoding="utf-8"))
        policy = payload["selection_policy"]
        self.assertEqual(policy["selector"], "persisted_bonta_order")
        self.assertTrue(policy["exactly_one"])
        self.assertTrue(policy["order_change_forbidden"])
        self.assertTrue(policy["unselected_routes_hidden"])
        self.assertEqual(set(payload["options"]), {"coeur vaillant", "oeil attentif", "esprit salvateur"})
        for option in payload["options"].values():
            self.assertIn("Aquadôme de Merkator", json.dumps(payload["shared_contract"], ensure_ascii=False))
            self.assertIn("Examen de passage", json.dumps(option, ensure_ascii=False))

    def test_level_191_200_v1_has_ivoire_causal_contracts(self) -> None:
        resolved = load_manual_chapter(BASE / "level_191_200_v1.json")
        self.assertEqual(resolved["stage_count"], 18)
        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}
        ids = [str(row.get("id") or "") for row in resolved["stages"]]
        self.assertEqual(len(ids), len(set(ids)))

        self.assertIn("bonta_order_rank100_v1.json", json.dumps(by_id["L200-05"], ensure_ascii=False))
        self.assertEqual(by_id["L200-06"]["dungeon"]["name"], "Défi du Chaloeil")
        self.assertEqual(by_id["L200-07"]["dungeon"]["boss"], "Protozorreur")
        self.assertEqual(by_id["L200-09"]["dungeon"]["name"], "Palais du roi Nidas")
        self.assertEqual(by_id["L200-12"]["dungeon"]["name"], "Manoir des Katrepat")

        meno = json.dumps(by_id["L200-13"], ensure_ascii=False)
        self.assertIn("RERUN CAUSAL MENO", meno)
        self.assertIn("Aucun troisième Meno", meno)
        self.assertIn("Laboratoire de Nileza", meno)

        final = json.dumps(by_id["L200-15"], ensure_ascii=False)
        self.assertIn("Dofus Ivoire obtenu uniquement si le runtime le confirme", final)
        checkpoint = json.dumps(by_id["L200-16"], ensure_ascii=False)
        self.assertIn("Aucune fausse validation Ébène", checkpoint)
        self.assertIn("Aucune fausse validation Nébuleux", checkpoint)
        self.assertIn("Aucune fausse validation DDG", checkpoint)


if __name__ == "__main__":
    unittest.main()
