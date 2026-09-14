from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.network_bridge import NetworkUiBridge


class _Coordinator:
    def __init__(self, _window_handles) -> None:
        self.results = []
        self.stopped = False

    def latest_status(self):
        return SimpleNamespace(reason="idle")

    def drain_statuses(self, _limit):
        return []

    def drain_results(self, _limit):
        rows = list(self.results)
        self.results.clear()
        return rows

    def stop(self):
        self.stopped = True
        return True


class UiAsyncBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_quest_collectors_never_join_worker_threads(self) -> None:
        source = Path("app/pages/lazy_quests_page.py").read_text(encoding="utf-8")
        detail = source[source.index("    def _collect_detail"):source.index("    def _refresh_loaded_hierarchy_labels")]
        search = source[source.index("    def _collect_search_index"):source.index("\n\n__all__")]
        self.assertNotIn(".join(", detail)
        self.assertNotIn(".join(", search)

    def test_network_burst_emits_one_progress_refresh_per_character(self) -> None:
        with patch(
            "app.network.application_coordinator.NetworkApplicationCoordinator",
            _Coordinator,
        ):
            bridge = NetworkUiBridge()
        bridge._timer.stop()
        bridge._progress_timer.stop()
        emitted = []
        bridge.progressChanged.connect(emitted.append)
        bridge.coordinator.results = [
            SimpleNamespace(
                accepted=True,
                changed=True,
                character_key="character:42",
                reason="quest_completed",
            ),
            SimpleNamespace(
                accepted=True,
                changed=True,
                character_key="character:42",
                reason="quest_journal_completed",
            ),
        ]

        bridge._poll()

        self.assertEqual(emitted, [])
        self.assertEqual(bridge._pending_progress_characters, {"character:42"})
        bridge._progress_timer.stop()
        bridge._emit_pending_progress()
        self.assertEqual(emitted, ["character:42"])
        bridge.stop()
        bridge.deleteLater()


if __name__ == "__main__":
    unittest.main()
