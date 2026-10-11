from __future__ import annotations

"""Behavioral guards for Guide graph hot-path optimizations."""

import random
import unittest
from collections import defaultdict
from types import SimpleNamespace

from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService


def _previous_sorted_queue(ids, edges, records):
    """Reference implementation kept independent of the optimized heap."""
    incoming = {qid: 0 for qid in ids}
    children = defaultdict(set)
    for previous, following in edges:
        if previous in ids and following in ids and following not in children[previous]:
            children[previous].add(following)
            incoming[following] += 1

    def key(qid):
        quest = records[qid]
        from app.quest_catalog import normalize_text
        return int(quest.level_min or 0), normalize_text(quest.name), qid

    ready = sorted((qid for qid, n in incoming.items() if n == 0), key=key)
    ordered = []
    while ready:
        qid = ready.pop(0)
        ordered.append(qid)
        for child in sorted(children.get(qid, ()), key=key):
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
                ready.sort(key=key)
    ordered.extend(sorted(ids - set(ordered), key=key))
    return ordered


class QuestGraphFullSuiteHotpathTests(unittest.TestCase):
    def test_criteria_cache_keeps_distinct_boolean_and_optional_branches(self):
        examples = (
            "",
            "Qf=11&(Qf=12|Qf=13)",
            "Qa=14&(Sc=15|OA=16)",
            "!Qf=4|Qf=5",
            "Qf=1&Sc=2",
        )
        for criterion in examples:
            with self.subTest(criterion=criterion):
                original = QuestGraphService.criterion_references(criterion)
                cached = QuestGraphService.criterion_references(criterion)
                self.assertIs(original, cached)
                self.assertEqual(original.branches, cached.branches)
        self.assertEqual(
            QuestGraphService.criterion_references(
                "Qf=11&(Qf=12|Qf=13)"
            ).mandatory_hard_quests, frozenset({11}),
        )

    def test_heap_matches_previous_topological_order_with_many_ready_quests(self):
        rng = random.Random(9817)
        records = {
            qid: SimpleNamespace(id=qid, name=f"Quest {qid % 23}", level_min=qid % 37)
            for qid in range(1, 301)
        }
        graph = QuestGraphService.__new__(QuestGraphService)
        graph.catalog = SimpleNamespace(by_id=records)
        ids = set(records)
        edges = {
            (rng.randrange(1, 220), rng.randrange(221, 301))
            for _ in range(1400)
        }
        original = _previous_sorted_queue(ids, edges, records)
        actual, cycles = graph._topological_order(ids, edges)
        self.assertEqual(actual, original)
        self.assertEqual(cycles, [])

    def test_heap_retains_cycle_fallback_and_skips_unknown_quest_ids(self):
        records = {
            qid: SimpleNamespace(id=qid, name=f"Quest {qid}", level_min=10)
            for qid in range(1, 7)
        }
        graph = QuestGraphService.__new__(QuestGraphService)
        graph.catalog = SimpleNamespace(by_id=records)
        ids = {1, 2, 3, 4, 5, 6, 999}
        edges = {(1, 2), (2, 3), (3, 2), (4, 5), (5, 4), (999, 2)}
        expected = _previous_sorted_queue(set(records), edges, records)
        actual, cycles = graph._topological_order(ids, edges)
        self.assertEqual(actual, expected)
        self.assertTrue(cycles)

    def test_repeated_achievement_roots_keep_exact_hard_edges(self):
        records = {
            qid: SimpleNamespace(id=qid, name=f"Quest {qid}", level_min=10,
                                start_criterion=("Sc=10" if qid in (1, 2) else ""))
            for qid in (1, 2, 3)
        }
        achievements = [
            SimpleNamespace(
                id=10,
                objectives=(SimpleNamespace(id=1, criterion="Qf=3&OA=11",
                                            entity_ref=None),),
                linked_quests=(),
            ),
            SimpleNamespace(
                id=11,
                objectives=(SimpleNamespace(id=2, criterion="OA=10",
                                            entity_ref=None),),
                linked_quests=(),
            ),
        ]
        graph = QuestGraphService.__new__(QuestGraphService)
        graph.catalog = SimpleNamespace(by_id=records)
        graph.achievement_provider = SimpleNamespace(load_all=lambda: achievements)
        result = graph.prerequisite_closure(seed_quests=(1, 2))
        self.assertEqual(set(result.ordered_quest_ids), {1, 2, 3})
        self.assertIn((3, 1), result.hard_edges)
        self.assertIn((3, 2), result.hard_edges)
        self.assertEqual(result.invalid_quest_ids, set())
        self.assertEqual(result.invalid_achievement_ids, set())


if __name__ == "__main__":
    unittest.main()
