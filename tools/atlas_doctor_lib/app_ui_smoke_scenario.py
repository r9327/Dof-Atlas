from __future__ import annotations

"""Opt-in real Dofus Atlas equipment QWidget scenario.

Run only via Doctor runtime-trace; no Huzounet URL is opened and no Chromium
process is created. Does not instrument application startup or other modules.
"""
from tools.atlas_doctor_lib.runtime_observation import active_observer


def main() -> None:
    observer = active_observer()
    if observer is None:
        raise RuntimeError("Use Doctor runtime-trace for this opt-in scenario")
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete, isValid
    from app.pages.equipment_page import EquipmentPage

    app = QApplication.instance() or QApplication([])
    statuses: list[str] = []
    page = EquipmentPage(statuses.append)
    if not observer.watch(page, label="equipment-page", kind="qwidget"):
        raise AssertionError("EquipmentPage weakref watch failed")
    if not observer.watch_qt_destroyed(page, label="equipment-page"):
        raise AssertionError("EquipmentPage QObject.destroyed watch failed")
    page.set_section("Equipment Doctor smoke")
    if page.section != "Equipment Doctor smoke" or page.section_label.text() != page.section:
        raise AssertionError("EquipmentPage section did not update")
    if page.web_loaded or getattr(page, "_legacy_view", None) is not None:
        raise AssertionError("Unexpected embedded WebEngine activity")
    observer.snapshot_watches(label="equipment-created")
    # No .show(), event loop or navigation: preserve the application's lazy rules.
    delete(page)
    if isValid(page):
        raise AssertionError("EquipmentPage C++ object still valid after delete")
    observer.snapshot_watches(label="equipment-destroyed")
    if not app:
        raise AssertionError("QApplication unavailable")


if __name__ == "__main__":
    main()
