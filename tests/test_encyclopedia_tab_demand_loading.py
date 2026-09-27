from __future__ import annotations

import unittest

from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB
from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage


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

    def test_obsolete_light_index_entry_points_are_removed(self) -> None:
        obsolete = (
            "_show_guide_index",
            "_show_achievement_index",
            "_on_guide_requested",
            "_on_achievement_requested",
            "_finish_pending_guide_request",
        )
        for name in obsolete:
            with self.subTest(name=name):
                self.assertFalse(hasattr(EncyclopediaPage, name))


if __name__ == "__main__":
    unittest.main()
