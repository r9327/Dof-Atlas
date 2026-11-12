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

                # Preview data stays IN THIS CI SCREENSHOT SCRIPT. No fake
                # clients/favorites are added to production or user profiles.
                demo_names = (
                    "Pandawa Witsis", "Huppermage Lokidor",
                    "Ecaflip Jokhair", "Enutrof Flooky",
                    "Sacrieur Sangrilla", "Feca Perso-6",
                    "Forgelance Perso-7", "Eniripsa Perso-8",
                )
                page.sessions = [
                    {"nom": name, "hwnd": 900001 + index,
                     "pid": 9001 + index, "_preview_only": True}
                    for index, name in enumerate(demo_names)
                ]
                page.render_sessions()
                favorite_names = ("Astrub", "Bonta", "Frigost", "Sufokia")
                page.zaap.zaaps = [
                    {"name": name, "label": name, "search": name, "x": i, "y": -i}
                    for i, name in enumerate(favorite_names)
                ]
                page.zaap.favorite_names = list(favorite_names)
                page.zaap.refresh_favorite_chips()
                page.zaap.refresh_results("")
                manifest["preview_only"] = {
                    "characters": list(demo_names),
                    "zaap_favorites": list(favorite_names),
                    "no_native_windows": True,
                    "no_user_data_changed": True,
                }
                for _ in range(5):
                    app.processEvents()
                if len(page.zaap.favorite_buttons) != 4:
                    raise RuntimeError("Four preview Zaap favorites were not rendered")
                aligned = {}
                for name, above, below in (
                    ("Macro", page.macro_mode_button, page.switch_character),
                    ("Miroir", page.mirror_mode_button, page.switch_click),
                ):
                    dx = (above.mapTo(window, QPoint()).x()
                          - below.mapTo(window, QPoint()).x())
                    aligned[name] = dx
                    if abs(dx) > 1:
                        raise RuntimeError(
                            f"{name} header misaligned from Macro grid by {dx} px"
                        )
                manifest["mode_switch_alignment_px"] = aligned
                macro_bottom = page.macro_panel.mapTo(window, QPoint()).y() + page.macro_panel.height()
                for action in (page.switch_movement, page.switch_double_click):
                    action_bottom = action.mapTo(window, QPoint()).y() + action.height()
                    if macro_bottom - action_bottom < 12:
                        raise RuntimeError(
                            "Macro bottom border clipped by final row: "
                            f"gap={macro_bottom - action_bottom}px"
                        )
                if len({panel.height() for panel in (
                    page.macro_panel, page.quick_actions_panel, page.controls_panel,
                )}) != 1:
                    raise RuntimeError("Top modules no longer share identical heights")
                if not (page.mode_switch.mapTo(window, QPoint()).y()
                        < page.switch_character.mapTo(window, QPoint()).y()):
                    raise RuntimeError("Macro/Mirror switch is not above the Macro grid")
                manifest["speed_preset_fixture"] = "normal-v2-synthetic-only"

                def capture(name: str, expected_slots: int) -> None:
                    app.processEvents()
                    if len(page.session_slot_widgets) != expected_slots:
                        raise RuntimeError(
                            f"Screenshot {name}: expected {expected_slots} slots, "
                            f"got {len(page.session_slot_widgets)}"
                        )
                    if len(page.zaap.favorite_buttons) != 4:
                        raise RuntimeError("Preview favorites missing from Zaap")
                    if page.zaap._favorite_columns != 2:
                        raise RuntimeError("Zaap favorites are not in two columns")
                    chips = [button.parentWidget() for button in page.zaap.favorite_buttons]
                    if len({chip.width() for chip in chips}) != 1:
                        raise RuntimeError("Zaap favorites have uneven widths")
                    if page.zaap.favorites_layout.itemAtPosition(
                        0, 0
                    ).widget() is not page.zaap.favorites_label:
                        raise RuntimeError("Favoris title is not in its own row")
                    if not (page.zaap.favorites_label.y() < chips[0].y()):
                        raise RuntimeError("Zaap favorites must be below the title")
                    for index, chip in enumerate(chips):
                        if page.zaap.favorites_layout.itemAtPosition(
                            1 + index // 2, index % 2
                        ).widget() is not chip:
                            raise RuntimeError("Zaap favorites are not aligned two by two")
                    if page.previous_character.icon().isNull() is False:
                        raise RuntimeError("Previous must have no decorative icon")
                    if page.next_character.icon().isNull() is False:
                        raise RuntimeError("Next must have no decorative icon")
                    if page.radial_select_button.icon().isNull():
                        raise RuntimeError("Missing pie-menu selection icon")
                    for button in (page.macro_mode_button, page.mirror_mode_button):
                        if button.icon().isNull():
                            raise RuntimeError("Macro/Miroir mode glyph missing")
                    style = page.styleSheet()
                    for selector in (
                        "QPushButton#secondaryButton:hover",
                        "QPushButton#secondaryButton:pressed",
                        "QPushButton#secondaryButton:disabled",
                        "QLineEdit#comboField",
                    ):
                        if selector not in style:
                            raise RuntimeError("Missing shared glass control state: " + selector)
                    for action, badge in (
                        (page.switch_click, page.click_button),
                        (page.switch_double_click, page.double_click_button),
                        (page.radial_select_button, page.radial_hotkey_button),
                        (page.previous_character, page.previous_character_hotkey_button),
                        (page.next_character, page.next_character_hotkey_button),
                        (page.mirror_mode_button, page.mirror_toggle_hotkey_button),
                        (page.stop_script_button, page.stop_script_hotkey_button),
                    ):
                        right = action.mapTo(window, QPoint()).x() + action.width()
                        badge_right = badge.mapTo(window, QPoint()).x() + badge.width()
                        if right - badge_right < 8:
                            raise RuntimeError(
                                f"Shortcut overflows right padding: {action.text()} "
                                f"gap={right - badge_right}px"
                            )
                    if page.stop_script_button.text() != "STOP URGENCE":
                        raise RuntimeError("Emergency stop caption changed")
                    if page.stop_script_button.icon().isNull():
                        raise RuntimeError("Warning icon missing")
                    if page.sessions_refresh_button.icon().isNull():
                        raise RuntimeError("Refresh icon missing")
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
                    ratio = slot_box.width() / max(1, zaap_box.width())
                    if not (1.90 <= ratio <= 2.10):
                        raise RuntimeError(
                            f"{name}: expected two-top-modules/one-top-module split, got "
                            f"{slot_box.width()} vs {zaap_box.width()} (ratio {ratio:.3f})"
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
                # Visually demonstrate disabled Macro actions without arming
                # or starting any native input relay in the CI fixture.
                from app.constants import KEY_ORGANIZER_MACRO_MODE
                page.profiles[KEY_ORGANIZER_MACRO_MODE] = "mirror"
                page.update_macro_mode_buttons()
                app.processEvents()
                if page._mirror_arm_active or page.macro_grid_host.isEnabled():
                    raise RuntimeError("Disarmed Mirror preview must gray out Macro")
                capture("organizer-window-1380x900-mirror-disarmed", 8)
                page.profiles[KEY_ORGANIZER_MACRO_MODE] = "macro"
                page.update_macro_mode_buttons()
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

    if len(manifest["captures"]) != 5:
        raise RuntimeError("Missing Organizer screenshot scenario")
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )


if __name__ == "__main__":
    main()
