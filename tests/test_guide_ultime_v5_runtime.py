from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.guide_ultime_runtime_service import GuideUltimeRuntimeService
from app.modules.encyclopedia.services.progress_service import AchievementProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService


class GuideUltimeV5RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        route = root / "route.json"
        final = root / "final.json"
        orders = [
            "Coeur Saignant", "Coeur Vaillant",
            "Esprit Malsain", "Esprit Salvateur",
            "Oeil Putride", "Oeil Attentif",
        ]
        route.write_text(json.dumps({
            "schema_version": 5,
            "universal_route": {"common_route_quest_count": 1, "qq_required_count": 1600},
            "conditional_branches": {
                "class_card": {"options": [
                    {"class": "Huppermage", "quest_id": 7001},
                    {"class": "Eliotrope", "quest_id": 7002},
                ]},
                "order_cards": [
                    {"rank": rank, "options": [
                        {"order": name, "quest_id": 10000 + rank * 10 + offset}
                        for offset, name in enumerate(orders)
                    ]}
                    for rank in (20, 40, 60, 80, 100)
                ],
            },
            "full_success_cards": {},
            "steps": [{
                "index": 1,
                "a_prendre": [{"quest_id": 1, "title": "Quest 1"}],
                "a_faire_ici": [],
                "progresse_aussi": {"quest_ids": [1]},
                "a_preparer": [],
                "hard_runtime_gates": [],
                "profession_gates": [],
                "avant_de_partir": [],
                "succes_monstres_a_faire": [],
                "succes_donjon_a_faire": [],
                "conditional_branch_gates": [{
                    "gate_type": "universal_class_card",
                    "required_count": 1,
                    "class_quest_options": [7001, 7002],
                }],
            }],
        }), encoding="utf-8")
        final.write_text(json.dumps({"schema_version": 5}), encoding="utf-8")
        self.q = QuestProgressService(root / "quests.json")
        self.a = AchievementProgressService(root / "achievements.json")
        self.g = GuideProgressService(root / "guides.json")
        self.service = GuideUltimeRuntimeService(
            self.q, self.a, self.g, route_path=route, final_path=final
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_only_three_bonta_orders_are_exposed(self):
        self.assertEqual(
            self.service.bonta_order_names(),
            ("Coeur Vaillant", "Oeil Attentif", "Esprit Salvateur"),
        )
        self.service.set_bonta_order("character:1", "Oeil Attentif")
        self.assertEqual(len(self.service.selected_order_quest_ids("character:1")), 5)

    def test_class_gate_blocks_common_card_until_one_class_quest_is_done(self):
        self.q.set_quest_completed("character:1", 1, True)
        self.assertFalse(self.service.card_state("character:1", self.service.cards[0], 0).complete)
        self.q.set_quest_completed("character:1", 7001, True)
        self.assertTrue(self.service.card_state("character:1", self.service.cards[0], 0).complete)


if __name__ == "__main__":
    unittest.main()
