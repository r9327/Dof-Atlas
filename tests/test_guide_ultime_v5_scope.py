from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.guide_ultime_scope_v5 import (
    active_qa_ids,
    branch_combination_counts,
    fill_to_qq_threshold,
    max_qq_requirement,
    meta_achievement_ids,
    mandatory_qf_ids,
    positive_qf_ids,
    qf_alternative_sets,
    residual_qf_alternatives,
    transitive_closure,
)


class GuideUltimeV5ScopeTests(unittest.TestCase):
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

    def test_qq_threshold_parser(self):
        self.assertEqual(max_qq_requirement(["QQ>=100", "QQ>499", "QQ=250"]), 500)

    def test_qq_filler_cost_includes_prerequisite_chain(self):
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


    def test_or_qf_is_not_flattened_into_two_hard_dependencies(self):
        criterion = "(Qf=10&PG=1)|(Qf=20&PG=2)"
        self.assertEqual(positive_qf_ids(criterion), {10, 20})
        self.assertEqual(mandatory_qf_ids(criterion), frozenset())
        self.assertEqual(set(qf_alternative_sets(criterion)), {frozenset({10}), frozenset({20})})
        self.assertEqual(set(residual_qf_alternatives(criterion)), {frozenset({10}), frozenset({20})})

    def test_common_qf_is_kept_across_or_branches(self):
        criterion = "Qf=1&(Qf=2|Qf=3)"
        self.assertEqual(mandatory_qf_ids(criterion), frozenset({1}))
        self.assertEqual(set(residual_qf_alternatives(criterion)), {frozenset({2}), frozenset({3})})

    def test_or_branch_can_be_deferred_to_universal_class_card(self):
        graph = {100: set(), 10: set(), 20: set()}
        alternatives = {100: (frozenset({10}), frozenset({20}))}
        selected, added, conflicts = transitive_closure(
            {100}, graph,
            allowed=lambda qid: qid == 100,
            exists=lambda qid: qid in graph,
            alternatives=alternatives,
            defer_allowed=lambda qid: qid in {10, 20},
        )
        self.assertEqual(selected, {100})
        self.assertEqual(added, set())
        self.assertEqual(conflicts, [])

    def test_branch_closure_does_not_revalidate_preselected_common(self):
        graph = {1: {99}, 2: set(), 99: set()}
        selected, added, conflicts = transitive_closure(
            {2}, graph,
            allowed=lambda qid: qid != 99,
            exists=lambda qid: qid in graph,
            preselected={1},
        )
        self.assertEqual(selected, {1, 2})
        self.assertEqual(added, set())
        self.assertEqual(conflicts, [])

    def test_qq_filler_does_not_revalidate_existing_common_conflict(self):
        # Quest 1 is already in the validated common scope. Its disallowed edge
        # must not poison every future QQ candidate evaluation.
        graph = {1: {99}, 2: set(), 99: set()}
        filled, fillers, conflicts = fill_to_qq_threshold(
            {1}, 2, [2], graph,
            allowed=lambda qid: qid != 99,
            exists=lambda qid: qid in graph,
            rank_key=lambda qid: (qid,),
        )
        self.assertEqual(filled, {1, 2})
        self.assertEqual(fillers, {2})
        self.assertEqual(conflicts, [])

    def test_meta_achievement_refs(self):
        self.assertEqual(meta_achievement_ids("Sc=123 & Sc=456"), {123, 456})

    def test_universal_branch_counts_do_not_create_profiles(self):
        common = {1, 2, 3}
        classes = {"A": {10}, "B": {11}}
        orders = {"O1": {20, 21}, "O2": {22, 23}, "O3": {24, 25}}
        counts = branch_combination_counts(common, classes, orders)
        self.assertEqual(set(counts), {6})
        self.assertEqual(len(counts), 6)  # validation combinations only, not generated guides


if __name__ == "__main__":
    unittest.main()
