"""Tests for the optional local Unity skin; no packaged or licensed assets implied."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from app.ui import unity_skin
from app.ui.unity_skin import (
    UNITY_PALETTE, UnityBackdrop, unity_enabled, unity_skin_stylesheet,
    sprite_icon_path, wallpaper_path,
)


class UnitySkinTests(unittest.TestCase):
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

    def test_tab_sprite_reserves_equal_border_for_all_states(self) -> None:
        sprite = "Assets_UI_Themes_darkStone_common_bg_tab_selected_normal-png.png"
        with patch.object(
            unity_skin, "_sprite_url",
            side_effect=lambda name: "/tmp/selected-tab.png" if name == sprite else None,
        ):
            style = unity_skin_stylesheet()
        self.assertIn(
            "QTabBar::tab, QTabWidget#EncyclopediaTabs QTabBar::tab { "
            "border: 6px solid transparent; }",
            style,
        )
        self.assertIn(
            "QTabBar::tab:selected, "
            "QTabWidget#EncyclopediaTabs QTabBar::tab:selected { "
            "border: 6px solid transparent; border-image:",
            style,
        )

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

    def test_primary_navigation_uses_local_unity_pictograms_with_fallback(self) -> None:
        main_source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn('sprite_icon_path("inventory")', main_source)
        self.assertIn('sprite_icon_path("encyclopedia")', main_source)
        self.assertIn('("Guide", "guide", GUIDES_TAB)', main_source)
        self.assertIn('("Quêtes", "quest", QUESTS_TAB)', main_source)
        self.assertIn('("Succès", "success", ACHIEVEMENTS_TAB)', main_source)
        self.assertIn('lambda _checked=False, chosen=tab:', main_source)
        self.assertIn("if icon_path:", main_source)

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
