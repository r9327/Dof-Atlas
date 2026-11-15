"""Qt smoke checks for the 95 metadata-only Ganymède UI containers.

Source metadata can be inspected; no source route can be played, validated,
certified, or silently manufactured by a catalogue preview.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QProgressBar, QSpinBox

from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView
from app.modules.encyclopedia.views.ganymede_guide_shell import GanymedeGuideShell
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
from app.modules.encyclopedia.views.guide_library_sources import load_ganymede_listings
from app.ui.theme import atlas_stylesheet


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
        self.assertIsInstance(shell, SharedGuideManualView)
        self.assertIsNotNone(shell.findChild(QFrame, "GuideCompactHeader"))
        self.assertIsNotNone(shell.findChild(QFrame, "GuideSheetHeader"))
        self.assertIsNotNone(shell.findChild(QFrame, "GuideManualNav"))
        self.assertEqual(shell.sheet_meta_label.text(), "")
        self.assertTrue(shell.sheet_meta_label.isHidden())
        self.assertEqual(shell.guide_icon_label.size().width(), 32)
        self.assertEqual(shell.guide_icon_label.size().height(), 32)
        self.assertIsNotNone(shell.findChild(QSpinBox, "GuideCompactPageJump"))
        self.assertFalse(shell.page_jump.isEnabled())
        self.assertEqual(shell.page_jump.text(), "—")
        stylesheet = atlas_stylesheet()
        self.assertIn("QSpinBox#GuideCompactPageJump::up-arrow", stylesheet)
        self.assertIn("QSpinBox#GuideCompactPageJump::down-arrow", stylesheet)
        self.assertEqual(shell.summary_button.arrowType(), Qt.NoArrow)
        self.assertEqual(shell.preparation_button.arrowType(), Qt.NoArrow)
        self.assertFalse(shell.summary_button.icon().isNull())
        self.assertFalse(shell.preparation_button.icon().isNull())
        self.assertEqual(shell.summary_button.width(), 18)
        self.assertFalse(shell.prev_button.icon().isNull())
        self.assertFalse(shell.next_button.icon().isNull())
        self.assertFalse(shell.summary_button.isEnabled())
        self.assertFalse(shell.preparation_button.isEnabled())
        self.assertFalse(shell.participants_button.isEnabled())
        self.assertEqual(shell.rendered_card_count, 0)
        self.assertEqual(shell.cards_layout.count(), 0)
        before = len(shell.findChildren(QProgressBar))
        self.assertEqual(before, 3)
        for entry in listings:
            shell.set_listing(entry)
            self.assertEqual(shell.guide_title_label.text(), entry.title)
            self.assertEqual(shell.sheet_title_label.text(), "Aucune fiche chargée")
            self.assertEqual(shell.sheet_meta_label.text(), "")
            self.assertTrue(shell.sheet_meta_label.isHidden())
            self.assertTrue(all(
                not progress.isEnabled()
                for progress in shell.findChildren(QProgressBar)
            ))
            self.assertEqual(len(shell.findChildren(QProgressBar)), before)
            self.assertEqual(shell.cards_layout.count(), 0)
            self.assertEqual(shell.rendered_card_count, 0)
            self.assertEqual(shell.service.cards, ())
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

        shell = None
        for entry in catalog.ganymede_listings:
            self.assertTrue(catalog.open_ganymede_container(entry.source_id))
            if shell is None:
                shell = catalog._ganymede_shell
                self.assertIsNotNone(shell)
            self.assertIs(catalog._ganymede_shell, shell)
            self.assertEqual(shell.guide_title_label.text(), entry.title)
            self.assertEqual(catalog.pages.count(), 2)
        self.assertIsNone(catalog.current_guide_id)
        self.assertEqual(requested, [])
        shell.guide_button.click()
        self.assertIs(catalog.pages.currentWidget(), catalog.home_scroll)
        self.assertEqual(requested, [])
