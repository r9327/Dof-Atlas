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
