"""Regression proof: Home redraw does not regenerate identical Qt icons."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, QCoreApplication
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget
from main import AtlasWindow


class HomeCharacterComboCacheTests(unittest.TestCase):
    def test_same_character_rows_reuse_combo_but_selection_and_runtime_stay_live(self):
        QApplication.instance() or QApplication([])
        one = SimpleNamespace(key="character:1", label="Panda", class_key="pandawa")
        two = SimpleNamespace(key="character:2", label="Enu", class_key="enutrof")
        combo = Mock()
        combo.blockSignals.return_value = False
        combo.count.return_value = 1
        fake = SimpleNamespace(
            current_character_key="character:1",
            current_character_label="Panda",
            character_combo=combo,
            _known_characters=lambda: [one, two],
            _connected_characters=lambda rows: rows,
            character_icon_path=lambda label, class_key="": f"/fake/{class_key}.png",
            persist_selected_character=Mock(),
            home_page=SimpleNamespace(set_character=Mock()),
            sync_selected_character_to_pages=Mock(),
            _refresh_runtime_hotkeys_for_client_mapping=Mock(),
        )
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(fake)
            self.assertEqual(combo.addItem.call_count, 2)
            self.assertEqual(combo.clear.call_count, 1)

            # A second Home visit must not regenerate or drop the same icons.
            AtlasWindow.refresh_global_characters(fake)
            self.assertEqual(combo.addItem.call_count, 2)
            self.assertEqual(combo.clear.call_count, 1)
            self.assertEqual(fake._refresh_runtime_hotkeys_for_client_mapping.call_count, 2)

            # Selection may change without forcing icon/item reconstruction.
            fake.current_character_key = "character:2"
            AtlasWindow.refresh_global_characters(fake)
            combo.setCurrentIndex.assert_called_with(1)
            self.assertEqual(combo.clear.call_count, 1)

            # A verified class/icon change must still rebuild the items.
            two.class_key = "ecaflip"
            AtlasWindow.refresh_global_characters(fake)
            self.assertEqual(combo.clear.call_count, 2)
            self.assertEqual(combo.addItem.call_count, 4)
            self.assertEqual(fake.current_character_key, "character:2")


class ShellWorldScanHibernationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Qt widgets require a living QApplication even when a single test is
        # selected directly by the targeted Windows workflow.
        cls.app = QApplication.instance() or QApplication([])

    def test_home_eviction_preserves_world_state_only_when_idle(self):
        state = {
            "view_key": "world-a", "world_name": "Astrub",
            "history": ("world-b",), "select_coord": (1, -2),
        }
        scan = SimpleNamespace(export_lightweight_navigation_state=Mock(return_value=state))
        home = QWidget()
        stack = QStackedWidget()
        stack.addWidget(home)
        stack.setCurrentWidget(home)
        factory = Mock()
        release = Mock()
        fake = SimpleNamespace(
            stack=stack,
            pending_page_name="",
            page_widgets={"Scan Monde": scan, "Home": home},
            page_factories={},
            _world_scan_return_state=None,
            create_world_scan_page=factory,
            release_reconstructible_page=release,
        )
        AtlasWindow._hibernate_world_scan_on_home(fake)
        self.assertEqual(fake._world_scan_return_state, state)
        release.assert_called_once_with("Scan Monde", factory)

        release.reset_mock()
        scan.export_lightweight_navigation_state.return_value = None
        AtlasWindow._hibernate_world_scan_on_home(fake)
        release.assert_not_called()

        fake.page_factories["Scan Monde"] = factory
        AtlasWindow._hibernate_world_scan_on_home(fake)
        release.assert_not_called()

        # A late worker completion must not evict a page the player reopened.
        fake.page_factories.clear()
        scan.export_lightweight_navigation_state.return_value = state
        new_active = QWidget()
        stack.addWidget(new_active)
        stack.setCurrentWidget(new_active)
        AtlasWindow._hibernate_world_scan_on_home(fake)
        release.assert_not_called()
        stack.deleteLater()

    def test_finished_worker_eviction_only_when_home_is_current(self):
        home, other = QWidget(), QWidget()
        stack = QStackedWidget()
        stack.addWidget(home)
        stack.addWidget(other)
        scheduler = Mock()
        fake = SimpleNamespace(
            stack=stack,
            page_widgets={"Home": home},
            _schedule_owned_callback=scheduler,
            _hibernate_world_scan_on_home=Mock(),
        )
        try:
            stack.setCurrentWidget(other)
            AtlasWindow._on_world_scan_load_finished(fake, 1, {})
            scheduler.assert_not_called()
            stack.setCurrentWidget(home)
            AtlasWindow._on_world_scan_load_finished(fake, 2, {})
            scheduler.assert_called_once_with(0, fake._hibernate_world_scan_on_home)
        finally:
            stack.deleteLater()

    def test_page_factory_rehydrates_only_the_saved_map_navigation(self):
        saved = {"view_key": "world-a", "history": (), "select_coord": (1, -2)}
        panel = Mock(spec=["restore_navigation_state", "cartographyLoadFinished"])
        fake = SimpleNamespace(
            _world_scan_return_state=saved,
            set_status=Mock(),
            _on_world_scan_load_finished=Mock(),
        )
        with patch("app.ui.world_scan_panel.WorldScanPanel", return_value=panel) as ctor:
            self.assertIs(AtlasWindow.create_world_scan_page(fake), panel)
        ctor.assert_called_once_with(fake.set_status)
        panel.cartographyLoadFinished.connect.assert_called_once_with(fake._on_world_scan_load_finished)
        panel.restore_navigation_state.assert_called_once_with(saved)
        self.assertIsNone(fake._world_scan_return_state)


class ShellTransientPlaceholderReleaseTests(unittest.TestCase):
    def test_home_releases_only_dynamic_placeholders_not_almanax_or_real_pages(self):
        QApplication.instance() or QApplication([])
        stack = QStackedWidget()
        home, almanax, real = QWidget(), QWidget(), QWidget()
        stubs = [QWidget(), QWidget()]
        names = ["Home", "Almanax", "Craft", "Placeholder::Ocre", "Placeholder::Chasse"]
        widgets = [home, almanax, real, *stubs]
        for widget in widgets:
            stack.addWidget(widget)
        stack.setCurrentWidget(home)
        page_widgets = dict(zip(names, widgets))
        fake = SimpleNamespace(
            stack=stack,
            page_widgets=page_widgets,
            page_nav_group={name: "Outils" for name in names},
            page_indexes={name: stack.indexOf(widget) for name, widget in page_widgets.items()},
            page_factories={},
            pages=list(zip(names, widgets)),
        )
        fake.rebuild_page_indexes = lambda: setattr(
            fake, "page_indexes",
            {name: stack.indexOf(widget) for name, widget in fake.page_widgets.items()}
        )
        try:
            AtlasWindow.release_transient_placeholders(fake)
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.assertEqual(stack.count(), 3)
            self.assertEqual(set(fake.page_widgets), {"Home", "Almanax", "Craft"})
            self.assertEqual(fake.page_indexes["Craft"], stack.indexOf(real))
            self.assertNotIn("Placeholder::Ocre", fake.page_nav_group)
            # Re-entry creates only the single chosen placeholder anew.
            self.assertIs(stack.currentWidget(), home)
        finally:
            stack.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
