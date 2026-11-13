"""Tests for the optional local Unity skin; no packaged or licensed assets implied."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from app.ui import unity_skin
from app.ui.unity_skin import (
    UNITY_PALETTE, UnityBackdrop, unity_enabled, unity_skin_stylesheet,
    sprite_icon_path, wallpaper_path,
)


class UnitySkinTests(unittest.TestCase):
    def test_atlas_button_variants_and_navigation_use_one_style_switch(self) -> None:
        from app.ui.components import AtlasButton

        button = AtlasButton("Voir", variant="secondary")
        try:
            self.assertEqual(button.objectName(), "SecondaryButton")
            self.assertEqual(button.minimumHeight(), 24)
            button.set_variant("primary")
            self.assertEqual(button.objectName(), "PrimaryActionButton")
            button.set_style_name("TopNavButton")
            self.assertEqual(button.objectName(), "TopNavButton")
            button.set_style_name("TopNavButtonActive")
            self.assertEqual(button.objectName(), "TopNavButtonActive")
            button.set_style_name("TopNavButtonActive")
            self.assertEqual(button.objectName(), "TopNavButtonActive")
            button.set_style_name("TopNavButton")
            self.assertEqual(button.objectName(), "TopNavButton")
            button.set_variant("navigation_active")
            self.assertEqual(button.objectName(), "TopNavButtonActive")
            button.set_variant("navigation")
            self.assertEqual(button.objectName(), "TopNavButton")
            with self.assertRaises(ValueError):
                button.set_variant("not-a-variant")
            self.assertEqual(button.objectName(), "TopNavButton")
        finally:
            button.deleteLater()

    def test_advanced_form_surfaces_match_unity_palette_and_states(self) -> None:
        style = unity_skin_stylesheet()
        fields = "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox"
        self.assertIn(fields, style)
        self.assertIn("QDateEdit, QTimeEdit, QTextEdit, QPlainTextEdit", style)
        self.assertIn("background: rgba(33, 49, 84, 0.96)", style)
        self.assertIn("QLineEdit:read-only, QPlainTextEdit:read-only", style)
        self.assertIn("QLineEdit:disabled, QComboBox:disabled", style)
        self.assertNotIn("rgba(20, 29, 55, 0.96)", style)

    def test_shared_buttons_never_inherit_gold_or_neon_sprite_borders(self) -> None:
        """Optional Unity assets cannot silently replace semantic button colors."""
        with patch.object(unity_skin, "_sprite_url", side_effect=lambda name: f"/fake/{name}"):
            css = unity_skin_stylesheet()
        self.assertNotIn("btn_yellow2_", css)
        self.assertNotIn("bg_tab_selected_normal", css)
        self.assertIn("padding: 5px 12px; min-height: 24px;", css)
        for name in ("PrimaryActionButton", "primaryButton",
                     "SecondaryButton", "secondaryButton"):
            self.assertNotIn(f"QPushButton#{name} {{ border: 8px", css)
        # Dedicated game-style actions can retain their own sprite treatment.
        self.assertIn("btn_green_normal.png", css)

    def test_panel_toggle_common_state_and_accessibility(self) -> None:
        from app.ui.components import AtlasPanelToggle

        toggle = AtlasPanelToggle()
        try:
            self.assertEqual(toggle.objectName(), "GuideRightPanelToggle")
            self.assertTrue(bool(toggle.focusPolicy() & Qt.TabFocus))
            self.assertIs(toggle.property("collapsed"), False)
            self.assertEqual(toggle.text(), "›")
            self.assertEqual(toggle.toolTip(), toggle.accessibleName())
            self.assertIn("Masquer", toggle.toolTip())

            toggle.set_collapsed(True)
            self.assertIs(toggle.property("collapsed"), True)
            self.assertEqual(toggle.text(), "‹")
            self.assertEqual(toggle.toolTip(), toggle.accessibleName())
            self.assertIn("Réafficher", toggle.toolTip())

            # The host, not this UI class, owns navigation and click effects.
            requested = []
            toggle.clicked.connect(lambda: requested.append("toggle"))
            toggle.click()
            self.assertEqual(requested, ["toggle"])
            self.assertIs(toggle.property("collapsed"), True)
            toggle.set_collapsed(True)
            self.assertIs(toggle.property("collapsed"), True)
            toggle.set_collapsed(False)
            self.assertEqual(toggle.text(), "›")
            self.assertIs(toggle.property("collapsed"), False)
        finally:
            toggle.deleteLater()

    def test_unity_skin_radius_overrides_follow_shared_metrics(self) -> None:
        from app.ui.unity_palette import UNITY_RADII

        style = unity_skin_stylesheet({
            "RADIUS_XS": "14px",
            "RADIUS_SM": "16px",
            "RADIUS_MD": "18px",
        })
        self.assertIn("border-radius: 16px;", style)
        self.assertIn("border-radius: 18px;", style)
        self.assertIn("border-radius: 14px;", style)
        self.assertEqual(UNITY_RADII["RADIUS_SM"], "6px")
        self.assertEqual(UNITY_RADII["RADIUS_MD"], "8px")

    def test_shared_unity_widget_families_follow_single_palette(self) -> None:
        overrides = {
            "TEXT": "#102030",
            "TEXT_SOFT": "#304050",
            "BORDER": "#405060",
            "BORDER_CARD": "#506070",
            "BORDER_STRONG": "#607080",
            "PANEL_ACTIVE": "#708090",
            "GREEN_BORDER": "#8192A3",
            "BORDER_SOFT": "#405060",
        }
        with patch.dict(UNITY_PALETTE, overrides):
            style = unity_skin_stylesheet()

        for selector, expected_rules in (
            ("QGroupBox, QTabWidget::pane {", ("color: #102030;", "border: 1px solid #405060;")),
            ("QTableWidget {", ("color: #102030;", "selection-background-color: #708090;")),
            ("QHeaderView::section {", ("color: #102030;", "border-bottom: 1px solid #405060;")),
            ("QToolTip {", ("color: #102030;", "border: 1px solid #607080;")),
            ("QProgressBar {", ("color: #102030;", "border: 1px solid #405060;")),
            ("QFrame#GuideFeaturedCard {", ("border: 1px solid #8192A3;",)),
            ("QDialog#AtlasDialog, QMenu {", ("color: #102030;", "border: 1px solid #506070;")),
            ("QPlainTextEdit {", ("color: #102030;", "border: 1px solid #405060;")),
        ):
            with self.subTest(selector=selector):
                section = style.rsplit(selector, 1)[1].split("}", 1)[0]
                for expected in expected_rules:
                    self.assertIn(expected, section)
        self.assertIn("border: 2px solid #304050; border-image: none;", style)

    def test_common_field_and_table_focus_uses_the_same_unity_border(self) -> None:
        style = unity_skin_stylesheet({"TEXT_SOFT": "#102030"})
        focus_rule = next(
            line for line in style.splitlines()
            if "QDoubleSpinBox:focus" in line
        )
        for selector in (
            "QSpinBox:focus", "QDoubleSpinBox:focus", "QPlainTextEdit:focus",
            "QTextEdit:focus", "QTableWidget:focus", "QTreeWidget:focus",
        ):
            self.assertIn(selector, focus_rule)
        self.assertIn("border: 2px solid #102030;", focus_rule)

    def test_unity_glass_surfaces_obey_global_color_overrides(self) -> None:
        """A palette change must reach cards, panels, lists, tabs and controls."""
        original = dict(UNITY_PALETTE)
        style = unity_skin_stylesheet({
            "PANEL": "#112233",
            "PANEL_2": "#223344",
            "LIST_SURFACE": "#334455",
            "NAV_SURFACE": "#445566",
            "SCROLL_SURFACE": "#556677",
            "TOOLTIP_SURFACE": "#667788",
            "FIELD_SURFACE": "#778899",
        })
        for expected in (
            "rgba(17, 34, 51, 0.88)",  # cards and Guide panels
            "rgba(17, 34, 51, 0.78)",  # shared tab/group panes
            "rgba(34, 51, 68, 0.88)",  # alternate list rows
            "rgba(51, 68, 85, 0.92)",  # lists and tables
            "rgba(51, 68, 85, 0.85)",  # shared progress
            "rgba(68, 85, 102, 0.93)",  # common tabs
            "rgba(68, 85, 102, 0.98)",  # dialogs and menus
            "rgba(85, 102, 119, 0.35)",  # scroll surfaces
            "background: #667788;",  # tooltips
            "rgba(119, 136, 153, 0.96)",  # shared text fields and combos
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, style)
        self.assertEqual(UNITY_PALETTE, original)

    def test_guide_special_surfaces_obey_canonical_unity_overrides(self) -> None:
        original = dict(UNITY_PALETTE)
        style = unity_skin_stylesheet({
            "GUIDE_COMPACT_SURFACE": "#102030",
            "GUIDE_SUMMARY_TOP": "#203040",
            "GUIDE_SUMMARY_BOTTOM": "#304050",
            "GUIDE_PREPARATION_ROW": "#405060",
            "GUIDE_PREPARATION_ROW_BORDER": "#506070",
            "GUIDE_COPY_HOVER": "#607080",
            "GUIDE_MANUAL_NAV_SURFACE": "#708090",
        })
        for expected in (
            "rgba(16, 32, 48, 0.93)",
            "rgba(32, 48, 64, 0.97)",
            "rgba(48, 64, 80, 0.97)",
            "rgba(64, 80, 96, 0.92)",
            "rgba(80, 96, 112, 0.65)",
            "rgba(96, 112, 128, 0.30)",
            "rgba(112, 128, 144, 0.94)",
        ):
            with self.subTest(value=expected):
                self.assertIn(expected, style)
        self.assertEqual(UNITY_PALETTE, original)

    def test_preview_palette_does_not_mutate_global_unity_colors(self) -> None:
        original = dict(UNITY_PALETTE)
        preview = unity_skin_stylesheet({
            "TEXT": "#142536",
            "BORDER_CARD": "#253647",
        })
        self.assertIn("QDialog#AtlasDialog, QMenu {", preview)
        self.assertIn("color: #142536; border: 1px solid #253647;", preview)
        self.assertEqual(UNITY_PALETTE, original)

    def test_guide_controls_render_the_canonical_palette_values(self) -> None:
        # Legacy role is an alias to the common BORDER by default, but
        # explicit per-role previews are still supported.
        self.assertIn(
            "border-top: 1px solid #010203;",
            unity_skin_stylesheet({"GUIDE_NAV_BORDER": "#010203"}),
        )

    def test_unity_only_theme_even_with_stale_legacy_override(self) -> None:
        for choice in ("", "atlas", "legacy", "dofus_unity"):
            with self.subTest(choice=choice), patch.dict(os.environ, {"ATLAS_THEME": choice}):
                self.assertTrue(unity_enabled())
                self.assertIn("AtlasUnityBackdrop", unity_skin_stylesheet())

    def test_personal_assets_persist_independently_of_theme_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            personal = Path(directory)
            sprites = personal / "sprites"
            sprites.mkdir()
            (personal / ".enabled").write_text("personal local theme\\n", encoding="utf-8")
            (personal / "background_selection_clean.png").write_bytes(b"personal")
            icon = sprites / "Assets_UI_Themes_Figma_menuIcons_1x_guide-png.png"
            icon.write_bytes(b"sprite")
            with patch.object(unity_skin, "_PERSONAL_ASSETS", personal):
                with patch.dict(os.environ, {"ATLAS_THEME": ""}):
                    self.assertTrue(unity_enabled())
                    self.assertEqual(wallpaper_path(), personal / "background_selection_clean.png")
                    self.assertEqual(sprite_icon_path("guide"), icon)
                with patch.dict(os.environ, {"ATLAS_THEME": "atlas"}):
                    self.assertTrue(unity_enabled())
                    self.assertEqual(wallpaper_path(), personal / "background_selection_clean.png")
            (personal / ".enabled").unlink()
            with patch.object(unity_skin, "_PERSONAL_ASSETS", personal):
                with patch.dict(os.environ, {"ATLAS_THEME": ""}):
                    self.assertTrue(unity_enabled())
                    self.assertEqual(wallpaper_path(), personal / "background_selection_clean.png")

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_atlas_brand_icon_uses_splash_transparency(self) -> None:
        from app.ui import components

        with tempfile.TemporaryDirectory() as directory:
            logo = Path(directory) / "brand.png"
            image = QImage(9, 9, QImage.Format_RGBA8888)
            image.fill(QColor(18, 18, 18, 255))
            image.setPixelColor(4, 4, QColor(255, 180, 30, 255))
            self.assertTrue(image.save(str(logo)))
            old = components._APPLICATION_ICON
            try:
                with patch.object(components, "APP_ICON_PATH", logo):
                    components._APPLICATION_ICON = None
                    pixmap = components.atlas_application_icon().pixmap(9, 9).toImage()
                    self.assertEqual(pixmap.pixelColor(0, 0).alpha(), 0)
                    self.assertEqual(pixmap.pixelColor(4, 4).alpha(), 255)
            finally:
                components._APPLICATION_ICON = old

    def test_unity_icons_have_white_vector_fallback_when_sprites_missing(self) -> None:
        """Missing personal textures never result in empty developer icons."""
        from app.ui.unity_palette import UNITY_ICON_NAMES, UNITY_SIZES_PX

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            with patch.object(unity_skin, "_ASSETS", path), patch.object(
                unity_skin, "_PERSONAL_ASSETS", path / "no-theme"
            ):
                unity_skin.unity_ui_icon.cache_clear()
                try:
                    for name in UNITY_ICON_NAMES:
                        for role in ("icon_small", "icon_large", "icon_xlarge"):
                            size = UNITY_SIZES_PX[role]
                            pix = unity_skin.unity_ui_icon(name, size).pixmap(size, size)
                            self.assertFalse(pix.isNull(), (name, size))
                            self.assertTrue(pix.toImage().hasAlphaChannel())
                            self.assertTrue(any(
                                pix.toImage().pixelColor(x, y).alpha() > 0
                                for x in range(size) for y in range(size)
                            ), (name, size))
                    with self.assertRaises(ValueError):
                        unity_skin.unity_ui_icon("unknown")
                    with self.assertRaises(ValueError):
                        unity_skin.unity_ui_icon("guide", 100)
                finally:
                    unity_skin.unity_ui_icon.cache_clear()

    def test_opaque_sprite_tiles_fall_back_to_transparent_white_icons(self) -> None:
        from app.ui.unity_skin import unity_ui_icon

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "icon.png"
            square = QImage(24, 24, QImage.Format_ARGB32)
            square.fill(QColor(0, 0, 0, 255))
            square.setPixelColor(12, 12, QColor(255, 255, 255, 255))
            self.assertTrue(square.save(str(path)))
            with patch.object(unity_skin, "sprite_icon_path", return_value=path):
                unity_ui_icon.cache_clear()
                try:
                    pix = unity_ui_icon("guide", 24).pixmap(24, 24).toImage()
                    self.assertEqual(pix.pixelColor(0, 0).alpha(), 0)
                finally:
                    unity_ui_icon.cache_clear()
            square.fill(Qt.transparent)
            square.setPixelColor(12, 12, QColor(255, 255, 255, 255))
            self.assertTrue(square.save(str(path)))
            with patch.object(unity_skin, "sprite_icon_path", return_value=path):
                unity_ui_icon.cache_clear()
                try:
                    pix = unity_ui_icon("guide", 24).pixmap(24, 24).toImage()
                    self.assertEqual(pix.pixelColor(0, 0).alpha(), 0)
                    self.assertGreater(pix.pixelColor(12, 12).alpha(), 0)
                    self.assertEqual(
                        pix.pixelColor(12, 12).name(),
                        QColor(UNITY_PALETTE["TEXT"]).name(),
                    )
                finally:
                    unity_ui_icon.cache_clear()
            # Bright parts remain legible white, while the original dark
            # contour becomes a transparent cut-out rather than a white blob.
            square.fill(Qt.transparent)
            square.setPixelColor(12, 12, QColor(UNITY_PALETTE["GREEN"]))
            square.setPixelColor(12, 11, QColor(8, 8, 8))
            self.assertTrue(square.save(str(path)))
            with patch.object(unity_skin, "sprite_icon_path", return_value=path):
                unity_ui_icon.cache_clear()
                try:
                    pix = unity_ui_icon("guide", 24).pixmap(24, 24).toImage()
                    self.assertGreater(
                        pix.pixelColor(12, 12).alpha(),
                        pix.pixelColor(12, 11).alpha(),
                    )
                    self.assertEqual(
                        pix.pixelColor(12, 12).name(),
                        QColor(UNITY_PALETTE["TEXT"]).name(),
                    )
                finally:
                    unity_ui_icon.cache_clear()

    def test_unknown_icon_does_not_escape_local_theme_directory(self) -> None:
        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            self.assertIsNone(sprite_icon_path("not-an-allowlisted-icon"))

    def test_real_local_sprites_have_all_states_and_single_background(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset_dir = Path(directory)
            sprites = asset_dir / "sprites"
            sprites.mkdir()
            source = QImage(48, 24, QImage.Format_ARGB32)
            source.fill(0xff5262a1)
            self.assertTrue(source.save(str(asset_dir / "background_selection_clean.png")))
            for state in ("normal", "over", "pressed", "disabled"):
                self.assertTrue(source.save(str(sprites / f"btn_green_{state}.png")))
            self.assertTrue(source.save(str(sprites / "Assets_UI_Themes_Figma_menuIcons_1x_guide-png.png")))
            with patch.object(unity_skin, "_ASSETS", asset_dir), patch.object(
                unity_skin, "_PERSONAL_ASSETS", asset_dir / "absent-personal"
            ), patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
                style = unity_skin_stylesheet()
                for state in ("normal", "over", "pressed", "disabled"):
                    self.assertIn(f"btn_green_{state}.png", style)
                self.assertIn("border-image:", style)
                self.assertIn("rgba(27, 39, 70, 0.88)", style)
                self.assertIn("QWidget#EncyclopediaPage", style)
                self.assertIn("QWidget#organizerPage", style)
                self.assertIn("QPushButton:focus", style)
                self.assertTrue(sprite_icon_path("guide").is_file())
                backdrop = UnityBackdrop()
                backdrop.resize(130, 90)
                self.assertFalse(backdrop._pixmap.isNull())
                backdrop.show()
                self.app.processEvents()
                # Widget paints from one parent pixmap, not one per child/page.
                self.assertEqual(backdrop._pixmap.size().width(), 48)
                backdrop.close()
                backdrop.deleteLater()
                self.app.processEvents()

    def test_public_backdrop_shows_stars_without_personal_unity_assets(self) -> None:
        # One deterministic field is painted on the shared shell, without a
        # bundled game texture, timer, animation or per-module stylesheet.
        with tempfile.TemporaryDirectory() as directory:
            absent = Path(directory) / "absent"
            with patch.object(unity_skin, "_PERSONAL_ASSETS", absent), patch.object(
                unity_skin, "_ASSETS", absent
            ):
                backdrop = UnityBackdrop()
                backdrop.resize(600, 380)
                self.assertTrue(backdrop._pixmap.isNull())
                backdrop.show()
                try:
                    self.app.processEvents()
                    with_stars = backdrop.grab().toImage()
                    with patch.object(unity_skin, "_PUBLIC_SKY_STARS", ()):
                        without_stars = backdrop.grab().toImage()
                    # First deterministic star sits at about (19, 28) px.
                    self.assertTrue(any(
                        with_stars.pixelColor(x, y) != without_stars.pixelColor(x, y)
                        for x in range(16, 23) for y in range(25, 33)
                    ))
                finally:
                    backdrop.close()
                    backdrop.deleteLater()
                    self.app.processEvents()

    def test_shell_home_margins_reveal_shared_fallback_stars(self) -> None:
        # Compose the real shared shell selectors without running the heavy
        # AtlasWindow bootstrap/preload in an offscreen Qt test runner.
        from PySide6.QtWidgets import QStackedWidget, QVBoxLayout
        from app.ui.theme import atlas_stylesheet

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(unity_skin, "_PERSONAL_ASSETS", Path(directory) / "personal"),
            patch.object(unity_skin, "_ASSETS", Path(directory) / "assets"),
            patch.object(unity_skin, "_PUBLIC_SKY_STARS", ((0.012, 0.55, 7.0, 255),)),
        ):
            backdrop = UnityBackdrop()
            backdrop.setStyleSheet(atlas_stylesheet())
            layout = QVBoxLayout(backdrop)
            layout.setContentsMargins(0, 0, 0, 0)
            stack = QStackedWidget(backdrop)
            stack.setObjectName("AtlasUnityStack")
            home = QWidget(stack)
            home.setObjectName("HomePage")
            home.setProperty("atlasUnityPage", True)
            stack.addWidget(home)
            layout.addWidget(stack)
            backdrop.resize(600, 380)
            try:
                backdrop.show()
                self.app.processEvents()
                self.assertTrue(backdrop._pixmap.isNull())
                self.assertEqual(stack.currentWidget(), home)
                with_star = backdrop.grab().toImage()
                with patch.object(unity_skin, "_PUBLIC_SKY_STARS", ()):
                    backdrop.update()
                    self.app.processEvents()
                    without_star = backdrop.grab().toImage()
                # The margin is in the stacked Home page, not a data card.
                self.assertNotEqual(
                    with_star.pixelColor(12, 210),
                    without_star.pixelColor(12, 210),
                )
            finally:
                backdrop.close()
                backdrop.deleteLater()
                self.app.processEvents()

    def test_starry_backdrop_remains_visible_under_all_shared_shell_roots(self) -> None:
        """A page-specific opaque QSS must not erase Unity stars after navigation."""
        from PySide6.QtWidgets import QStackedWidget, QVBoxLayout
        from app.ui.theme import atlas_stylesheet

        # Both already-mounted and lazy-loaded pages use these actual root
        # object names / the same atlasUnityPage dynamic property.
        roots = (
            "HomePage", "EncyclopediaPage", "GuidesView", "GuidesHomePage",
            "organizerPage", "worldScanPage", "CraftPage", "EquipmentPage",
            "PlaceholderPage", "SettingsPage", "DevUiPage",
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(unity_skin, "_PERSONAL_ASSETS", Path(directory) / "personal"),
            patch.object(unity_skin, "_ASSETS", Path(directory) / "assets"),
            patch.object(unity_skin, "_PUBLIC_SKY_STARS", ((0.012, 0.55, 7.0, 255),)),
        ):
            backdrop = UnityBackdrop()
            backdrop.setStyleSheet(atlas_stylesheet())
            layout = QVBoxLayout(backdrop)
            layout.setContentsMargins(0, 0, 0, 0)
            stack = QStackedWidget(backdrop)
            stack.setObjectName("AtlasUnityStack")
            pages = []
            for name in roots:
                widget = QWidget(stack)
                widget.setObjectName(name)
                widget.setProperty("atlasUnityPage", True)
                stack.addWidget(widget)
                pages.append(widget)
            layout.addWidget(stack)
            backdrop.resize(600, 380)
            try:
                backdrop.show()
                self.app.processEvents()
                self.assertTrue(backdrop._pixmap.isNull())
                for name, page in zip(roots, pages):
                    with self.subTest(page=name):
                        stack.setCurrentWidget(page)
                        backdrop.update()
                        self.app.processEvents()
                        with_star = backdrop.grab().toImage().pixelColor(12, 210)
                        with patch.object(unity_skin, "_PUBLIC_SKY_STARS", ()):
                            backdrop.update()
                            self.app.processEvents()
                            without_star = backdrop.grab().toImage().pixelColor(12, 210)
                        self.assertNotEqual(with_star, without_star)
            finally:
                backdrop.close()
                backdrop.deleteLater()
                self.app.processEvents()

    def test_clean_wallpaper_has_priority_without_mutating_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset_dir = Path(directory)
            original = asset_dir / "background_selection_original.png"
            cleaned = asset_dir / "background_selection_clean.png"
            original.write_bytes(b"unchanged-original")
            with patch.object(unity_skin, "_ASSETS", asset_dir), patch.object(
                unity_skin, "_PERSONAL_ASSETS", asset_dir / "absent-personal"
            ):
                with patch.dict(os.environ, {"ATLAS_THEME": "atlas"}):
                    self.assertIsNone(wallpaper_path())
                with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
                    self.assertIsNone(wallpaper_path())
                    cleaned.write_bytes(b"approved-derived-image")
                    self.assertEqual(wallpaper_path(), cleaned)
                    self.assertEqual(original.read_bytes(), b"unchanged-original")
                    cleaned.unlink()
                    self.assertIsNone(wallpaper_path())

    def test_global_widget_families_and_focus_stay_themable(self) -> None:
        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            style = unity_skin_stylesheet()
        for selector in (
            "QTreeWidget", "QTabWidget::pane", "QToolTip", "QProgressBar",
            "QTableView", "QPlainTextEdit", "QHeaderView::section",
        ):
            self.assertIn(selector, style)
        self.assertIn("rgba(27, 39, 70, 0.78)", style)
        self.assertIn('QWidget[atlasUnityPage="true"]', style)
        self.assertIn("QPushButton#FeaturedGuideOpen:focus", style)
        for root_name in ("GuidesView", "GuidesHomePage", "GuidesHomeContent", "GuidesDetailPage"):
            self.assertIn(f"QWidget#{root_name}", style)
        self.assertIn("QListView#GuidesHomeDofusGrid", style)
        self.assertIn("QWidget#GuideLibraryResults", style)
        self.assertIn("border-image: none", style)
        self.assertIn("selection-color: #F1F6FB", style)
        # This final rule must not be masked by the normal/hover sprite rule.
        self.assertEqual(
            style.rfind("QPushButton:focus"),
            style.rfind("QPushButton:focus, QToolButton:focus"),
        )
        with patch.dict(os.environ, {"ATLAS_THEME": "atlas"}):
            self.assertIn("AtlasUnityBackdrop", unity_skin_stylesheet())

    def test_tabs_are_palette_owned_without_gold_selected_artwork(self) -> None:
        sprite = "Assets_UI_Themes_darkStone_common_bg_tab_selected_normal-png.png"
        with patch.object(
            unity_skin, "_sprite_url",
            side_effect=lambda name: "/tmp/gold-tab.png" if name == sprite else None,
        ):
            style = unity_skin_stylesheet()
        self.assertNotIn("gold-tab.png", style)
        self.assertIn("padding: 5px 12px; min-height: 24px;", style)
        self.assertIn("QTabBar::tab:selected", style)

    def test_encyclopedia_tab_sizes_do_not_change_on_selection(self) -> None:
        from app.ui.theme import atlas_stylesheet

        tabs = QTabWidget()
        tabs.setObjectName("EncyclopediaTabs")
        tabs.tabBar().setExpanding(False)
        for label in ("Quêtes", "Succès", "Guides", "Donjons"):
            tabs.addTab(QWidget(), label)
        tabs.setStyleSheet(atlas_stylesheet())
        tabs.resize(800, 260)
        tabs.show()
        try:
            self.app.processEvents()
            bar = tabs.tabBar()
            expected = tuple(bar.tabRect(i).size() for i in range(bar.count()))
            for index in range(bar.count()):
                tabs.setCurrentIndex(index)
                self.app.processEvents()
                self.assertEqual(
                    tuple(bar.tabRect(i).size() for i in range(bar.count())),
                    expected,
                )
        finally:
            tabs.close()
            tabs.deleteLater()

    def test_top_navigation_hover_menu_is_keyboard_accessible_and_clickable(self) -> None:
        from PySide6.QtWidgets import QMenu
        from main import HoverMenuButton

        button = HoverMenuButton("Outils")
        menu = QMenu(button)
        activated: list[str] = []
        first = menu.addAction("Crafts", lambda: activated.append("Crafts"))
        menu.addAction("Map monde", lambda: activated.append("Map monde"))
        button.set_hover_menu(menu)
        button.resize(150, 36)
        button.show()
        try:
            self.app.processEvents()
            self.assertTrue(bool(button.focusPolicy() & Qt.TabFocus))
            button.setFocus(Qt.TabFocusReason)
            self.assertTrue(button.hasFocus())

            # A real Qt Down key opens the same QMenu as the hover path.
            QTest.keyClick(button, Qt.Key_Down)
            self.app.processEvents()
            self.assertTrue(menu.isVisible())
            self.assertIs(menu.activeAction(), first)
            self.assertFalse(button._poll_timer.isActive())

            QTest.keyClick(menu, Qt.Key_Return)
            self.app.processEvents()
            self.assertEqual(activated, ["Crafts"])
            self.assertFalse(menu.isVisible())

            # Mouse-hover opening remains polled and uses the same actions.
            button.open_hover_menu()
            self.assertTrue(menu.isVisible())
            self.assertTrue(button._poll_timer.isActive())
            button.close_hover_menu()
            self.assertFalse(menu.isVisible())
            self.assertFalse(button._poll_timer.isActive())
        finally:
            button.close_hover_menu()
            button.close()
            button.deleteLater()

    def test_primary_navigation_uses_local_unity_pictograms_with_fallback(self) -> None:
        main_source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn('sprite_icon_path("inventory")', main_source)
        self.assertIn('sprite_icon_path("encyclopedia")', main_source)
        self.assertIn('("Guide", "guide", GUIDES_TAB)', main_source)
        self.assertIn('("Quêtes", "quest", QUESTS_TAB)', main_source)
        self.assertIn('("Succès", "success", ACHIEVEMENTS_TAB)', main_source)
        self.assertIn('lambda _checked=False, chosen=tab:', main_source)
        self.assertIn("if icon_path:", main_source)

    def test_module_subnav_reuses_buttons_and_keeps_clicks_correct(self) -> None:
        # Changing Outils tabs updates the same shared button row without
        # accumulating stale Qt controls or losing the callback.
        from main import AtlasWindow
        with (
            patch.object(AtlasWindow, "start_runtime", return_value=None),
            patch.object(AtlasWindow, "setup_tray", return_value=None),
        ):
            window = AtlasWindow(initial_preload={})
        selected: list[str] = []
        other: list[str] = []

        def select_tool(label: str) -> None:
            selected.append(label)

        def select_stuff(label: str) -> None:
            other.append(label)

        try:
            labels = ("Crafts", "Map monde", "Ocre")
            window.configure_module_subnav("Outils", labels, "Crafts", select_tool)
            first = tuple(window._module_subnav_buttons)
            self.assertEqual(len(first), 3)
            self.assertEqual(first[0].objectName(), "TopNavButtonActive")

            window.configure_module_subnav("Outils", labels, "Ocre", select_tool)
            self.assertTrue(all(a is b for a, b in zip(first, window._module_subnav_buttons)))
            self.assertEqual(first[0].objectName(), "TopNavButton")
            self.assertEqual(first[2].objectName(), "TopNavButtonActive")
            first[0].click()
            self.assertEqual(selected, ["Crafts"])

            window.hide_module_subnav()
            window.configure_module_subnav("Outils", labels, "Map monde", select_tool)
            self.assertIs(window._module_subnav_buttons[1], first[1])
            self.assertEqual(first[1].objectName(), "TopNavButtonActive")

            window.configure_module_subnav("Stuffs", ("PvM", "PvP"), "PvP", select_stuff)
            self.assertEqual(len(window._module_subnav_buttons), 2)
            self.assertIsNot(window._module_subnav_buttons[0], first[0])
            window._module_subnav_buttons[1].click()
            self.assertEqual(other, ["PvP"])
            self.assertEqual(selected, ["Crafts"])
        finally:
            window.deleteLater()

    def test_deep_link_uses_encyclopedia_filter_after_bestiary(self) -> None:
        import main
        from app.modules.encyclopedia.constants import GUIDES_TAB

        calls = []

        class Shell:
            pending_guide_target = None
            def open_encyclopedia_tab(self, tab) -> None:
                calls.append(("tab", tab))
            def show_page(self, page) -> None:
                raise AssertionError("Bypassing the Encyclopedia tab group")
            def _schedule_owned_callback(self, delay, callback) -> None:
                calls.append(("scheduled", delay, callback))
            finish_pending_guide_target = main.AtlasWindow.finish_pending_guide_target

        shell = Shell()
        main.AtlasWindow.open_guide_progress(shell, "guide_complet", quest_id="42")
        self.assertEqual(shell.pending_guide_target, ("guide_complet", 42))
        self.assertEqual(calls, [
            ("tab", GUIDES_TAB),
            ("scheduled", 0, shell.finish_pending_guide_target),
        ])
        calls.clear()
        main.AtlasWindow.open_guide_progress(shell, "dofus_sylvestre", quest_id="bad")
        self.assertEqual(shell.pending_guide_target, ("dofus_sylvestre", None))
        self.assertEqual(calls[0], ("tab", GUIDES_TAB))

    def test_home_layout_fits_atlas_minimum_window_without_clipping_columns(self) -> None:
        from app.constants import MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH
        from app.pages.home_page import HomePage

        home = HomePage()
        try:
            for width, height in (
                (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT),
                (1180, 720),
            ):
                with self.subTest(width=width, height=height):
                    home.resize(width, height)
                    home.show()
                    self.app.processEvents()
                    self.assertEqual(home.width(), width)
                    self.assertLessEqual(home.minimumSizeHint().width(), width)
                    self.assertTrue(home.right_column.isVisible())
                    self.assertTrue(home.almanax_card.isVisible())
                    self.assertLess(
                        home.left_column.geometry().right(),
                        home.guide_card.geometry().left(),
                    )
                    self.assertLess(
                        home.guide_card.geometry().right(),
                        home.right_column.geometry().left(),
                    )
                    self.assertLessEqual(
                        home.right_column.geometry().right(),
                        home.rect().right(),
                    )
        finally:
            home.close()
            home.deleteLater()
            self.app.processEvents()

    def test_home_tracking_icons_preserve_local_alpha_and_fallback(self) -> None:
        from PySide6.QtWidgets import QLabel
        from app.pages.home_page import HomeTrackingRow

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quest.png"
            image = QImage(16, 16, QImage.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))
            image.setPixelColor(8, 8, QColor(250, 200, 80, 255))
            self.assertTrue(image.save(str(path)))
            with patch("app.pages.home_page.sprite_icon_path", return_value=path) as lookup:
                row = HomeTrackingRow("◆", "Quêtes", sprite_key="quest")
            try:
                lookup.assert_called_once_with("quest")
                icon = row.findChild(QLabel, "HomeTrackingIcon")
                self.assertIsNotNone(icon)
                self.assertFalse(icon.pixmap().isNull())
                self.assertEqual(icon.pixmap().toImage().pixelColor(0, 0).alpha(), 0)
            finally:
                row.deleteLater()

            with patch("app.pages.home_page.sprite_icon_path", return_value=None):
                fallback = HomeTrackingRow("◆", "Quêtes", sprite_key="quest")
            try:
                self.assertEqual(
                    fallback.findChild(QLabel, "HomeTrackingIcon").text(), "◆",
                )
            finally:
                fallback.deleteLater()
        app.processEvents()

    def test_home_uses_canonical_transparent_logo_not_raw_png(self) -> None:
        home_source = (Path(__file__).resolve().parents[1] / "app/pages/home_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self.almanax_icon.setIcon(atlas_application_icon())", home_source)
        self.assertIn("atlas_application_icon() if selected == fallback", home_source)
        self.assertNotIn("self.almanax_icon.setIcon(QIcon(str(LOGO_PATH)))", home_source)

    def test_application_has_only_unity_palette(self) -> None:
        from app.ui import theme
        self.assertEqual(theme.PALETTE["BG"], UNITY_PALETTE["BG"])
        self.assertEqual(theme.PALETTE["PANEL"], UNITY_PALETTE["PANEL"])
        self.assertEqual(theme.PALETTE["GREEN"], UNITY_PALETTE["GREEN"])
        self.assertIn("QWidget#AtlasUnityBackdrop", theme.atlas_stylesheet())

    def test_unity_fallback_background_is_not_flat(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            unity_skin, "_PERSONAL_ASSETS", Path(directory) / "no-assets"
        ), patch.object(unity_skin, "_ASSETS", Path(directory) / "no-source"):
            backdrop = UnityBackdrop()
            self.assertTrue(backdrop._pixmap.isNull())
            backdrop.resize(220, 140)
            image = QImage(220, 140, QImage.Format_ARGB32)
            image.fill(0xff000000)
            backdrop.render(image)
            self.assertNotEqual(image.pixelColor(10, 10), image.pixelColor(10, 130))
            backdrop.deleteLater()

    def test_palette_contrast_roles_and_sprite_state_contract(self) -> None:
        self.assertNotEqual(UNITY_PALETTE["BG"], UNITY_PALETTE["TEXT"])
        self.assertIn("SHELL_GRADIENT", UNITY_PALETTE)
        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            style = unity_skin_stylesheet()
            self.assertIn("AtlasUnityBackdrop", style)
            self.assertIn("QPushButton:focus", style)
            if "btn_green_normal.png" in style:
                for required in ("btn_green_over.png", "btn_green_pressed.png", "btn_green_disabled.png"):
                    self.assertIn(required, style)
                self.assertIn("border-image", style)


class EncyclopediaQuestLoadingUITests(unittest.TestCase):
    """Shared Qt UI regression: abandoned Quest hydration remains inert."""

    def test_abandoned_quest_result_never_mounts_inactive_view(self) -> None:
        from queue import Queue
        from unittest.mock import Mock
        from app.modules.encyclopedia.views.encyclopedia_page import (
            EncyclopediaPage, _QuestRuntimePayload,
        )

        class Probe:
            _collect_quest_runtime = EncyclopediaPage._collect_quest_runtime

            def __init__(self) -> None:
                self._quest_load_queue = Queue(maxsize=1)
                self._quest_load_timer = Mock()
                self._quest_load_started = True
                self._quest_load_abandoned = True
                self._quest_graph = None
                self.quest_page = None
                self.status_callback = Mock()

            def _build_quests_page_progressive(self):
                raise AssertionError("Obsolete Quests must not hydrate")

        probe = Probe()
        probe._quest_load_queue.put(_QuestRuntimePayload(object()))
        probe._collect_quest_runtime()
        self.assertFalse(probe._quest_load_started)
        self.assertFalse(probe._quest_load_abandoned)
        self.assertIsNone(probe._quest_graph)
        self.assertTrue(probe._quest_load_queue.empty())
        probe._quest_load_timer.stop.assert_called_once()
        probe.status_callback.assert_not_called()

    def test_quest_worker_result_is_reused_if_user_returns_early(self) -> None:
        from app.modules.encyclopedia.constants import GUIDES_TAB, QUESTS_TAB
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage

        class Tabs:
            label = GUIDES_TAB
            def tabText(self, _index: int) -> str:
                return self.label

        class Probe:
            _on_tab_changed_indexed_runtime = (
                EncyclopediaPage._on_tab_changed_indexed_runtime
            )
            def __init__(self):
                self.tabs = Tabs()
                self._initializing = False
                self._quest_load_started = True
                self._quest_load_abandoned = False
                self._pending_lazy_tab = ""
                self._pending_guide_id = ""
                self._pending_achievement_context_id = None
                self.guides_view = None
                self._related_ready = False
                self._achievement_ready = False
                self.actions = []
            def _start_full_guide_runtime(self):
                self.actions.append("guide-runtime")
            def _on_tab_changed_indexed(self, index: int):
                self.actions.append(("quest-indexed", index))

        probe = Probe()
        probe._on_tab_changed_indexed_runtime(0)
        self.assertTrue(probe._quest_load_abandoned)
        probe.tabs.label = QUESTS_TAB
        probe._on_tab_changed_indexed_runtime(0)
        self.assertFalse(probe._quest_load_abandoned)
        self.assertEqual(probe.actions, ["guide-runtime", ("quest-indexed", 0)])


if __name__ == "__main__":
    unittest.main()
