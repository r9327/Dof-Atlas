from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.views.guides_view import GuidesView


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


if __name__ == "__main__":
    unittest.main()
