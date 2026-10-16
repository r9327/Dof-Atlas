"""Real Qt page and real public providers, with a bounded load barrier."""
from __future__ import annotations

import gc
from pathlib import Path
import tempfile
from threading import Event, enumerate as active_threads
import unittest
import weakref
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from app.modules.encyclopedia.providers import QuestProvider, AchievementProvider
from app.modules.encyclopedia.providers.memory_bound_guide_provider import MemoryBoundGuideProvider
from app.modules.encyclopedia.views import EncyclopediaPage


class EncyclopediaColdWorkerReleaseTests(unittest.TestCase):
    def test_deleted_page_is_not_retained_after_real_guide_worker_finishes(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            quests = QuestProvider()
            self.assertGreater(len(quests.list_quests()), 1900)
            achievements = AchievementProvider(quest_provider=quests)
            guides = MemoryBoundGuideProvider(quest_provider=quests, achievement_provider=achievements)
            page = EncyclopediaPage(
                lambda _status: None, quest_provider=quests,
                achievement_provider=achievements, guide_provider=guides,
                progress_path=root / "quests.json", achievement_progress_path=root / "achievements.json",
                guide_progress_path=root / "guide.json", profile_path=root / "profiles.json",
                client_index_path=root / "clients.json", owned_items_path=root / "craft.json",
            )
            entered, finish = Event(), Event()
            real_load = guides.load_all

            def held_real_load():
                entered.set()
                if not finish.wait(20):
                    raise TimeoutError("Guide worker load barrier was not released")
                return real_load()

            before = set(active_threads())
            workers = []
            try:
                page.show()
                app.processEvents()
                with patch.object(guides, "load_all", side_effect=held_real_load):
                    page.request_related_preload()
                    self.assertTrue(entered.wait(10), "Canonical Guide worker did not start")
                    workers = [thread for thread in active_threads() if thread not in before
                               and thread.name == "DofusAtlasGuideStage"]
                    self.assertEqual(len(workers), 1)
                    page_ref = weakref.ref(page)
                    page.hide()
                    page.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                    self.assertFalse(isValid(page))
                    del page
                    # The running closure temporarily owns its Python wrapper;
                    # this is measured separately from a permanently live view.
                    self.assertIsNotNone(page_ref())
                    finish.set()
                    workers[0].join(timeout=30)
                    self.assertFalse(workers[0].is_alive())
                app.processEvents()
                gc.collect()
                self.assertIsNone(page_ref())
                print("PC04_QT PASS: QObject deleted during load; worker terminal; Python view collected", flush=True)
            finally:
                finish.set()
                for thread in workers:
                    thread.join(timeout=30)
                if "page" in locals() and isValid(page):
                    page.close()
                    page.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
