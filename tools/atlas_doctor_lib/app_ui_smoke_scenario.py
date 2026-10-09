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
    # Real QLabel text assignment from a decoded isolated JSON payload.
    # The temporary file lives in ignored Doctor runtime state, not app data.
    import json
    from tempfile import NamedTemporaryFile
    runtime = observer.root / ".ai" / "runtime" / "atlas_doctor"
    runtime.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                            dir=runtime, delete=False) as handle:
        handle.write(json.dumps({"section": "Doctor UI binding smoke"}))
        fixture = Path(handle.name)
    try:
        payload, token = observer.read_json(fixture.relative_to(observer.root))
        if not observer.bind_json_label_text(token, page.section_label, payload["section"]):
            raise AssertionError("Real EquipmentPage QLabel binding was not observed")
        if page.section_label.text() != payload["section"]:
            raise AssertionError("Qt label did not retain decoded section text")
    finally:
        fixture.unlink(missing_ok=True)
    # Preserve the normal EquipmentPage section state before disposal.
    page.set_section(page.section)
    observer.snapshot_watches(label="equipment-created")
    observer.snapshot_qt_objects(label="equipment-created")
    # No .show(), event loop or navigation: preserve the application's lazy rules.
    delete(page)
    if isValid(page):
        raise AssertionError("EquipmentPage C++ object still valid after delete")
    observer.snapshot_watches(label="equipment-destroyed")
    observer.snapshot_qt_objects(label="equipment-destroyed")
    if not app:
        raise AssertionError("QApplication unavailable")


if __name__ == "__main__":
    main()
