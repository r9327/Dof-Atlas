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
