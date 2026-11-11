"""Render the actual OrganizerPage QWidget on Windows CI, without DOFUS sessions.

This is a Qt offscreen capture of the real application widget, not a mockup
and not evidence that native Unity input works.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from app.ui.theme import atlas_stylesheet
from tests.test_organizer_layout import OrganizerLayoutTests


def main() -> None:
    app = QApplication.instance() or QApplication([])
    # Hosted Windows offscreen Qt can resolve the multi-family Lexend QSS
    # declaration to a missing font and render every glyph as a tofu square.
    # Select the installed Segoe UI fallback explicitly for the capture only.
    style = atlas_stylesheet().replace(
        'font-family: "Lexend", "Segoe UI", Arial;',
        'font-family: "Segoe UI";',
    )
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(style)
    print(f"ORGANIZER_CAPTURE_FONT_AVAILABLE={'Segoe UI' in QFontDatabase.families()}")
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
        print("ORGANIZER_CAPTURE_CONTEXT=actual Qt page, Windows runner, no DOFUS clients")


if __name__ == "__main__":
    main()
