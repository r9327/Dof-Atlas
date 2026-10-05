from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QScrollArea

import app.pages.organizer_page as organizer
import app.pages.organizer.character_sessions as organizer_sessions
from app.pages.organizer.organizer_ui import CharacterSlotsPanel


class OrganizerLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @contextmanager
    def organizer_page(self, root: Path):
        profile = root / "client_profiles.json"
        client_index = root / "client_index.json"
        client_ini = root / "client_index.ini"
        profile.write_text("{}", encoding="utf-8")
        client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")

        with (
            patch.object(organizer, "PROFILE_FILE", profile),
            patch.object(organizer_sessions, "PROFILE_FILE", profile),
            patch.object(organizer_sessions, "CLIENT_INDEX_JSON", client_index),
            patch.object(organizer_sessions, "CLIENT_INDEX_INI", client_ini),
            patch.object(organizer_sessions, "scan_unity_sessions", return_value=[]),
            patch.object(organizer.UnityWindowEventWatcher, "start", return_value=None),
            patch.object(organizer.UnityWindowEventWatcher, "stop", return_value=None),
        ):
            page = organizer.OrganizerPage(lambda _text: None, lambda *_args: None)
            try:
                page.render_sessions()
                page.resize(900, page.sizeHint().height())
                page.show()
                self.app.processEvents()
                yield page
            finally:
                page.close()
                page.deleteLater()
                self.app.processEvents()

    def test_character_slots_panel_calculates_height_from_grid_geometry(self):
        refresh = QFrame()
        refresh.setFixedSize(32, organizer.BUTTON_HEIGHT)
        panel = CharacterSlotsPanel(
            refresh,
            slot_count=organizer.SESSION_SLOT_COUNT,
            row_height=organizer.CHARACTER_SLOT_HEIGHT,
            card_padding=organizer.CARD_PADDING,
            card_spacing=organizer.CARD_SPACING,
        )
        try:
            for index in range(organizer.SESSION_SLOT_COUNT):
                slot = QFrame()
                slot.setFixedHeight(organizer.CHARACTER_SLOT_HEIGHT)
                panel.add_slot(slot, index)

            expected_grid_height = 4 * organizer.CHARACTER_SLOT_HEIGHT + 3 * panel.vertical_spacing
            self.assertEqual(panel.row_count(), 4)
            self.assertEqual(panel.slot_grid_height(), expected_grid_height)
            self.assertEqual(panel.grid.count(), organizer.SESSION_SLOT_COUNT)
            self.assertEqual(panel.findChildren(QScrollArea), [])
            self.assertEqual(panel.sizeHint().height(), panel.calculated_height())
            self.assertEqual(panel.height(), panel.calculated_height())
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_organizer_renders_exactly_eight_visible_slots_without_internal_scroll_area(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.assertEqual(page.session_slot_count(), 8)
                self.assertEqual(len(page.session_slot_widgets), 8)
                self.assertEqual(page.sessions_panel.findChildren(QScrollArea), [])
                self.assertEqual(
                    sorted(page.sessions_panel.grid_position(index) for _widget, index in page.session_slot_widgets),
                    [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)],
                )
                self.assertGreaterEqual(page.sessions_panel.height(), page.sessions_panel.calculated_height())
                self.assertEqual(page.sessions_content.height(), page.sessions_panel.slot_grid_height())
                content_rect = page.sessions_content.rect()
                for widget, _index in page.session_slot_widgets:
                    self.assertFalse(widget.isHidden())
                    self.assertGreaterEqual(widget.geometry().top(), content_rect.top())
                    self.assertLessEqual(widget.geometry().bottom(), content_rect.bottom())

    def test_reorder_keeps_exactly_eight_slots_and_persists_detected_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                page.sessions = page.build_session_slots(
                    [
                        {"nom": "Alpha", "hwnd": 101, "pid": 1},
                        {"nom": "Beta", "hwnd": 202, "pid": 2},
                    ]
                )
                self.assertEqual(len(page.sessions), 8)
                self.assertTrue(page.move_session_to_slot(0, 1))
                page.save_session_order()
                expected = tuple(
                    page.persisted_session_order_key(session)
                    for session in page.sessions
                    if organizer.session_is_detected(session)
                )
                self.assertEqual(page.character_order_service.load_order(), expected)
                self.assertEqual(len(page.sessions), 8)


if __name__ == "__main__":
    unittest.main()
