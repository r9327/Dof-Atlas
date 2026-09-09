from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


BASE = Path(__file__).resolve().parents[1] / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeMerkatorCausalityTests(unittest.TestCase):
    def test_first_merkator_fuses_level180_threads_and_post_boss_dialogue(self) -> None:
        payload = load_manual_chapter(BASE / "level_171_180_v13.json")
        stages = {str(row.get("id") or ""): row for row in payload.get("stages", []) if isinstance(row, dict)}
        stage = stages["L180-13S"]
        rendered = str(stage)

        self.assertIn("Tour nage", rendered)
        self.assertIn("Pollution je dis non", rendered)
        self.assertIn("Test d'étanchéité", rendered)
        self.assertIn("Prise de notes", rendered)
        self.assertIn("Après le boss", rendered)
        self.assertIn("dialogue demandé par Pollution", rendered)
        self.assertIn("Merkator fait une seule fois", rendered)

    def test_order100_merkator_is_late_and_causal_for_every_order(self) -> None:
        payload = json.loads((BASE / "bonta_order_rank100_v1.json").read_text(encoding="utf-8"))
        shared = payload["shared_contract"]
        self.assertEqual(shared["dungeon"], "Aquadôme de Merkator")
        self.assertEqual(shared["rerun"], "causal")
        self.assertIn("L'exorciste", shared["reason"])
        self.assertIn("Merkator déjà fait au palier180", shared["reason"])
        self.assertTrue(any("interroger Merkator après le boss" in value for value in shared["route_policy"]))

        self.assertEqual(set(payload["options"]), {"coeur vaillant", "oeil attentif", "esprit salvateur"})
        for order_name, option in payload["options"].items():
            route = "\n".join(str(row.get("do") or "") for row in option.get("route", []) if isinstance(row, dict))
            self.assertIn("Merkator", route, order_name)
            self.assertIn("Après le boss, ne pas sortir", route, order_name)
            self.assertIn("puits de pouvoir englouti", route, order_name)


if __name__ == "__main__":
    unittest.main()
