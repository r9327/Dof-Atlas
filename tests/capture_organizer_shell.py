"""Screenshots of the exact real AtlasWindow Organizer QWidget on Windows CI.

No game client, native hook, background preload or invented application pixels.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tests.capture_organizer_ui import configure_capture_fonts


def main() -> None:
    app = QApplication.instance() or QApplication([])
    configure_capture_fonts(app)
    destination = Path(os.getenv("ATLAS_ORGANIZER_SHELL_DIR", "artifacts/organizer-shell"))
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "candidate_sha": os.getenv("CANDIDATE_SHA", "unknown"),
        "system": "Windows GitHub Actions; actual AtlasWindow/PySide6 Qt",
        "limitations": "synthetic offscreen UI; no DOFUS Unity, native hook or game focus",
        "captures": [],
    }

    import main as atlas_main

    window = None
    with tempfile.TemporaryDirectory() as td:
        with (
            patch.object(atlas_main, "PROFILE_FILE", Path(td) / "profiles.json"),
            patch.object(atlas_main.AtlasWindow, "start_startup_preload_sequence", return_value=None),
            patch.object(atlas_main.AtlasWindow, "_start_post_preload_services", return_value=None),
            patch.object(atlas_main.AtlasWindow, "setup_tray", return_value=None),
        ):
            try:
                window = atlas_main.AtlasWindow()
                window.resize(1380, 900)
                window.show()
                window.show_page("Organizer")
                for _ in range(5):
                    app.processEvents()
                page = window.page_widgets.get("Organizer")
                if page is None or type(page).__name__ != "OrganizerPage":
                    raise RuntimeError("OrganizerPage real widget did not load")

                def capture(name: str, expected_slots: int) -> None:
                    app.processEvents()
                    if len(page.session_slot_widgets) != expected_slots:
                        raise RuntimeError(
                            f"Screenshot {name}: expected {expected_slots} slots, "
                            f"got {len(page.session_slot_widgets)}"
                        )
                    shot = window.grab()
                    file = destination / (name + ".png")
                    if shot.isNull() or not shot.save(str(file), "PNG") or file.stat().st_size < 2000:
                        raise RuntimeError(f"Screenshot {name} missing or invalid")
                    record = {
                        "name": name, "file": file.name,
                        "pixels": [shot.width(), shot.height()],
                        "slots": len(page.session_slot_widgets),
                        "scroll_maximum": page.organizer_scroll.verticalScrollBar().maximum(),
                    }
                    manifest["captures"].append(record)
                    print("ORGANIZER_SHELL_CAPTURE=" + json.dumps(record))

                capture("organizer-window-1380x900", 8)
                page.render_sessions()
                capture("organizer-window-1380x900-8slots", 8)
                window.resize(1000, 740)
                for _ in range(5):
                    app.processEvents()
                capture("organizer-window-1000x740-8slots", 8)
                page.organizer_scroll.verticalScrollBar().setValue(
                    page.organizer_scroll.verticalScrollBar().maximum()
                )
                capture("organizer-window-1000x740-bottom", 8)
            finally:
                if window is not None:
                    window.quit_requested = True
                    window.close()
                    app.processEvents()

    if len(manifest["captures"]) != 4:
        raise RuntimeError("Missing Organizer screenshot scenario")
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )


if __name__ == "__main__":
    main()
