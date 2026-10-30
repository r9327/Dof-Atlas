from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.views.guides_view import (
    GUIDE_ULTIME_LEGACY_ID,
    GUIDE_ULTIME_TITLE,
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

    def test_prerequisite_lookup_index_reuses_one_catalog_and_preserves_duplicate_order(self) -> None:
        view = _GuidesCacheHarness()
        quests = [
            SimpleNamespace(id=101, name="Premier combat"),
            SimpleNamespace(id=102, name="Premier combat"),
            SimpleNamespace(id=103, name="Deuxième quête"),
        ]
        view.quest_catalog = SimpleNamespace(quests=quests)
        self.assertIsNone(view._quest_id_from_requirement_line("Objet nécessaire"))
        self.assertEqual(
            view._quest_id_from_requirement_line("Quête terminée: Premier combat"),
            101,
        )
        first_index = view._quest_name_id_index
        self.assertEqual(
            view._quest_id_from_requirement_line("Quête active: Deuxième quête"),
            103,
        )
        self.assertIs(view._quest_name_id_index, first_index)
        self.assertIsNone(
            view._quest_id_from_requirement_line("Quête terminée: inconnue"),
        )
        view.quest_catalog = SimpleNamespace(
            quests=[SimpleNamespace(id=205, name="Premier combat")],
        )
        self.assertEqual(
            view._quest_id_from_requirement_line("Quête terminée: Premier combat"),
            205,
        )
        self.assertIsNot(view._quest_name_id_index, first_index)

    def test_prerequisite_index_is_not_built_for_unknown_lines_or_missing_catalog(self) -> None:
        view = _GuidesCacheHarness()
        view.quest_catalog = None
        self.assertIsNone(view._quest_id_from_requirement_line("Quête active: exemple"))
        self.assertFalse(hasattr(view, "_quest_name_id_index"))
        view.quest_catalog = SimpleNamespace(quests=[])
        self.assertIsNone(view._quest_id_from_requirement_line("Fais les combats"))
        self.assertFalse(hasattr(view, "_quest_name_id_index"))

    def test_guide_ultime_card_is_selected_by_stable_id(self) -> None:
        class _Model:
            def __init__(self) -> None:
                self.title_overrides: dict[str, str] = {}
                self.subtitle_overrides: dict[str, str] = {}

            def set_title_override(self, guide_id: str, title: str) -> None:
                self.title_overrides[str(guide_id)] = str(title)

            def set_subtitle_override(self, guide_id: str, subtitle: str) -> None:
                self.subtitle_overrides[str(guide_id)] = str(subtitle)

        view = _GuidesCacheHarness()
        view.result_model = _Model()
        view.guide_ultime_service = SimpleNamespace(
            available=True,
            route_sheet_progress=lambda _character: (12, 34),
        )
        view.current_character_key = "character:42"

        view._refresh_guide_ultime_home_labels()

        self.assertEqual(
            view.result_model.title_overrides,
            {GUIDE_ULTIME_LEGACY_ID: GUIDE_ULTIME_TITLE},
        )
        self.assertEqual(
            view.result_model.subtitle_overrides,
            {GUIDE_ULTIME_LEGACY_ID: "12 / 34 fiches"},
        )


if __name__ == "__main__":
    unittest.main()
