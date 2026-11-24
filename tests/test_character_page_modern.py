from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame

from app.constants import KEY_SELECTED_CHARACTER
from app.core.file_stamp import resolved_mtime_size_stamp
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.pages.character_page import CharacterPage


class ModernCharacterPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_character_cache_stamps_use_canonical_file_signature(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            self.assertEqual(CharacterPage._file_stamp(path), resolved_mtime_size_stamp(path))
            path.write_text('{"characters": []}', encoding="utf-8")
            self.assertEqual(CharacterPage._file_stamp(path), resolved_mtime_size_stamp(path))

    def test_live_character_projection_has_one_implementation(self) -> None:
        from app.pages._character_page_impl import CharacterPage as Base
        for method in ("_rebuild_character_selector", "_refresh_character_selector_runtime_labels",
                       "_render_identity", "_set_portrait"):
            self.assertIs(getattr(CharacterPage, method), getattr(Base, method))

    def test_success_point_format_preserves_grouping_and_fallback(self) -> None:
        self.assertEqual(CharacterPage._success_text(12345), "12 345")
        self.assertEqual(CharacterPage._success_text("1234567"), "1 234 567")
        self.assertEqual(CharacterPage._success_text(None), "—")
        self.assertEqual(CharacterPage._success_text("indisponible"), "indisponible")

    def test_legacy_character_page_shim_stays_retired(self) -> None:
        self.assertFalse(Path("app/pages/character_page_modern.py").exists())
        self.assertEqual(CharacterPage.__module__, "app.pages.character_page")

    def test_shell_character_resolver_keeps_canonical_path(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn(
            "from app.pages.character_page import CharacterPage as resolved",
            source,
        )
        self.assertNotIn("app.pages.character_page_modern", source)

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

            self.assertTrue(page.stats_scroll.widgetResizable())
            self.assertEqual(page.stats_scroll.frameShape(), QFrame.NoFrame)
            self.assertEqual(page.stats_scroll.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
            self.assertEqual(page.stats_scroll.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded)

            columns = page.layout().itemAt(2).layout()
            self.assertEqual(columns.count(), 2)
            self.assertIs(columns.itemAt(0).widget(), page.equipment_panel)
            self.assertIs(columns.itemAt(1).widget(), page.stats_panel)
            self.assertTrue(page.identity_panel.isHidden())
            from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX, UNITY_SPACING_PX
            geometry = UNITY_MODULE_GEOMETRY_PX["character"]
            self.assertEqual(page.layout().spacing(), UNITY_SPACING_PX["sm"])
            self.assertEqual(columns.spacing(), UNITY_SPACING_PX["md"])
            self.assertEqual(page.equipment_panel.layout().spacing(), UNITY_SPACING_PX["xs"])
            self.assertEqual(page.stats_panel.layout().spacing(), UNITY_SPACING_PX["sm"])
            for panel, key in (
                (page.equipment_panel, "equipment_panel_margins"),
                (page.stats_panel, "stats_panel_margins"),
            ):
                margin = panel.layout().contentsMargins()
                self.assertEqual(
                    (margin.left(), margin.top(), margin.right(), margin.bottom()),
                    geometry[key],
                )

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

            # The former 650 + 250 + 8 + 20 minimum exceeded the shell's
            # 900px minimum, shifting the right card beyond the viewport.
            # Preserve the 70/30 layout and the equipment/selector hierarchy
            # while proving that the actual Qt geometry fits at both sizes.
            self.assertLessEqual(page.minimumSizeHint().width(), 900)
            for width in (900, 1180):
                page.resize(width, 740)
                page.show()
                self.app.processEvents()
                left = page.equipment_panel.geometry()
                right = page.stats_panel.geometry()
                self.assertGreater(right.left(), left.right())
                self.assertLessEqual(
                    right.right() + page.layout().contentsMargins().right(),
                    page.width(),
                )
                self.assertGreaterEqual(page.character_selector.width(), 260)
                self.assertTrue(page.character_selector.isVisibleTo(page))
            page.close()
            page.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
