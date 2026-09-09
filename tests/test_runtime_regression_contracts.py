from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

import app.storage as storage
from main import AtlasWindow, find_lookup_item


class RuntimeRegressionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_storage_read_json_backs_up_corrupt_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.json"
            path.write_text("{not-json", encoding="utf-8")

            payload = storage.read_json(path, {"safe": True})

            self.assertEqual(payload, {"safe": True})
            backups = list(path.parent.glob("profiles.json.corrupt.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "{not-json")

    def test_zaap_callback_typeerror_is_not_retried(self) -> None:
        calls: list[tuple[object, ...]] = []

        def callback(search, position, ratios) -> None:
            calls.append((search, position, ratios))
            raise TypeError("bug inside callback")

        widget = storage.ZaapWidget(lambda _text: None, callback)
        try:
            with self.assertRaisesRegex(TypeError, "bug inside callback"):
                widget.launch_zaap(
                    {
                        "label": "Cité d'Astrub [5,-18]",
                        "search": "Cité d'Astrub",
                        "posX": 5,
                        "posY": -18,
                    }
                )
            self.assertEqual(len(calls), 1)
        finally:
            # Reset only this widget. A global processEvents() here also runs
            # unrelated callbacks left by earlier Qt tests and can make the
            # Windows runner fail before unittest reports its result.
            widget.reset_launch_guard()
            widget.close()
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)

    def test_zaap_legacy_zero_argument_callback_still_runs_once(self) -> None:
        calls: list[str] = []

        def callback() -> None:
            calls.append("called")

        widget = storage.ZaapWidget(lambda _text: None, callback)
        try:
            widget.launch_zaap({"label": "Bonta [-32,-56]", "search": "Bonta"})
            self.assertEqual(calls, ["called"])
        finally:
            widget.reset_launch_guard()
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)

    def test_lookup_refuses_ambiguous_partial_match(self) -> None:
        oak = {"name": "Bois de Chêne"}
        soft_oak = {"name": "Bois de Chêne Mou"}
        index = {
            "bois_de_chene": oak,
            "bois_de_chene_mou": soft_oak,
        }

        self.assertIs(find_lookup_item("Bois de Chêne", index), oak)
        self.assertIsNone(find_lookup_item("Chêne", index))

    def test_emergency_stop_does_not_fake_hook_badge_off(self) -> None:
        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
        method = source.split("    def stop_runtime(self) -> None:", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('self.runtime.emergency_stop("bouton stop")', method)
        self.assertNotIn("update_runtime_badge(False)", method)

    def test_main_explicitly_enables_dpi_before_qapplication(self) -> None:
        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
        main_body = source.split("def main() -> int:", 1)[1]
        self.assertLess(main_body.index("enable_dpi_awareness()"), main_body.index("QApplication(sys.argv)"))


if __name__ == "__main__":
    unittest.main()
