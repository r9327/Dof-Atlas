from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_progress_calculator import GuideProgressCalculator
from app.quest_catalog import QuestObjective, QuestRecord, QuestStep


class _QuestProgressProbe:
    def __init__(self) -> None:
        self.quest_done_calls = 0
        self.objective_set_calls = 0

    def is_quest_completed(self, _character_key: str, _quest_id: int) -> bool:
        self.quest_done_calls += 1
        return False

    def completed_objectives(self, _character_key: str, _quest_id: int) -> set[int]:
        self.objective_set_calls += 1
        return {11, 13}

    def is_objective_completed(self, *_args, **_kwargs) -> bool:
        raise AssertionError("scalar objective reads must not be used by quest_progress")


class GuideProgressBatchingTests(unittest.TestCase):
    def test_quest_progress_reads_completed_objectives_once(self) -> None:
        quest = QuestRecord(
            id=101,
            name="Batch probe",
            category="Tests",
            level_min=1,
            level_max=1,
            start_criterion="",
            steps=[
                QuestStep(
                    id=1,
                    name="Probe",
                    description="",
                    objectives=[
                        QuestObjective(id=11, text="A", type_id=0),
                        QuestObjective(id=12, text="B", type_id=0),
                        QuestObjective(id=13, text="C", type_id=0),
                    ],
                )
            ],
        )
        probe = _QuestProgressProbe()
        calculator = GuideProgressCalculator(
            probe,
            object(),
            object(),
            {quest.id: quest},
        )

        progress = calculator.quest_progress(quest, "slot:1")

        self.assertEqual((progress.completed, progress.total), (2, 3))
        self.assertEqual(probe.quest_done_calls, 1)
        self.assertEqual(probe.objective_set_calls, 1)


if __name__ == "__main__":
    unittest.main()
