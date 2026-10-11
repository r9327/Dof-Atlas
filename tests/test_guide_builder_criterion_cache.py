from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService

ROOT = Path(__file__).resolve().parents[1]


class _QuestProvider:
    def __init__(self):
        quests = [
            SimpleNamespace(id=1, name="First", start_criterion="Qf = 2 & Sc = 11", level_min=1, achievements=()),
            SimpleNamespace(id=2, name="Second", start_criterion="", level_min=1, achievements=()),
            SimpleNamespace(id=3, name="Third", start_criterion="Sc = 11", level_min=2, achievements=()),
        ]
        self.catalog = SimpleNamespace(quests=quests, by_id={row.id: row for row in quests})

    def get_catalog(self):
        return self.catalog


class _AchievementProvider:
    def load_all(self):
        return [
            SimpleNamespace(
                id=11,
                objectives=(SimpleNamespace(id=101, criterion="Qf = 2",
                                            entity_ref=None),),
                linked_quests=(),
            )
        ]


class _CountingGraph(QuestGraphService):
    parsed = 0

    @classmethod
    def criterion_references(cls, criterion: str):
        cls.parsed += 1
        return super().criterion_references(criterion)


class GuideBuilderCriterionCacheTests(unittest.TestCase):
    def _graph(self, cache: bool):
        return _CountingGraph(
            quest_provider=_QuestProvider(),
            achievement_provider=_AchievementProvider(),
            eager=False,
            cache_criteria=cache,
        )

    def test_cache_reuses_immutable_criterion_and_stays_bounded(self):
        graph = self._graph(cache=True)
        _CountingGraph.parsed = 0
        first = graph._references("Qf = 2 & Sc = 11")
        for _ in range(40):
            self.assertIs(graph._references("Qf = 2 & Sc = 11"), first)
        self.assertEqual(_CountingGraph.parsed, 1)
        for i in range(2060):
            graph._references(f"Qf = 2 & Qa = {i + 1000}")
        self.assertLessEqual(len(graph._criterion_cache), 2048)

    def test_cached_and_uncached_closure_preserve_full_contract(self):
        cached, normal = self._graph(cache=True), self._graph(cache=False)
        for _ in range(2):
            a = cached.prerequisite_closure(seed_quests=[1, 3], seed_achievements=[11])
            b = normal.prerequisite_closure(seed_quests=[1, 3], seed_achievements=[11])
            for key in (
                "ordered_quest_ids", "mandatory_quests", "context_quests",
                "optional_quests", "hard_edges", "context_edges",
                "alternative_edges", "alternative_groups",
                "quest_alternative_groups", "invalid_quest_ids",
                "invalid_achievement_ids", "cycles",
            ):
                self.assertEqual(getattr(a, key), getattr(b, key), key)
            self.assertEqual(set(a.ordered_quest_ids), {1, 2, 3})

    def test_normal_runtime_graph_does_not_accumulate_criterion_cache(self):
        graph = self._graph(cache=False)
        for _ in range(10):
            graph._references("Qf = 2")
        self.assertEqual(graph._criterion_cache, {})
        self.assertFalse(graph._cache_criteria)

    def test_builder_explicitly_owns_opt_in_cache(self):
        src = (ROOT / "app/modules/encyclopedia/services/guide_catalog_builder.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("cache_criteria=True", src)
        self.assertNotIn("cache_criteria=True", (
            ROOT / "app/modules/encyclopedia/services/quest_graph_service.py"
        ).read_text(encoding="utf-8"))

    def test_cached_parser_respects_changed_criterion_value(self):
        graph = self._graph(cache=True)
        one = graph._references("Qf = 2")
        two = graph._references("Qf = 3")
        self.assertEqual(one.mandatory_hard_quests, frozenset({2}))
        self.assertEqual(two.mandatory_hard_quests, frozenset({3}))


if __name__ == "__main__":
    unittest.main()
