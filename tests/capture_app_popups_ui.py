"""Capture every concrete popup/dialog family shipped by the Atlas Qt app.

The fixtures are local to this capture script. They prove that the real Qt
widgets paint; they do not certify native DOFUS integration or user data.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def capture(output: Path) -> dict[str, object]:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget

    import main as atlas_main
    from app.pages.craft_page import (
        CraftResourceDialog,
        ItemSetDialog,
        LevelingDialog,
        RouteDialog,
    )
    from app.modules.encyclopedia.views.guides_view import SolutionImageLabel
    from app.pages.dev_ui_page import DevUiPage
    from app.storage import ZaapWidget
    from app.ui.theme import atlas_stylesheet
    from app.ui.preload_popup import PreloadProgressPopup
    from app.ui.unity_skin import register_unity_fonts

    app = QApplication.instance() or QApplication([])
    register_unity_fonts()
    app.setStyleSheet(atlas_stylesheet())
    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "candidate_sha": os.environ.get("CANDIDATE_SHA", "unknown"),
        "kind": "real PySide6 popup/dialog inventory",
        "limitations": (
            "Offscreen Qt with capture-only fixtures; no native DOFUS window, "
            "game focus, user profile, network capture or gameplay validation."
        ),
        "captures": [],
    }

    def save(widget: QWidget, slug: str, family: str, fixture: str) -> None:
        record: dict[str, object] = {
            "family": family,
            "fixture": fixture,
            "status": "NOT_RUN",
        }
        try:
            widget.show()
            widget.raise_()
            for _ in range(4):
                app.processEvents()
            shot = widget.grab()
            target = output / f"{slug}.png"
            if shot.isNull() or not shot.save(str(target), "PNG"):
                raise RuntimeError("Qt screenshot was not saved")
            if target.stat().st_size < 1500:
                raise RuntimeError("Qt screenshot unexpectedly small")
            record.update(
                status="CAPTURED",
                image=target.name,
                widget=type(widget).__name__,
                size=[shot.width(), shot.height()],
            )
        except Exception as error:
            record.update(status="ERROR", error=f"{type(error).__name__}: {error}")
        finally:
            widget.hide()
            widget.deleteLater()
            app.processEvents()
        manifest["captures"].append(record)
        print("ATLAS_POPUP_CAPTURE=" + json.dumps(record, ensure_ascii=False))

    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(atlas_main, "PROFILE_FILE", Path(tmp) / "profiles.json"):
            host = QWidget()
            host.resize(900, 650)
            host.show()
            app.processEvents()

            preload = PreloadProgressPopup(host)
            preload.begin({"quests": "READY", "encyclopedia": "LOADING", "craft": "IDLE"})
            save(preload, "prechargement", "PreloadProgressPopup", "one ready, one loading, one pending")

            save(
                atlas_main.CloseActionDialog(host),
                "fermeture-application",
                "CloseActionDialog",
                "real close choices; no action triggered",
            )

            question = QMessageBox(
                QMessageBox.Question,
                "Confirmer",
                "Voulez-vous vraiment fermer la fenêtre des ressources craft ?",
                QMessageBox.Yes | QMessageBox.No,
                host,
            )
            question.setDefaultButton(QMessageBox.No)
            save(
                question,
                "confirmation-standard",
                "QMessageBox.Question",
                "real standard confirmation; no button triggered",
            )

            warning = QMessageBox(
                QMessageBox.Warning,
                "Leveling indisponible",
                "Aucun guide leveling local n'est disponible pour ce métier.",
                QMessageBox.Ok,
                host,
            )
            save(
                warning,
                "avertissement-standard",
                "QMessageBox.Warning",
                "real standard warning; no button triggered",
            )

            resources = {
                "Bois de Frêne": {"quantity": 12},
                "Fer": {"quantity": 8},
                "Ortie": {"quantity": 5},
            }
            save(
                CraftResourceDialog(resources, ["Ressource inconnue"], host),
                "craft-ressources",
                "CraftResourceDialog",
                "capture-only resource names and quantities",
            )

            item_set = {
                "name_fr": "Panoplie de démonstration",
                "items": [
                    {"name": "Coiffe", "level": 40},
                    {"name": "Cape", "level": 42},
                    {"name": "Anneau", "level": 38},
                ],
            }
            save(
                ItemSetDialog(item_set, lambda *_args: None, host),
                "craft-panoplie",
                "ItemSetDialog",
                "capture-only item set; add callback disabled",
            )

            guide = {
                "source": "atlas-local",
                "kind": "harvest",
                "entries": [
                    {"level_range": "1-20", "craft": {"name": "Ortie"}},
                    {"level_range": "20-40", "craft": {"name": "Sauge"}},
                    {"level_range": "40-60", "craft": {"name": "Trèfle"}},
                ],
            }
            save(
                LevelingDialog("Alchimiste", guide, lambda _name: None, lambda _craft: None, host),
                "craft-leveling",
                "LevelingDialog",
                "capture-only local progression markers",
            )

            save(
                RouteDialog("Mineur", {"name": "Fer"}, host),
                "craft-route-manquante",
                "RouteDialog",
                "real missing-route state; no invented map",
            )

            zaap_host = QWidget()
            zaap_host.resize(760, 180)
            zaap_layout = QVBoxLayout(zaap_host)
            zaap = ZaapWidget(lambda _message: None, parent=zaap_host)
            zaap.zaaps = [
                {"name": "Astrub", "label": "Astrub", "x": 5, "y": -18},
                {"name": "Bonta", "label": "Bonta", "x": -32, "y": -56},
                {"name": "Brâkmar", "label": "Brâkmar", "x": -26, "y": 35},
            ]
            zaap_layout.addWidget(zaap)
            zaap_host.show()
            app.processEvents()
            zaap.refresh_results("")
            zaap.suggestion_popup.setFixedSize(520, 130)
            save(
                zaap.suggestion_popup,
                "zaap-suggestions",
                "ZaapSuggestionPopup",
                "capture-only destinations; no travel action",
            )
            zaap_host.hide()
            zaap_host.deleteLater()

            image = SolutionImageLabel("", "Image de solution", host)
            pixmap = QPixmap(640, 360)
            pixmap.fill(QColor("#18202b"))
            image.source = pixmap
            image._image_load_started = True
            image.resize(520, 300)
            image.show()
            app.processEvents()
            QTest.mouseClick(image, Qt.LeftButton)
            app.processEvents()
            image_popup = image._image_popup
            if image_popup is None:
                raise RuntimeError("SolutionImageLabel did not create its real popup")
            save(
                image_popup,
                "guide-image-solution",
                "GuideImagePopup",
                "real SolutionImageLabel popup; neutral capture-only image surface",
            )

            dev_ui = DevUiPage()
            dev_ui.resize(1100, 800)
            dev_ui.show()
            app.processEvents()
            menu = dev_ui.menu_button.menu()
            if menu is None:
                raise RuntimeError("Dev UI menu missing")
            save(menu, "menu-actions", "QMenu", "real Dev UI menu and submenu actions")
            dev_ui.preview_combo.showPopup()
            app.processEvents()
            save(
                dev_ui.preview_combo.view(),
                "liste-deroulante",
                "QComboBox popup",
                "real shared AtlasComboBox popup view",
            )
            dev_ui.hide()
            dev_ui.deleteLater()

            host.hide()
            host.deleteLater()
            app.processEvents()

    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    failed = [
        entry["family"] for entry in manifest["captures"]
        if entry["status"] != "CAPTURED"
    ]
    if failed:
        raise RuntimeError("Popup captures failed: " + ", ".join(failed))
    return manifest


if __name__ == "__main__":
    capture(Path(os.environ.get("ATLAS_UI_POPUP_DIR", "artifacts/app-popups")))
