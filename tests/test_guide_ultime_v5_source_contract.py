from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL = (ROOT / "tools" / "build_guide_ultime_final.py").read_text(encoding="utf-8")
GPS = (ROOT / "tools" / "build_guide_ultime_gps_route.py").read_text(encoding="utf-8")
MASTER = (ROOT / "tools" / "guide_ultime_master_2026-08-22.json").read_text(encoding="utf-8")
RUNNER = (ROOT / "tools" / "run_guide_ultime_v5.ps1").read_text(encoding="utf-8")


class GuideUltimeV5SourceContractTests(unittest.TestCase):
    def test_single_universal_scope_no_runtime_profiles(self):
        self.assertIn('"universal_scope": universal', FINAL)
        self.assertNotIn('"runtime_profiles": runtime_profiles', FINAL)
        self.assertIn('"single_universal_guide": True', FINAL)

    def test_no_class_or_order_cli_parameter(self):
        self.assertNotIn('add_argument("--class"', GPS)
        self.assertNotIn('add_argument("--order"', GPS)
        self.assertNotIn('add_argument("--alignment"', GPS)
        self.assertNotIn('--class', RUNNER)
        self.assertNotIn('--order', RUNNER)
        self.assertNotIn('--alignment', RUNNER)

    def test_class_and_order_are_conditional_cards(self):
        self.assertIn('conditional_branch_cards', GPS)
        self.assertIn('"class_card"', GPS)
        self.assertIn('"order_cards"', GPS)
        self.assertIn('"conditional_class_card"', FINAL)
        self.assertIn('"conditional_order_card"', FINAL)

    def test_full_success_includes_quest_monster_dungeon_categories(self):
        self.assertIn('target_dungeon_successes', FINAL)
        self.assertIn('target_monster_successes', FINAL)
        self.assertIn('target_quest_success_ids', FINAL)
        self.assertIn('dungeon_achievements_included', FINAL)
        self.assertNotIn('excluded_dungeon_achievement_ids', FINAL)
        self.assertIn('succes_donjon_a_faire', GPS)
        self.assertIn('succes_monstres_a_faire', GPS)
        self.assertIn('missing_dungeon_success_ids', GPS)
        self.assertIn('missing_monster_success_ids', GPS)
        self.assertIn('all_target_dungeon_successes_routed', GPS)
        self.assertIn('all_target_monster_successes_routed', GPS)

    def test_hdv_and_craft_rule_stays_locked(self):
        self.assertIn('HDV si échangeable', GPS)
        self.assertIn('CRAFT optionnel', GPS)
        self.assertIn('one_universal_master_route_with_inline_class_and_order_branches', MASTER)

    def test_one_of_candidates_are_not_all_counted_in_common_execution(self):
        self.assertIn('one_of_variant_ids', FINAL)
        self.assertIn('direct_targets.difference_update(one_of_variant_ids)', FINAL)
        self.assertIn('qid not in one_of_variant_ids', FINAL)
        self.assertIn('reference_route_expected_ids', GPS)

    def test_generic_alignment_ps_gate_is_used_by_content_lock(self):
        self.assertIn('criterion_alignment_side', FINAL)
        self.assertIn('condition = {**condition, "alignment": criterion_side}', FINAL)

    def test_universal_class_choice_is_bridged_as_a_conditional_gate(self):
        self.assertIn('apply_universal_class_gate_bridges', GPS)
        self.assertIn('"universal_class_gate_bridges"', GPS)
        self.assertIn('"conditional_branch_gates"', GPS)

    def test_full_success_dedicated_cards_are_part_of_the_payload(self):
        self.assertIn('"full_success_cards": success_cards', GPS)
        self.assertIn('carded_monster_success_ids', GPS)
        self.assertIn('carded_dungeon_success_ids', GPS)


if __name__ == "__main__":
    unittest.main()
