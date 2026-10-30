"""Regression proof: Home redraw does not regenerate identical Qt icons."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication
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


if __name__ == "__main__":
    unittest.main()
