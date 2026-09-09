from __future__ import annotations

import unittest

from app.modules.encyclopedia.views.guides_view import GuidesView


class _ScrollBar:
    def value(self) -> int:
        return 0


class _Scroll:
    def verticalScrollBar(self) -> _ScrollBar:
        return _ScrollBar()


class _ProgressService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[int, ...], bool]] = []
        self.progress = {"characters": {}}

    def set_quests_completed(self, character_key: str, quest_ids, completed: bool = True) -> bool:
        ids = tuple(quest_ids)
        self.calls.append((character_key, ids, bool(completed)))
        return True


class _DummyGuidesView:
    current_character_key = "character:1"
    left_scroll = _Scroll()
    right_scroll = _Scroll()

    def __init__(self) -> None:
        self.quest_progress_service = _ProgressService()
        self.quest_progress = None
        self.sync_calls = 0
        self.external_refresh_marks = 0

    def current_guide(self):
        return None

    def _sync_achievement_progress(self) -> bool:
        self.sync_calls += 1
        return True

    def _mark_external_progress_refreshed(self) -> None:
        self.external_refresh_marks += 1


class GuidesBatchProgressTests(unittest.TestCase):
    def test_group_completion_uses_one_deduplicated_batch_mutation(self):
        view = _DummyGuidesView()

        GuidesView.set_quest_group_completed(view, [11, 12, 11, 13], True)

        self.assertEqual(
            view.quest_progress_service.calls,
            [("character:1", (11, 12, 13), True)],
        )
        self.assertIs(view.quest_progress, view.quest_progress_service.progress)
        self.assertEqual(view.sync_calls, 1)
        self.assertEqual(view.external_refresh_marks, 1)


if __name__ == "__main__":
    unittest.main()
