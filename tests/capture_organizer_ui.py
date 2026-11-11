"""Render the actual OrganizerPage QWidget on Windows CI, without DOFUS sessions.

This is a Qt offscreen capture of the real application widget, not a mockup
and not evidence that native Unity input works.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from app.ui.theme import atlas_stylesheet
from tests.test_organizer_layout import OrganizerLayoutTests


def main() -> None:
    app = QApplication.instance() or QApplication([])
    # Do not create false all-square evidence if the offscreen plugin cannot
    # resolve the Unity multi-family QSS. Use an actually available Qt family.
    families = QFontDatabase.families()
    print(f"ORGANIZER_CAPTURE_FONT_FAMILIES={families[:60]!r}")
    for candidate in ("C:/Windows/Fonts/arial.ttf",
                      "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.isfile(candidate):
            font_id = QFontDatabase.addApplicationFont(candidate)
            print(f"ORGANIZER_REGISTER_FONT={candidate}:{font_id}")
    families = QFontDatabase.families()
    selected = next((family for family in ("Arial", "Segoe UI", "Tahoma",
                     "DejaVu Sans", "Liberation Sans") if family in families),
                    QFont().family())
    if selected not in families:
        raise RuntimeError(f"No working font on Windows Qt runner: {families!r}")
    print(f"ORGANIZER_CAPTURE_SELECTED_FONT={selected}")
    style = re.sub(r"font-family:\\s*[^;]+;", f'font-family: "{selected}";',
                   atlas_stylesheet())
    app.setFont(QFont(selected, 10))
    app.setStyleSheet(style)
    OrganizerLayoutTests.app = app
    fixture = OrganizerLayoutTests(
        "test_session_ids_refuse_fractional_boolean_and_corrupt_native_values"
    )
    destination = Path(os.environ.get("ATLAS_ORGANIZER_SCREENSHOT_DIR", "artifacts/organizer-ui"))
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, fixture.organizer_page(Path(tmp)) as page:
        page.resize(1100, max(850, page.sizeHint().height()))
        page.show()
        app.processEvents()
        capture = page.grab()
        if capture.isNull() or capture.width() < 800 or capture.height() < 500:
            raise RuntimeError("Organizer Qt capture is empty or too small")
        target = destination / "organizer-real-qt-windows-no-sessions.png"
        if not capture.save(str(target), "PNG") or target.stat().st_size < 2000:
            raise RuntimeError("Organizer PNG was not written correctly")
        print(f"ORGANIZER_SCREENSHOT={target.as_posix()}")
        print(f"ORGANIZER_CAPTURE_PIXELS={capture.width()}x{capture.height()}")
        from tools.atlas_doctor_lib.doctor_ui_qt import glyph_legibility_probe
        probe = glyph_legibility_probe(page, screenshots=[target])
        print(f"ORGANIZER_CAPTURE_FONT_CHECK={probe['status']}:{probe['reason']}")
        if probe["status"] != "PASS":
            raise RuntimeError("Organizer Qt capture rejected: missing or square glyphs")
        print("ORGANIZER_CAPTURE_CONTEXT=actual Qt page, Windows runner, no DOFUS clients")


if __name__ == "__main__":
    main()
