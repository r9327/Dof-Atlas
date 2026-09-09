from __future__ import annotations

import unittest

from app.modules.encyclopedia.views.guides_view import GuidesView


class _QuestProgress:
    def __init__(self) -> None:
        self.progress = {"characters": {}}
        self.reload_calls = 0

    def reload(self):
        self.reload_calls += 1
        return self.progress


class _GuideUltimeView:
    def __init__(self) -> None:
        self.refresh_calls: list[bool] = []

    def refresh(self, reset_to_active: bool = True) -> None:
        self.refresh_calls.append(bool(reset_to_active))


class _DummyGuidesView:
    def __init__(self) -> None:
        self.quest_progress_service = _QuestProgress()
        self.quest_progress = None
        self.guide_ultime_view = _GuideUltimeView()
        self.sync_calls = 0
        self.label_refresh_calls = 0
        self.external_refresh_calls = 0

    def _mark_external_progress_refreshed(self) -> None:
        self.external_refresh_calls += 1

    def _sync_achievement_progress(self) -> bool:
        self.sync_calls += 1
        return True

    def _refresh_guide_ultime_home_labels(self) -> None:
        self.label_refresh_calls += 1

    def refresh_home(self) -> None:
        raise AssertionError("hidden Guides home must not be rebuilt")


class GuidesHiddenHomeRefreshTests(unittest.TestCase):
    def test_guide_ultime_quest_change_updates_only_hidden_home_labels(self):
        view = _DummyGuidesView()

        GuidesView._on_guide_ultime_quest_progress_changed(view, 123)

        self.assertEqual(view.quest_progress_service.reload_calls, 1)
        self.assertIs(view.quest_progress, view.quest_progress_service.progress)
        self.assertEqual(view.sync_calls, 1)
        self.assertEqual(view.label_refresh_calls, 1)
        self.assertEqual(view.external_refresh_calls, 1)
        self.assertEqual(view.guide_ultime_view.refresh_calls, [False])


if __name__ == "__main__":
    unittest.main()
