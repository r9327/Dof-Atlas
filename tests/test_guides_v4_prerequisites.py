from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_catalog_builder import GuideBuildResult, GuideCatalogBuilder
from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService
from app.quest_catalog import QuestCatalog, QuestRecord


def quest(quest_id: int, criterion: str = "", level: int = 1) -> QuestRecord:
    return QuestRecord(
        id=quest_id,
        name=f"Quest {quest_id}",
        category="test",
        level_min=level,
        level_max=level,
        start_criterion=criterion,
    )


class FakeQuestProvider:
    def __init__(self, quests: list[QuestRecord]) -> None:
        self.catalog = QuestCatalog(quests)

    def get_catalog(self) -> QuestCatalog:
        return self.catalog


class FakeAchievementProvider:
    def __init__(self, achievements: list[SimpleNamespace]) -> None:
        self.achievements = achievements

    def load_all(self) -> list[SimpleNamespace]:
        return self.achievements


def achievement(achievement_id: int, *criteria: str) -> SimpleNamespace:
    objectives = tuple(
        SimpleNamespace(id=index, criterion=criterion, entity_ref=None)
        for index, criterion in enumerate(criteria, 1)
    )
    return SimpleNamespace(id=achievement_id, objectives=objectives, linked_quests=())


class GuidesV4PrerequisitesTests(unittest.TestCase):
    def test_criterion_cache_is_instance_scoped_and_follows_updated_input(self):
        provider = FakeQuestProvider([quest(1), quest(2, "Qf=1")])
        first = QuestGraphService(provider, achievement_provider=FakeAchievementProvider([]), eager=False)
        second = QuestGraphService(provider, achievement_provider=FakeAchievementProvider([]), eager=False)
        expression = "Qf=1|Qa=2"
        parsed = first._cached_criterion_references(expression)
        self.assertIs(parsed, first._cached_criterion_references(expression))
        self.assertIsNot(parsed, second._cached_criterion_references(expression))
        updated = first._cached_criterion_references("Qf=1&Qa=2")
        self.assertEqual(updated.mandatory_hard_quests, {1})
        self.assertEqual(updated.mandatory_context_quests, {2})
        self.assertNotEqual(parsed.branches, updated.branches)

    def test_heap_order_matches_sorted_frontier_with_cycles_and_ties(self):
        from app.modules.encyclopedia.services.quest_graph_service import _cycle_components
        from app.quest_catalog import normalize_text
        from collections import defaultdict

        quests = [quest(i, level=(i * 3) % 7) for i in range(1, 41)]
        graph = QuestGraphService(FakeQuestProvider(quests), achievement_provider=FakeAchievementProvider([]), eager=False)
        ids = set(range(1, 41))
        edges = {(i, i + 1) for i in range(1, 39, 3)}
        edges.update({(i, i + 2) for i in range(1, 35, 4)})
        edges.update({(30, 31), (31, 30), (40, 40)})

        def legacy_order():
            incoming = {qid: 0 for qid in ids}
            children = defaultdict(set)
            for before, after in edges:
                if before not in ids or after not in ids or after in children[before]:
                    continue
                children[before].add(after)
                incoming[after] += 1

            def key(qid):
                row = graph.catalog.by_id[qid]
                return int(row.level_min or 0), normalize_text(row.name), qid

            ready = sorted((qid for qid, count in incoming.items() if count == 0), key=key)
            ordered = []
            while ready:
                qid = ready.pop(0)
                ordered.append(qid)
                for child in sorted(children.get(qid, ()), key=key):
                    incoming[child] -= 1
                    if incoming[child] == 0:
                        ready.append(child)
                        ready.sort(key=key)
            remaining = ids - set(ordered)
            cycles = _cycle_components(remaining, children)
            ordered.extend(sorted(remaining, key=key))
            return ordered, cycles

        self.assertEqual(graph._topological_order(ids, edges), legacy_order())

    def test_qf_qa_sc_and_or_are_not_flattened(self):
        refs = QuestGraphService.criterion_references("Qf=1&Qa=2&Sc=3")
        self.assertEqual(refs.mandatory_hard_quests, {1})
        self.assertEqual(refs.mandatory_context_quests, {2})
        self.assertEqual(refs.mandatory_achievements, {3})

        alternatives = QuestGraphService.criterion_references("Qf=1|Qf=2")
        self.assertEqual(alternatives.mandatory_hard_quests, set())
        self.assertEqual(
            {tuple(sorted(branch.quest_ids)) for branch in alternatives.alternative_branches},
            {(1,), (2,)},
        )

        active_or_finished = QuestGraphService.criterion_references("Qf=4|(Qa=4&Qo>10)")
        self.assertEqual(active_or_finished.mandatory_hard_quests, set())
        self.assertEqual(active_or_finished.mandatory_context_quests, {4})

    def test_recursive_closure_expands_success_and_keeps_qa_context_only(self):
        quests = [
            quest(1),
            quest(2, "Qf=1", 2),
            quest(3, "Qa=2", 3),
            quest(4, "Sc=10", 4),
        ]
        graph = QuestGraphService(
            FakeQuestProvider(quests),
            achievement_provider=FakeAchievementProvider([achievement(10, "Qf=3"), achievement(20, "Qf=4")]),
        )
        closure = graph.prerequisite_closure(seed_achievements=[20])

        self.assertEqual(set(closure.ordered_quest_ids), {1, 2, 3, 4})
        self.assertLess(closure.ordered_quest_ids.index(1), closure.ordered_quest_ids.index(2))
        self.assertLess(closure.ordered_quest_ids.index(2), closure.ordered_quest_ids.index(3))
        self.assertLess(closure.ordered_quest_ids.index(3), closure.ordered_quest_ids.index(4))
        self.assertIn(2, closure.context_quests)
        self.assertIn(3, closure.mandatory_quests)
        self.assertIn((2, 3), closure.context_edges)
        self.assertNotIn((2, 3), closure.hard_edges)
        self.assertIn((3, 4), closure.hard_edges)

    def test_or_branches_are_optional_and_not_hard_prerequisites(self):
        quests = [quest(1), quest(2), quest(3, "Qf=1|Qf=2", 3)]
        graph = QuestGraphService(FakeQuestProvider(quests), achievement_provider=FakeAchievementProvider([]))
        closure = graph.prerequisite_closure(seed_quests=[3])

        self.assertEqual(closure.mandatory_quests, {3})
        self.assertEqual(closure.optional_quests, {1, 2})
        self.assertEqual(closure.hard_prerequisites(3), [])
        self.assertEqual(len(closure.alternative_groups), 1)

    def test_guide_display_order_does_not_create_dependency_edges(self):
        quests = [quest(1), quest(2)]
        guide = SimpleNamespace(id="guide", quest_ids=(1, 2))
        guide_provider = SimpleNamespace(load_all=lambda: [guide], get_by_id=lambda _guide_id: guide)
        graph = QuestGraphService(
            FakeQuestProvider(quests),
            guide_provider=guide_provider,
            achievement_provider=FakeAchievementProvider([]),
        )

        self.assertEqual(graph.previous_ids(2), [])
        self.assertEqual(graph.next_ids(1), [])
        self.assertEqual(graph.reliable_neighbors(2, "guide"), (1, None))

    def test_v4_writer_replaces_only_dofus_and_creates_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            guides_dir = Path(tmp)
            adventure = {"id": "guide_complet", "category": "aventure", "sections": []}
            alignment = {"id": "alignement_bonta", "category": "alignements", "sections": []}
            old_dofus = {"id": "dofus_test", "category": "dofus", "sections": []}
            new_dofus = {"id": "dofus_test", "category": "dofus", "sections": [{"id": "v4", "steps": []}]}
            for payload in (adventure, alignment, old_dofus):
                (guides_dir / f"{payload['id']}.json").write_text(json.dumps(payload), encoding="utf-8")
            catalog = {
                "schema_version": 1,
                "categories": [],
                "guides": [
                    {"id": "guide_complet", "file": "guide_complet.json", "category": "aventure", "order": 10},
                    {"id": "dofus_test", "file": "dofus_test.json", "category": "dofus", "order": 10},
                    {"id": "alignement_bonta", "file": "alignement_bonta.json", "category": "alignements", "order": 10},
                ],
            }
            (guides_dir / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            builder = GuideCatalogBuilder.__new__(GuideCatalogBuilder)
            builder.guides_dir = guides_dir
            result = GuideBuildResult(
                catalog={
                    **catalog,
                    "guides": [
                        catalog["guides"][0],
                        {**catalog["guides"][1], "enabled": True},
                        catalog["guides"][2],
                    ],
                },
                guides={"guide_complet": {**adventure, "changed": True}, "dofus_test": new_dofus, "alignement_bonta": {**alignment, "changed": True}},
                report={},
            )

            written = builder.write_dofus_v4(result)

            self.assertIn(str(guides_dir / "dofus_test.json"), written)
            self.assertEqual(json.loads((guides_dir / "dofus_test.json").read_text(encoding="utf-8")), new_dofus)
            self.assertEqual(json.loads((guides_dir / "dofus_test.json.bak_v4").read_text(encoding="utf-8")), old_dofus)
            self.assertEqual(json.loads((guides_dir / "guide_complet.json").read_text(encoding="utf-8")), adventure)
            self.assertEqual(json.loads((guides_dir / "alignement_bonta.json").read_text(encoding="utf-8")), alignment)
            self.assertFalse((guides_dir / "guide_complet.json.bak_v4").exists())
            self.assertFalse((guides_dir / "alignement_bonta.json.bak_v4").exists())


if __name__ == "__main__":
    unittest.main()
