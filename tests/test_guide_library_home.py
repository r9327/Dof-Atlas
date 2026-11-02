"""Guide library and featured-card contracts for the compact 2026-10-24 UI."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout, QComboBox, QLabel, QListView, QLineEdit, QPlainTextEdit

from app.modules.encyclopedia.models.guide import Guide
from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView
from app.modules.encyclopedia.views.encyclopedia_page import _has_embedded_search
from app.modules.encyclopedia.views.guide_library_sources import (
    ATLAS_EQUIVALENTS, CATEGORIES, classify_title, displayable_listings,
    load_ganymede_listings, load_ganymede_local_observations,
)
from app.modules.encyclopedia.widgets.guide_card import GUIDE_ID_ROLE
from app.modules.encyclopedia.widgets.guide_card import GuideCardDelegate


def _guide(name, category):
    return Guide(id=name, category=category, title=name, search_text=name.casefold())


class _Provider:
    def __init__(self):
        self.guides = [
            _guide("guide_complet", "aventure"),
            _guide("dofus_sylvestre", "aventure"),
            _guide("alignement_bonta", "alignements"),
            _guide("alignement_brakmar", "alignements"),
            _guide("dofus_cawotte", "dofus"),
            _guide("dofus_ivoire", "dofus"),
        ]

    def load_all(self):
        return list(self.guides)

    def search(self, query):
        q = str(query or "").casefold().strip()
        return [g for g in self.guides if not q or q in g.id.casefold()]


class GuideLibraryHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_95_unique_canonical_ids_are_classified_without_playable_routes(self):
        records = load_ganymede_listings()
        ids = [entry.source_id for entry in records]
        self.assertEqual(len(ids), 95)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue({entry.category for entry in records}.issubset(
            {key for key, _title in CATEGORIES}
        ))
        self.assertTrue(all(not entry.playable for entry in records))
        self.assertEqual(classify_title("Srambad 1"), "dimensions")
        self.assertEqual(classify_title("Kwismas"), "events")

    def test_existing_dofus_guides_are_not_duplicated_by_source_metadata(self):
        records = load_ganymede_listings()
        merged = displayable_listings(records, {"dofus_cawotte"}, "dofus")
        self.assertNotIn(2205, {entry.source_id for entry in merged})
        self.assertIn(2203, {entry.source_id for entry in merged})
        self.assertEqual(ATLAS_EQUIVALENTS[2205], "dofus_cawotte")
        aliases = {"dofus_nebuleux", "dofus_dom_de_pin", "dofus_sylvestre"}
        selected = displayable_listings(records, aliases, "dofus")
        visible_ids = {entry.source_id for entry in selected}
        self.assertTrue({2247, 2285, 2290}.isdisjoint(visible_ids))

    def test_real_ganymede_home_counts_manual_steps_not_completed_quests(self):
        from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            progress_path = root / "guide_progress.json"
            source_dir = Path(__file__).resolve().parents[1] / "data" / "encyclopedia" / "guides"
            manual = GuideProgressService(progress_path)
            manual.set_manual_step_completed(
                "character:1", "dofus_cawotte", "ganymede_2205_step_0001", True,
            )
            provider = _Provider()
            provider.guides_dir = source_dir
            provider._detail_entries = {
                "dofus_cawotte": (
                    source_dir / "replacement_drafts" / "cutovers" / "dofus_cawotte.json",
                    0, {},
                ),
            }
            with patch(
                "app.modules.encyclopedia.views.guide_catalog_view.GUIDE_PROGRESS_FILE",
                progress_path,
            ), patch(
                "app.modules.encyclopedia.views.encyclopedia_page.GUIDE_PROGRESS_FILE",
                progress_path,
            ):
                view = GuideCatalogView(
                    lambda _message: None, provider=provider,
                    quest_progress_path=root / "quest_progress.json",
                    character_key="character:1",
                    defer_runtime=True,
                )
                self.addCleanup(view.deleteLater)
                view.hydrate_runtime()
                progress = view._progress_snapshot()
                self.assertEqual(progress["dofus_cawotte"], (1, 64, "En cours"))
                self.assertNotEqual(progress["dofus_ivoire"], (1, 64, "En cours"))
                self.assertEqual(
                    EncyclopediaPage._build_guide_progress_snapshot(
                        provider, "character:1", root / "quest_progress.json",
                    )["dofus_cawotte"],
                    (1, 64, "En cours"),
                )
                # The two optimized routes retain their previous progress contract.
                self.assertEqual(progress["guide_complet"], (0, 0, ""))

    def test_source_library_exposes_all_95_without_replacing_optimized_guides(self):
        from app.modules.encyclopedia.services.guide_ganymede_cutover import (
            active_manual_catalog_sources,
        )
        import json

        base = Path(__file__).resolve().parents[1] / "data" / "encyclopedia" / "guides"
        manifest = json.loads((
            base / "replacement_drafts" / "cutovers" / "cutover_manifest.json"
        ).read_text(encoding="utf-8"))["guides"]
        guides = [
            _guide("guide_complet", "aventure"),
            _guide("dofus_sylvestre", "aventure"),
            _guide("alignement_bonta", "alignements"),
            _guide("alignement_brakmar", "alignements"),
            *(_guide(guide_id, "dofus") for guide_id in manifest),
        ]
        provider = _Provider()
        provider.guides = guides
        provider.guides_dir = base
        provider._detail_entries = {
            guide_id: (
                base / "replacement_drafts" / "cutovers" / f"{guide_id}.json",
                i, {},
            )
            for i, guide_id in enumerate(manifest)
        }
        with tempfile.TemporaryDirectory() as directory:
            view = GuideCatalogView(
                lambda _message: None, provider=provider,
                quest_progress_path=Path(directory) / "quest_progress.json",
                defer_runtime=True,
            )
            view._progress_snapshot = lambda: {}
            view.hydrate_runtime()
            try:
                self.assertEqual(set(view.featured_cards), {
                    "guide_complet", "dofus_sylvestre",
                })
                self.assertEqual(
                    len(active_manual_catalog_sources(provider, guides)), 20,
                )
                ids_visible_as_links = set()
                for key, _label in CATEGORIES:
                    view.library_category = key
                    view.refresh_home()
                    for i in range(view.home_metadata_list.count()):
                        item = view.home_metadata_list.item(i)
                        self.assertTrue(item.flags() & Qt.ItemIsEnabled)
                        ids_visible_as_links.add(item.data(Qt.UserRole))

                source_ids = {entry.source_id for entry in view.ganymede_listings}
                native_ids = {
                    row["source_guide_id"] for row in manifest.values()
                }
                # The short Ganymède Sylvan Dofus remains accessible
                # independently from the large preserved Atlas Sylvestre Opti.
                self.assertIn(2290, ids_visible_as_links)
                self.assertEqual(len(ids_visible_as_links), 73)
                # Alignments open through their existing left-tree entries.
                alignment_sources = {2249, 2263}
                self.assertEqual(
                    ids_visible_as_links | native_ids | alignment_sources,
                    source_ids,
                )
                self.assertTrue(ids_visible_as_links.isdisjoint(native_ids))
            finally:
                view.deleteLater()
                self.app.processEvents()

    def test_all_75_non_native_source_routes_have_complete_local_fact_rows(self):
        import json

        root = Path(__file__).resolve().parents[1] / "data" / "encyclopedia" / "guides"
        cutovers = json.loads((
            root / "replacement_drafts" / "cutovers" / "cutover_manifest.json"
        ).read_text(encoding="utf-8"))["guides"]
        native_source_ids = {entry["source_guide_id"] for entry in cutovers.values()}
        listings = load_ganymede_listings()
        missing_native = [
            entry for entry in listings if entry.source_id not in native_source_ids
        ]
        self.assertEqual(len(native_source_ids), 20)
        self.assertEqual(len(missing_native), 75)
        total_steps = 0
        for entry in missing_native:
            with self.subTest(source_id=entry.source_id):
                steps = load_ganymede_local_observations(entry)
                self.assertEqual(len(steps), entry.step_count)
                self.assertEqual(steps[0]["source_step_number"], 1)
                self.assertEqual(
                    steps[-1]["source_step_number"], entry.step_count,
                )
                total_steps += len(steps)
        self.assertGreater(total_steps, 5000)

    def test_corrupt_local_source_data_fails_closed(self):
        import json

        entry = next(
            entry for entry in load_ganymede_listings()
            if entry.source_id == 2290
        )
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "ganymede_2290_observed_links.json"
            source = json.loads((
                Path(__file__).resolve().parents[1] / "data" / "encyclopedia"
                / "guides" / "ganymede_2290_observed_links.json"
            ).read_text(encoding="utf-8"))
            source["steps"][0]["source_step_number"] = 2
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid offline source step"):
                load_ganymede_local_observations(entry, data_dir=folder)

    def test_source_guide_click_reads_verified_local_facts_without_network(self):
        import sys

        class FakeWebView(QLabel):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.visited_url = None

            def setUrl(self, url):
                self.visited_url = url

        provider = _Provider()
        with tempfile.TemporaryDirectory() as directory:
            view = GuideCatalogView(
                lambda _message: None, provider=provider,
                quest_progress_path=Path(directory) / "quest_progress.json",
                defer_runtime=True,
            )
            view._progress_snapshot = lambda: {}
            view.hydrate_runtime()
            try:
                view.library_category = "dimensions"
                view.refresh_home()
                self.assertGreater(view.home_metadata_list.count(), 0)
                item = view.home_metadata_list.item(0)
                source_id = item.data(Qt.UserRole)
                fake_module = SimpleNamespace(QWebEngineView=FakeWebView)
                with patch.dict(sys.modules, {
                    "PySide6.QtWebEngineWidgets": fake_module,
                }):
                    view._open_ganymede_source_item(item)
                    dialog = view._ganymede_source_dialog
                    self.assertIsNotNone(dialog)
                    self.assertIsNone(
                        dialog.findChild(FakeWebView, "GanymedeSourceWebView")
                    )
                    local = dialog.findChild(
                        QPlainTextEdit, "GanymedeOfflineSourceStep"
                    )
                    self.assertIsNotNone(local)
                    self.assertIn("ÉTAPE 1", local.toPlainText())
                    self.assertIn("REPÈRES HORS LIGNE", local.toPlainText())
                    self.assertEqual(dialog.objectName(), "GanymedeSourceReader")
                    view.set_character_key("character:12")
                    self.assertIsNone(view._ganymede_source_dialog)
                    self.assertEqual(view.current_character_key, "character:12")
                    self.app.processEvents()
            finally:
                view.close()
                view.deleteLater()
                self.app.processEvents()

    def test_source_offline_reader_step_navigation_and_character_progress(self):
        import sys
        from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
        from PySide6.QtWidgets import QSpinBox, QPushButton

        class OfflineWeb(QLabel):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.visited_url = None

            def setUrl(self, url):
                self.visited_url = url

        with tempfile.TemporaryDirectory() as directory:
            progress_path = Path(directory) / "guide_progress.json"
            view = GuideCatalogView(
                lambda _message: None, provider=_Provider(),
                quest_progress_path=Path(directory) / "quests.json",
                character_key="character:7", defer_runtime=True,
            )
            view._progress_snapshot = lambda: {}
            view.hydrate_runtime()
            try:
                view.library_category = "dofus"
                view.refresh_home()
                item = view.home_metadata_list.item(0)
                source = next(
                    row for row in view.ganymede_listings
                    if row.source_id == item.data(Qt.UserRole)
                )
                self.assertGreater(source.step_count, 2)
                with patch.dict(sys.modules, {
                    "PySide6.QtWebEngineWidgets": SimpleNamespace(
                        QWebEngineView=OfflineWeb,
                    ),
                }), patch(
                    "app.modules.encyclopedia.views.guide_catalog_view.GUIDE_PROGRESS_FILE",
                    progress_path,
                ):
                    view._open_ganymede_source_item(item)
                    dialog = view._ganymede_source_dialog
                    self.assertIsNone(
                        dialog.findChild(OfflineWeb, "GanymedeSourceWebView")
                    )
                    local = dialog.findChild(
                        QPlainTextEdit, "GanymedeOfflineSourceStep"
                    )
                    self.assertIsNotNone(local)
                    spinner = dialog.findChild(QSpinBox, "GanymedeSourceStepNumber")
                    validate = dialog.findChild(
                        QPushButton, "GanymedeSourceValidateStep"
                    )
                    self.assertEqual(spinner.value(), 1)
                    self.assertTrue(validate.isEnabled())
                    validate.click()
                    progress = GuideProgressService(progress_path)
                    step_id = f"ganymede_{source.source_id}_step_0001"
                    mapped_id = ATLAS_EQUIVALENTS.get(source.source_id)
                    progress_id = (
                        mapped_id if mapped_id and mapped_id != "dofus_sylvestre"
                        else f"ganymede_source_{source.source_id}"
                    )
                    self.assertTrue(progress.is_manual_step_completed(
                        "character:7", progress_id, step_id,
                    ))
                    spinner.setValue(2)
                    self.assertIn("ÉTAPE 2 /", local.toPlainText())
                    self.assertIn("REPÈRES HORS LIGNE", local.toPlainText())
                    spinner.setValue(1)
                    self.assertEqual(validate.text(), "Annuler la validation")
                    # A second session clears the step after this dialog
                    # read it. The first click must reject its stale state.
                    GuideProgressService(progress_path).set_manual_step_completed(
                        "character:7", progress_id, step_id, False,
                    )
                    validate.click()
                    self.assertEqual(validate.text(), "Valider l'étape")
                    self.assertFalse(
                        GuideProgressService(progress_path).is_manual_step_completed(
                            "character:7", progress_id, step_id,
                        )
                    )
                    validate.click()
                    self.assertTrue(
                        GuideProgressService(progress_path).is_manual_step_completed(
                            "character:7", progress_id, step_id,
                        )
                    )
                    validate.click()
                    self.assertFalse(
                        GuideProgressService(progress_path).is_manual_step_completed(
                            "character:7", progress_id, step_id,
                        )
                    )
                    dialog.close()
                    self.app.processEvents()
                    # Ganymède Sylvan Dofus is a 2-step source, not the
                    # separate large Atlas Sylvestre Opti progress namespace.
                    source_row = next(
                        i for i in range(view.home_metadata_list.count())
                        if view.home_metadata_list.item(i).data(Qt.UserRole) == 2290
                    )
                    view._open_ganymede_source_item(
                        view.home_metadata_list.item(source_row),
                    )
                    sylvan = view._ganymede_source_dialog
                    sylvan_validate = sylvan.findChild(
                        QPushButton, "GanymedeSourceValidateStep",
                    )
                    sylvan_validate.click()
                    self.assertTrue(
                        GuideProgressService(progress_path).is_manual_step_completed(
                            "character:7", "ganymede_source_2290",
                            "ganymede_2290_step_0001",
                        )
                    )
                    self.assertFalse(
                        GuideProgressService(progress_path).is_manual_step_completed(
                            "character:7", "dofus_sylvestre",
                            "ganymede_2290_step_0001",
                        )
                    )
                    sylvan.close()
                    self.app.processEvents()
            finally:
                view.close()
                view.deleteLater()
                self.app.processEvents()

    def test_unity_catalog_inner_roots_and_featured_card_alpha(self):
        from unittest.mock import patch

        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            with tempfile.TemporaryDirectory() as directory:
                view = GuideCatalogView(
                    lambda _message: None, provider=_Provider(),
                    quest_progress_path=Path(directory) / "progress.json",
                    defer_runtime=True,
                )
                try:
                    self.assertEqual(
                        view.home_scroll.widget().objectName(), "GuidesHomeContent"
                    )
                    self.assertEqual(view.library_right.objectName(), "GuideLibraryResults")
                    for card in view.featured_cards.values():
                        self.assertIn("rgba(27, 39, 70, 0.88)", card.styleSheet())
                    self.assertIn(
                        "rgba(27, 39, 70, 0.88)",
                        view.home_metadata_list.styleSheet(),
                    )
                finally:
                    view.deleteLater()
                    self.app.processEvents()

    def test_rich_guides_signals_and_external_catalog_navigation(self):
        from app.modules.encyclopedia.views.guides_view import GuidesView

        # The lazy Encyclopedia wires these Qt signals on the rich GuidesView.
        # Regression: both were missing, raising AttributeError on first open.
        self.assertTrue(hasattr(GuidesView, "catalogRequested"))
        self.assertTrue(hasattr(GuidesView, "achievementRuntimeRequested"))

        requested = []
        fake = SimpleNamespace(
            _catalog_external_owner=True,
            catalogRequested=SimpleNamespace(emit=lambda: requested.append("catalog")),
        )
        GuidesView.show_home(fake)
        self.assertEqual(requested, ["catalog"])

        # Outside Encyclopedia the historical embedded home still works.
        page = object()
        switched = []
        standalone = SimpleNamespace(
            _catalog_external_owner=False,
            catalogRequested=SimpleNamespace(emit=lambda: requested.append("wrong")),
            current_guide_id="guide_complet",
            current_quest_id=42,
            state="GUIDE_OVERVIEW",
            CATALOG="CATALOG",
            refresh_home=lambda: switched.append("refresh"),
            stack=SimpleNamespace(setCurrentWidget=switched.append),
            home_page=page,
            status_callback=lambda text: switched.append(text),
        )
        GuidesView.show_home(standalone)
        self.assertEqual(standalone.state, "CATALOG")
        self.assertIsNone(standalone.current_guide_id)
        self.assertIsNone(standalone.current_quest_id)
        self.assertIn(page, switched)
        self.assertEqual(requested, ["catalog"])

    def test_two_featured_cards_and_stable_alignment_tree(self):
        provider = _Provider()
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "app.modules.encyclopedia.views.guide_catalog_view.catalog_route_map_count_hint",
                return_value=0,
            ):
                view = GuideCatalogView(
                    lambda _message: None,
                    provider=provider,
                    quest_progress_path=Path(directory) / "progress.json",
                    defer_runtime=True,
                )
                view._progress_snapshot = lambda: {}
                view.hydrate_runtime()
                view.resize(1180, 780)
                view.show()
                self.app.processEvents()
                try:
                    self.assertEqual(set(view.featured_cards), {
                        "guide_complet", "dofus_sylvestre",
                    })
                    # The two optimized cards now span the whole top row.
                    self.assertEqual(view.optimized_pair.pair_layout.direction(),
                                     QBoxLayout.LeftToRight)
                    self.assertTrue(view.featured_cards["guide_complet"].isVisibleTo(view))
                    self.assertIsNone(view.findChild(QLineEdit, "GuideLibrarySearch"))
                    self.assertEqual(view._category_nodes["alignements"].childCount(), 2)
                    self.assertEqual(view.home_dofus_list.viewMode(), QListView.IconMode)
                    requested = []
                    view.guideRequested.connect(requested.append)
                    view.featured_cards["guide_complet"].open_button.click()
                    self.assertEqual(requested, ["guide_complet"])
                    alignments = view._category_nodes["alignements"]
                    requested.clear()
                    with patch.object(view, "_open_ganymede_source_item") as open_source:
                        view.library_categories.setCurrentItem(alignments.child(0))
                        self.assertEqual(requested, [])
                        self.assertEqual(
                            open_source.call_args.args[0].data(Qt.UserRole),
                            2249,
                        )
                    view.library_categories.setCurrentItem(view._category_nodes["dimensions"])
                    self.assertEqual(view.library_category, "dimensions")
                    self.assertGreater(view.home_metadata_list.count(), 0)
                    self.assertTrue(all(
                        bool(view.home_metadata_list.item(i).flags() & Qt.ItemIsEnabled)
                        for i in range(view.home_metadata_list.count())
                    ))
                    alignments.setExpanded(False)
                    view.set_search_text("no-matching-library-entry")
                    self.assertTrue(view.featured_cards["guide_complet"].isVisibleTo(view))
                    self.assertFalse(alignments.isExpanded())
                    self.assertFalse(view.home_dofus_list.isVisible())
                    view.resize(610, 780)
                    self.app.processEvents()
                    self.assertEqual(view.home_columns.layout().direction(),
                                     QBoxLayout.TopToBottom)
                finally:
                    view.close()
                    view.deleteLater()
                    self.app.processEvents()

    def test_home_shows_two_optimized_cards_above_dropdown_and_selected_content(self):
        with tempfile.TemporaryDirectory() as directory:
            view = GuideCatalogView(
                lambda _text: None, provider=_Provider(),
                quest_progress_path=Path(directory) / "progress.json",
                defer_runtime=True,
            )
            view._progress_snapshot = lambda: {}
            view.hydrate_runtime()
            view.resize(1200, 800)
            view.show()
            self.app.processEvents()
            try:
                self.assertEqual(
                    view.home_columns.layout().direction(), QBoxLayout.LeftToRight,
                )
                self.assertEqual(view.optimized_pair.pair_layout.direction(),
                                 QBoxLayout.LeftToRight)
                self.assertTrue(view.optimized_pair.isVisibleTo(view))
                self.assertTrue(view.featured_cards["guide_complet"].isVisibleTo(view))
                self.assertTrue(view.featured_cards["dofus_sylvestre"].isVisibleTo(view))
                self.assertTrue(view.category_selector.isVisibleTo(view))
                self.assertIsInstance(view.category_selector, QComboBox)
                self.assertEqual(view.category_selector.currentData(), "dofus")
                self.assertFalse(view.library_categories.isVisibleTo(view))
                self.assertFalse(view.other_groups_widget.isVisibleTo(view))
                self.assertFalse(any(
                    button.isVisibleTo(view)
                    for button in view.alignment_buttons.values()
                ))
                self.assertFalse(view.alignment_shared_button.isVisibleTo(view))
                self.assertEqual(view.library_results_title.text(), "DOFUS")
                self.assertTrue(view.home_dofus_list.isVisibleTo(view))
                self.assertEqual(
                    [
                        view.category_selector.itemData(i)
                        for i in range(view.category_selector.count())
                    ],
                    [
                        "dofus", "alignements", "islands", "dimensions",
                        "eliocalypse", "regions", "adventures", "events",
                    ],
                )
                self.assertEqual(
                    view.category_selector.itemText(2), "Îles et territoires",
                )
                self.assertEqual(
                    view.category_selector.itemText(
                        view.category_selector.count() - 1
                    ), "Événements",
                )

                # Only the right side switches when a category is selected.
                view.category_selector.setCurrentIndex(
                    view.category_selector.findData("alignements"),
                )
                self.assertEqual(view.library_category, "alignements")
                self.assertEqual(view.library_results_title.text(), "ALIGNEMENTS")
                self.assertEqual(view.home_dofus_model.rowCount(), 2)
                self.assertTrue(any(
                    view.home_metadata_list.item(i).data(Qt.UserRole) == 2226
                    for i in range(view.home_metadata_list.count())
                ))
                self.assertTrue(view.optimized_pair.isVisibleTo(view))
                for key in ("islands", "dimensions", "eliocalypse",
                            "regions", "adventures", "events"):
                    view.category_selector.setCurrentIndex(
                        view.category_selector.findData(key),
                    )
                    self.assertEqual(view.library_category, key)
                    self.assertEqual(
                        view.library_results_title.text(),
                        dict(CATEGORIES)[key].upper(),
                    )
                    self.assertGreater(view.home_metadata_list.count(), 0, key)
                    self.assertFalse(view.other_groups_widget.isVisibleTo(view))

                # Existing programmatic navigation still synchronizes the menu.
                view.library_categories.setCurrentItem(view._category_nodes["dofus"])
                self.assertEqual(view.category_selector.currentData(), "dofus")
                self.assertEqual(view.library_results_title.text(), "DOFUS")
                view.resize(610, 780)
                self.app.processEvents()
                self.assertEqual(
                    view.home_columns.layout().direction(), QBoxLayout.TopToBottom,
                )
            finally:
                view.close()
                view.deleteLater()
                self.app.processEvents()

    def test_home_family_lists_cover_sources_without_duplication(self):
        from app.modules.encyclopedia.services.guide_ganymede_cutover import (
            active_manual_catalog_sources,
        )
        import json

        root = Path(__file__).resolve().parents[1] / "data" / "encyclopedia" / "guides"
        manifest = json.loads((
            root / "replacement_drafts" / "cutovers" / "cutover_manifest.json"
        ).read_text(encoding="utf-8"))["guides"]
        provider = _Provider()
        provider.guides_dir = root
        provider.guides.append(_guide("dofus_ocre", "dofus"))
        provider.guides.extend(
            _guide(guide_id, "dofus")
            for guide_id in manifest
            if not any(g.id == guide_id for g in provider.guides)
        )
        provider._detail_entries = {
            guide_id: (root / "replacement_drafts" / "cutovers" /
                       f"{guide_id}.json", i, {})
            for i, guide_id in enumerate(manifest)
        }
        with tempfile.TemporaryDirectory() as directory:
            view = GuideCatalogView(
                lambda _text: None, provider=provider,
                quest_progress_path=Path(directory) / "progress.json",
                defer_runtime=True,
            )
            view._progress_snapshot = lambda: {}
            view.hydrate_runtime()
            try:
                native = active_manual_catalog_sources(provider, provider.guides)
                self.assertEqual(len(native), 20)
                self.assertEqual(
                    view.home_dofus_model.row_for_guide("dofus_ocre"), -1,
                )
                self.assertIn(
                    2218, {
                        view.home_metadata_list.item(i).data(Qt.UserRole)
                        for i in range(view.home_metadata_list.count())
                    },
                )
                visible_source_ids = {
                    view.home_metadata_list.item(i).data(Qt.UserRole)
                    for i in range(view.home_metadata_list.count())
                }
                for listing in view.other_category_lists.values():
                    for i in range(listing.count()):
                        item = listing.item(i)
                        if item.data(Qt.UserRole) is not None:
                            visible_source_ids.add(item.data(Qt.UserRole))
                # 20 native Dofus + 3 left alignment buttons + 72 source
                # entries in the home = all 95 with no duplicated route.
                expected = {entry.source_id for entry in view.ganymede_listings}
                native_sources = {
                    row["source_guide_id"] for row in manifest.values()
                }
                self.assertEqual(len(visible_source_ids), 72)
                self.assertEqual(
                    visible_source_ids | native_sources | {2226, 2249, 2263}, expected,
                )
                self.assertFalse(visible_source_ids.intersection(native_sources))
            finally:
                view.deleteLater()
                self.app.processEvents()

    def test_entire_featured_card_is_clickable_and_keyboard_accessible(self):
        provider = _Provider()
        with tempfile.TemporaryDirectory() as directory:
            view = GuideCatalogView(
                lambda _message: None,
                provider=provider,
                quest_progress_path=Path(directory) / "progress.json",
                defer_runtime=True,
            )
            view._progress_snapshot = lambda: {}
            view.hydrate_runtime()
            view.resize(1200, 800)
            view.show()
            self.app.processEvents()
            try:
                events = []
                view.guideRequested.connect(events.append)
                card = view.featured_cards["guide_complet"]
                QTest.mouseClick(card, Qt.LeftButton)
                QTest.keyClick(card, Qt.Key_Return)
                self.assertEqual(events, ["guide_complet", "guide_complet"])
                self.assertTrue(card.accessibleName())
                model = view.home_dofus_model
                row = model.row_for_guide("dofus_cawotte")
                self.assertGreaterEqual(row, 0)
                self.assertNotIn("0 %", model.index(row, 0).data(Qt.DisplayRole))
                self.assertIn("Progression inconnue", model.index(row, 0).data(Qt.DisplayRole))
            finally:
                view.close()
                view.deleteLater()
                self.app.processEvents()

    def test_global_encyclopedia_search_is_absent(self):
        # The common header has no QLineEdit; Quêtes/Sommaire search is separate.
        import inspect
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
        self.assertNotIn("EncyclopediaSearch", inspect.getsource(EncyclopediaPage))
        self.assertFalse(_has_embedded_search(type("GuideCatalogView", (), {})()))

    def test_progress_bar_geometry_never_escapes_later_grid_columns(self):
        second_column = QRect(280, 96, 280, 96)
        bar = GuideCardDelegate.progress_rect(
            second_column,
            second_column.left() + 71,
            second_column.right() - 10,
        )
        self.assertGreaterEqual(bar.left(), second_column.left())
        self.assertLessEqual(bar.right(), second_column.right())
        self.assertEqual(bar.height(), 4)

    def test_rich_guide_return_restores_canonical_lightweight_library(self):
        """The detail view must never leave its legacy home after a return."""
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
        from app.modules.encyclopedia.views.deferred_achievement_guides_view import (
            DeferredAchievementGuidesView,
        )
        import inspect

        # Genuine production signal: Guide card's back action -> GuidesView
        # show_home -> Encyclopedia owner -> lightweight approved catalogue.
        self.assertIn(
            "self.catalogRequested.emit()",
            inspect.getsource(DeferredAchievementGuidesView.show_home),
        )
        selected = []
        catalog = SimpleNamespace(
            _runtime_ready=False, hydrate_runtime=lambda **kw: selected.append(("hydrate", kw)),
            set_search_text=lambda query: selected.append(("search", query)),
        )
        owner = SimpleNamespace(
            guides_view=SimpleNamespace(search_text="cawotte"),
            _guide_runtime_ready=True,
            _quest_graph=None,
            _guide_progress_by_guide={},
            _guide_progress_character_key="",
            sync_search_visibility=lambda: selected.append(("sync",)),
            status_callback=lambda text: selected.append(("status", text)),
        )

        def ensure_catalog():
            self.assertIsNone(owner.guides_view)
            owner.guides_view = catalog
            return catalog

        owner.ensure_guides_view = ensure_catalog
        EncyclopediaPage._restore_guides_catalog_home(owner)
        self.assertIs(owner.guides_view, catalog)
        self.assertEqual(selected[0][0], "hydrate")
        self.assertIn(("search", "cawotte"), selected)
        self.assertIn(("sync",), selected)



if __name__ == "__main__":
    unittest.main()
