from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.services import guide_ultime_manual_route


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
