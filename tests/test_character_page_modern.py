from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.constants import KEY_SELECTED_CHARACTER
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.pages.character_page import CharacterPage


class ModernCharacterPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_identity_equipment_and_stats_have_the_requested_layout(self) -> None:
        self.assertEqual(CharacterPage.__module__, "app.pages.character_page")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profiles.json"
            clients = root / "clients.json"
            bindings = root / "bindings.json"
            profile.write_text(
                json.dumps({KEY_SELECTED_CHARACTER: "character:42"}),
                encoding="utf-8",
            )
            clients.write_text(
                json.dumps({"clients": [{"character_name": "Alpha", "pid": 111, "slot": 1}]}),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps(
                    {
                        "characters": {
                            "42": {
                                "name": "Alpha",
                                "pid": 111,
                                "organizer_slot": 1,
                                "source": "verified_network_identity",
                            },
                            "84": {
                                "name": "Beta",
                                "organizer_slot": 2,
                                "source": "verified_network_identity",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            runtime = CharacterRuntimeStateStore()
            runtime.identify(
                session_id="s1",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
            runtime.update_verified_profile(
                "s1",
                level=200,
                achievement_points=12345,
            )

            page = CharacterPage(
                profile_path=profile,
                client_index_path=clients,
                binding_path=bindings,
                runtime_state_store=runtime,
                icon_resolver=lambda _label: "",
                skin_resolver=lambda _label: "",
            )
            self.app.processEvents()

            columns = page.layout().itemAt(2).layout()
            self.assertEqual(columns.count(), 2)
            self.assertIs(columns.itemAt(0).widget(), page.equipment_panel)
            self.assertIs(columns.itemAt(1).widget(), page.stats_panel)
            self.assertTrue(page.identity_panel.isHidden())

            self.assertTrue(page.equipment_panel.isAncestorOf(page.achievement_points))
            self.assertTrue(page.equipment_panel.isAncestorOf(page.character_selector))
            self.assertEqual(page.achievement_points.text(), "12 345")
            self.assertEqual(page.achievement_points.objectName(), "CharacterAchievementPoints")
            self.assertEqual(page.achievement_points.styleSheet(), "")
            self.assertTrue(page.achievement_points.font().bold())
            self.assertEqual(page.achievement_points.alignment(), Qt.AlignCenter)

            self.assertEqual(page.character_selector.currentText(), "Alpha")
            self.assertEqual(page.character_selector.count(), 2)
            self.assertTrue(page.character_order_list.isHidden())

            self.assertEqual(page.skin_character_name.text(), "Alpha")
            self.assertEqual(page.skin_success_points.text(), "12 345")
            self.assertIs(page.skin_success_points, page.achievement_points)
            self.assertEqual(page.skin_success_points.styleSheet(), "")
            self.assertIn("Skin du personnage", page.portrait.text())

            self.assertIn("Statistiques en jeu", page.stats_empty_label.text())
            self.assertTrue(page.stats_scroll.isHidden())

            page.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
