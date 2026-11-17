"""Qt smoke checks for the 95 metadata-only Ganymède UI containers.

Source metadata can be inspected; no source route can be played, validated,
certified, or silently manufactured by a catalogue preview.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QProgressBar, QPushButton, QSpinBox, QToolButton

from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView
from app.modules.encyclopedia.views.ganymede_guide_shell import GanymedeGuideShell
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
from app.modules.encyclopedia.views.guide_library_sources import load_ganymede_listings
from app.ui.theme import atlas_stylesheet
from app.ui.components import AtlasGuideCharacterButton


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
        self.assertEqual(shell.preparation_button.arrowType(), Qt.NoArrow)
        self.assertFalse(shell.preparation_button.icon().isNull())
        self.assertFalse(shell.prev_button.icon().isNull())
        self.assertFalse(shell.next_button.icon().isNull())
        self.assertFalse(shell.preparation_button.isEnabled())
        self.assertFalse(shell.participants_button.isEnabled())
        self.assertIsInstance(shell.participants_button, AtlasGuideCharacterButton)
        self.assertFalse(shell.participants_button.icon().isNull())
        self.assertEqual(shell.participants_button.width(), 24)
        # Personnages is on the compact title row, above global progress.
        from PySide6.QtWidgets import QGridLayout
        self.assertIs(
            shell._compact_title_row.itemAt(
                shell._compact_title_row.count() - 1
            ).widget(), shell.participants_button,
        )
        self.assertIs(
            shell._header_content_layout.itemAt(1).widget(),
            shell.participants_panel,
        )
        self.assertIsNotNone(shell.global_details_panel.findChild(
            QProgressBar, "GuideCompactPreparationProgress"
        ))
        self.assertEqual(shell.rendered_card_count, 0)
        self.assertEqual(shell.cards_layout.count(), 0)
        before = len(shell.findChildren(QProgressBar))
        self.assertEqual(before, 2)
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

    def test_first_cawotte_ui_pilot_opens_from_catalog_and_preserves_real_guide(self) -> None:
        from app.modules.encyclopedia.models.guide import Guide
        from app.modules.encyclopedia.views.guide_library_sources import INDEX_PATH
        from app.modules.encyclopedia.services.guide_source_reading_pages import (
            review_candidate_reading_blocks,
        )
        candidate = json.loads(
            (INDEX_PATH.parent / "ganymede_2205_action_candidates.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(candidate["source_step_count"], 64)
        self.assertFalse(candidate["ready_to_replace"])
        self.assertEqual(candidate["certified_actions"], 0)
        catalog = GuideCatalogView(
            lambda _message: None, provider=object(),
            quest_progress_path=Path("unused_cawotte_pilot.json"),
            defer_runtime=True,
        )
        self.addCleanup(catalog.deleteLater)
        self.addCleanup(catalog.close)
        catalog.guides = [Guide(id="dofus_cawotte", title="Dofus Cawotte", category="dofus")]
        catalog.ganymede_listings = load_ganymede_listings()
        catalog._ganymede_by_id = {
            row.source_id: row for row in catalog.ganymede_listings
        }
        catalog._populate_library_tree()
        pilot = catalog._cawotte_pilot_item
        self.assertEqual(pilot.data(0, Qt.UserRole + 2), 2205)
        requested = []
        catalog.guideRequested.connect(requested.append)
        catalog.resize(1180, 720)
        catalog.show()
        self.app.processEvents()
        tree = catalog.library_categories
        tree.scrollToItem(pilot)
        self.app.processEvents()
        rect = tree.visualItemRect(pilot)
        self.assertTrue(rect.isValid())
        QTest.mouseClick(tree.viewport(), Qt.LeftButton, pos=rect.center())
        self.app.processEvents()
        shell = catalog._ganymede_shell
        self.assertIsInstance(shell, GanymedeGuideShell)
        self.assertIs(catalog.pages.currentWidget(), shell)
        self.assertEqual(len(shell.service.cards), 64)
        self.assertEqual(len({card["source_step_id"] for card in shell.service.cards}), 64)
        self.assertGreater(len(review_candidate_reading_blocks(shell.service.cards)), 64)
        self.assertEqual(shell.rendered_card_count, 1)
        self.assertEqual(len(shell.findChildren(QFrame, "GuideManualSheet")), 1)
        self.assertTrue(shell.cards_layout.itemAt(0).widget().property(
            "sourceContinuousReading"
        ))
        self.assertEqual(shell.sheet_title_label.text(), "Parcours")
        self.assertEqual(shell.sheet_meta_label.text(), "")
        self.assertTrue(shell.sheet_meta_label.isHidden())
        self.assertEqual(len(shell.findChildren(QProgressBar)), 2)
        pages = shell._source_reading_pages()
        self.assertLess(len(pages), 64)
        self.assertGreater(len(pages), 1)
        self.assertEqual(shell.page_jump.text(), f"1 / {len(pages)}")
        first = pages[0]
        self.assertGreater(len(first), 1)
        self.assertFalse(shell.validation_host.isVisibleTo(shell))
        self.assertEqual(shell.validation_layout.count(), 0)

        # Tabs and a temporary checklist work without saving uncertified data.
        shell.global_details_button.click()
        shell.preparation_button.click()
        self.app.processEvents()
        self.assertTrue(shell.preparation_panel.isVisibleTo(shell))
        self.assertEqual(shell._preparation_tab, "Prérequis")
        self.assertEqual(len(shell._preparation_preview), 10)
        material_tab = next(
            tab for tab in shell.preparation_tab_group.buttons()
            if tab.property("tabKey") == "À préparer"
        )
        material_tab.click()
        self.app.processEvents()
        self.assertEqual(shell._preparation_tab, "À préparer")
        checks = shell.preparation_panel.findChildren(QToolButton, "GuidePreparationReady")
        self.assertEqual(checks, [])
        from PySide6.QtWidgets import QCheckBox
        checks = shell.preparation_panel.findChildren(QCheckBox, "GuidePreparationReady")
        self.assertEqual(len(checks), 7)
        checks[0].click()
        self.assertTrue(checks[0].isChecked())
        self.assertFalse(hasattr(shell.service, "guide_progress"))
        self.assertEqual(len(shell.findChildren(QToolButton, "GuideMetricDropdown")), 2)
        # The second click collapses global details; a third click restores
        # the same nested preparation panel without losing its state.
        shell.global_details_button.click()
        self.app.processEvents()
        self.assertFalse(shell.global_details_panel.isVisibleTo(shell))
        shell.global_details_button.click()
        self.app.processEvents()
        self.assertTrue(shell.global_details_panel.isVisibleTo(shell))
        self.assertTrue(shell.preparation_panel.isVisibleTo(shell))
        self.assertIn(
            "aperçu non certifié",
            shell.global_details_panel.findChild(QLabel, "GuidePreparationEmpty").text(),
        )

        # X/X moves between adaptive pages while keeping original card IDs.
        shell.page_jump.setValue(2)
        self.assertEqual(shell.page_jump.value(), 2)
        self.assertEqual(shell.rendered_card_count, 1)
        self.assertTrue(shell.preparation_panel.isVisibleTo(shell))
        shell.page_jump.setValue(len(pages))
        self.assertEqual(shell.page_jump.value(), len(pages))
        self.assertEqual(shell.view_index, pages[-1][0]["source_index"])
        self.assertFalse(shell.next_button.isEnabled())
        self.assertEqual(shell.validation_layout.count(), 0)
        shell.guide_button.click()
        self.assertIs(catalog.pages.currentWidget(), catalog.home_scroll)
        other = next(row for row in catalog.ganymede_listings if row.source_id != 2205)
        self.assertTrue(catalog.open_ganymede_container(other.source_id))
        self.assertIs(catalog._ganymede_shell, shell)
        self.assertEqual(shell.service.cards, ())
        self.assertEqual(shell.rendered_card_count, 0)
        self.assertFalse(shell.page_jump.isEnabled())
        self.assertEqual(requested, [])
        self.assertTrue(catalog.select_guide("dofus_cawotte"))
        self.assertEqual(requested, ["dofus_cawotte"])

    def test_single_sheet_survives_resize_and_long_text(self) -> None:
        import copy
        from app.modules.encyclopedia.services.guide_source_reading_pages import (
            review_candidate_reading_blocks, paginate_authored_blocks,
        )
        shell = GanymedeGuideShell(lambda: None)
        self.addCleanup(shell.deleteLater)
        self.addCleanup(shell.close)
        source = next(
            row for row in load_ganymede_listings() if row.source_id == 2205
        )
        shell.resize(1220, 1050)
        shell.show()
        self.app.processEvents()
        shell.set_listing(source)
        self.assertTrue(shell.show_cawotte_review())
        self.app.processEvents()
        self.assertEqual(shell.rendered_card_count, 1)
        wide_pages = shell._source_reading_pages()
        self.assertGreater(len(wide_pages[0]), 1)
        shell.resize(760, 560)
        self.app.processEvents()
        self.assertEqual(shell.rendered_card_count, 1)
        self.assertGreaterEqual(len(shell._source_reading_pages()), len(wide_pages))

        extended = copy.deepcopy(shell.service.cards[1])
        huge = "Instruction Cawotte très détaillée. " * 700
        extended["manual_sections"]["now"][0]["text"] = huge
        shell.service.cards = (
            shell.service.cards[:1] + (extended,) + shell.service.cards[2:]
        )
        shell._source_pages_cache_key = None
        shell._show_index(1)
        self.app.processEvents()
        self.assertEqual(shell.rendered_card_count, 1)
        self.assertGreater(shell.scroll.verticalScrollBar().maximum(), 0)
        blocks = review_candidate_reading_blocks(shell.service.cards)
        pages = paginate_authored_blocks(blocks, chars_per_line=35)
        self.assertEqual(
            sum("Instruction Cawotte très détaillée." in
                "".join(run["text"] for run in row["block"]["runs"])
                for page in pages for row in page),
            1,
        )
        self.assertEqual(shell.validation_layout.count(), 0)

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
