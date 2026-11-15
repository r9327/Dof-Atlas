"""Direct UI-theme owner: Guide Ultime follows shared Successes widgets.

The legacy designer must not reintroduce per-view dropdown overrides.
"""
from __future__ import annotations

import unittest

import app.ui.theme as theme


class SharedThemeTests(unittest.TestCase):
    def test_guide_ultime_dropdown_inherits_successes_global_rules(self) -> None:
        overrides = {
            "PANEL_2": "#123ABC",
            "PANEL_ACTIVE": "#234BCD",
            "BORDER": "#345CDE",
            "BORDER_STRONG": "#456DEF",
        }
        style = theme.atlas_stylesheet(overrides)
        # A Guide-specific QComboBox rule used to override the common
        # popup/focus/hover rules twice with incompatible padding/colors.
        self.assertNotIn("#GuideUltimeGeneratedView QComboBox", style)
        common = style.split(
            "QLineEdit, QComboBox, QSpinBox, #inputField, #comboField {", 1
        )[0]
        self.assertIn("QComboBox", common)
        dropdown = style.split("QComboBox QAbstractItemView {", 1)[1].split("}", 1)[0]
        self.assertIn("background: #123ABC;", dropdown)
        self.assertIn("selection-background-color: #234BCD;", dropdown)
        self.assertIn("border: 1px solid #345CDE;", dropdown)
        hover = style.split("QComboBox:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("border-color: #456DEF;", hover)
        # Do not disturb Guide-only buttons and other interactive controls.
        self.assertIn(
            "#GuideUltimeGeneratedView QPushButton,\n"
            "#GuideUltimeGeneratedView QToolButton {",
            style,
        )
        self.assertIn("#GuideUltimeGeneratedView QCheckBox {", style)

    def test_shared_buttons_use_one_typography_spacing_and_radius_contract(self) -> None:
        from app.ui.components import BUTTON_OBJECT_NAMES

        self.assertEqual(BUTTON_OBJECT_NAMES["navigation"], "TopNavButton")
        self.assertEqual(BUTTON_OBJECT_NAMES["navigation_active"], "TopNavButtonActive")
        self.assertEqual(BUTTON_OBJECT_NAMES["primary"], "PrimaryActionButton")
        self.assertEqual(BUTTON_OBJECT_NAMES["secondary"], "SecondaryButton")

        style = theme.atlas_stylesheet({
            "FONT_SMALL": "15px",
            "FONT_BODY": "16px",
            "RADIUS_SM": "9px",
            "SPACE_LG": "17px",
            "SPACE_MD": "13px",
        })
        common = style.split(
            "#primaryButton, #ActiveButton, #PrimaryActionButton,\n"
            "#secondaryButton, #SecondaryButton {", 1,
        )[1].split("}", 1)[0]
        for rule in (
            "font-size: 15px;",
            "padding-left: 17px;",
            "padding-right: 13px;",
        ):
            self.assertIn(rule, common)

        primary = style.split(
            "#primaryButton, #PrimaryActionButton {", 1
        )[1].split("}", 1)[0]
        secondary = style.rsplit(
            "#secondaryButton, #SecondaryButton {", 1
        )[1].split("}", 1)[0]
        selected = style.split("#ActiveButton {", 1)[1].split("}", 1)[0]
        self.assertIn("background: ", primary)
        self.assertIn("background: ", secondary)
        self.assertNotIn("padding-left", primary)
        self.assertNotIn("padding-left", secondary)
        self.assertNotIn("border-bottom", primary)
        self.assertIn(f'border-bottom: 2px solid {theme.PALETTE["GREEN"]};', selected)
        self.assertIn("font-size: 16px;", style)
        self.assertIn("border-radius: 9px;", style)

        normal = theme.atlas_stylesheet()
        self.assertIn("font-size: 11px;", normal)
        self.assertIn("font-size: 12px;", normal)
        self.assertIn("border-radius: 6px;", normal)

    def test_stateful_toggles_share_unity_roles_without_losing_layout(self) -> None:
        """Guide and segmented controls share states, not their text layout."""
        # Verify the QSS role owner without coupling this assertion to a
        # second optional Qt sprite layer or test execution order.
        style = theme.render_theme_template(theme._STYLE_TEMPLATE, {
            "PANEL_2": "#123456",
            "BORDER": "#345678",
            "TEXT_SOFT": "#789ABC",
            "PANEL_HOVER": "#234567",
            "BORDER_STRONG": "#456789",
            "PANEL_ACTIVE": "#345634",
            "GREEN_BORDER": "#668833",
            "GREEN": "#456745",
        })
        shared = style.split(
            "#GuideHideCompletedToggle,\n"
            "#segmentedButton, #segmentedButtonActive {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("background: #123456;", shared)
        self.assertIn("border-color: #345678;", shared)
        self.assertIn("color: #789ABC;", shared)
        hover = style.split(
            "#GuideHideCompletedToggle:hover, #segmentedButton:hover {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("background: #234567;", hover)
        self.assertIn("border-color: #456789;", hover)
        active = style.split(
            "#GuideHideCompletedToggle:checked, #segmentedButtonActive {", 1,
        )[1].split("}", 1)[0]
        # The Qt preview must remain on the shared blue selected surface,
        # including when another role is previewed. Prove that active UI
        # widgets are not using a private Organizer stylesheet.
        self.assertIn("background: #345634;", active)
        self.assertIn("border-color: #668833;", active)
        self.assertIn("color: #456745;", active)
        preview = theme.render_theme_template(
            "background: @PANEL_ACTIVE; border-color: @GREEN_BORDER;",
            {"PANEL_ACTIVE": "#345634", "GREEN_BORDER": "#668833"},
        )
        self.assertIn("background: #345634;", preview)
        self.assertIn("border-color: #668833;", preview)
        guide_layout = style.split(
            "#GuideHideCompletedToggle {", 1,
        )[1].split("}", 1)[0]
        segment_layout = style.split("#GuideHideCompletedToggle {", 1)[1].split(
            "#segmentedButton, #segmentedButtonActive {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("text-align: left;", guide_layout)
        self.assertIn("text-align: center;", segment_layout)
        self.assertIn("border: 1px solid #345678;", segment_layout)
        self.assertIn(
            "#GuideHideCompletedToggle:checked:hover, #segmentedButtonActive:hover {",
            style,
        )

    def test_breadcrumb_has_one_global_owner_and_live_unity_tokens(self) -> None:
        style = theme.atlas_stylesheet({
            "TEXT_MUTED": "#102030",
            "PANEL_HOVER": "#203040",
            "GREEN_BORDER": "#304050",
        })
        self.assertNotIn("QPushButton#GuideBreadcrumbButton,\n", style)
        self.assertNotIn("QPushButton#GuideBreadcrumbButton:hover,\n", style)
        self.assertEqual(style.count("QPushButton#GuideBreadcrumbButton {"), 1)
        self.assertEqual(style.count("QPushButton#GuideBreadcrumbButton:hover {"), 1)
        normal = style.split("QPushButton#GuideBreadcrumbButton {", 1)[1].split("}", 1)[0]
        hover = style.split("QPushButton#GuideBreadcrumbButton:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("color: #102030;", normal)
        self.assertIn("background: #203040;", hover)
        self.assertIn("border-color: #304050;", hover)
        links = style.split(
            "QPushButton#GuideInlineQuestButton,\n"
            "            QPushButton#GuideInlineAchievementButton {", 1
        )[1].split("}", 1)[0]
        self.assertIn("text-decoration: underline;", links)
        self.assertIn(f'color: {theme.PALETTE["TEXT_SOFT"]};', links)

    def test_quest_launch_position_has_unified_bold_typography(self) -> None:
        from app.ui.unity_palette import UNITY_UI_FAMILY_INDEX

        style = theme.atlas_stylesheet({
            "TEXT": "#ABCDEF", "FONT_BODY": "17px",
        })
        rule = style.split(
            "QLabel#QuestLaunchPosition {", 1
        )[1].split("}", 1)[0]
        self.assertIn("color: #ABCDEF;", rule)
        self.assertIn("font-size: 17px;", rule)
        self.assertIn("font-weight: 800;", rule)
        self.assertIn(
            "QuestLaunchPosition",
            UNITY_UI_FAMILY_INDEX["guides"]["components"],
        )
        # Do not change the source position or link generation.
        from pathlib import Path
        source = (
            Path(__file__).resolve().parents[1]
            / "app/modules/encyclopedia/widgets/quest_detail_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"QuestLaunchPosition"', source)

    def test_guide_icons_preserve_transparent_background(self) -> None:
        style = theme.atlas_stylesheet()
        block = style.split(
            "QLabel#GuideHeaderImage,\n"
            "            QLabel#GuideAdventureImage,\n"
            "            QLabel#GuideAlignmentImage,\n"
            "            QLabel#GuideDofusImage {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background: transparent;", block)
        self.assertIn("border: 1px solid #354966;", block)
        self.assertNotIn("background: #151821;", block)

    def test_guide_surfaces_use_the_shared_glass_in_both_stylesheet_layers(self) -> None:
        from app.ui.unity_palette import resolve_unity_colors

        overrides = {
            "PANEL_2": "#203050", "PANEL": "#142038",
            "PANEL_ACTIVE": "#30456A", "PANEL_HOVER": "#405775",
            "BORDER_SOFT": "#637A94", "TEXT_SOFT": "#DCE7F2",
            "GREEN": "#A3D153", "GREEN_BORDER": "#86B343",
            "RADIUS_MD": "12px",
        }
        style = theme.atlas_stylesheet(overrides)
        roots = style.split("QWidget#GuidesHomePage,\n", 1)[1].split("}", 1)[0]
        self.assertIn("background: transparent;", roots)
        panels = style.split(
            "QFrame#GuideHeader,\n            QFrame#GuideBreadcrumb,", 1
        )[1].split("}", 1)[0]
        self.assertIn("rgba(32, 48, 80, 0.82)", panels)
        self.assertIn("rgba(20, 32, 56, 0.88)", panels)
        self.assertIn("border-radius: 12px;", panels)
        cards = style.split("QFrame#GuideAdventureCard,\n", 1)[1].split("}", 1)[0]
        expected = theme.unity_glass_gradient(
            palette=resolve_unity_colors(overrides)
        )
        self.assertIn(f"background: {expected};", cards)
        active = style.split(
            "QFrame#GuideQuestLineActive,\n"
            "            QFrame#GuideTreeRowActive {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-bottom: 2px solid #A3D153;", active)
        actual_skin = style.split(
            "QFrame#GuideHeader, QFrame#GuidesHomeCategory,", 1
        )[1].split("}", 1)[0]
        self.assertIn("rgba(32, 48, 80, 0.82)", actual_skin)
        self.assertIn("rgba(20, 32, 56, 0.88)", actual_skin)
        self.assertIn("border-radius: 12px;", actual_skin)

    def test_shared_guide_row_glass_tracks_live_unity_tokens(self) -> None:
        style = theme.atlas_stylesheet({
            "PANEL_HOVER": "#123456",
            "BORDER_SOFT": "#ABCDEF",
            "RADIUS_XS": "11px",
            "RADIUS_SM": "13px",
            "SPACE_XXS": "3px",
        })
        rules = style.split(
            "QFrame#GuideManualCombatSection,\n"
            "QFrame#GuideManualCombatLineRow,\n"
            "QFrame#GuideManualCombatInlineRow {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("background: rgba(18, 52, 86, 0.05);", rules)
        self.assertIn("border: 1px solid rgba(171, 205, 239, 0.18);", rules)
        self.assertIn("border-radius: 11px;", rules)
        section_rule = style.split(
            "QFrame#GuideManualCombatSection {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-radius: 13px;", section_rule)
        warning_line = style.split(
            "QFrame#GuideManualWarningSection QLabel#GuideManualLine {", 1
        )[1].split("}", 1)[0]
        self.assertIn("padding: 3px 0;", warning_line)
        self.assertIn("QFrame#GuideManualLineRow", style)
        # This rule intentionally uses an object-name selector, independent
        # of the concrete Qt class (the live widget remains a QCheckBox).
        self.assertIn("#GuideManualCombatCheck {", style)

    def test_unity_skin_radii_follow_theme_overrides_without_local_duplicates(self) -> None:
        from app.ui.unity_palette import UNITY_RADII

        self.assertEqual(
            {key: theme.SIZES[key] for key in UNITY_RADII}, UNITY_RADII,
        )
        style = theme.atlas_stylesheet({
            "RADIUS_XS": "14px",
            "RADIUS_SM": "16px",
            "RADIUS_MD": "18px",
        })
        group = style.split("QGroupBox, QTabWidget::pane {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: 18px;", group)
        featured = style.split(
            "QFrame#GuideFeaturedCard { background: qlineargradient(", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-radius: 18px;", featured)
        progress = style.split(
            "QFrame#GuideFeaturedCard QProgressBar#GuideFeaturedProgress {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-radius: 14px;", progress)
        copy_hover = style.split(
            "QPushButton#GuidePreparationItemCopy:hover {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-radius: 14px;", copy_hover)
        self.assertEqual(theme.SIZES["RADIUS_SM"], "6px")
        self.assertEqual(theme.SIZES["RADIUS_MD"], "8px")

    def test_guide_color_aliases_follow_common_unity_overrides(self) -> None:
        from app.ui.unity_palette import UNITY_SIZES_PX

        style = theme.atlas_stylesheet({
            "PANEL": "#112233",
            "PANEL_2": "#223344",
            "PANEL_ACTIVE": "#334455",
            "BORDER_CARD": "#445566",
        })
        header = style.split("QFrame#GuideHeader, QFrame#GuidesHomeCategory,", 1)[1].split("}", 1)[0]
        summary = style.split("QFrame#GuidePreparationSummary, QFrame#GuideManualWarningSection {", 1)[1].split("}", 1)[0]
        row = style.split("QFrame#GuidePreparationRow, QFrame#GuidePreparationDetails {", 1)[1].split("}", 1)[0]
        self.assertIn("rgba(17, 34, 51, 0.88)", header)
        self.assertIn("rgba(34, 51, 68, 0.82)", header)
        self.assertIn("rgba(51, 68, 85, 0.97)", summary)
        self.assertIn("rgba(34, 51, 68, 0.92)", row)
        self.assertIn("rgba(68, 85, 102, 0.65)", row)
        self.assertEqual(
            theme.SIZES["CONTROL_HEIGHT_COMPACT"],
            f'{UNITY_SIZES_PX["control_compact"]}px',
        )
        self.assertEqual(
            theme.SIZES["ICON_SIZE_LARGE"],
            f'{UNITY_SIZES_PX["icon_large"]}px',
        )

    def test_guide_buttons_remain_themed_after_dropdown_unification(self) -> None:
        style = theme.atlas_stylesheet({"GREEN_BORDER": "#135790"})
        button_hover = style.split(
            "#GuideUltimeGeneratedView QPushButton:hover,\n"
            "#GuideUltimeGeneratedView QToolButton:hover {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-color: #135790;", button_hover)
        self.assertNotIn("#GuideUltimeGeneratedView QComboBox", style)

    def test_sidebar_reuses_compact_tabs_glass_and_single_selection_language(self) -> None:
        from app.ui.unity_palette import UNITY_GLASS_INTENSITY
        self.assertEqual(UNITY_GLASS_INTENSITY, 0.16)
        style = theme.atlas_stylesheet({
            "PANEL": "#112233", "PANEL_2": "#223344",
            "PANEL_ACTIVE": "#334455", "GREEN": "#99CC33",
        })
        sidebar = style.split("#sidebar, #SideNav {", 1)[1].split("}", 1)[0]
        self.assertIn("rgba(34, 51, 68, 0.82)", sidebar)
        self.assertIn("rgba(17, 34, 51, 0.88)", sidebar)
        self.assertIn("border-radius: 8px;", sidebar)
        normal = style.split(
            "#navItem, #navItemActive, #NavButton, #ActiveNavButton,", 1
        )[1].split("}", 1)[0]
        active = style.split(
            "#navItemActive, #ActiveNavButton, #TopmostButtonActive {", 1
        )[1].split("}", 1)[0]
        self.assertIn("min-height: 24px;", normal)
        self.assertIn("max-height: 24px;", normal)
        self.assertIn("border-bottom: 2px solid #99CC33;", active)
        self.assertIn("color: #99CC33;", active)
        expected_active_glass = theme.unity_glass_gradient(
            "PANEL_HOVER", "PANEL_ACTIVE",
            top_alpha=199, bottom_alpha=206,
            palette=theme.resolve_unity_colors({
                "PANEL": "#112233", "PANEL_2": "#223344",
                "PANEL_ACTIVE": "#334455", "GREEN": "#99CC33",
            }),
        )
        self.assertIn(f"background: {expected_active_glass};", active)
        self.assertNotIn("border-left: 4px", active)
        self.assertNotIn("background: #497332;", active)

    def test_disabled_shared_actions_override_normal_identity_colors(self) -> None:
        style = theme.atlas_stylesheet()
        disabled = style.split(
            "#primaryButton:disabled, #ActiveButton:disabled,", 1
        )[1].split("}", 1)[0]
        self.assertIn("#DangerButton:disabled", disabled)
        self.assertIn("#segmentedButtonActive:disabled", disabled)
        self.assertIn("background: #1B2746;", disabled)
        self.assertIn("color: #8998B6;", disabled)

    def test_all_selected_segments_follow_dev_ui_no_solid_green(self) -> None:
        style = theme.atlas_stylesheet({
            "PANEL_ACTIVE": "#334455", "GREEN_BORDER": "#668833",
            "GREEN": "#99CC33",
        })
        block = style.split(
            "#GuideHideCompletedToggle:checked, #segmentedButtonActive {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background: #334455;", block)
        self.assertIn("border-color: #668833;", block)
        self.assertIn("color: #99CC33;", block)
        self.assertNotIn("background: #497332;", block)

    def test_success_catalogue_root_reveals_unity_sky_and_shared_panel_glass(self) -> None:
        style = theme.atlas_stylesheet({
            "PANEL_2": "#223344", "PANEL": "#112233",
            "BORDER_SOFT": "#445566", "TEXT_SOFT": "#AABBCC",
            "RADIUS_MD": "14px",
        })
        root = style.split("QWidget#AchievementsView {", 1)[1].split("}", 1)[0]
        self.assertIn("background: transparent;", root)
        self.assertNotIn("background: #", root)
        self.assertIn("#AchievementFilterPanel {", style)
        columns = style.split(
            "QWidget#AchievementsView QFrame#GuideLeftPanel,\n", 1
        )[1].split("}", 1)[0]
        self.assertIn("QStackedWidget#AchievementDetailStack", columns)
        self.assertIn("rgba(34, 51, 68, 0.82)", columns)
        self.assertIn("rgba(17, 34, 51, 0.88)", columns)
        self.assertIn("border: 1px solid #445566;", columns)
        self.assertIn("border-radius: 14px;", columns)

    def test_world_map_menu_and_detail_values_use_shared_material(self) -> None:
        from app.ui.unity_palette import resolve_unity_colors

        overrides = {
            "PANEL": "#112233", "PANEL_2": "#223344",
            "PANEL_HOVER": "#2A3A4A", "PANEL_ACTIVE": "#334455",
            "BORDER_SOFT": "#445566", "BORDER_CARD": "#556677",
            "BORDER_STRONG": "#667788", "TEXT_SOFT": "#BBDDEE",
            "GREEN": "#99CC33", "GREEN_BORDER": "#668833",
            "RADIUS_MD": "12px", "RADIUS_SM": "9px",
        }
        style = theme.atlas_stylesheet(overrides)
        expected_button = theme.unity_glass_gradient(
            palette=resolve_unity_colors(overrides),
        )
        for selector in ("#WorldDetailValue, #MapDetailValue {",
                         "#MapToolbar, #WorldDetailPanel {",
                         "#WorldMenu {"):
            self.assertIn(selector, style)

        value = style.split("#WorldDetailValue, #MapDetailValue {", 1)[1].split("}", 1)[0]
        self.assertIn(f"background: {expected_button};", value)
        self.assertIn("border-radius: 9px;", value)
        for selector in ("#MapToolbar, #WorldDetailPanel {", "#WorldMenu {", "QMenu {"):
            block = style.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn("rgba(34, 51, 68, 0.82)", block)
            self.assertIn("rgba(17, 34, 51, 0.88)", block)
            self.assertIn("border-radius: 12px;", block)
        active = style.split("\n#WorldMenuItemActive {", 1)[1].split("}", 1)[0]
        self.assertIn("background: #334455;", active)
        self.assertIn("border-bottom: 2px solid #99CC33;", active)
        hover = style.split("\n#WorldMenuItem:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("background:", hover)
        self.assertIn("border-color: #667788;", hover)
        self.assertNotIn("#16263A", hover)
        scroll = style.split("#WorldMenuScroll QScrollBar:vertical {", 1)[1].split("}", 1)[0]
        self.assertIn("background: rgba(17, 34, 51, 0.88);", scroll)
        self.assertIn("#MapCanvas {", style)

    def test_all_module_selections_use_blue_surfaces_and_fine_green_accents(self) -> None:
        style = theme.atlas_stylesheet()
        for selector in (
            "#EncyclopediaResultList::item:selected, #GuideResultList::item:selected {",
            "\n#WorldMenuItemActive {",
            "#MapViewTree::item:selected {",
        ):
            block = style.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn("background: #344978;", block)
            self.assertNotIn("background: #497332;", block)
        home = style.split(
            "#HomeChangeCharacterButton,\n#HomeContinueButton,\n#HomeAlmanaxButton {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background: #213154;", home)
        self.assertNotIn("background: qlineargradient", home)
        pressed = style.split(
            "QPushButton:pressed, QToolButton:pressed {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background: #344978;", pressed)

    def test_character_equipment_dressing_inherits_shared_panel_material(self) -> None:
        # The equipment grid must not hide its parent HomeTrackingCard with a
        # solid dark QWidget background when no player data is present.
        from PySide6.QtWidgets import QApplication, QWidget
        from app.pages.character_page import CharacterPage
        app = QApplication.instance() or QApplication([])
        style = theme.atlas_stylesheet()
        self.assertIn("QWidget#AtlasTransparentHost,", style)
        self.assertIn("QWidget#CharacterEquipmentGrid,", style)
        rule = style.split("QWidget#CharacterEquipmentCenter {", 1)[1].split("}", 1)[0]
        self.assertIn("background: transparent;", rule)
        self.assertIn("border: none;", rule)
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            root = Path(directory)
            page = CharacterPage(
                profile_path=root / "profiles.json",
                client_index_path=root / "clients.json",
                binding_path=root / "bindings.json",
            )
            try:
                self.assertIsNotNone(page.findChild(QWidget, "CharacterEquipmentGrid"))
                self.assertIsNotNone(page.findChild(QWidget, "CharacterEquipmentCenter"))
            finally:
                page.close()
                page.deleteLater()

    def test_dev_ui_shared_surface_style_reaches_real_widgets(self) -> None:
        style = theme.atlas_stylesheet({
            "PANEL": "#112233", "PANEL_2": "#223344",
            "BORDER_SOFT": "#345678",
        })
        group = style.split("QGroupBox {", 1)[1].split("}", 1)[0]
        card = style.split(
            "#card, #OrganizerPanel, #Panel, #CraftPanel, #QuestPanel {", 1
        )[1].split("}", 1)[0]
        slider = style.split("QSlider::groove:horizontal {", 1)[1].split("}", 1)[0]
        self.assertIn("rgba(34, 51, 68, 0.82)", group)
        self.assertIn("rgba(17, 34, 51, 0.88)", group)
        self.assertIn("rgba(34, 51, 68, 0.82)", card)
        self.assertIn("rgba(17, 34, 51, 0.88)", card)
        self.assertIn("border: 1px solid #345678;", slider)
        for common in (
            "QGroupBox::title {", "QTreeWidget::item {",
            "QSplitter::handle:horizontal {",
            "QScrollBar::handle:vertical {",
            "QComboBox QAbstractItemView {",
        ):
            self.assertIn(common, style)
        for obsolete in (
            "QWidget#DevUiPage QGroupBox {",
            "QWidget#DevUiPage QSlider#DevUiProgressSlider",
            "QWidget#DevUiPage QSplitter#DevUiResizeSplitter",
            "QWidget#DevUiPage QTreeWidget::item {",
        ):
            self.assertNotIn(obsolete, style)


    def test_global_scrollbars_keep_one_shared_unity_owner(self) -> None:
        # A later unscoped Guide rule used to silently override the shared
        # thumb with a dark color and an inconsistent 7 px geometry.
        source = theme._STYLE_TEMPLATE
        self.assertEqual(source.count("\\nQScrollBar:vertical {"), 1)
        self.assertEqual(source.count("\\nQScrollBar::handle:vertical {"), 1)
        self.assertEqual(source.count("\\nQScrollBar::handle:vertical:hover {"), 1)
        style = theme.atlas_stylesheet({
            "BORDER_CARD": "#ABCDEF", "BORDER_STRONG": "#FEDCBA",
        })
        normal = style.split("\\nQScrollBar::handle:vertical {", 1)[1].split("}", 1)[0]
        hover = style.split("\\nQScrollBar::handle:vertical:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("background: #ABCDEF;", normal)
        self.assertIn("background: #FEDCBA;", hover)
        self.assertNotIn("background: #2b3341;", style)
        self.assertNotIn("width: 7px;", style)

    def test_quest_hierarchy_reuses_shared_list_surface(self) -> None:
        style = theme.atlas_stylesheet({"LIST_SURFACE": "#123456"})
        hierarchy = style.split("QTreeWidget#QuestHierarchyTree {", 1)[1].split("}", 1)[0]
        self.assertIn("background: #123456;", hierarchy)
        self.assertNotIn("background: #151821;", hierarchy)



if __name__ == "__main__":
    unittest.main()
