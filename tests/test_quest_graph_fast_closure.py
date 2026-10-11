from __future__ import annotations

import ast
import random
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService
from app.quest_catalog import normalize_text

ROOT = Path(__file__).resolve().parents[1]


def old_order(graph, ids, edges):
    # Preserve the exact previous algorithm as a small regression oracle.
    by_id = graph.catalog.by_id
    incoming = {qid: 0 for qid in ids}
    children = defaultdict(set)
    for previous, following in edges:
        if previous not in ids or following not in ids or following in children[previous]:
            continue
        children[previous].add(following)
        incoming[following] += 1

    def key(qid):
        row = by_id[qid]
        return int(getattr(row, "level_min", 0) or 0), normalize_text(row.name), qid

    ready = sorted((qid for qid, count in incoming.items() if count == 0), key=key)
    result = []
    while ready:
        qid = ready.pop(0)
        result.append(qid)
        for child in sorted(children.get(qid, ()), key=key):
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
                ready.sort(key=key)
    remaining = ids - set(result)
    result.extend(sorted(remaining, key=key))
    return result


class QuestGraphFastClosureTests(unittest.TestCase):
    def test_heap_preserves_exact_legacy_order_with_forks_and_cycles(self):
        rng = random.Random(9327)
        graph = object.__new__(QuestGraphService)
        graph.catalog = SimpleNamespace(by_id={
            qid: SimpleNamespace(
                id=qid, name=f"Guide {qid % 13}", level_min=qid % 7
            ) for qid in range(1, 101)
        })
        ids = set(graph.catalog.by_id)
        for case in range(60):
            # Includes cycles and fully acyclic scenarios.
            edges = set()
            for qid in ids:
                if qid > 1 and rng.random() < 0.6:
                    previous = rng.randrange(1, qid)
                    edges.add((previous, qid))
                if case % 3 == 0 and rng.random() < 0.12:
                    edges.add((qid, rng.randrange(1, 101)))
            expected = old_order(graph, ids, edges)
            actual, _cycles = graph._topological_order(ids, edges)
            self.assertEqual(actual, expected, f"case={case}")
            self.assertEqual(set(actual), ids)
            self.assertEqual(len(actual), len(ids))

    def test_parser_cache_is_bounded_and_semantics_unchanged(self):
        refs = QuestGraphService.criterion_references
        sample = "(Qf=19000001 | Qf=19000002) & Sc=19000003"
        before = refs.cache_info().hits
        first = refs(sample)
        second = refs(sample)
        self.assertIs(first, second)
        self.assertEqual(refs.cache_info().hits, before + 1)
        self.assertLessEqual(refs.cache_info().maxsize, 1024)
        self.assertEqual(first.mandatory_achievements, frozenset({19000003}))
        self.assertEqual(first.mandatory_hard_quests, frozenset())

    def test_builder_never_pays_for_global_navigation_indexes(self):
        source = (ROOT / "app/modules/encyclopedia/services/guide_catalog_builder.py").read_text(encoding="utf-8")
        klass = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.ClassDef) and node.name == "GuideCatalogBuilder"
        )
        constructor = next(
            node for node in klass.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        calls = [
            node for node in ast.walk(constructor)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "QuestGraphService"
        ]
        self.assertEqual(len(calls), 1)
        flags = {
            keyword.arg: keyword.value for keyword in calls[0].keywords
        }
        self.assertIsInstance(flags["eager"], ast.Constant)
        self.assertIs(flags["eager"].value, False)

    def test_lazy_graph_closure_matches_eager_graph_on_same_fixture(self):
        class FakeQuestProvider:
            def __init__(self):
                rows = {
                    1: SimpleNamespace(id=1, name="Départ", level_min=1, start_criterion="", achievements=()),
                    2: SimpleNamespace(id=2, name="Suite", level_min=2, start_criterion="Qf=1", achievements=()),
                    3: SimpleNamespace(id=3, name="Suite suivante", level_min=3, start_criterion="Qf=2", achievements=()),
                }
                self.catalog = SimpleNamespace(by_id=rows, quests=list(rows.values()))
            def get_catalog(self):
                return self.catalog
        class FakeAchievementProvider:
            def load_all(self):
                return []

        quests = FakeQuestProvider()
        achievements = FakeAchievementProvider()
        lazy = QuestGraphService(quests, achievement_provider=achievements, eager=False)
        eager = QuestGraphService(quests, achievement_provider=achievements, eager=True)
        self.assertFalse(lazy._built)
        for seed in (1, 2, 3):
            fast = lazy.prerequisite_closure(seed_quests=[seed])
            baseline = eager.prerequisite_closure(seed_quests=[seed])
            self.assertEqual(fast.ordered_quest_ids, baseline.ordered_quest_ids)
            self.assertEqual(fast.hard_edges, baseline.hard_edges)
            self.assertEqual(fast.context_edges, baseline.context_edges)
            self.assertEqual(fast.alternative_groups, baseline.alternative_groups)


if __name__ == "__main__":
    unittest.main()
