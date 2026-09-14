from __future__ import annotations

import unittest

from app.modules.encyclopedia.views.achievements_view import AchievementsView


class _ProgressProbe:
    def __init__(self, changed: bool = False) -> None:
        self.changed = changed
        self.calls = 0

    def refresh_if_changed(self) -> bool:
        self.calls += 1
        return self.changed


class _FailIfCalled:
    def __call__(self, *args, **kwargs):
        raise AssertionError("expensive achievement refresh should not run")


class OptimizedAchievementsRefreshTests(unittest.TestCase):
    def test_unchanged_quest_progress_skips_all_expensive_refresh_work(self):
        quest_progress = _ProgressProbe()
        achievement_progress = _ProgressProbe()

        class DummyView:
            quest_progress_service = quest_progress
            progress_service = achievement_progress
            sync_automatic_progress = _FailIfCalled()
            refresh_completion_styles = _FailIfCalled()

        AchievementsView.refresh_external_progress(DummyView())

        self.assertEqual(quest_progress.calls, 1)
        self.assertEqual(achievement_progress.calls, 1)

    def test_manual_achievement_change_refreshes_without_quest_resync(self):
        calls: list[str] = []

        class _Stack:
            def currentWidget(self):
                return None

        class DummyView:
            quest_progress_service = _ProgressProbe()
            progress_service = _ProgressProbe(changed=True)
            detail_stack = _Stack()
            quest_detail_page = object()
            _detail_open = False
            current_achievement_id = None
            sync_automatic_progress = _FailIfCalled()

            @staticmethod
            def refresh_completion_styles() -> None:
                calls.append("styles")

        AchievementsView.refresh_external_progress(DummyView())

        self.assertEqual(calls, ["styles"])


if __name__ == "__main__":
    unittest.main()
