from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.guide_ultime_generated_service import GuideUltimeGeneratedService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import AchievementProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.views.guide_ultime_generated_view import GuideUltimeGeneratedView


class FakeAchievementProvider:
    def __init__(self, achievements=()):
        self._rows = tuple(achievements)

    def load_retained(self):
        return self._rows


class GuideUltimeV5UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.quest_path = self.root / "quest_progress.json"
        self.achievement_path = self.root / "achievement_progress.json"
        self.guide_path = self.root / "guide_progress.json"
        self.route_path = self.root / "guide_ultime_gps_route.json"
        self.final_path = self.root / "guide_ultime_final.json"
        self._write_route(30)
        self.final_path.write_text(json.dumps({"schema_version": 5}), encoding="utf-8")
        self.make_services()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_services(self) -> None:
        self.q = QuestProgressService(self.quest_path)
        self.a = AchievementProgressService(self.achievement_path)
        self.g = GuideProgressService(self.guide_path)
        self.v5 = GuideUltimeGeneratedService(
            self.q, self.a, self.g,
            route_path=self.route_path,
            final_path=self.final_path,
        )

    def _write_route(self, count: int) -> None:
        cards = []
        for index in range(1, count + 1):
            qid = index
            card = {
                "index": index,
                "planned_at_level": min(200, index),
                "destination": f"[{index},0] Zone",
                "x": index,
                "y": 0,
                "zone": "Zone",
                "subzone": "Sous-zone",
                "a_prendre": [{
                    "quest_id": qid,
                    "quest_name": f"Quest {qid}",
                    "action_id": f"quest:{qid}:start",
                    "title": f"Prendre — Quest {qid}",
                    "kind": "start",
                    "objective_id": None,
                }],
                "a_faire_ici": [],
                "progresse_aussi": {"quest_ids": [qid], "success_ids": []},
                "a_preparer": [],
                "hard_runtime_gates": [],
                "conditional_branch_gates": [],
                "avant_de_partir": [],
                "succes_monstres_a_faire": [],
                "succes_donjon_a_faire": [],
                "ensuite": None,
            }
            if index == 1:
                card["a_preparer"] = [{"item_id": 9001, "name": "Ressource test", "quantity": 10}]
                card["succes_monstres_a_faire"] = [{"achievement_id": 501, "name": "Monstres test"}]
            if index == 2:
                card["succes_donjon_a_faire"] = [{"achievement_id": 502, "name": "Donjon test"}]
            cards.append(card)
        payload = {
            "schema_version": 5,
            "id": "guide_ultime_gps_route",
            "universal_route": {
                "common_route_quest_count": count,
                "qq_required_count": 1600,
            },
            "conditional_branches": {
                "class_card": {
                    "required_slots": 1,
                    "options": [
                        {"class": "Huppermage", "quest_id": 7001},
                        {"class": "Eliotrope", "quest_id": 7002},
                    ],
                },
                "order_cards": [
                    {
                        "rank": rank,
                        "alignment_level": rank,
                        "options": [
                            {"order": "Coeur Vaillant", "quest_id": 8000 + rank},
                            {"order": "Oeil Attentif", "quest_id": 8100 + rank},
                            {"order": "Esprit Salvateur", "quest_id": 8200 + rank},
                        ],
                    }
                    for rank in (20, 40, 60, 80, 100)
                ],
                "order_required_slots": 5,
                "guide_is_single_universal_route": True,
            },
            "full_success_cards": {
                "monster_success_cards": [{"achievement_id": 501, "name": "Monstres test"}],
                "dungeon_success_cards": [{
                    "dungeon_id": 10,
                    "dungeon_name": "Donjon test",
                    "achievements": [{"achievement_id": 502, "name": "Donjon test"}],
                }],
                "dungeon_meta_success_cards": [],
            },
            "steps": cards,
        }
        self.route_path.write_text(json.dumps(payload), encoding="utf-8")

    # 1. chargement V5
    def test_01_loads_generated_gps_route(self):
        self.assertTrue(self.v5.available)
        self.assertEqual(len(self.v5.cards), 30)
        self.assertEqual(self.v5.route["id"], "guide_ultime_gps_route")

    # 2. l'ancien identifiant de catalogue ouvre désormais la route manuelle canonique
    def test_02_guides_wrapper_routes_legacy_id_to_manual_guide(self):
        source = (Path(__file__).parents[1] / "app/modules/encyclopedia/views/guides_view.py").read_text(encoding="utf-8")
        self.assertIn("GuideUltimeManualRuntimeService", source)
        self.assertIn("GuideUltimeManualView", source)
        self.assertIn('GUIDE_ULTIME_LEGACY_ID = "guide_complet"', source)
        self.assertNotIn("guides_view_legacy", source)

    # 3. Guide ↔ Quêtes : même fichier/source de vérité
    def test_03_shared_quest_progress_is_single_source(self):
        quests_view_service = QuestProgressService(self.quest_path)
        quests_view_service.set_quest_completed("character:1", 3, True)
        self.assertTrue(self.v5.quest_progress.reload() and self.v5.quest_progress.is_quest_completed("character:1", 3))
        self.v5.quest_progress.set_quest_completed("character:1", 4, True)
        quests_view_service.reload()
        self.assertTrue(quests_view_service.is_quest_completed("character:1", 4))

    # 4. reprise rétroactive
    def test_04_existing_progress_jumps_to_first_real_card(self):
        self.q.set_quest_completed("character:1", 1, True)
        self.q.set_quest_completed("character:1", 2, True)
        self.a.set_achievement_completed("character:1", 501, True)
        self.a.set_achievement_completed("character:1", 502, True)
        self.assertEqual(self.v5.first_incomplete_index("character:1"), 2)

    # 5. ressource cochable persistante et indépendante d'une quête
    def test_05_resource_state_persists_without_completing_quest(self):
        card = self.v5.cards[0]
        key = self.v5.resource_key(card, card["a_preparer"][0], 0, 0)
        self.v5.set_manual_checked("character:1", key, True)
        self.assertFalse(self.q.is_quest_completed("character:1", 1))
        reloaded = GuideProgressService(self.guide_path)
        self.assertTrue(reloaded.is_manual_step_completed("character:1", "guide_ultime_v5", key))

    # 6. Guide Dofus : écrire ailleurs est immédiatement lu par V5
    def test_06_dofus_guide_quest_completion_is_reused(self):
        dofus_guide_shared = QuestProgressService(self.quest_path)
        dofus_guide_shared.set_quest_completed("character:1", 6, True)
        self.q.reload()
        self.assertTrue(self.v5.card_state("character:1", self.v5.cards[5], 5).complete)

    # 7. Alignement : même mécanisme partagé
    def test_07_alignment_quest_completion_is_reused(self):
        alignment_shared = QuestProgressService(self.quest_path)
        alignment_shared.set_quest_completed("character:1", 7, True)
        self.q.reload()
        self.assertTrue(self.v5.card_state("character:1", self.v5.cards[6], 6).complete)

    # 8. succès Quêtes dérivé du QuestProgressService
    def test_08_quest_achievement_sync_uses_shared_quest_state(self):
        ref = SimpleNamespace(entity_type="quest", entity_id=8)
        objective = SimpleNamespace(id=11, objective_type="", criterion="", entity_refs=(ref,))
        achievement = SimpleNamespace(id=600, category_name="Quêtes", objectives=(objective,))
        provider = FakeAchievementProvider((achievement,))
        self.q.set_quest_completed("character:1", 8, True)
        changed = self.a.sync_from_quest_progress("character:1", provider, self.q)
        self.assertTrue(changed)
        self.assertTrue(self.a.is_achievement_completed("character:1", 600))

    # 9. succès Monstres existant reconnu
    def test_09_monster_success_state_is_shared(self):
        self.a.set_achievement_completed("character:1", 501, True)
        self.assertTrue(self.a.is_achievement_completed("character:1", self.v5.card_success_ids(self.v5.cards[0])[0]))

    # 10. succès Donjons existant reconnu
    def test_10_dungeon_success_state_is_shared(self):
        self.a.set_achievement_completed("character:1", 502, True)
        self.assertTrue(self.a.is_achievement_completed("character:1", self.v5.card_success_ids(self.v5.cards[1])[0]))

    # 11. choix d'Ordre persistant, uniquement Bonta
    def test_11_bonta_order_choice_persists(self):
        self.v5.set_bonta_order("character:1", "Oeil Attentif")
        reloaded = AchievementProgressService(self.achievement_path)
        self.assertEqual(reloaded.alignment_order_choice("character:1"), ("bonta", "Oeil Attentif"))
        self.assertEqual(len(self.v5.selected_order_quest_ids("character:1")), 5)

    # 12. carte classe : une branche, pas 19 profils générés
    def test_12_class_branch_is_inferred_from_shared_completion(self):
        self.q.set_quest_completed("character:1", 7001, True)
        option = self.v5.inferred_class_option("character:1")
        self.assertIsNotNone(option)
        self.assertEqual(option["class"], "Huppermage")

    # 13. passage automatique à la prochaine carte
    def test_13_auto_advance_after_real_completion(self):
        self.a.set_achievement_completed("character:1", 501, True)
        key = self.v5.resource_key(self.v5.cards[0], self.v5.cards[0]["a_preparer"][0], 0, 0)
        self.v5.set_manual_checked("character:1", key, True)
        self.q.set_quest_completed("character:1", 1, True)
        self.assertEqual(self.v5.first_incomplete_index("character:1"), 1)

    # 14. carte terminée ne redevient pas active après reload
    def test_14_completed_card_stays_behind_after_restart(self):
        self.q.set_quest_completed("character:1", 1, True)
        self.a.set_achievement_completed("character:1", 501, True)
        self.make_services()
        self.assertGreaterEqual(self.v5.first_incomplete_index("character:1"), 1)

    # 15. virtualisation : jamais une instance QWidget par carte GPS
    def test_15_view_instantiates_only_small_window(self):
        view = GuideUltimeGeneratedView(self.v5, character_key="character:1")
        view.show()
        QApplication.processEvents()
        self.assertLessEqual(view.rendered_card_count, view.WINDOW_BEFORE + view.WINDOW_AFTER + 1)
        self.assertLess(view.rendered_card_count, len(self.v5.cards))
        view.close()


if __name__ == "__main__":
    unittest.main()
