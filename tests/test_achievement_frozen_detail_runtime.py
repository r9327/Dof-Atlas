from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
    MemoryBoundAchievementProvider,
    RAW_QUEST_DATA_DIR,
)


class AchievementFrozenDetailRuntimeTests(unittest.TestCase):
    """Regression: the packaged app cannot use the subprocess detail loader."""

    @staticmethod
    def _provider(data_dir: Path) -> MemoryBoundAchievementProvider:
        # No catalogue I/O is needed for this lifecycle/worker preparation test.
        provider = object.__new__(MemoryBoundAchievementProvider)
        provider.data_dir = data_dir
        return provider

    def test_windows_exe_prepares_success_details_during_runtime_warmup(self) -> None:
        provider = self._provider(Path(RAW_QUEST_DATA_DIR))
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(MemoryBoundAchievementProvider, "_ensure_loaded") as loaded,
            patch.object(MemoryBoundAchievementProvider, "prepare_detail_sources") as prepared,
        ):
            provider.load_runtime()
            loaded.assert_called_once_with()
            prepared.assert_called_once_with()

    def test_development_subprocess_runtime_keeps_details_cold(self) -> None:
        provider = self._provider(Path(RAW_QUEST_DATA_DIR))
        with (
            patch.object(sys, "frozen", False, create=True),
            patch.object(MemoryBoundAchievementProvider, "_ensure_loaded") as loaded,
            patch.object(MemoryBoundAchievementProvider, "prepare_detail_sources") as prepared,
        ):
            provider.load_runtime()
            loaded.assert_called_once_with()
            prepared.assert_not_called()

    def test_windows_frozen_detail_does_not_spawn_console_or_worker(self) -> None:
        provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
        marker = object()
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(MemoryBoundAchievementProvider, "_ensure_loaded"),
            patch.object(
                MemoryBoundAchievementProvider,
                "_get_detail_in_process", return_value=marker,
            ) as in_process,
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.run",
                side_effect=AssertionError("frozen details must stay in process"),
            ),
        ):
            self.assertIs(provider.get_detail_by_id(321), marker)
        in_process.assert_called_once_with(321)
        self.assertFalse(provider.last_detail_breakdown_ms["subprocess_path_used"])
        self.assertEqual(
            provider.last_detail_breakdown_ms["synchronous_subprocess_ms"], 0.0
        )
        self.assertEqual(provider.last_cold_detail_breakdown_ms["achievement_id"], 321)
        self.assertEqual(provider.last_cold_detail_breakdown_ms["status"], "OBSERVED")
        self.assertFalse(
            provider.last_cold_detail_breakdown_ms["subprocess_path_used"]
        )
        self.assertGreaterEqual(
            provider.last_cold_detail_breakdown_ms["total_ms"], 0.0
        )

    def test_frozen_reuses_recent_rich_details_without_reopening_sources(self) -> None:
        provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
        first, second = object(), object()
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(MemoryBoundAchievementProvider, "_ensure_loaded"),
            patch.object(
                MemoryBoundAchievementProvider, "_get_detail_in_process",
                side_effect=[first, second],
            ) as reader,
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.run",
                side_effect=AssertionError("EXE may not launch a detail child"),
            ),
        ):
            self.assertIs(provider.get_detail_by_id(101), first)
            self.assertIs(provider.get_detail_by_id(102), second)
            self.assertIs(provider.get_detail_by_id(101), first)
            self.assertIs(provider.get_detail_by_id(102), second)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(provider.last_detail_breakdown_ms["cache_source"], "recent")
        self.assertFalse(provider.last_detail_breakdown_ms["subprocess_path_used"])
        self.assertEqual(len(provider._recent_rich_details), 1)

    def test_rebuilding_catalogue_drops_recent_rich_detail_cache(self) -> None:
        provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
        provider._recent_rich_details[10] = object()
        provider._detail_cache_id = 12
        provider._detail_cache = object()
        provider._last_detail_cache_source = "hot"
        provider._achievements = []
        with (
            patch.object(MemoryBoundAchievementProvider, "_trim_catalogue_payload"),
            patch.object(MemoryBoundAchievementProvider, "_reset_sources"),
        ):
            provider._finish_in_process_catalogue()
        self.assertEqual(provider._recent_rich_details, {})
        self.assertIsNone(provider._detail_cache)
        self.assertIsNone(provider._detail_cache_id)
        self.assertEqual(provider._last_detail_cache_source, "cold")
        self.assertEqual(provider.last_cold_detail_breakdown_ms, {})

    def test_nonstandard_runtime_data_directory_uses_in_process_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = self._provider(Path(directory))
            with (
                patch.object(sys, "frozen", False, create=True),
                patch.object(MemoryBoundAchievementProvider, "_ensure_loaded") as loaded,
                patch.object(MemoryBoundAchievementProvider, "prepare_detail_sources") as prepared,
            ):
                provider.load_runtime()
                loaded.assert_called_once_with()
                prepared.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
