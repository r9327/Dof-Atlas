from __future__ import annotations

import importlib
from queue import Queue
import unittest
from unittest.mock import Mock

from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.views.encyclopedia_page import (
    EncyclopediaPage, _QuestRuntimePayload,
)


class _Tabs:
    def __init__(self, label: str) -> None:
        self.label = label

    def tabText(self, _index: int) -> str:
        return self.label


class _PageProbe:
    on_tab_changed = EncyclopediaPage.on_tab_changed
    _on_tab_changed_indexed_runtime = EncyclopediaPage._on_tab_changed_indexed_runtime

    def __init__(self, label: str) -> None:
        self.tabs = _Tabs(label)
        self._initializing = False
        self.guides_view = None
        self._related_ready = False
        self._achievement_ready = False
        self._pending_lazy_tab = ""
        self.calls: list[object] = []

    def _activate_loaded_tab(self, label: str) -> None:
        self.calls.append(("activate", label))

    def _start_full_guide_runtime(self) -> None:
        self.calls.append("guide-runtime")

    def _start_full_achievement_runtime(self) -> None:
        self.calls.append("achievement-runtime")

    def open_pending_lazy_tab(self) -> None:
        self.calls.append("open-pending")

    def _on_tab_changed_indexed(self, index: int) -> None:
        self.calls.append(("indexed", index))


class EncyclopediaDemandLoadingTests(unittest.TestCase):
    def test_cold_guide_tab_starts_canonical_runtime_directly(self) -> None:
        page = _PageProbe(GUIDES_TAB)
        page.on_tab_changed(0)
        self.assertEqual(page.calls, ["guide-runtime"])

    def test_cold_success_tab_starts_canonical_runtime_directly(self) -> None:
        page = _PageProbe(ACHIEVEMENTS_TAB)
        page.on_tab_changed(0)
        self.assertEqual(page.calls, ["achievement-runtime"])

    def test_loaded_guide_tab_reuses_existing_canonical_view(self) -> None:
        page = _PageProbe(GUIDES_TAB)
        page.guides_view = object()
        page.on_tab_changed(0)
        self.assertEqual(page.calls, [("activate", GUIDES_TAB)])

    def test_ready_success_tab_opens_canonical_view_without_intermediate_index(self) -> None:
        page = _PageProbe(ACHIEVEMENTS_TAB)
        page._achievement_ready = True
        page.on_tab_changed(0)
        self.assertEqual(page._pending_lazy_tab, ACHIEVEMENTS_TAB)
        self.assertEqual(page.calls, ["open-pending"])

    def test_leaving_quests_marks_pending_worker_obsolete_without_stopping_it(self) -> None:
        page = _PageProbe(GUIDES_TAB)
        page._quest_load_started = True
        page._quest_load_abandoned = False
        page.on_tab_changed(0)
        self.assertTrue(page._quest_load_abandoned)
        page.tabs.label = QUESTS_TAB
        page.on_tab_changed(0)
        self.assertFalse(page._quest_load_abandoned)
        self.assertEqual(page.calls[-1], ("indexed", 0))

    def test_completed_abandoned_quest_worker_does_not_mount_heavy_page(self) -> None:
        class QuestResultProbe:
            _collect_quest_runtime = EncyclopediaPage._collect_quest_runtime

            def __init__(self) -> None:
                self._quest_load_queue = Queue(maxsize=1)
                self._quest_load_timer = Mock()
                self._quest_load_started = True
                self._quest_load_abandoned = True
                self._quest_graph = None
                self.quest_page = None
                self.status_callback = Mock()

            def _build_quests_page_progressive(self):
                raise AssertionError("Abandoned Quests must not hydrate")

        page = QuestResultProbe()
        page._quest_load_queue.put(_QuestRuntimePayload(object()))
        page._collect_quest_runtime()
        self.assertFalse(page._quest_load_started)
        self.assertFalse(page._quest_load_abandoned)
        self.assertIsNone(page._quest_graph)
        self.assertTrue(page._quest_load_queue.empty())
        page._quest_load_timer.stop.assert_called_once()
        page.status_callback.assert_not_called()

    def test_obsolete_light_index_entry_points_are_removed(self) -> None:
        obsolete = (
            "_show_guide_index",
            "_show_achievement_index",
            "_on_guide_requested",
            "_on_achievement_requested",
            "_finish_pending_guide_request",
            "_ensure_guides_view_base",
            "_ensure_guides_view_progressive",
            "_promote_guides_runtime_context",
            "_on_tab_changed_progressive",
        )
        for name in obsolete:
            with self.subTest(name=name):
                self.assertFalse(hasattr(EncyclopediaPage, name))

    def test_obsolete_placeholder_view_is_not_public(self) -> None:
        views = importlib.import_module("app.modules.encyclopedia.views")
        self.assertNotIn("EncyclopediaPlaceholderView", views.__all__)
        self.assertFalse(hasattr(views, "EncyclopediaPlaceholderView"))


if __name__ == "__main__":
    unittest.main()
