from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

# UI fixtures exercise the real offline importer in an isolated writable cache.
# Raw game inputs and images retain their repository paths.
_VALIDATION_TEMP = None
if not os.environ.get("DOFUS_ATLAS_VALIDATION_DATA_DIR"):
    _VALIDATION_TEMP = tempfile.TemporaryDirectory(prefix="atlas-test-local-data-")
    os.environ["DOFUS_ATLAS_VALIDATION_DATA_DIR"] = _VALIDATION_TEMP.name
_validation_local = Path(os.environ["DOFUS_ATLAS_VALIDATION_DATA_DIR"]) / "local"
_validation_local.mkdir(parents=True, exist_ok=True)
_zaap_seed = Path(__file__).resolve().parents[1] / "data" / "local" / "zaaps.json"
if _zaap_seed.is_file() and not (_validation_local / "zaaps.json").exists():
    shutil.copyfile(_zaap_seed, _validation_local / "zaaps.json")


def _cleanup_validation_data() -> None:
    if _VALIDATION_TEMP is not None:
        module = sys.modules.get("local_dofus_data.compatibility_adapter")
        adapter = getattr(module, "_ADAPTER", None)
        if adapter is not None:
            adapter.close()
        _VALIDATION_TEMP.cleanup()


atexit.register(_cleanup_validation_data)


# unittest discovery imports every test module before class-level fixtures run.
# Keep one offscreen QApplication alive from package import so Qt modules and
# global signal dispatchers never precede the process-wide application object.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


QT_TEST_APPLICATION = QApplication.instance() or QApplication([])
