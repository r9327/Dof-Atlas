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

from PySide6.QtCore import QPoint
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
                # Show one explicit v2 choice in a synthetic capture; avoid
                # misrepresenting legacy Classique as a selected Normal preset.
                from app.constants import KEY_SCRIPT_SPEED, KEY_SCRIPT_SPEED_SCHEMA
                page.profiles[KEY_SCRIPT_SPEED_SCHEMA] = 2
                page.profiles[KEY_SCRIPT_SPEED] = "normal"
                page.update_script_speed_buttons()
                app.processEvents()
                aligned = {}
                for name, above, below in (
                    ("Macro", page.macro_mode_button, page.switch_character),
                    ("Miroir", page.mirror_mode_button, page.switch_click),
                ):
                    dx = (above.mapTo(window, QPoint()).x()
                          - below.mapTo(window, QPoint()).x())
                    aligned[name] = dx
                    if abs(dx) > 2:
                        raise RuntimeError(
                            f"{name} header misaligned from Macro grid by {dx} px"
                        )
                manifest["mode_header_alignment_px"] = aligned
                manifest["speed_preset_fixture"] = "normal-v2-synthetic-only"

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
                    # Verify the actual horizontal placement on the real
                    # AtlasWindow: slots first, then the narrow Zaap sidebar.
                    slot_box = page.sessions_panel
                    zaap_box = page.zaap_panel
                    slot_x = slot_box.mapTo(window, QPoint()).x()
                    zaap_x = zaap_box.mapTo(window, QPoint()).x()
                    if zaap_x < slot_x + slot_box.width():
                        raise RuntimeError(f"{name}: Zaap overlaps the character slots")
                    if not (slot_box.width() > zaap_box.width() * 3):
                        raise RuntimeError(
                            f"{name}: Zaap is not a slim sidebar: "
                            f"{slot_box.width()} vs {zaap_box.width()}"
                        )
                    if zaap_box.height() != slot_box.height():
                        raise RuntimeError(f"{name}: Zaap and slots heights differ")
                    if page.organizer_scroll.horizontalScrollBar().maximum() != 0:
                        raise RuntimeError(f"{name}: horizontal overflow in Organizer")
                    record = {
                        "name": name, "file": file.name,
                        "bottom_widths": [slot_box.width(), zaap_box.width()],
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
