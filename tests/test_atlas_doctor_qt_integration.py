from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.runtime_observation import RuntimeObserver


@unittest.skipUnless(importlib.util.find_spec("PySide6") is not None,
                     "Qt for Python not installed on this runner")
class DoctorRealQtSignalTests(unittest.TestCase):
    def test_real_qt_signal_reaches_slot_and_records_registration(self):
        from PySide6.QtCore import QCoreApplication, QObject, Signal, Slot

        class Sender(QObject):
            fired = Signal(int)

        class Receiver(QObject):
            def __init__(self):
                super().__init__()
                self.values: list[int] = []

            @Slot(int)
            def record(self, value: int):
                self.values.append(value)

        app = QCoreApplication.instance() or QCoreApplication([])
        sender, receiver = Sender(), Receiver()
        root = Path(__file__).resolve().parents[1]
        observer = RuntimeObserver(root, max_events=1000)
        with observer:
            observer.connect_qt_signal(sender.fired, receiver.record)
            sender.fired.emit(73)

        self.assertEqual(receiver.values, [73])
        report = observer.report()
        source = "tests/test_atlas_doctor_qt_integration.py"
        matching = [event for event in report["events"]
                    if event["type"] == "qt_signal_connect_returned"
                    and event.get("source") == source and event.get("target") == source]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["confidence"],
                         "CONNECT_RETURNED_NOT_CALLBACK_INVOKED")
        self.assertFalse(report["truncated"])
        self.assertTrue(app)


if __name__ == "__main__":
    unittest.main()
