"""Capture real AtlasWindow module pages using the shared UI theme.

This fixture disables startup I/O and profile writes. A screenshot proves
that a genuine Qt page was painted; it is NOT a content or gameplay PASS.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# Name, displayed filename, widget type, data-readiness note.
SCENARIOS = (
    ("Home", "accueil", "HomePage", "no-game-preview"),
    ("Settings", "parametres", "QWidget", "no-game-preview"),
    ("Almanax", "almanax", "QWidget", "not-implemented"),
    ("Craft", "craft", "CraftPage", "deferred-local-data"),
    ("Equipement", "stuffs", "EquipmentPage", "no-user-equipment"),
    ("Scan Monde", "carte", "WorldScanPanel", "deferred-cartography"),
    ("Quetes", "encyclopedie", "EncyclopediaPage", "deferred-quest-providers"),
)


def capture(output: Path) -> dict[str, object]:
    from PySide6.QtWidgets import QApplication
    from app.ui.unity_skin import register_unity_fonts
    import main as atlas_main

    app = QApplication.instance() or QApplication([])
    register_unity_fonts()
    output.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {
        "candidate_sha": os.environ.get("CANDIDATE_SHA", "unknown"),
        "kind": "Windows Qt offscreen full AtlasWindow shell",
        "limitations": (
            "No game process, native focus, profiles, login, live quests or local "
            "Unity wallpaper. Deferred modules do not certify real data rendering."
        ),
        "screenshots": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        with (
            patch.object(atlas_main, "PROFILE_FILE", Path(tmp) / "profiles.json"),
            patch.object(atlas_main.AtlasWindow, "start_startup_preload_sequence", return_value=None),
            patch.object(atlas_main.AtlasWindow, "_start_post_preload_services", return_value=None),
            patch.object(atlas_main.AtlasWindow, "setup_tray", return_value=None),
            patch.object(atlas_main.AtlasWindow, "start_preload", return_value=None),
        ):
            window = atlas_main.AtlasWindow()
            try:
                window.resize(1380, 900)
                window.show()
                for name, slug, expected, readiness in SCENARIOS:
                    record: dict[str, object] = {
                        "module": name, "readiness": readiness, "status": "NOT_RUN"
                    }
                    try:
                        if name in window.page_factories:
                            window.ensure_page_loaded(name)
                        page = window.page_widgets.get(name)
                        if page is None:
                            raise RuntimeError("module missing from AtlasWindow")
                        if expected != "QWidget" and type(page).__name__ != expected:
                            raise RuntimeError(
                                f"wrong widget: {type(page).__name__} instead of {expected}"
                            )
                        window.switch_to_page(name)
                        for _ in range(3):
                            app.processEvents()
                        if window.stack.currentWidget() is not page:
                            raise RuntimeError("screenshot not showing requested module")
                        if not app.styleSheet() or page.styleSheet():
                            raise RuntimeError("page overrides the shared Unity stylesheet")
                        path = output / f"{slug}-atlas-window.png"
                        shot = window.grab()
                        if shot.isNull() or not shot.save(str(path), "PNG"):
                            raise RuntimeError("Qt screenshot was not saved")
                        if path.stat().st_size < 2000:
                            raise RuntimeError("Qt screenshot unexpectedly small")
                        record.update(
                            status="CAPTURED", image=path.name,
                            widget=type(page).__name__,
                            size=[shot.width(), shot.height()],
                        )
                    except Exception as error:
                        # Do not turn an unrendered page into a false PASS.
                        record.update(status="ERROR", error=f"{type(error).__name__}: {error}")
                    result["screenshots"].append(record)
                    print("ATLAS_MODULE_CAPTURE=" + json.dumps(record, ensure_ascii=False))
            finally:
                window.quit_requested = True
                window.close()
                app.processEvents()
    (output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    required = {"Home", "Settings", "Almanax", "Craft", "Equipement"}
    failed = [
        entry["module"] for entry in result["screenshots"]
        if entry["module"] in required and entry["status"] != "CAPTURED"
    ]
    if failed:
        raise RuntimeError("Real shell captures failed: " + ", ".join(failed))
    return result


if __name__ == "__main__":
    capture(Path(os.environ.get("ATLAS_UI_SHELL_DIR", "artifacts/app-shell")))
