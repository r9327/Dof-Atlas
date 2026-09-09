from __future__ import annotations

import os


# unittest discovery imports every test module before class-level fixtures run.
# Keep one offscreen QApplication alive from package import so Qt modules and
# global signal dispatchers never precede the process-wide application object.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


QT_TEST_APPLICATION = QApplication.instance() or QApplication([])
