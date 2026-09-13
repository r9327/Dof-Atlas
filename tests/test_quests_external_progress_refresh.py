from __future__ import annotations

import unittest

from app.pages._quests_page_impl import QuestsPage


class _ProgressProbe:
    def __init__(self, changed: bool = False) -> None:
        self.changed = changed
        self.calls = 0
        self.progress = {"version": 1, "characters": {}}

    def refresh_if_changed(self) -> bool:
        self.calls += 1
        return self.changed


class _FailIfCalled:
    def __call__(self, *args, **kwargs):
        raise AssertionError("unrelated quest refresh work should not run")


class QuestsExternalProgressRefreshTests(unittest.TestCase):
    def test_unchanged_sources_skip_all_render_work(self) -> None:
        quest_progress = _ProgressProbe()
        achievement_progress = _ProgressProbe()

        class DummyPage:
            quest_progress_service = quest_progress
            achievement_progress_service = achievement_progress
            selected_quest_id = 42
            _sync_achievement_progress = _FailIfCalled()
            rebuild_hierarchy = _FailIfCalled()
            refresh_quests = _FailIfCalled()
            show_quest_detail = _FailIfCalled()
            restore_last_quest = _FailIfCalled()

        QuestsPage.refresh_external_progress(DummyPage())

        self.assertEqual(quest_progress.calls, 1)
        self.assertEqual(achievement_progress.calls, 1)

    def test_manual_achievement_change_refreshes_only_open_quest_detail(self) -> None:
        calls: list[object] = []

        class DummyPage:
            quest_progress_service = _ProgressProbe()
            achievement_progress_service = _ProgressProbe(changed=True)
            selected_quest_id = 42
            _sync_achievement_progress = _FailIfCalled()
            rebuild_hierarchy = _FailIfCalled()
            refresh_quests = _FailIfCalled()
            restore_last_quest = _FailIfCalled()

            @staticmethod
            def show_quest_detail(quest_id: int) -> None:
                calls.append(quest_id)

        QuestsPage.refresh_external_progress(DummyPage())

        self.assertEqual(calls, [42])


if __name__ == "__main__":
    unittest.main()
