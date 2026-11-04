from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.storage import ZaapWidget


class OrganizerZaapPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_widget(self, callback) -> ZaapWidget:
        with (
            patch("app.storage.load_zaap_index", return_value=[]),
            patch("app.storage.read_zaap_click_locked", return_value=True),
            patch("app.storage.read_zaap_click_position", return_value=(0, 0)),
        ):
            widget = ZaapWidget(
                status_callback=Mock(),
                start_callback=callback,
                show_position_controls=False,
                show_favorites=False,
            )
        widget.show()
        widget.suggestion_popup.addItem("Zaap test")
        widget.suggestion_popup.show()
        self.app.processEvents()
        self.assertTrue(widget.suggestion_popup.isVisible())
        return widget

    def test_selection_closes_popup_before_runtime_callback(self) -> None:
        observed = []

        def launch(*args):
            observed.append((widget.suggestion_popup.isVisible(), args[0]))

        widget = self.make_widget(launch)
        try:
            widget.launch_zaap({"label": "Zaap test", "posX": 1, "posY": 2})
            self.assertEqual(observed, [(False, "/zaap 1,2")])
            self.assertFalse(widget.suggestion_popup.isVisible())
        finally:
            widget.close()


    def test_scheduled_zaap_popup_reopen_is_cancelled_after_selection(self) -> None:
        widget = self.make_widget(Mock(return_value=True))
        try:
            widget.search_input.setText("Zaap test")
            # FocusIn/MousePress can enqueue show at 0 ms before itemPressed
            # closes the popup. It must not resurrect on the next Qt cycle.
            widget._schedule_owned_callback(0, widget.show_suggestions)
            widget.launch_zaap({"label": "Zaap test", "posX": 1, "posY": 2})
            self.app.processEvents()
            self.assertFalse(widget.suggestion_popup.isVisible())
            self.assertTrue(widget._suppress_autoshow_after_launch)
            widget.show_suggestions()
            self.assertFalse(widget.suggestion_popup.isVisible())
        finally:
            widget.close()

    def test_new_zaap_search_can_reopen_popup_after_completed_selection(self) -> None:
        widget = self.make_widget(Mock(return_value=True))
        try:
            widget.launch_zaap({"label": "Zaap test", "posX": 1, "posY": 2})
            self.app.processEvents()
            self.assertTrue(widget._suppress_autoshow_after_launch)
            with patch.object(widget, "search", return_value=[
                {"label": "Zaap suivant", "posX": 3, "posY": 4},
            ]):
                widget.refresh_results("Zaap suivant")
            self.assertFalse(widget._suppress_autoshow_after_launch)
            widget.show_suggestions()
            self.assertTrue(widget.suggestion_popup.isVisible())
        finally:
            widget.close()

    def test_zaap_reports_runtime_acceptance_without_claiming_completion(self) -> None:
        for accepted in (True, False, None):
            with self.subTest(accepted=accepted):
                launcher = Mock(return_value=accepted)
                widget = self.make_widget(launcher)
                try:
                    widget.launch_zaap({"label": "Astrub", "posX": 1, "posY": 2})
                    launcher.assert_called_once()
                    self.assertFalse(widget.suggestion_popup.isVisible())
                    message = widget.status_callback.call_args.args[0]
                    if accepted is True:
                        self.assertIn("en cours", message)
                        self.assertNotIn("lance:", message)
                    elif accepted is False:
                        self.assertIn("non lancé", message)
                    else:
                        self.assertIn("non confirmé", message)
                finally:
                    widget.close()

    def test_zaap_refused_by_runtime_closes_popup_before_reporting_failure(self) -> None:
        observed = []
        def reject(*_args):
            observed.append(widget.suggestion_popup.isVisible())
            return False
        widget = self.make_widget(reject)
        try:
            widget.launch_zaap({"label": "Astrub", "posX": 1, "posY": 2})
            self.assertEqual(observed, [False])
            self.assertIn("non lancé", widget.status_callback.call_args.args[0])
        finally:
            widget.close()

    def test_zaap_start_callback_exception_reports_failure_without_qt_crash(self) -> None:
        callback = Mock(side_effect=RuntimeError("runtime failed"))
        widget = self.make_widget(callback)
        try:
            with patch("app.storage.LOGGER.exception") as log:
                widget.launch_zaap({"label": "Astrub", "posX": 1, "posY": 2})
            log.assert_called_once()
            self.assertFalse(widget.suggestion_popup.isVisible())
            self.assertIn("non lancé", widget.status_callback.call_args.args[0])
        finally:
            widget.close()

    def test_zaap_missing_start_callback_never_reports_success(self) -> None:
        widget = self.make_widget(None)
        try:
            widget.launch_zaap({"label": "Astrub", "posX": 1, "posY": 2})
            self.assertFalse(widget.suggestion_popup.isVisible())
            self.assertIn("indisponible", widget.status_callback.call_args.args[0])
        finally:
            widget.close()

    def test_zaap_legacy_no_argument_launcher_keeps_compatibility(self) -> None:
        launcher = Mock()
        widget = self.make_widget(launcher)
        try:
            # Legacy Organizer callbacks with no arguments are deliberately
            # still accepted by invoke_compatible_callback.
            def older():
                launcher()
            widget.start_callback = older
            widget.launch_zaap({"label": "Astrub", "posX": 1, "posY": 2})
            launcher.assert_called_once_with()
            self.assertIn("non confirmé", widget.status_callback.call_args.args[0])
        finally:
            widget.close()

    def test_runtime_zaap_preserves_async_spawn_boolean(self) -> None:
        from app.core.runtime_state import AtlasRuntime

        runtime = Mock()
        for accepted in (False, True):
            with self.subTest(accepted=accepted):
                runtime.zaap.run_async.return_value = accepted
                with patch("app.core.runtime_state.load_settings",
                           return_value=runtime.settings):
                    self.assertIs(
                        AtlasRuntime.launch_zaap(runtime, "/zaap 1,2"),
                        accepted,
                    )
                runtime.zaap.run_async.assert_called_with(
                    "/zaap 1,2", click_position=None, click_ratios=None,
                )

    def test_invalid_destination_closes_popup_without_dispatch(self) -> None:
        launcher = Mock()
        widget = self.make_widget(launcher)
        try:
            widget.launch_zaap({"label": "Sans coordonnées"})
            self.assertFalse(widget.suggestion_popup.isVisible())
            launcher.assert_not_called()
        finally:
            widget.close()


if __name__ == "__main__":
    unittest.main()
