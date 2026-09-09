from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QWidget

import app.pages.lazy_zaap_widget as lazy_zaap_module
from app.pages.lazy_zaap_widget import LazyZaapWidget


class _FakeZaapWidget(QWidget):
    created = 0
    calls = []

    def __init__(
        self,
        status_callback,
        start_callback=None,
        config_update_callback=None,
        parent=None,
        show_position_controls=True,
        show_favorites=True,
    ) -> None:
        super().__init__(parent)
        type(self).created += 1
        type(self).calls.append(
            (
                status_callback,
                start_callback,
                config_update_callback,
                bool(show_position_controls),
                bool(show_favorites),
            )
        )


class LazyZaapWidgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        _FakeZaapWidget.created = 0
        _FakeZaapWidget.calls = []

    def test_hidden_proxy_does_not_construct_real_zaap(self) -> None:
        with patch.object(lazy_zaap_module, "_EagerZaapWidget", _FakeZaapWidget):
            widget = LazyZaapWidget(lambda _text: None)
            try:
                self.app.processEvents()
                self.assertFalse(widget.is_hydrated)
                self.assertEqual(_FakeZaapWidget.created, 0)
            finally:
                widget.deleteLater()
                self.app.processEvents()

    def test_first_visible_tick_hydrates_real_zaap_once(self) -> None:
        status = lambda _text: None
        start = lambda *_args: None
        update = lambda *_args: None
        with patch.object(lazy_zaap_module, "_EagerZaapWidget", _FakeZaapWidget):
            widget = LazyZaapWidget(
                status,
                start,
                update,
                show_position_controls=False,
                show_favorites=False,
            )
            try:
                widget.show()
                self.app.processEvents()
                self.app.processEvents()

                self.assertTrue(widget.is_hydrated)
                self.assertEqual(_FakeZaapWidget.created, 1)
                self.assertEqual(
                    _FakeZaapWidget.calls,
                    [(status, start, update, False, False)],
                )

                widget.hide()
                widget.show()
                self.app.processEvents()
                self.assertEqual(_FakeZaapWidget.created, 1)
            finally:
                widget.close()
                widget.deleteLater()
                self.app.processEvents()

    def test_hydration_is_cancelled_if_proxy_is_hidden_before_qt_tick(self) -> None:
        with patch.object(lazy_zaap_module, "_EagerZaapWidget", _FakeZaapWidget):
            widget = LazyZaapWidget(lambda _text: None)
            try:
                widget.show()
                widget.hide()
                self.app.processEvents()
                self.app.processEvents()

                self.assertFalse(widget.is_hydrated)
                self.assertEqual(_FakeZaapWidget.created, 0)

                widget.show()
                self.app.processEvents()
                self.app.processEvents()
                self.assertTrue(widget.is_hydrated)
                self.assertEqual(_FakeZaapWidget.created, 1)
            finally:
                widget.close()
                widget.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
