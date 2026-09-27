from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.modules.encyclopedia.services.guide_progress_calculator import (
    GuideProgressCalculator,
)


class _DeferredQuest:
    id = 1653

    def __init__(self) -> None:
        self._details = SimpleNamespace(cached=lambda _quest_id: False)

    @property
    def steps(self):
        raise AssertionError("Guide summary progress must not load quest details")


class GuideProgressDeferredDetailsTests(unittest.TestCase):
    def test_guide_summary_progress_does_not_load_detail_without_objective_progress(self):
        quest_progress = Mock()
        quest_progress.completed_quest_ids.return_value = set()
        quest_progress.completed_objectives.return_value = set()
        calculator = GuideProgressCalculator(
            quest_progress,
            Mock(),
            Mock(),
            {1653: _DeferredQuest()},
        )
        step = SimpleNamespace(
            step_type="quest",
            entity_id=1653,
            counts_for_completion=True,
        )
        guide = SimpleNamespace(id="dofus_turquoise", required_steps=(step,))

        progress = calculator.guide_progress(guide, "character:1")

        self.assertEqual((progress.completed, progress.total), (0, 1))
        quest_progress.completed_quest_ids.assert_called_once_with("character:1")
        quest_progress.completed_objectives.assert_called_once_with(
            "character:1",
            1653,
        )


if __name__ == "__main__":
    unittest.main()
