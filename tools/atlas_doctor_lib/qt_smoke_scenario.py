from __future__ import annotations

"""Explicit opt-in real PySide6 scenario for Doctor; no app startup hooks."""
from tools.atlas_doctor_lib.runtime_observation import active_observer


def main() -> None:
    from PySide6.QtCore import QCoreApplication, QObject, Signal, Slot, QThread
    from shiboken6 import delete

    observer = active_observer()
    if observer is None:
        raise RuntimeError("Run via Doctor runtime-trace; no implicit Qt monitoring.")

    class Sender(QObject):
        fired = Signal(int)

    class Receiver(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.received: list[int] = []

        @Slot(int)
        def receive(self, value: int) -> None:
            self.received.append(value)

    app = QCoreApplication.instance() or QCoreApplication([])
    sender = Sender()
    receiver = Receiver()
    if not observer.watch_qt_destroyed(sender, label="qt-smoke-sender"):
        raise RuntimeError("QObject.destroyed instrumentation unavailable")
    callback = observer.wrap_qt_slot(receiver.receive)
    observer.connect_qt_signal(sender.fired, callback)
    sender.fired.emit(73)
    if receiver.received != [73]:
        raise AssertionError("Qt signal was not delivered to the real Python slot")
    delete(sender)  # deterministic QObject destruction in this isolated scenario

    class ShortThread(QThread):
        def run(self) -> None:
            # Actual PySide6 QThread lifecycle without network or catalog data.
            return

    thread = ShortThread()
    if not observer.watch_qt_thread(thread, label="qt-smoke-worker"):
        raise AssertionError("Qt worker signals unavailable")
    thread.start()
    if not thread.wait(3000):
        raise AssertionError("Short Qt worker did not finish")
    app.processEvents()  # Deliver any queued notifications to the main thread.
    delete(thread)
    if not app:
        raise AssertionError("QCoreApplication unavailable")


if __name__ == "__main__":
    main()
