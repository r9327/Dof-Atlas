from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.guide_ultime_scope_v4 import (
    ProfileKey,
    active_qa_ids,
    condition_matches_profile,
    fill_to_qq_threshold,
    max_qq_requirement,
    meta_achievement_ids,
    positive_qf_ids,
    transitive_closure,
)


class GuideUltimeV4ScopeTests(unittest.TestCase):
    def test_only_positive_qf_is_hard_dependency(self):
        criterion = "Qf=10 & Qa=20 & Qf!=30 & Qf>=40"
        self.assertEqual(positive_qf_ids(criterion), {10})
        self.assertEqual(active_qa_ids(criterion), {20})

    def test_transitive_qf_closure(self):
        graph = {3: {2}, 2: {1}, 1: set()}
        selected, added, conflicts = transitive_closure(
            {3}, graph, allowed=lambda _qid: True, exists=lambda qid: qid in graph
        )
        self.assertEqual(selected, {1, 2, 3})
        self.assertEqual(added, {1, 2})
        self.assertEqual(conflicts, [])

    def test_incompatible_prerequisite_is_a_conflict_not_silently_injected(self):
        graph = {3: {2}, 2: set()}
        selected, _added, conflicts = transitive_closure(
            {3}, graph, allowed=lambda qid: qid != 2, exists=lambda qid: qid in graph
        )
        self.assertEqual(selected, {3})
        self.assertEqual(conflicts[0]["type"], "incompatible_prerequisite")

    def test_profile_filters_other_order_and_class(self):
        p = ProfileKey("bonta", "Ordre du Cœur Vaillant", "Huppermage")
        self.assertTrue(condition_matches_profile({"alignment": "bonta"}, p))
        self.assertTrue(condition_matches_profile({"alignment": "bonta", "order": "Ordre du Cœur Vaillant"}, p))
        self.assertTrue(condition_matches_profile({"class": "Huppermage"}, p))
        self.assertFalse(condition_matches_profile({"alignment": "brakmar"}, p))
        self.assertFalse(condition_matches_profile({"order": "Ordre de l'Œil Attentif"}, p))
        self.assertFalse(condition_matches_profile({"class": "Eliotrope"}, p))

    def test_qq_threshold_parser(self):
        self.assertEqual(max_qq_requirement(["QQ>=100", "QQ>499", "QQ=250"]), 500)

    def test_qq_fill_adds_minimum_candidates(self):
        graph = {1: set(), 2: set(), 3: set(), 4: set()}
        filled, fillers, conflicts = fill_to_qq_threshold(
            {1}, 3, [2, 3, 4], graph,
            allowed=lambda _qid: True,
            exists=lambda qid: qid in graph,
            rank_key=lambda qid: (qid,),
        )
        self.assertEqual(len(filled), 3)
        self.assertEqual(fillers, {2, 3})
        self.assertEqual(conflicts, [])

    def test_qq_filler_cost_includes_prerequisite_chain(self):
        # Quest 2 looks first by id but drags 20+21. Quest 3 is truly cheaper.
        graph = {1: set(), 2: {20}, 20: {21}, 21: set(), 3: set()}
        filled, fillers, conflicts = fill_to_qq_threshold(
            {1}, 2, [2, 3], graph,
            allowed=lambda _qid: True,
            exists=lambda qid: qid in graph,
            rank_key=lambda qid: (qid,),
        )
        self.assertEqual(filled, {1, 3})
        self.assertEqual(fillers, {3})
        self.assertEqual(conflicts, [])

    def test_qq_filler_never_uses_incompatible_candidate(self):
        graph = {1: set(), 2: set(), 3: set()}
        filled, fillers, conflicts = fill_to_qq_threshold(
            {1}, 2, [2, 3], graph,
            allowed=lambda qid: qid != 2,
            exists=lambda qid: qid in graph,
            rank_key=lambda qid: (qid,),
        )
        self.assertEqual(filled, {1, 3})
        self.assertEqual(fillers, {3})
        self.assertEqual(conflicts, [])

    def test_meta_achievement_refs(self):
        self.assertEqual(meta_achievement_ids("Sc=123 & Sc=456"), {123, 456})


if __name__ == "__main__":
    unittest.main()
