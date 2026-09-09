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
