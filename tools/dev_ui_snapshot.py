"""Capture the real Dev UI QWidget, without starting the game or CI.

Usage: python -m tools.dev_ui_snapshot --output artifacts/dev-ui
Requires the normal developer PySide6 dependencies. Assets stay local and
optional; these Qt offscreen images are not physical Windows/EXE proof.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def capture(output: Path, *, width: int = 1100, height: int = 800) -> dict[str, object]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QApplication, QVBoxLayout
    from app.pages.dev_ui_page import DevUiPage
    from app.ui.theme import atlas_stylesheet
    from app.ui.unity_palette import UNITY_WINDOW_PRESETS_PX
    from app.ui.unity_skin import UnityBackdrop, register_unity_fonts

    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    register_unity_fonts()
    app.setStyleSheet(atlas_stylesheet())
    # Use the exact backdrop widget from the real Atlas shell. A standalone
    # DevUiPage is transparent, so grabbing it alone produces a misleading
    # BLACK background on offscreen Qt instead of the Unity sky.
    backdrop = UnityBackdrop()
    host_layout = QVBoxLayout(backdrop)
    host_layout.setContentsMargins(0, 0, 0, 0)
    host_layout.setSpacing(0)
    page = DevUiPage(on_back=lambda: None, parent=backdrop)
    host_layout.addWidget(page)
    backdrop.resize(width, height)
    backdrop.show()
    app.processEvents()
    results: dict[str, object] = {
        "kind": "real Qt offscreen QWidget capture",
        "families": page.gallery_navigation.count(),
        "viewport": [width, height],
        # Identify the real source. A blue fallback must never be represented
        # as the user's missing personal Unity wallpaper.
        "background_source": (
            "local-unity-image" if backdrop.has_wallpaper
            else "unity-blue-gradient"
        ),
        "screenshots": {},
    }
    try:
        # A normal viewport capture AND the actual complete scroll content.
        viewport = output / "dev-ui-viewport.png"
        complete = output / "dev-ui-complete.png"
        if not backdrop.grab().save(str(viewport), "PNG"):
            raise RuntimeError(f"Unable to capture {viewport}")
        body = page.gallery_scroll.widget()
        if body is None:
            raise RuntimeError("Dev UI scroll content is missing")
        # The full-height capture is actual Qt scroll content painted over
        # the same UnityBackdrop, not a designed screenshot or a flat fill.
        full_backdrop = UnityBackdrop()
        try:
            full_backdrop.resize(body.size())
            full_pixmap = full_backdrop.grab()
            painter = QPainter(full_pixmap)
            try:
                body.render(painter, QPoint(0, 0))
            finally:
                painter.end()
            if not full_pixmap.save(str(complete), "PNG"):
                raise RuntimeError(f"Unable to capture {complete}")
        finally:
            full_backdrop.deleteLater()
        results["screenshots"] = {
            "viewport": str(viewport),
            "complete": str(complete),
        }

        # Real Qt layouts at all four reference window sizes. Each image
        # captures the shared sizing section after a genuine window resize;
        # no scaled mockup or fabricated Windows/DPI evidence is used.
        results["viewport_profiles"] = {}
        baseline_positions = None
        for preset, (viewport_width, viewport_height) in UNITY_WINDOW_PRESETS_PX.items():
            selector_index = page.preview_window_selector.findData(preset)
            if selector_index < 0:
                raise RuntimeError(f"Missing Dev UI window preset: {preset}")
            page.preview_window_selector.setCurrentIndex(selector_index)
            backdrop.resize(viewport_width, viewport_height)
            app.processEvents()
            metrics_y = page.gallery_family_widgets["metrics"].mapTo(
                page.gallery_scroll.widget(), QPoint(0, 0)
            ).y()
            page.gallery_scroll.verticalScrollBar().setValue(max(0, metrics_y - 8))
            app.processEvents()
            horizontal_overflow = page.gallery_scroll.horizontalScrollBar().maximum()
            actual_size = [backdrop.width(), backdrop.height()]
            if actual_size != [viewport_width, viewport_height]:
                raise RuntimeError(
                    f"Wrong actual Qt size in {preset}: {actual_size}, "
                    f"expected {[viewport_width, viewport_height]}"
                )
            if page.preview_responsive_host.width() > viewport_width:
                raise RuntimeError(
                    f"Responsive preview exceeds the real {preset} viewport"
                )
            profile_image = output / f"dev-ui-responsive-{preset}.png"
            if not backdrop.grab().save(str(profile_image), "PNG"):
                raise RuntimeError(f"Unable to capture real Qt viewport: {preset}")
            results["screenshots"][f"responsive_{preset}"] = str(profile_image)
            positions = [
                list(page.preview_responsive_grid.getItemPosition(
                    page.preview_responsive_grid.indexOf(card)
                ))
                for card in page.preview_responsive_cards
            ]
            if baseline_positions is None:
                baseline_positions = positions
            if positions != baseline_positions or page.preview_responsive_columns != 3:
                raise RuntimeError(
                    f"Structural panels changed position in {preset}: {positions}"
                )
            results["viewport_profiles"][preset] = {
                "size": actual_size,
                "preview_width": page.preview_responsive_host.width(),
                "columns": page.preview_responsive_columns,
                "module_positions": positions,
                "module_gap": page.preview_responsive_grid.spacing(),
                "horizontal_scroll_max": horizontal_overflow,
            }
            if horizontal_overflow:
                raise RuntimeError(
                    f"Unexpected horizontal scroll in {preset}: {horizontal_overflow}"
                )
        # Return to the requested viewport before the full-page stitching.
        page.preview_window_selector.setCurrentIndex(
            page.preview_window_selector.findData("standard")
        )
        backdrop.resize(width, height)
        page.gallery_scroll.verticalScrollBar().setValue(0)
        app.processEvents()

        # Record scroll evidence *before* expanding the real Qt window.
        results["horizontal_scroll_max"] = page.gallery_scroll.horizontalScrollBar().maximum()
        results["vertical_scroll_max"] = page.gallery_scroll.verticalScrollBar().maximum()

        # Capture the complete real page, including its breadcrumb and title.
        # The old 'complete' image was only the inner scrolling widget and
        # silently omitted the page header from three-part screenshots.
        scroll_y = page.gallery_scroll.mapTo(backdrop, QPoint(0, 0)).y()
        page_height = scroll_y + body.height() + 24
        if page_height > 16000:
            raise RuntimeError(f"Dev UI full-page height is unreasonable: {page_height}")
        backdrop.resize(width, page_height)
        app.processEvents()
        full_page = backdrop.grab()
        if full_page.isNull():
            raise RuntimeError("Unable to capture full Qt page")
        whole = output / "dev-ui-page-complete.png"
        if not full_page.save(str(whole), "PNG"):
            raise RuntimeError(f"Unable to save {whole}")
        results["screenshots"]["page_complete"] = str(whole)
        results["page_complete_size"] = [full_page.width(), full_page.height()]
        # Three real QPixmap crops, independently zoomable on mobile.
        for number in range(3):
            top = full_page.height() * number // 3
            bottom = full_page.height() * (number + 1) // 3
            part = output / f"dev-ui-partie-{number + 1}.png"
            if not full_page.copy(0, top, full_page.width(), bottom - top).save(
                str(part), "PNG"
            ):
                raise RuntimeError(f"Unable to save {part}")
            results["screenshots"][f"part_{number + 1}"] = str(part)
        # Six real Qt captures of the *current* canonical Guide hierarchy.
        # Never reopen the deleted Route/Sommaire controls.
        backdrop.resize(width, height)
        app.processEvents()
        combinations = (
            ("classique", False, False, False, "À préparer"),
            ("progression-globale", True, False, False, "À préparer"),
            ("personnages", False, False, True, "À préparer"),
            ("preparation", True, True, False, "À préparer"),
            ("prerequis", True, True, False, "Prérequis"),
            ("preparation-personnages", True, True, True, "À préparer"),
        )
        for label, global_open, prep_open, people, selected_tab in combinations:
            page.preview_header_controls["Progression globale"].setChecked(global_open)
            page.preview_header_controls["Préparation"].setChecked(prep_open)
            page.preview_header_controls["Personnages"].setChecked(people)
            tab = page.preview_header_preparation_tabs[selected_tab]
            tab.click()
            app.processEvents()
            # Place the real Guide header near the top, preserving the
            # active nested menus in the capture.
            header_y = page.preview_compact_header.mapTo(
                page.gallery_scroll.widget(), QPoint(0, 0)
            ).y()
            page.gallery_scroll.verticalScrollBar().setValue(max(0, header_y - 12))
            app.processEvents()
            file = output / f"dev-ui-entete-{label}.png"
            if not backdrop.grab().save(str(file), "PNG"):
                raise RuntimeError(f"Unable to capture {file}")
            results["screenshots"][f"header_{label.replace('-', '_')}"] = str(file)
            if label == "preparation":
                results["screenshots"]["header_preparation"] = str(file)
        for key in ("Préparation", "Progression globale", "Personnages"):
            page.preview_header_controls[key].setChecked(False)
        app.processEvents()
        # Restore the user-sized viewport before opening native popups.
        backdrop.resize(width, height)
        app.processEvents()

        # Screenshot the actual expanded Qt family dropdown, not a simulated
        # painted list. This proves the popup rows match the approved palette.
        page.gallery_navigation.showPopup()
        app.processEvents()
        try:
            family_popup_file = output / "dev-ui-family-dropdown.png"
            dropdown_view = page.gallery_navigation.view()
            # An uncapped family popup is a genuine visual regression even if
            # setMaxVisibleItems(8) was called: Qt native styles may ignore it.
            row_height = dropdown_view.sizeHintForRow(0)
            row_limit = page.gallery_navigation.maxVisibleItems()
            if row_height > 0 and dropdown_view.height() > row_height * row_limit + 24:
                raise RuntimeError(
                    f"Dev UI dropdown is too tall: {dropdown_view.height()} px "
                    f"for {row_limit} rows of {row_height} px"
                )
            results["family_dropdown_height"] = dropdown_view.height()
            if not dropdown_view.grab().save(str(family_popup_file), "PNG"):
                raise RuntimeError(f"Unable to capture {family_popup_file}")
            results["screenshots"]["family_dropdown"] = str(family_popup_file)
        finally:
            page.gallery_navigation.hidePopup()
            app.processEvents()

        # The real popup is a separate Qt surface, not pasted into a mockup.
        page.dialog_button.click()
        app.processEvents()
        popup = page._preview_dialog
        if popup is not None and popup.isVisible():
            dialog_file = output / "dev-ui-dialog.png"
            if not popup.grab().save(str(dialog_file), "PNG"):
                raise RuntimeError(f"Unable to capture {dialog_file}")
            results["screenshots"]["dialog"] = str(dialog_file)
            popup.reject()
    finally:
        backdrop.close()
        page.deleteLater()
        backdrop.deleteLater()
    (output / "dev-ui-capture.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/dev-ui"))
    parser.add_argument("--width", type=int, default=1100)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args()
    if args.width < 900 or args.height < 600:
        parser.error("Minimum capture window: 900 x 600 px")
    print(json.dumps(
        capture(args.output, width=args.width, height=args.height),
        indent=2, ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
