from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.constants import KEY_SELECTED_CHARACTER
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.pages.character_page import CharacterPage


class CharacterPageStatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _files(root: Path) -> dict[str, Path]:
        paths = {
            "profile": root / "profiles.json",
            "clients": root / "clients.json",
            "bindings": root / "network_character_bindings.json",
        }
        paths["profile"].write_text(
            json.dumps({KEY_SELECTED_CHARACTER: "character:42"}),
            encoding="utf-8",
        )
        paths["clients"].write_text(
            json.dumps({"clients": [{"character_name": "Alpha", "pid": 111, "slot": 1}]}),
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
        return paths

    @staticmethod
    def _page(paths: dict[str, Path], state: CharacterRuntimeStateStore) -> CharacterPage:
        return CharacterPage(
            profile_path=paths["profile"],
            client_index_path=paths["clients"],
            binding_path=paths["bindings"],
            runtime_state_store=state,
            icon_resolver=lambda _label: "",
        )

    def test_stats_column_stays_blank_until_verified_values_exist(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = CharacterRuntimeStateStore()
            state.identify(
                session_id="s1",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
            page = self._page(self._files(Path(temporary)), state)
            page.refresh_from_sources("character:42")

            self.assertTrue(all(row.isHidden() for row in page.stat_rows.values()))
            self.assertTrue(all(not label.text() for label in page.stat_value_labels.values()))

            page.deleteLater()
            self.app.processEvents()

    def test_verified_zero_and_nonzero_stats_render_only_for_active_character(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = CharacterRuntimeStateStore()
            state.identify(
                session_id="s1",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
            state.update_verified_profile(
                "s1",
                stats=(("action_points", 11), ("critical", 0), ("strength", 350)),
            )
            page = self._page(self._files(Path(temporary)), state)
            page.refresh_from_sources("character:42")

            self.assertEqual(page.stat_value_labels["action_points"].text(), "11")
            self.assertEqual(page.stat_value_labels["critical"].text(), "0")
            self.assertEqual(page.stat_value_labels["strength"].text(), "350")
            self.assertFalse(page.stat_rows["action_points"].isHidden())
            self.assertFalse(page.stat_rows["critical"].isHidden())
            self.assertTrue(page.stat_rows["vitality"].isHidden())

            page.refresh_from_sources("character:84")
            self.assertTrue(all(row.isHidden() for row in page.stat_rows.values()))
            self.assertTrue(all(not label.text() for label in page.stat_value_labels.values()))

            page.deleteLater()
            self.app.processEvents()

    def test_runtime_generation_updates_stats_without_rebuilding_character_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = CharacterRuntimeStateStore()
            state.identify(
                session_id="s1",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
            page = self._page(self._files(Path(temporary)), state)
            page.refresh_from_sources("character:42")

            order_before = tuple(
                page.character_order_list.item(index).text()
                for index in range(page.character_order_list.count())
            )
            rows_inserted: list[bool] = []
            rows_removed: list[bool] = []
            model = page.character_order_list.model()
            model.rowsInserted.connect(lambda *_args: rows_inserted.append(True))
            model.rowsRemoved.connect(lambda *_args: rows_removed.append(True))

            state.update_verified_profile("s1", stats=(("movement_points", 6),))
            page._refresh_runtime_projection()

            self.assertEqual(page.stat_value_labels["movement_points"].text(), "6")
            self.assertFalse(page.stat_rows["movement_points"].isHidden())
            self.assertFalse(rows_inserted)
            self.assertFalse(rows_removed)
            self.assertEqual(
                tuple(
                    page.character_order_list.item(index).text()
                    for index in range(page.character_order_list.count())
                ),
                order_before,
            )

            page.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
