from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.ui.theme import atlas_stylesheet
from tools.ui_lab.window import UiLabWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Dofus Atlas UI Lab")
    app.setStyleSheet(atlas_stylesheet())

    window = UiLabWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
