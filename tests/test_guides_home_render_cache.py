from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.views.guides_view import (
    GUIDE_ULTIME_LEGACY_ID,
    GUIDE_ULTIME_TITLE,
    GuideHomeCard,
    GuidesView,
)


class _GuidesCacheHarness(GuidesView):
    """Exercise Python-only cache paths without constructing the full Qt view."""

    def __init__(self) -> None:
        pass


class GuidesHomeRenderCacheTests(unittest.TestCase):
    def make_view(self, root: Path) -> _GuidesCacheHarness:
        quest = root / "quest_progress.json"
        achievement = root / "achievement_progress.json"
        guide = root / "guide_progress.json"
        for path in (quest, achievement, guide):
            path.write_text("{}", encoding="utf-8")

        view = _GuidesCacheHarness()
        view.current_character_key = "slot:1"
        view.search_text = ""
        view.guides = [SimpleNamespace(id="guide-a", title="Guide A", category="dofus", order=1)]
        view.quest_progress_service = SimpleNamespace(path=quest)
        view.achievement_progress_service = SimpleNamespace(path=achievement)
        view.guide_progress_service = SimpleNamespace(path=guide)
        view.guide_ultime_service = None
        view._home_render_signature = None
        view._home_progress_cache_signature = None
        view._home_progress_cache = {}
        return view

    def test_unchanged_home_signature_skips_second_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            with (
                patch.object(GuidesView, "_refresh_home_uncached") as base_refresh,
                patch.object(GuidesView, "_refresh_guide_ultime_home_labels"),
            ):
                view.refresh_home()
                view.refresh_home()
                self.assertEqual(base_refresh.call_count, 1)

                view.search_text = "turquoise"
                view.refresh_home()
                self.assertEqual(base_refresh.call_count, 2)

    def test_progress_file_change_invalidates_render_and_progress_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            guide = view.guides[0]
            with (
                patch.object(GuidesView, "_refresh_home_uncached"),
                patch.object(GuidesView, "_refresh_guide_ultime_home_labels"),
                patch.object(GuidesView, "_guide_progress_tuple_uncached", return_value=(2, 5, "En cours")) as base_progress,
            ):
                first = view.guide_progress_tuple(guide)
                second = view.guide_progress_tuple(guide)
                self.assertEqual(first, second)
                self.assertEqual(base_progress.call_count, 1)

                Path(view.quest_progress_service.path).write_text('{"changed": true}', encoding="utf-8")
                third = view.guide_progress_tuple(guide)
                self.assertEqual(third, (2, 5, "En cours"))
                self.assertEqual(base_progress.call_count, 2)

    def test_guide_ultime_card_is_selected_by_stable_id(self) -> None:
        class _Label:
            def __init__(self, text: str) -> None:
                self.value = text

            def setText(self, text: str) -> None:
                self.value = text

        class _Card:
            def __init__(self, guide_id: str, title: str) -> None:
                self.guide = SimpleNamespace(id=guide_id)
                self.title = _Label(title)
                self.progress = _Label("legacy")
                self.tooltip = ""

            def findChild(self, _kind, name: str):
                return self.title if name == "GuideHomeCardTitle" else self.progress

            def setToolTip(self, text: str) -> None:
                self.tooltip = text

        canonical = _Card(GUIDE_ULTIME_LEGACY_ID, "Titre catalogue libre")
        decoy = _Card("autre-guide", "Aventure de zéro")
        view = _GuidesCacheHarness()
        view.home_content = SimpleNamespace(
            findChildren=lambda kind: [canonical, decoy] if kind is GuideHomeCard else []
        )
        view.guide_ultime_service = SimpleNamespace(
            available=True,
            route_sheet_progress=lambda _character: (12, 34),
        )
        view.current_character_key = "character:42"

        view._refresh_guide_ultime_home_labels()

        self.assertEqual(canonical.title.value, GUIDE_ULTIME_TITLE)
        self.assertEqual(canonical.progress.value, "12 / 34 fiches")
        self.assertIn(GUIDE_ULTIME_TITLE, canonical.tooltip)
        self.assertEqual(decoy.title.value, "Aventure de zéro")
        self.assertEqual(decoy.progress.value, "legacy")


if __name__ == "__main__":
    unittest.main()
