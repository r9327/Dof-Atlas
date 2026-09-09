from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualPost200Tests(unittest.TestCase):
    def _by_id(self, filename: str) -> tuple[dict, list[str], dict[str, dict]]:
        payload = load_manual_chapter(BASE / filename)
        stages = [row for row in payload.get("stages", []) if isinstance(row, dict)]
        ids = [str(row.get("id") or "") for row in stages]
        return payload, ids, {str(row.get("id") or ""): row for row in stages}

    def test_legacy_backpatches_are_composed(self) -> None:
        astrub, _, ast = self._by_id("astrub_v4.json")
        self.assertEqual(astrub["stage_count"], 16)
        self.assertIn("Bûcherons en détresse", ast["AST-05"]["quests"])

        level100, _, by100 = self._by_id("level_100_120_v6.json")
        self.assertEqual(level100["stage_count"], 16)
        for quest in ("À la croisée des mondes", "Sous le bois de sa colère", "Infâme pourriture", "Le Saule du Promeneur", "Dites-le avec des fleurs"):
            self.assertIn(quest, by100["L100-15"]["quests"])

        level181, ids181, by181 = self._by_id("level_181_190_v4.json")
        self.assertEqual(level181["stage_count"], len(ids181))
        text = json.dumps(by181["L181-00"], ensure_ascii=False)
        self.assertIn("métier de récolte niveau200", text)
        self.assertIn("Vulbis", text)
        self.assertIn("Six sur six", text)

    def test_vulbis_is_enabled_before_final_level200_boss_campaign(self) -> None:
        payload, ids, by = self._by_id("level_191_200_v6.json")
        self.assertEqual(payload["stage_count"], 36)
        self.assertLess(ids.index("L200-VUL0"), ids.index("L200-DDG1"))
        self.assertLess(ids.index("L200-VUL1"), ids.index("L200-DDG1"))
        self.assertLess(ids.index("L200-VUL2"), ids.index("L200-16"))

        self.assertIn("La mère des Dragoeufs", by["L200-VUL0"]["quests"])
        vul0 = json.dumps(by["L200-VUL0"], ensure_ascii=False)
        self.assertIn("0,7%", vul0)
        self.assertIn("jamais en arène", vul0)
        self.assertEqual(by["L200-VUL1"]["dungeon"]["name"], "Sanctuaire de Torkélonia")
        self.assertTrue(by["L200-VUL1"]["dungeon"]["parangon_attempt"])
        self.assertIn("Dofus Vulbis obtenu si et seulement si runtime confirmé", json.dumps(by["L200-VUL2"], ensure_ascii=False))

    def test_post200_v4_closes_main_dofus_chain_without_synthetic_completion(self) -> None:
        payload, ids, by = self._by_id("level_200_plus_v4.json")
        self.assertEqual(payload["stage_count"], 26)
        self.assertEqual(len(ids), len(set(ids)))
        for row in payload["stages"]:
            self.assertTrue(row.get("pause") or row.get("pause_checkpoint"), row.get("id"))

        self.assertIn("L'éternelle moisson", by["P200-00"]["quests"])
        self.assertIn("Quatre sur six", json.dumps(by["P200-05"], ensure_ascii=False))
        self.assertIn("Six sur six", json.dumps(by["P200-08"], ensure_ascii=False))
        self.assertIn("Prise de conscience", by["P200-10"]["quests"])
        self.assertIn("En ce jardin qui nous unit", by["P200-11"]["quests"])
        self.assertIn("Par ce serment s'écrit le monde", by["P200-12"]["quests"])
        self.assertIn("Descendre aux cendres", by["P200-14"]["quests"])
        self.assertIn("Les totems de Maïmane", by["P200-15"]["quests"])
        self.assertIn("La bête au bois dormant", by["P200-16"]["quests"])

        self.assertIn("L'héritage de l'île brisée", json.dumps(by["P200-20"], ensure_ascii=False))
        self.assertEqual(by["P200-21"]["dungeon"]["name"], "Akadémie des Gobs")
        self.assertIn("Gobalden", json.dumps(by["P200-21"], ensure_ascii=False))
        self.assertIn("Dom de Pin réellement obtenu", json.dumps(by["P200-21"], ensure_ascii=False))

        self.assertIn("Cultures et turpitudes", by["P200-22"]["quests"])
        protecteur = json.dumps(by["P200-23"], ensure_ascii=False)
        for token in ("Palais du Roi Nidas", "Bataille de l'Aurore Pourpre", "Tour de Solar", "100 Âmes de Possédé", "Elya Wood"):
            self.assertIn(token, protecteur)

        flovoraison = by["P200-24"]
        self.assertEqual(flovoraison["dungeon"]["boss"], "Belladone")
        self.assertIn("final_dofus_sylvestre=false", flovoraison["hard_exit"])
        self.assertIn("quest_receptacle_sylvestre=true", flovoraison["hard_exit"])

        final = json.dumps(by["P200-25"], ensure_ascii=False)
        self.assertIn("200000", final)
        self.assertIn("Vrai Dofus Sylvestre reçu", final)
        self.assertIn("final_dofus_sylvestre=true only_if_runtime_confirmed", by["P200-25"]["hard_exit"])


if __name__ == "__main__":
    unittest.main()
