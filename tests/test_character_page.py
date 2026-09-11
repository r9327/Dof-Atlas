from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.constants import KEY_SELECTED_CHARACTER, KEY_SESSION_ORDER
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.pages._character_page_impl import CharacterPage, EQUIPMENT_SLOTS


class CharacterPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def build_files(self, root: Path) -> dict[str, Path]:
        paths = {
            "profile": root / "profiles.json",
            "clients": root / "clients.json",
            "bindings": root / "network_character_bindings.json",
        }
        paths["profile"].write_text(
            json.dumps({KEY_SELECTED_CHARACTER: "character:42"}),
            encoding="utf-8",
        )
        paths["bindings"].write_text(
            json.dumps(
                {
                    "characters": {
                        "42": {
                            "name": "Alpha",
                            "pid": 111,
                            "organizer_slot": 1,
                            "class_key": "cra",
                            "source": "verified_network_identity",
                        },
                        "84": {
                            "name": "Beta",
                            "organizer_slot": 2,
                            "class_key": "pandawa",
                            "source": "verified_network_identity",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        paths["clients"].write_text(
            json.dumps(
                {
                    "clients": [
                        {"character_name": "Alpha", "pid": 111, "slot": 1}
                    ]
                }
            ),
            encoding="utf-8",
        )
        return paths

    def build_page(
        self,
        paths: dict[str, Path],
        runtime_state: CharacterRuntimeStateStore | None = None,
        *,
        skin_resolver=None,
        icon_resolver=None,
    ) -> CharacterPage:
        return CharacterPage(
            profile_path=paths["profile"],
            client_index_path=paths["clients"],
            binding_path=paths["bindings"],
            runtime_state_store=runtime_state or CharacterRuntimeStateStore(),
            skin_resolver=skin_resolver,
            icon_resolver=icon_resolver or (lambda _label: ""),
        )

    def order_keys(self, page: CharacterPage) -> list[str]:
        return [
            str(page.character_order_list.item(row).data(Qt.UserRole) or "")
            for row in range(page.character_order_list.count())
        ]

    def test_known_characters_are_kept_without_fake_stats_or_offline_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(self.build_files(Path(temporary)))
            page.refresh_from_sources("character:42")
            self.app.processEvents()

            self.assertEqual(
                [(row.key, row.label, row.connected) for row in page.characters],
                [
                    ("character:42", "Alpha", True),
                    ("character:84", "Beta", False),
                ],
            )
            self.assertEqual(page.character_name.text(), "Alpha")
            self.assertEqual(page.character_selector.count(), 2)
            self.assertEqual(page.character_selector.currentData(), "character:42")
            self.assertIn("Alpha", page.character_selector.currentText())
            self.assertIn("— succès", page.character_selector.currentText())
            self.assertEqual(page.character_order_list.count(), 2)
            self.assertEqual(self.order_keys(page), ["character:42", "character:84"])
            order_text = " ".join(
                page.character_order_list.item(row).text()
                for row in range(page.character_order_list.count())
            )
            self.assertNotIn("Slot", order_text)
            self.assertNotIn("hors ligne", order_text.casefold())
            self.assertEqual(page.character_level.text(), "")
            self.assertEqual(page.achievement_points.text(), "— points de succès")
            self.assertFalse(hasattr(page, "connection_state"))
            self.assertFalse(hasattr(page, "stat_values"))
            self.assertEqual(len(page.equipment_slots), len(EQUIPMENT_SLOTS))
            self.assertTrue(all(not button.isEnabled() for button in page.equipment_slots.values()))

            page.deleteLater()
            self.app.processEvents()

    def test_verified_runtime_profile_facts_are_rendered_for_active_character_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.build_files(Path(temporary))
            state = CharacterRuntimeStateStore()
            state.identify(
                session_id="s1",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
            state.update_verified_profile(
                "s1",
                level=199,
                achievement_points=12345,
            )
            page = self.build_page(paths, state)

            page.refresh_from_sources("character:42")
            self.assertEqual(page.character_level.text(), "Niveau 199")
            self.assertEqual(page.achievement_points.text(), "12345 points de succès")
            self.assertIn("12345 succès", page.character_selector.currentText())
            self.assertIn("12345 succès", page.character_order_list.item(0).text())

            page.refresh_from_sources("character:84")
            self.assertEqual(page.character_level.text(), "")
            self.assertEqual(page.achievement_points.text(), "— points de succès")
            self.assertIn("Beta", page.character_selector.currentText())
            self.assertIn("— succès", page.character_selector.currentText())

            page.deleteLater()
            self.app.processEvents()

    def test_runtime_profile_generation_refreshes_labels_without_rebuilding_character_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.build_files(Path(temporary))
            state = CharacterRuntimeStateStore()
            state.identify(
                session_id="s1",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
            page = self.build_page(paths, state)
            page.refresh_from_sources("character:42")
            alpha_item = page.character_order_list.item(0)
            beta_item = page.character_order_list.item(1)

            self.assertEqual(page.character_level.text(), "")
            self.assertEqual(page.achievement_points.text(), "— points de succès")

            state.update_verified_profile(
                "s1",
                level=200,
                achievement_points=24680,
            )
            page._refresh_runtime_projection()

            self.assertEqual(page.character_level.text(), "Niveau 200")
            self.assertEqual(page.achievement_points.text(), "24680 points de succès")
            self.assertIn("24680 succès", page.character_selector.currentText())
            self.assertIs(page.character_order_list.item(0), alpha_item)
            self.assertIs(page.character_order_list.item(1), beta_item)

            page.deleteLater()
            self.app.processEvents()

    def test_character_selector_requests_central_selection_without_local_persistence(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.build_files(Path(temporary))
            page = self.build_page(paths)
            page.refresh_from_sources("character:42")
            selected: list[str] = []
            page.characterSelected.connect(selected.append)

            beta_index = next(
                index
                for index in range(page.character_selector.count())
                if page.character_selector.itemData(index) == "character:84"
            )
            page.character_selector.setCurrentIndex(beta_index)
            self.app.processEvents()

            self.assertEqual(selected, ["character:84"])
            persisted = json.loads(paths["profile"].read_text(encoding="utf-8"))
            self.assertEqual(persisted[KEY_SELECTED_CHARACTER], "character:42")

            page.deleteLater()
            self.app.processEvents()

    def test_arrow_reorder_persists_and_is_reloaded_by_character_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.build_files(Path(temporary))
            page = self.build_page(paths)
            page.refresh_from_sources("character:42")
            changed: list[bool] = []
            page.characterOrderChanged.connect(lambda: changed.append(True))

            page.character_order_list.setCurrentRow(1)
            page.character_move_up.click()
            self.app.processEvents()

            self.assertEqual(self.order_keys(page), ["character:84", "character:42"])
            self.assertEqual([row.label for row in page.characters], ["Beta", "Alpha"])
            payload = json.loads(paths["profile"].read_text(encoding="utf-8"))
            self.assertEqual(payload[KEY_SESSION_ORDER], ["beta", "alpha"])
            self.assertEqual(changed, [True])

            reloaded = self.build_page(paths)
            reloaded.refresh_from_sources("character:42")
            self.assertEqual([row.label for row in reloaded.characters], ["Beta", "Alpha"])
            self.assertEqual(self.order_keys(reloaded), ["character:84", "character:42"])

            reloaded.deleteLater()
            page.deleteLater()
            self.app.processEvents()

    def test_delete_button_requires_confirmation_before_requesting_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(self.build_files(Path(temporary)))
            page.refresh_from_sources("character:42")
            deleted: list[str] = []
            page.characterDeleteRequested.connect(deleted.append)
            page.character_order_list.setCurrentRow(1)

            with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel):
                page.character_delete_button.click()
            self.assertEqual(deleted, [])

            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                page.character_delete_button.click()
            self.assertEqual(deleted, ["character:84"])

            page.deleteLater()
            self.app.processEvents()

    def test_equipment_slots_follow_dofus_dressing_positions(self):
        expected = {
            "hat": (0, 0),
            "cape": (1, 0),
            "weapon": (3, 0),
            "shield": (4, 0),
            "pet": (5, 0),
            "amulet": (0, 5),
            "ring_left": (1, 5),
            "ring_right": (2, 5),
            "belt": (3, 5),
            "boots": (4, 5),
            "dofus_1": (6, 0),
            "dofus_2": (6, 1),
            "dofus_3": (6, 2),
            "dofus_4": (6, 3),
            "dofus_5": (6, 4),
            "dofus_6": (6, 5),
        }
        self.assertEqual(
            {slot_key: (row, column) for slot_key, _label, row, column in EQUIPMENT_SLOTS},
            expected,
        )

        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(self.build_files(Path(temporary)))
            self.assertNotIn("character", page.equipment_slots)
            self.assertTrue(page.equipment_panel.isAncestorOf(page.portrait))
            page.deleteLater()
            self.app.processEvents()

    def test_real_skin_has_priority_and_class_icon_is_the_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self.build_files(root)
            skin = root / "skin.png"
            class_icon = root / "class.png"
            skin.write_bytes(b"skin")
            class_icon.write_bytes(b"class")

            page = self.build_page(
                paths,
                skin_resolver=lambda _label: skin,
                icon_resolver=lambda _label: class_icon,
            )
            self.assertEqual(page._visual_path("Alpha"), str(skin))

            page.skin_resolver = lambda _label: root / "missing-skin.png"
            self.assertEqual(page._visual_path("Alpha"), str(class_icon))

            page.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
