from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService


def _quest(quest_id: int, criterion: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id=quest_id, name=f"Quest {quest_id}", level_min=1,
        start_criterion=criterion, achievements=(),
    )


class QuestGraphHotpathTests(unittest.TestCase):
    def _graph(self, quests, achievements=()):
        catalog = SimpleNamespace(
            quests=list(quests),
            by_id={quest.id: quest for quest in quests},
        )
        quest_provider = SimpleNamespace(get_catalog=lambda: catalog)
        achievement_provider = SimpleNamespace(load_all=Mock(return_value=list(achievements)))
        return QuestGraphService(
            quest_provider, achievement_provider=achievement_provider, eager=False,
        ), achievement_provider

    def test_criterion_cache_is_pure_and_retains_or_semantics(self):
        criterion = "Qf=1 & (Qa=2 | Sc=5)"
        first = QuestGraphService.criterion_references(criterion)
        self.assertIs(first, QuestGraphService.criterion_references(criterion))
        self.assertEqual(first.mandatory_hard_quests, frozenset({1}))
        self.assertEqual(first.mandatory_context_quests, frozenset())
        self.assertEqual(first.mandatory_achievements, frozenset())
        self.assertEqual(len(first.alternative_branches), 2)
        self.assertEqual(
            QuestGraphService.criterion_references("Qf=9").mandatory_hard_quests,
            frozenset({9}),
        )

    def test_snapshot_matches_fresh_provider_without_reloading(self):
        achievement = SimpleNamespace(
            id=100,
            objectives=(SimpleNamespace(id=1, criterion="Qf=1", entity_ref=None),),
            linked_quests=(),
        )
        graph, provider = self._graph([_quest(1)], [achievement])
        fresh = graph.prerequisite_closure(seed_achievements=[100])
        self.assertEqual(provider.load_all.call_count, 1)
        reused = graph.prerequisite_closure(
            seed_achievements=[100], achievement_catalog={100: achievement},
        )
        self.assertEqual(provider.load_all.call_count, 1)
        self.assertEqual(fresh, reused)
        self.assertEqual(fresh.mandatory_quests, {1})

    def test_separate_provider_calls_pick_up_changed_achievements(self):
        initial = SimpleNamespace(id=100, objectives=(), linked_quests=())
        changed = SimpleNamespace(
            id=100,
            objectives=(SimpleNamespace(id=2, criterion="Qf=2", entity_ref=None),),
            linked_quests=(),
        )
        graph, provider = self._graph([_quest(2)], [initial])
        self.assertEqual(graph.prerequisite_closure(seed_achievements=[100]).mandatory_quests, set())
        provider.load_all.return_value = [changed]
        self.assertEqual(graph.prerequisite_closure(seed_achievements=[100]).mandatory_quests, {2})
        self.assertEqual(provider.load_all.call_count, 2)

    def test_heap_order_keeps_determinism_and_cycles(self):
        graph, _ = self._graph([_quest(i) for i in range(1, 7)])
        ordered, cycles = graph._topological_order(
            set(range(1, 7)),
            {(1, 3), (2, 3), (3, 4), (5, 6), (6, 5)},
        )
        self.assertEqual(ordered, [1, 2, 3, 4, 5, 6])
        self.assertEqual(cycles, [[5, 6]])


if __name__ == "__main__":
    unittest.main()
