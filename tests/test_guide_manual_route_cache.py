from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.services import (
    guide_ultime_manual_route,
    guide_ultime_manual_runtime_core,
)


class GuideManualRouteCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        guide_ultime_manual_route.clear_manual_route_cache()

    def test_top_level_resolution_is_reused_and_returns_isolated_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chapter = root / "chapter.json"
            chapter.write_text("{}", encoding="utf-8")
            calls = 0

            def resolver(path, *, _seen=None, _expand_hooks=True):
                nonlocal calls
                calls += 1
                return {"path": Path(path).name, "rows": [calls]}

            with patch.object(
                guide_ultime_manual_route,
                "_load_manual_chapter_uncached",
                resolver,
            ):
                first = guide_ultime_manual_route.load_manual_chapter(chapter)
                first["rows"].append(999)
                second = guide_ultime_manual_route.load_manual_chapter(chapter)

            self.assertEqual(calls, 1)
            self.assertEqual(second["rows"], [1])

    def test_sibling_json_change_invalidates_top_level_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chapter = root / "chapter.json"
            dependency = root / "dependency.json"
            chapter.write_text("{}", encoding="utf-8")
            dependency.write_text("{}", encoding="utf-8")
            calls = 0

            def resolver(path, *, _seen=None, _expand_hooks=True):
                nonlocal calls
                calls += 1
                return {"call": calls}

            with patch.object(
                guide_ultime_manual_route,
                "_load_manual_chapter_uncached",
                resolver,
            ):
                guide_ultime_manual_route.load_manual_chapter(chapter)
                guide_ultime_manual_route.load_manual_chapter(chapter)
                dependency.write_text('{"changed": true}', encoding="utf-8")
                third = guide_ultime_manual_route.load_manual_chapter(chapter)

            self.assertEqual(calls, 2)
            self.assertEqual(third["call"], 2)

    def test_shared_memo_reuses_recursive_resolution_without_duplicate_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapter = Path(tmp) / "chapter.json"
            chapter.write_text("{}", encoding="utf-8")
            calls = 0

            def resolver(path, *, _seen=None, _expand_hooks=True, _memo=None):
                nonlocal calls
                calls += 1
                return {"call": calls, "rows": [calls]}

            memo: dict[tuple[Path, bool], dict] = {}
            seen = {Path(tmp) / "parent.json"}
            with patch.object(guide_ultime_manual_route, "_load_manual_chapter_uncached", resolver):
                first = guide_ultime_manual_route.load_manual_chapter(chapter, _seen=seen, _memo=memo)
                second = guide_ultime_manual_route.load_manual_chapter(chapter, _seen=seen, _memo=memo)

            self.assertEqual(calls, 1)
            self.assertIs(first, second)
            self.assertEqual(second["rows"], [1])

    def test_copy_on_write_patch_does_not_mutate_memoized_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.json"
            child = root / "child.json"
            base.write_text(
                '{"stages":[{"id":"A","quests":["Q1"],"meta":{"keep":true}}]}',
                encoding="utf-8",
            )
            child.write_text(
                '{"base_file":"base.json","stage_patches":{"A":{"append":{"quests":["Q2"]}}}}',
                encoding="utf-8",
            )
            memo: dict[tuple[Path, bool], dict] = {}
            resolved = guide_ultime_manual_route.load_manual_chapter(
                child,
                _seen={root / "parent.json"},
                _expand_hooks=False,
                _memo=memo,
            )

            memoized_base = memo[(base.resolve(), False)]
            self.assertEqual(memoized_base["stages"][0]["quests"], ["Q1"])
            self.assertEqual(resolved["stages"][0]["quests"], ["Q1", "Q2"])
            self.assertIsNot(resolved["stages"][0], memoized_base["stages"][0])
            self.assertIs(
                resolved["stages"][0]["meta"],
                memoized_base["stages"][0]["meta"],
            )

    def test_shared_memo_does_not_mask_active_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapter = Path(tmp) / "chapter.json"
            chapter.write_text("{}", encoding="utf-8")
            resolved = chapter.resolve()
            memo = {(resolved, True): {"rows": [1]}}

            with self.assertRaisesRegex(ValueError, "Cycle de composition"):
                guide_ultime_manual_route.load_manual_chapter(chapter, _seen={resolved}, _memo=memo)

    def test_compact_runtime_builds_hidden_cards_without_full_render_payload(self) -> None:
        service = object.__new__(
            guide_ultime_manual_runtime_core.GuideUltimeManualRuntimeService
        )
        service._quest_name_to_id = {"quest_a": 42}

        chapter = {
            "coverage": {"chapter": "Astrub"},
            "preparation": [{"name": "Potion de rappel"}],
        }
        stage = {
            "id": "AST-1",
            "title": "Départ",
            "start": {"x": 4, "y": -19, "zone": "Astrub"},
            "quests": ["Quest A"],
            "instructions": ["Parler au PNJ."],
            "successes": ["Succès A"],
            "temporal_hooks": ["window-a"],
        }

        with patch.object(
            service,
            "_stage_lines",
            side_effect=AssertionError("hidden compact cards must not render lines"),
        ):
            card = service._stage_to_compact_card(
                "astrub",
                {"label": "Astrub"},
                chapter,
                stage,
                1,
            )

        self.assertEqual(card["manual_stage_id"], "AST-1")
        self.assertEqual(card["manual_quest_ids"], [42])
        self.assertEqual(card["manual_quest_names"], ["quest_a"])
        self.assertTrue(card["manual_has_lines"])
        self.assertEqual(card["manual_lines"], [])
        self.assertNotIn("manual_stage_data", card)
        self.assertNotIn("manual_chapter_preparation", card)
        self.assertNotIn("structured_runtime_lines", card)
        self.assertNotIn("manual_runtime_metadata", card)

    def test_compact_runtime_hydrates_only_current_manual_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = object.__new__(
                guide_ultime_manual_runtime_core.GuideUltimeManualRuntimeService
            )
            service.compact_runtime = True
            service.manual_dir = Path(tmp)
            service._manual_base_lines_cache = ("old", [{"text": "old"}])

            previous = {
                "manual_stage_data": {"id": "previous"},
                "manual_chapter_preparation": [{"name": "old"}],
            }
            service._manual_hydrated_card = previous
            card = {
                "manual_source_file": "chapter.json",
                "manual_stage_position": 1,
            }
            chapter = {
                "stages": [
                    {"id": "first"},
                    {"id": "visible", "instructions": ["Do it"]},
                ]
            }

            with (
                patch.object(
                    guide_ultime_manual_runtime_core,
                    "load_manual_chapter",
                    return_value=chapter,
                ),
                patch.object(
                    service,
                    "_chapter_preparation_schedule",
                    return_value={1: [{"name": "needed"}]},
                ),
            ):
                stage = service._hydrate_manual_card_source(card)

            self.assertIs(stage, chapter["stages"][1])
            self.assertIs(card["manual_stage_data"], chapter["stages"][1])
            self.assertEqual(
                card["manual_chapter_preparation"],
                [{"name": "needed"}],
            )
            self.assertNotIn("manual_stage_data", previous)
            self.assertNotIn("manual_chapter_preparation", previous)
            self.assertIs(service._manual_hydrated_card, card)
            self.assertIsNone(service._manual_base_lines_cache)

    def test_recursive_resolution_bypasses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapter = Path(tmp) / "chapter.json"
            chapter.write_text("{}", encoding="utf-8")
            calls = 0

            def resolver(path, *, _seen=None, _expand_hooks=True):
                nonlocal calls
                calls += 1
                return {"call": calls}

            seen = {Path(tmp) / "parent.json"}
            with patch.object(
                guide_ultime_manual_route,
                "_load_manual_chapter_uncached",
                resolver,
            ):
                first = guide_ultime_manual_route.load_manual_chapter(
                    chapter,
                    _seen=seen,
                )
                second = guide_ultime_manual_route.load_manual_chapter(
                    chapter,
                    _seen=seen,
                )

            self.assertEqual((first["call"], second["call"]), (1, 2))
            self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
