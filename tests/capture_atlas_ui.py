"""Capture real AtlasWindow pages on Windows Qt for UI PR #365 review.

These are screenshots of actual Qt widgets with network/preload disabled.
Missing modules, loading placeholders and incomplete data are recorded honestly.
No simulated DOFUS client or custom visual mockup is used.
"""
from __future__ import annotations

import json
import os
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tests.capture_organizer_ui import configure_capture_fonts


SCENARIOS = (
    ("00-home", "Home", None),
    ("01-organizer", "Organizer", None),
    ("02-encyclopedia-guides", "Quetes", "GUIDES"),
    ("03-encyclopedia-quests", "Quetes", "QUÊTES"),
    ("04-encyclopedia-success", "Quetes", "SUCCÈS"),
    ("05-bestiary-dungeons", "Quetes", "DONJONS"),
    ("06-bestiary-monsters", "Quetes", "MONSTRES"),
    ("07-bestiary-archmonsters", "Quetes", "ARCHIMONSTRES"),
    ("08-bestiary-wanted", "Quetes", "AVIS DE RECHERCHE"),
    ("09-tools-crafts", "Craft", None),
    ("10-tools-world-map", "Scan Monde", None),
    ("11-tools-treasure-hunt", "Chasse au trésor", None),
    ("12-tools-ochre", "Ocre", None),
    ("13-stuffs-pvm", "PvM", None),
    ("14-stuffs-pvp", "PvP", None),
    ("15-stuffs-builders", "Builders", None),
    ("16-almanax", "Almanax", None),
    ("17-settings", "Settings", None),
)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    configure_capture_fonts(app)
    dest = Path(os.environ.get("ATLAS_UI_CAPTURE_DIR", "artifacts/atlas-ui-screens"))
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {
        "candidate_sha": os.getenv("CANDIDATE_SHA", "unknown"),
        "host": "Windows GitHub runner", "renderer": "PySide6 Qt actual widgets",
        "mode": "offscreen; no DOFUS/Unity, no native game input",
        "screens": [],
        "not_captured": ["Launcher (separate process)", "Réseau (no independent shell page)",
                         "Personnage (not present as separate shell page)",
                         "popups and overlays needing runtime interactions"],
    }

    import main as atlas_main
    window = None
    with tempfile.TemporaryDirectory() as td:
        # Real widget hierarchy, isolated empty profile. No startup subprocess,
        # OS keyboard hook, tray, remote connections, or background game scanner.
        with (
            patch.object(atlas_main, "PROFILE_FILE", Path(td) / "profiles.json"),
            patch.object(atlas_main.AtlasWindow, "start_startup_preload_sequence",
                         return_value=None),
            patch.object(atlas_main.AtlasWindow, "_start_post_preload_services",
                         return_value=None),
            patch.object(atlas_main.AtlasWindow, "setup_tray", return_value=None),
        ):
            try:
                window = atlas_main.AtlasWindow()
                window.resize(1380, 900)
                window.show()
                app.processEvents()

                for slug, page_name, tab in SCENARIOS:
                    record = {"slug": slug, "page": page_name, "tab": tab,
                              "status": "NOT_RUN", "file": None}
                    try:
                        if page_name == "Quetes":
                            if tab:
                                window.open_encyclopedia_tab(tab)
                            else:
                                window.show_page("Quetes")
                        elif page_name in ("PvM", "PvP", "Builders"):
                            window.open_stuffs_tab(page_name)
                        elif page_name in ("Chasse au trésor", "Ocre"):
                            window.open_tools_tab(page_name)
                        elif page_name == "Craft":
                            window.open_tools_tab("Crafts")
                        elif page_name == "Scan Monde":
                            window.open_tools_tab("Map monde")
                        else:
                            window.show_page(page_name)
                        for _ in range(5):
                            app.processEvents()
                        expected = ("Quetes" if page_name == "Quetes" else
                                    "Equipement" if page_name in ("PvM", "PvP", "Builders") else
                                    "Craft" if page_name == "Craft" else
                                    "Scan Monde" if page_name == "Scan Monde" else
                                    f"Placeholder::{page_name}" if page_name in ("Ocre", "Chasse au trésor") else
                                    page_name)
                        active = window.active_page_name()
                        if active != expected:
                            # Some heavy page factories are lazy and do not
                            # complete navigation without local catalog data.
                            # Do not capture Home falsely labelled as a module.
                            record["status"] = "BLOCKED_NAVIGATION"
                            record["detail"] = f"expected={expected}; actual={active}"
                            continue
                        real_page = window.stack.currentWidget()
                        if real_page is None:
                            record["status"] = "NO_WIDGET"
                            continue
                        app.processEvents()
                        shot = window.grab()
                        if shot.isNull() or shot.width() < 900 or shot.height() < 600:
                            record["status"] = "EMPTY_CAPTURE"
                            continue
                        target = dest / f"{slug}.png"
                        if not shot.save(str(target), "PNG") or target.stat().st_size < 2000:
                            record["status"] = "SAVE_FAILURE"
                            continue
                        record["file"] = target.name
                        record["size"] = [shot.width(), shot.height()]
                        record["widget_class"] = type(real_page).__name__
                        record["status"] = ("PLACEHOLDER" if
                                             real_page.objectName() == "PlaceholderPage"
                                             else "CAPTURED")
                        # A lazy UI can be captured but not fully initialized;
                        # those states must never imply functional acceptance.
                        navigation_ready = getattr(real_page, "is_navigation_ready", None)
                        if callable(navigation_ready) and not navigation_ready():
                            record["status"] = "LOADING_OR_INCOMPLETE"
                    except Exception as error:
                        record["status"] = "ERROR"
                        record["detail"] = f"{type(error).__name__}: {error}"
                        record["traceback"] = traceback.format_exc(limit=5)
                    finally:
                        manifest["screens"].append(record)
                        print("ATLAS_UI_CAPTURE=" + json.dumps(record, ensure_ascii=False))
            finally:
                if window is not None:
                    window.quit_requested = True
                    window.close()
                    app.processEvents()

    path = dest / "capture-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    num = sum(record["file"] is not None for record in manifest["screens"])
    print(f"ATLAS_UI_CAPTURE_COUNT={num} of {len(SCENARIOS)}")
    if num == 0:
        raise RuntimeError("Atlas UI capture: no real module screenshot produced")


if __name__ == "__main__":
    main()
