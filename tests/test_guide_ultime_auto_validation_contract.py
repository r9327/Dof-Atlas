from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_auto_validation_contract import (
    AUTO_VALIDATION_SCHEMA_VERSION,
    build_card_auto_validation_contract,
    build_route_auto_validation_contract,
    route_progress_counts,
)
from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    GuideManualProgressBar,
    GuideUltimeManualCard,
    GuideUltimeManualView,
)


class _AchievementProvider:
    def load_all(self):
        return [SimpleNamespace(id=123, name="Circulez")]


class _QuestProgress:
    def completed_quest_ids(self, _character_key: str):
        return {10}


class _Service:
    def __init__(self, cards):
        self.cards = cards
        self.quest_progress = _QuestProgress()

    def card_state(self, _character_key: str, _card: dict, index: int):
        return SimpleNamespace(complete=index == 0)


class GuideUltimeAutoValidationContractTests(unittest.TestCase):
    def _card(self) -> dict:
        return {
            "index": 1,
            "manual_source": True,
            "manual_chapter_id": "test",
            "manual_stage_id": "GPS-01",
            "manual_quest_ids": [10],
            "manual_quest_names": ["Quête test"],
            "manual_success_names": ["Circulez"],
            "a_preparer": [
                {"name": "Plume de Glan", "quantity": 74, "policy": "Garder en banque pour plus tard."},
                {"name": "Pierre d'âme", "quantity": 1, "for": "Donjon test"},
            ],
            "manual_lines": [
                {"kind": "action", "text": "Farmer 22 Glans dans la forêt."},
            ],
            "manual_stage_data": {
                "id": "GPS-01",
                "dungeon": {"name": "Donjon des Glans", "boss": "Roi Glan"},
                "monsters": [{"name": "Glan", "quantity": 22}],
            },
        }

    def test_contract_exposes_every_future_network_domain(self):
        route = build_route_auto_validation_contract(
            [self._card()],
            achievement_provider=_AchievementProvider(),
        )
        self.assertEqual(route["schema_version"], AUTO_VALIDATION_SCHEMA_VERSION)
        row = route["cards"][0]
        self.assertEqual(row["card_key"], "manual:test:GPS-01")
        self.assertEqual(row["quests"][0]["quest_id"], 10)
        self.assertEqual(row["successes"][0]["achievement_id"], 123)
        self.assertEqual(row["dungeons"][0]["name"], "Donjon des Glans")
        self.assertEqual(row["monsters"][0]["quantity"], 22)
        self.assertEqual(row["reserved_items"][0]["quantity"], 74)
        self.assertEqual(row["bank_reservations"][0]["quantity"], 74)
        self.assertEqual(row["capture_requirements"][0]["quantity"], 1)
        self.assertEqual(row["missing_structured_categories"], [])

    def test_waypoint_success_dungeon_and_monster_targets_are_consumed(self):
        card = self._card()
        card["manual_success_names"] = []
        card["manual_stage_data"] = {
            "id": "GPS-01",
            "waypoints": [
                {
                    "successes": ["Circulez"],
                    "dungeon": {"name": "Donjon waypoint", "boss": "Boss waypoint"},
                    "monsters": [{"name": "Mob waypoint", "quantity": 7}],
                }
            ],
        }
        row = build_route_auto_validation_contract(
            [card], achievement_provider=_AchievementProvider()
        )["cards"][0]
        self.assertEqual(row["successes"][0]["achievement_id"], 123)
        self.assertEqual(row["dungeons"][0]["name"], "Donjon waypoint")
        self.assertEqual(row["monsters"][0]["name"], "Mob waypoint")
        self.assertEqual(row["monsters"][0]["quantity"], 7)

    def test_prose_farm_without_structured_monsters_is_reported_not_guessed(self):
        card = self._card()
        card["manual_stage_data"] = {"id": "GPS-01"}
        row = build_card_auto_validation_contract(card)
        self.assertIn("monster_farm", row["missing_structured_categories"])
        self.assertEqual(row["monsters"], [])
        self.assertTrue(row["prose_farm_hints"])

    def test_unstructured_reserve_bank_capture_and_item_quantities_are_reported(self):
        card = self._card()
        card["a_preparer"] = []
        card["manual_stage_data"] = {"id": "GPS-01"}
        card["manual_lines"] = [
            {"kind": "action", "text": "Conserver 20 Plumes de Glan pour plus tard."},
            {"kind": "action", "text": "Mettre 74 Plumes de Glan en banque."},
            {"kind": "warning", "text": "Prévoir 1 Pierre d'âme avant le donjon."},
            {"kind": "action", "text": "Apporter 3 Clefs usées au PNJ."},
        ]
        row = build_card_auto_validation_contract(card)
        self.assertIn("reserve_stock", row["missing_structured_categories"])
        self.assertIn("bank_stock", row["missing_structured_categories"])
        self.assertIn("capture_stock", row["missing_structured_categories"])
        self.assertIn("item_quantity", row["missing_structured_categories"])
        self.assertTrue(row["prose_hints"]["reserve_stock"])
        self.assertTrue(row["prose_hints"]["bank_stock"])
        self.assertTrue(row["prose_hints"]["capture_stock"])
        self.assertTrue(row["prose_hints"]["item_quantity"])

    def test_generic_keep_instruction_is_reserved_but_not_falsely_marked_as_bank(self):
        card = self._card()
        card["a_preparer"] = [
            {"name": "Bave de Bouftou", "quantity": 4, "policy": "Conserver pour la quête suivante."},
        ]
        row = build_card_auto_validation_contract(card)
        self.assertEqual(len(row["reserved_items"]), 1)
        self.assertEqual(row["reserved_items"][0]["name"], "Bave de Bouftou")
        self.assertEqual(row["bank_reservations"], [])

    def test_explicit_bank_source_field_is_bank_even_without_wording(self):
        card = self._card()
        card["a_preparer"] = [
            {"name": "Ressource rare", "quantity": 12, "_source_field": "keep_in_bank"},
        ]
        row = build_card_auto_validation_contract(card)
        self.assertEqual(len(row["reserved_items"]), 1)
        self.assertEqual(len(row["bank_reservations"]), 1)

    def test_same_item_for_distinct_future_uses_is_never_collapsed(self):
        card = self._card()
        card["a_preparer"] = [
            {"name": "Plume de Glan", "quantity": 20, "for": "Quête A", "policy": "Garder en banque."},
            {"name": "Plume de Glan", "quantity": 54, "for": "Quête B", "policy": "Garder en banque."},
        ]
        row = build_card_auto_validation_contract(card)
        self.assertEqual([target["quantity"] for target in row["items"]], [20, 54])
        self.assertEqual([target["quantity"] for target in row["reserved_items"]], [20, 54])
        self.assertEqual([target["quantity"] for target in row["bank_reservations"]], [20, 54])
        self.assertNotEqual(row["items"][0]["target_key"], row["items"][1]["target_key"])

    def test_smart_stock_sums_distinct_future_uses_without_losing_targets(self):
        first = self._card()
        first["a_preparer"] = [
            {"name": "Plume de Glan", "quantity": 20, "for": "Quête A", "policy": "Garder en banque."},
        ]
        second = self._card()
        second["manual_stage_id"] = "GPS-02"
        second["a_preparer"] = [
            {"name": "Plume de Glan", "quantity": 54, "for": "Quête B", "policy": "Garder en banque."},
        ]
        contract = build_route_auto_validation_contract([first, second])
        stock = contract["inventory_plan"]["bank_reservations"]
        self.assertEqual(len(stock), 1)
        self.assertEqual(stock[0]["name"], "Plume de Glan")
        self.assertEqual(stock[0]["required_quantity"], 74)
        self.assertEqual(stock[0]["quantified_target_count"], 2)
        self.assertEqual(len(stock[0]["target_keys"]), 2)

    def test_route_header_counts_quests_and_dungeon_passages_without_new_progress_store(self):
        first = self._card()
        second = self._card()
        second["manual_stage_id"] = "GPS-02"
        second["manual_quest_ids"] = [11]
        second["manual_stage_data"] = {
            "id": "GPS-02",
            "dungeon": {"name": "Deuxième donjon"},
            "monsters": [],
        }
        contract = build_route_auto_validation_contract([first, second], achievement_provider=_AchievementProvider())
        counts = route_progress_counts(_Service([first, second]), "hero", contract)
        self.assertEqual(counts["quests_completed"], 1)
        self.assertEqual(counts["quests_total"], 2)
        self.assertEqual(counts["dungeons_completed"], 1)
        self.assertEqual(counts["dungeons_total"], 2)
        self.assertEqual(contract["summary"]["reserved_target_count"], 2)

    def test_manual_view_uses_clickable_progress_scrubber_and_only_bottom_arrows(self):
        build = inspect.getsource(GuideUltimeManualView._build_ui)
        self.assertIn("GuideManualProgressBar", build)
        self.assertIn("navigationRequested.connect", build)
        self.assertNotIn("current_button", build)
        self.assertIn("Précédent", build)
        self.assertIn("Suivant", build)
        self.assertTrue(hasattr(GuideManualProgressBar, "navigationRequested"))

    def test_resource_and_npc_emphasis_are_both_bold_but_distinct_colors(self):
        rich = GuideUltimeManualCard._format_line_html(
            "• ",
            "[0,0]",
            "Parler à Jean Michel puis donner 3 Plumes de Glan.",
            ["Jean Michel"],
            ["Plumes de Glan"],
        )
        self.assertIn("<b>Jean Michel</b>", rich)
        self.assertIn("<b>Plumes de Glan</b>", rich)


if __name__ == "__main__":
    unittest.main()
