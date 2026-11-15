"""Qt smoke checks for the 95 metadata-only Ganymède UI containers.

Source metadata can be inspected; no source route can be played, validated,
certified, or silently manufactured by a catalogue preview.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QProgressBar

from app.modules.encyclopedia.views.guide_catalog_view import (
    GuideCatalogView, GanymedeGuideShell,
)
from app.modules.encyclopedia.views.guide_library_sources import load_ganymede_listings


class GanymedeGuideShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_index_has_95_distinct_metadata_only_guides(self) -> None:
        listings = load_ganymede_listings()
        self.assertEqual(len(listings), 95)
        self.assertEqual(len({item.source_id for item in listings}), 95)
        self.assertEqual(sum(item.step_count or 0 for item in listings), 7705)
        self.assertTrue(all(not item.playable for item in listings))

    def test_one_indexed_shell_supports_all_entries_without_loading_routes(self) -> None:
        listings = load_ganymede_listings()
        shell = GanymedeGuideShell(lambda: None)
        self.addCleanup(shell.deleteLater)
        before = len(shell.findChildren(QProgressBar))
        self.assertEqual(before, 3)
        for entry in listings:
            shell.set_listing(entry)
            self.assertEqual(shell.title_label.text(), entry.title)
            self.assertEqual(shell.sheet_title.text(), "Aucune fiche chargée")
            self.assertTrue(all(
                not progress.isEnabled()
                for progress in shell.findChildren(QProgressBar)
            ))
            self.assertEqual(len(shell.findChildren(QProgressBar)), before)
        self.assertFalse(shell.findChildren(QProgressBar)[0].isEnabled())

    def test_catalogue_reuses_one_preview_and_does_not_dispatch_guide(self) -> None:
        catalog = GuideCatalogView(
            lambda _message: None,
            provider=object(),
            quest_progress_path=Path("unused_catalogue_progress.json"),
            defer_runtime=True,
        )
        self.addCleanup(catalog.deleteLater)
        catalog.ganymede_listings = load_ganymede_listings()
        catalog._ganymede_by_id = {
            entry.source_id: entry for entry in catalog.ganymede_listings
        }
        requested: list[str] = []
        catalog.guideRequested.connect(requested.append)
        self.assertFalse(catalog.open_ganymede_container(-1))
        self.assertFalse(catalog.open_ganymede_container(True))
        self.assertEqual(catalog.pages.count(), 1)

        first, second = catalog.ganymede_listings[0], catalog.ganymede_listings[-1]
        self.assertTrue(catalog.open_ganymede_container(first.source_id))
        shell = catalog._ganymede_shell
        self.assertIsNotNone(shell)
        self.assertEqual(shell.title_label.text(), first.title)
        self.assertTrue(catalog.open_ganymede_container(second.source_id))
        self.assertIs(catalog._ganymede_shell, shell)
        self.assertEqual(shell.title_label.text(), second.title)
        self.assertEqual(catalog.pages.count(), 2)
        self.assertIsNone(catalog.current_guide_id)
        self.assertEqual(requested, [])
        shell.back_button.click()
        self.assertIs(catalog.pages.currentWidget(), catalog.home_scroll)
        self.assertEqual(requested, [])
