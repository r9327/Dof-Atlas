from __future__ import annotations

import unittest

from app.modules.encyclopedia.views.achievements_view import AchievementsView


class _UnchangedQuestProgress:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_if_changed(self) -> bool:
        self.calls += 1
        return False


class _FailIfCalled:
    def __call__(self, *args, **kwargs):
        raise AssertionError("expensive achievement refresh should not run")


class OptimizedAchievementsRefreshTests(unittest.TestCase):
    def test_unchanged_quest_progress_skips_all_expensive_refresh_work(self):
        progress = _UnchangedQuestProgress()

        class DummyView:
            quest_progress_service = progress
            sync_automatic_progress = _FailIfCalled()
            refresh_completion_styles = _FailIfCalled()

        AchievementsView.refresh_external_progress(DummyView())

        self.assertEqual(progress.calls, 1)


if __name__ == "__main__":
    unittest.main()
