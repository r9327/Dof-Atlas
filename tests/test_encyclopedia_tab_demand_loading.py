from __future__ import annotations

import unittest

from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB
from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage


class _Tabs:
    def __init__(self, label: str) -> None:
        self.label = label

    def tabText(self, _index: int) -> str:
        return self.label


class _IndexProbe:
    def __init__(self) -> None:
        self.loading: list[object] = []

    def set_loading(self, value) -> None:
        self.loading.append(value)


class _PageProbe:
    on_tab_changed = EncyclopediaPage.on_tab_changed
    _on_tab_changed_indexed = EncyclopediaPage._on_tab_changed_indexed
    _on_guide_requested = EncyclopediaPage._on_guide_requested
    _on_achievement_requested = EncyclopediaPage._on_achievement_requested

    def __init__(self, label: str) -> None:
        self.tabs = _Tabs(label)
        self._initializing = False
        self.guides_view = None
        self._related_ready = False
        self._achievement_ready = False
        self._guide_runtime_ready = False
        self._last_ready_tab_index = -1
        self._pending_guide_id = ""
        self._pending_achievement_id = None
        self._pending_lazy_tab = ""
        self._guide_index_view = None
        self._achievement_index_view = None
        self.calls: list[object] = []

    def tab_labels(self) -> list[str]:
        return [self.tabs.label]

    def _show_guide_index(self):
        self.calls.append("guide-index")
        return object()

    def _show_achievement_index(self):
        self.calls.append("achievement-index")
        return object()

    def sync_tab_accent(self, label: str | None = None) -> None:
        self.calls.append(("accent", label))

    def sync_search_visibility(self) -> None:
        self.calls.append("search")

    def status_callback(self, message: str) -> None:
        self.calls.append(("status", message))

    def _activate_loaded_tab(self, label: str) -> None:
        self.calls.append(("activate", label))

    def _on_tab_changed_progressive(self, index: int) -> None:
        self.calls.append(("progressive", index))

    def ensure_guides_view(self):
        raise AssertionError("cold Guide tab must not build the rich Guide view")

    def ensure_achievements_view(self):
        raise AssertionError("cold Success tab must not build the rich Success view")

    def _start_full_guide_runtime(self) -> None:
        raise AssertionError("cold Guide tab must not start the rich Guide runtime")

    def _start_full_achievement_runtime(self) -> None:
        raise AssertionError("cold Success tab must not start the rich Success runtime")

    def request_related_preload(self, target_tab: str = "") -> None:
        self.calls.append(("guide-runtime", target_tab))

    def request_achievement_runtime(self) -> None:
        self.calls.append("achievement-runtime")

    def open_pending_lazy_tab(self) -> None:
        self.calls.append("open-pending")

    def _finish_pending_guide_request(self) -> bool:
        self.calls.append("finish-guide")
        return True


class EncyclopediaDemandLoadingTests(unittest.TestCase):
    def test_cold_guide_tab_uses_light_index_without_starting_runtime(self) -> None:
        page = _PageProbe(GUIDES_TAB)

        page.on_tab_changed(0)

        self.assertIn("guide-index", page.calls)
        self.assertNotIn(("guide-runtime", GUIDES_TAB), page.calls)

    def test_cold_success_tab_uses_light_index_without_starting_runtime(self) -> None:
        page = _PageProbe(ACHIEVEMENTS_TAB)

        page.on_tab_changed(0)

        self.assertIn("achievement-index", page.calls)
        self.assertNotIn("achievement-runtime", page.calls)

    def test_success_tab_stays_light_when_only_guide_runtime_is_ready(self) -> None:
        page = _PageProbe(ACHIEVEMENTS_TAB)
        page._related_ready = True

        page.on_tab_changed(0)

        self.assertIn("achievement-index", page.calls)
        self.assertNotIn("open-pending", page.calls)
        self.assertNotIn(("activate", ACHIEVEMENTS_TAB), page.calls)

    def test_selecting_guide_from_index_starts_guide_runtime(self) -> None:
        page = _PageProbe(GUIDES_TAB)
        page._guide_index_view = _IndexProbe()

        page._on_guide_requested("aventure_1_20")

        self.assertEqual(page._pending_guide_id, "aventure_1_20")
        self.assertEqual(page._guide_index_view.loading, ["aventure_1_20"])
        self.assertIn(("guide-runtime", GUIDES_TAB), page.calls)

    def test_selecting_success_from_index_starts_success_runtime_even_if_guide_is_ready(self) -> None:
        page = _PageProbe(ACHIEVEMENTS_TAB)
        page._related_ready = True
        page._achievement_index_view = _IndexProbe()

        page._on_achievement_requested(123)

        self.assertEqual(page._pending_achievement_id, 123)
        self.assertEqual(page._pending_lazy_tab, ACHIEVEMENTS_TAB)
        self.assertEqual(page._achievement_index_view.loading, [123])
        self.assertIn("achievement-runtime", page.calls)
        self.assertNotIn("open-pending", page.calls)


if __name__ == "__main__":
    unittest.main()
