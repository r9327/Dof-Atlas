from __future__ import annotations

import copy
import math
import unittest

from tools.phase8_deep_comparison import compare_deep_first_use

BASE = "a" * 40
HEAD = "b" * 40
FIRST = ("quests_open_ms", "achievements_open_ms", "guide_open_ms",
         "craft_open_ms", "equipment_open_ms")
DETAIL = ("deep_quest_detail_ms", "deep_guide_detail_ms", "deep_achievement_detail_ms")


def sample(sha: str, preload_ms: float, detail_ms: tuple[float, float, float]):
    record = {
        "git_head": sha,
        "preload_completed_from_constructor_ms": preload_ms,
        "quests_open_ms": 140, "achievements_open_ms": 50,
        "guide_open_ms": 60, "craft_open_ms": 20, "equipment_open_ms": 5,
        "deep_quest_detail_ms": detail_ms[0],
        "deep_guide_detail_ms": detail_ms[1],
        "deep_achievement_detail_ms": detail_ms[2],
        "deep_first_content": {
            "quest_id": 123, "guide_id": "guide-1",
            "achievement_id": 456, "all_details_rendered": True,
        },
    }
    record["deep_first_content_total_ms"] = round(sum(record[k] for k in DETAIL), 2)
    record["total_first_path_ms"] = round(
        record["deep_first_content_total_ms"] + preload_ms
        + sum(record[k] for k in FIRST), 2
    )
    return record


class DeepFirstUseTimingTests(unittest.TestCase):
    def test_detects_a_real_net_gain_and_delayed_cost(self):
        before = sample(BASE, 6780, (200, 350, 450))
        after = sample(HEAD, 1550, (300, 450, 550))
        result = compare_deep_first_use(before, after, base_sha=BASE, candidate_sha=HEAD)
        self.assertEqual(result["preload_gain_ms"], 5230)
        self.assertEqual(result["shifted_into_deep_details_ms"], 300)
        self.assertEqual(result["net_full_first_use_gain_ms"], 4930)
        self.assertEqual(result["verdict"], "NET_FASTER_WITH_DEFERRED_SHIFT")
        self.assertTrue(result["single_run_not_statistical_proof"])

    def test_detects_deferred_cost_that_cancels_preload_gain(self):
        before = sample(BASE, 6780, (200, 350, 450))
        after = sample(HEAD, 1550, (2000, 3000, 2800))
        result = compare_deep_first_use(before, after, base_sha=BASE, candidate_sha=HEAD)
        self.assertEqual(result["verdict"], "NET_REGRESSION")
        self.assertLess(result["net_full_first_use_gain_ms"], -1000)

    def test_missing_details_or_wrong_ids_cannot_claim_gain(self):
        before = sample(BASE, 6780, (200, 350, 450))
        after = sample(HEAD, 1550, (300, 450, 550))
        after["deep_first_content"]["all_details_rendered"] = False
        with self.assertRaises(ValueError):
            compare_deep_first_use(before, after, base_sha=BASE, candidate_sha=HEAD)
        after["deep_first_content"]["all_details_rendered"] = True
        after["deep_first_content"]["guide_id"] = "other"
        with self.assertRaises(ValueError):
            compare_deep_first_use(before, after, base_sha=BASE, candidate_sha=HEAD)

    def test_inconsistent_sum_and_nan_are_rejected(self):
        before = sample(BASE, 6780, (200, 350, 450))
        after = sample(HEAD, 1550, (300, 450, 550))
        after["total_first_path_ms"] += 1000
        with self.assertRaises(ValueError):
            compare_deep_first_use(before, after, base_sha=BASE, candidate_sha=HEAD)
        after["total_first_path_ms"] -= 1000
        after["deep_guide_detail_ms"] = math.nan
        with self.assertRaises(ValueError):
            compare_deep_first_use(before, after, base_sha=BASE, candidate_sha=HEAD)

    def test_same_sha_cannot_fake_base_candidate_comparison(self):
        before = sample(BASE, 6780, (200, 350, 450))
        with self.assertRaises(ValueError):
            compare_deep_first_use(before, before, base_sha=BASE, candidate_sha=BASE)

    def test_source_benchmark_has_real_detail_actions(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        src = (root / "tools/benchmark_phase8_preload.py").read_text(encoding="utf-8")
        workflow = (root / ".github/workflows/phase8-preload-benchmark.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('page.navigate_to_entity("quest", quest_id', src)
        self.assertIn("page.navigate_to_guide(guide_id)", src)
        self.assertIn("page.navigate_to_achievement_tab(achievement_id)", src)
        self.assertIn("current_quest_id", src)
        self.assertIn("current_guide_id", src)
        self.assertIn("current_achievement_id", src)
        self.assertIn("window.open_encyclopedia_tab(QUESTS_TAB)", src)
        self.assertIn("window.open_encyclopedia_tab(GUIDES_TAB)", src)
        self.assertIn("window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)", src)
        self.assertIn("total_first_path_ms", workflow)
        self.assertIn("compare_deep_first_use", workflow)
        self.assertIn("shifted_into_deep_details_ms", workflow)


if __name__ == "__main__":
    unittest.main()
