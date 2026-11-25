"""Regression gate: Dev UI is the single contract for all Atlas modules.

Checks actual compiled Qt QSS, indexed families and all screen/UI owners.
Only validated widget states are treated as shared; prototypes are excluded.
"""
from __future__ import annotations

import ast
import inspect
import re
import unittest
from pathlib import Path

from app.ui.theme import atlas_stylesheet
from app.ui.ui_registry import (
    UI_CONSUMER_INDEX, UI_FAMILY_QSS_SELECTORS,
    UI_INTERACTION_QSS_SELECTORS, UI_MUTUALIZATION_TARGETS,
    inspect_ui_mutualization_sources, validate_ui_index,
)
from app.ui.unity_palette import (
    UNITY_UI_FAMILY_INDEX, UNITY_UI_CONSUMERS,
    UNITY_GLASS_INTENSITY, unity_glass_gradient,
)
from app.ui.organizer_style import ORGANIZER_STYLE_TEMPLATE


REPO_ROOT = Path(__file__).resolve().parents[1]


class UiUniversalContractTests(unittest.TestCase):
    def test_global_template_has_no_legacy_hex_and_scroll_viewport_is_transparent(self):
        from app.ui.theme import _STYLE_TEMPLATE
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{6}\b", _STYLE_TEMPLATE))
        self.assertIn("QScrollArea > QWidget#qt_scrollarea_viewport", atlas_stylesheet())

    def test_fallback_item_icon_has_one_painter_owner(self):
        from app.ui.guide_glyphs import atlas_icon
        from app.modules.encyclopedia.views.guides_view import atlas_icon as guide_icon
        from app.modules.encyclopedia.widgets.quest_item_row import _fallback_item_icon
        self.assertIs(guide_icon, atlas_icon)
        self.assertIs(_fallback_item_icon.__globals__["atlas_icon"], atlas_icon)

    def test_dev_ui_and_manual_guide_share_progress_bar_configuration(self):
        dev = (REPO_ROOT / "app/pages/dev_ui_page.py").read_text(encoding="utf-8")
        manual = (
            REPO_ROOT / "app/modules/encyclopedia/views/shared_manual_guide_view.py"
        ).read_text(encoding="utf-8")
        components = (REPO_ROOT / "app/ui/components.py").read_text(encoding="utf-8")
        continuous = (
            REPO_ROOT / "app/modules/encyclopedia/views/guide_continuous_route_panel.py"
        ).read_text(encoding="utf-8")
        for source in (dev, manual, continuous):
            self.assertIn("AtlasGuideReadingHeader(", source)
            self.assertNotIn('object_name="GuideGlobalProgress"', source)
            self.assertNotIn('object_name="GuideCompactPreparationProgress"', source)
        self.assertEqual(components.count('object_name="GuideGlobalProgress"'), 1)
        self.assertEqual(components.count('"GuideCompactPreparationProgress"'), 1)
        preload = (REPO_ROOT / "app/ui/preload_popup.py").read_text(encoding="utf-8")
        self.assertIn("configure_unity_progress_bar(", preload)
        self.assertIn("maximum=len(PRELOAD_TASK_ORDER), text_visible=True", preload)
        self.assertNotIn("self.progress.setRange(", preload)
        self.assertEqual(dev.count("configure_unity_progress_bar("), dev.count("QProgressBar()"))
        self.assertIn("maximum=0, text_visible=True", dev)
        self.assertIn("maximum=3,", dev)
        self.assertIn('object_name="DevUiMotionProgress", text_visible=True', dev)
        self.assertNotIn("configure_unity_progress_bar(", manual)
        self.assertNotIn("self.global_progress_bar.setTextVisible(False)", manual)

    def test_quests_breadcrumb_rebuild_shares_layout_cleanup_without_new_widget(self):
        source = (REPO_ROOT / "app/pages/_quests_page_impl.py").read_text(encoding="utf-8")
        self.assertIn("clear_unity_widget_layout(self.breadcrumb_layout)", source)
        self.assertIn('AtlasButton("Quêtes", variant="guide_breadcrumb")', source)

    def test_shell_capture_exercises_real_almanax_and_no_fake_tributes(self):
        from tests.capture_app_shell_ui import SCENARIOS
        almanax = [row for row in SCENARIOS if row[0] == "Almanax"]
        self.assertEqual(len(almanax), 1)
        self.assertEqual(almanax[0][3], "offline-calendar-no-offering-data")
        source = (REPO_ROOT / "tests/capture_app_shell_ui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('QCalendarWidget, "AlmanaxCalendar"', source)
        self.assertIn('QDate.currentDate().addDays(40)', source)
        self.assertIn("Almanax future-day selection failed", source)
        self.assertIn("0 game records", source)
        self.assertIn('QLabel, "AlmanaxDayDetails"', source)
        self.assertIn("service.dayUnavailable.emit(day_key", source)
        self.assertNotIn('QLabel, "AlmanaxUnavailable"', source)

    def test_real_module_geometry_reads_one_dev_ui_index(self):
        """Preserve original visual sizes while linking primary consumers."""
        root = REPO_ROOT
        paths = (
            "main.py", "app/pages/home_page.py", "app/pages/character_page.py",
            "app/pages/craft_page.py",
            "app/pages/_quests_page_impl.py",
            "app/modules/encyclopedia/widgets/filter_panel.py",
            "app/modules/encyclopedia/views/achievements_view.py",
            "app/modules/encyclopedia/views/guide_catalog_view.py",
            "app/modules/encyclopedia/views/guides_view.py",
            "app/ui/map_canvas_widget.py", "app/ui/world_scan_panel.py",
        )
        for path in paths:
            with self.subTest(path=path):
                source = (root / path).read_text(encoding="utf-8")
                self.assertIn("UNITY_MODULE_GEOMETRY_PX", source)
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["shell"]["settings_button_box"], 34,
        )
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["home"]["right_column_min_width"], 205,
        )
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["world_map"]["canvas_min_size"], (420, 320),
        )

    def test_craft_leveling_and_guide_section_sizes_reuse_existing_ui_index(self):
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX, UNITY_SIZES_PX

        craft = UNITY_MODULE_GEOMETRY_PX["craft"]
        self.assertEqual(craft["leveling_level_badge_width"], 88)
        self.assertEqual(craft["leveling_copy_action_width"], 64)
        self.assertEqual(craft["leveling_add_action_width"], 38)
        self.assertEqual(craft["leveling_action_height"], 28)
        source = (REPO_ROOT / "app/pages/craft_page.py").read_text(encoding="utf-8")
        self.assertIn('CRAFT_GEOMETRY["leveling_level_badge_width"]', source)
        self.assertIn('CRAFT_GEOMETRY["leveling_action_height"]', source)
        section = (REPO_ROOT / "app/modules/encyclopedia/widgets/guide_section_widget.py").read_text(encoding="utf-8")
        self.assertEqual(UNITY_SIZES_PX["control_compact"], 24)
        self.assertIn('setFixedWidth(UNITY_SIZES_PX["control_compact"])', section)

    def test_compat_character_dimensions_are_indexed_without_moving_panels(self):
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        data = UNITY_MODULE_GEOMETRY_PX["character_compat"]
        source = (REPO_ROOT / "app/pages/_character_page_impl.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(data["equipment_slot_box"], 62)
        self.assertEqual(data["portrait_min_size"], (214, 292))
        self.assertIn("CHARACTER_COMPAT_GEOMETRY =", source)
        self.assertIn('CHARACTER_COMPAT_GEOMETRY["equipment_slot_box"]', source)
        self.assertIn('CHARACTER_COMPAT_GEOMETRY["page_margins"]', source)

    def test_shell_nav_uses_indexed_spacing_without_changing_order(self):
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        geometry = UNITY_MODULE_GEOMETRY_PX["shell"]
        source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertEqual(geometry["subnav_margins"], (10, 4, 10, 4))
        self.assertEqual(geometry["top_nav_margins"], (10, 6, 10, 6))
        self.assertIn('UNITY_MODULE_GEOMETRY_PX["shell"]["subnav_margins"]',
                      source)
        self.assertIn('UNITY_MODULE_GEOMETRY_PX["shell"]["top_nav_margins"]',
                      source)

    def test_shell_character_selector_uses_the_shared_unity_combo(self):
        # The shell used a bare QComboBox, whose popup could show every
        # character and lacked the Dev UI separator/scroll contract.
        # Keep creation lazy; the real popup is exercised in Dev UI Qt tests.
        source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("self.character_combo = AtlasComboBox()", source)
        self.assertNotIn("self.character_combo = QComboBox()", source)
        self.assertIn("AtlasComboBox,", source)

    def test_content_sized_selectors_remain_shared_across_modules(self):
        # The shared AtlasComboBox constructor owns the policy once: screens
        # must not repeat an identical Maximum/Fixed override.
        shared = (REPO_ROOT / "app/ui/components.py").read_text(encoding="utf-8")
        self.assertIn(
            "self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)", shared
        )
        for path in ("app/pages/character_page.py", "app/pages/_character_page_impl.py"):
            source = (REPO_ROOT / path).read_text(encoding="utf-8")
            self.assertIn("self.character_selector = AtlasComboBox()", source)
            self.assertNotIn("self.character_selector.setSizePolicy(", source)
        achievements = (
            REPO_ROOT / "app/modules/encyclopedia/views/achievements_view.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("AdjustToMinimumContentsLengthWithIcon", achievements)
        self.assertIn("combo = AtlasComboBox()", achievements)
        self.assertNotIn("combo.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)", achievements)

        quests = (
            REPO_ROOT / "app/pages/_quests_page_impl.py"
        ).read_text(encoding="utf-8")
        self.assertIn("quantity = configure_unity_number_spinbox(", quests)
        self.assertNotIn(
            'quantity.setFixedWidth(QUEST_GEOMETRY["item_quantity_width"])',
            quests,
        )

    def test_success_runtime_defers_only_optional_reward_indexes(self):
        base = (
            REPO_ROOT / "app/modules/encyclopedia/providers/achievement_provider.py"
        ).read_text(encoding="utf-8")
        memory_bound = (
            REPO_ROOT
            / "app/modules/encyclopedia/providers/memory_bound_achievement_provider.py"
        ).read_text(encoding="utf-8")
        stage = (
            REPO_ROOT / "app/modules/encyclopedia/views/encyclopedia_page.py"
        ).read_text(encoding="utf-8")
        detail_view = (
            REPO_ROOT / "app/modules/encyclopedia/views/achievements_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def load_catalogue_only(self)", base)
        self.assertIn("def detail_source_index_required(self)", memory_bound)
        self.assertIn("def load_runtime(self)", memory_bound)
        self.assertIn('"load_catalogue_only"', stage)
        self.assertIn('"prepare_detail_sources"', stage)
        self.assertIn('"detail_source_index_required"', detail_view)
        self.assertIn('"prepare_detail_sources"', detail_view)
        self.assertIn("detail = self._get_detail_in_process(achievement_id)", memory_bound)

    def test_zaap_favorite_button_reuses_atlas_style_and_click_owner(self):
        source = (REPO_ROOT / "app/storage.py").read_text(encoding="utf-8")
        self.assertIn(
            "short_label(name, 24), chip, variant=\"zaap_favorite\"", source
        )
        from app.ui.components import BUTTON_OBJECT_NAMES
        self.assertEqual(BUTTON_OBJECT_NAMES["zaap_favorite"], "favoriteChipName")
        self.assertNotIn('button.setObjectName("favoriteChipName")', source)
        self.assertIn("button.clicked.connect", source)
        self.assertNotIn("button = QPushButton(short_label(name, 24), chip)", source)
        self.assertIn("#favoriteChipName", atlas_stylesheet())

    def test_success_level_filters_reuse_indexed_numeric_width(self):
        source = (
            REPO_ROOT / "app/modules/encyclopedia/widgets/filter_panel.py"
        ).read_text(encoding="utf-8")
        imports = {
            alias.name for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module == "app.ui.components"
            for alias in node.names
        }
        self.assertTrue({"AtlasComboBox", "configure_unity_number_spinbox",
                         "configure_unity_progress_bar", "clear_unity_widget_layout"} <= imports)
        self.assertIn("bar = configure_unity_progress_bar(", source)
        self.assertIn('object_name="EncyclopediaProgressBar"', source)
        self.assertIn("bar.setValue(clamped_percent(completed, total))", source)
        self.assertIn("percent = clamped_percent(completed, total)", source)
        self.assertIn("self.min_level = configure_unity_number_spinbox(", source)
        self.assertIn("self.max_level = configure_unity_number_spinbox(", source)
        self.assertIn("clear_unity_widget_layout(self.category_layout", source)
        self.assertNotIn("fit_unity_number_spinbox(", source)

    def test_every_gallery_family_and_consumer_is_registered(self):
        validate_ui_index()
        self.assertGreaterEqual(len(UI_FAMILY_QSS_SELECTORS), 23)
        self.assertEqual(len(UI_CONSUMER_INDEX), 18)
        self.assertEqual(tuple(UI_FAMILY_QSS_SELECTORS), tuple(UNITY_UI_FAMILY_INDEX))
        self.assertEqual(tuple(UI_CONSUMER_INDEX), UNITY_UI_CONSUMERS)
        for module, entry in UI_CONSUMER_INDEX.items():
            with self.subTest(module=module):
                for path in entry["paths"]:
                    self.assertTrue((REPO_ROOT / path).is_file(), path)
        self.assertEqual(UI_CONSUMER_INDEX["Launcher"]["adapter"], "tk")
        self.assertEqual(UI_CONSUMER_INDEX["Organizer"]["adapter"], "qt_scoped")
        from tests.capture_app_shell_ui import SCENARIOS
        expected = {
            "Home": "Accueil", "Organizer": "Organizer",
            "Settings": "Paramètres", "Dev UI": "Dev UI",
            "Almanax": "Almanax", "Craft": "Craft",
            "Equipement": "Stuffs", "Scan Monde": "Carte du monde",
            "Personnage": "Personnage", "Quetes": "Quêtes",
            "Guides": "Guides", "Succes": "Succès",
            "Bestiaire": "Bestiaire",
        }
        self.assertEqual({name for name, *_rest in SCENARIOS}, set(expected))
        self.assertTrue(set(expected.values()) <= set(UI_CONSUMER_INDEX))
        self.assertIn("main.py", UI_CONSUMER_INDEX["Almanax"]["paths"])
        self.assertIn("main.py", UI_CONSUMER_INDEX["Paramètres"]["paths"])

        popups = UI_CONSUMER_INDEX["Popups et dialogues"]["surfaces"]
        overlays = UI_CONSUMER_INDEX["Overlays et démarrage"]["surfaces"]
        self.assertEqual(len(popups), 12)
        self.assertEqual(len(overlays), 4)
        screenshot_source = (REPO_ROOT / "tests/capture_app_popups_ui.py").read_text(
            encoding="utf-8"
        )
        for label, _path in popups:
            with self.subTest(popup=label):
                self.assertIn(f'"{label}"', screenshot_source)

        self.assertEqual(
            set(UI_CONSUMER_INDEX) -
            {"Launcher", "Organizer"},
            {name for name, data in UI_CONSUMER_INDEX.items()
             if data["adapter"] == "qt"},
        )

    def test_live_guide_and_dev_ui_share_character_and_page_selector_roles(self):
        # Both screens must consume the same component and style selector;
        # a screenshot-only or module-local patch would regress the other.
        paths = (
            REPO_ROOT / "app/pages/dev_ui_page.py",
            REPO_ROOT / "app/modules/encyclopedia/views/shared_manual_guide_view.py",
        )
        for path in paths:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("AtlasGuideReadingHeader(", source)
                self.assertIn("AtlasGuideSheetHeader(", source)
                self.assertNotIn("AtlasGuideParticipantButton()", source)
                self.assertNotIn('setObjectName("GuideCompactPageJump")', source)
        components = (REPO_ROOT / "app/ui/components.py").read_text(encoding="utf-8")
        self.assertEqual(components.count('setObjectName("GuideCompactPageJump")'), 1)
        self.assertIn("AtlasGuideParticipantButton()", components)
        self.assertIn("self.page_jump, minimum=1 if total else 0, maximum=total", components)
        theme = (REPO_ROOT / "app/ui/theme.py").read_text(encoding="utf-8")
        self.assertIn(
            "QToolButton#GuideParticipantsButton:focus,", theme,
        )
        self.assertIn(
            "QSpinBox#GuideCompactPageJump QLineEdit,", theme,
        )
        self.assertIn(
            "QSpinBox#GuideCompactPageJump {\n    padding-left: @SPACE_LG;", theme,
        )

    def test_guide_state_markers_share_one_indexed_width(self):
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX

        source = (
            REPO_ROOT / "app/modules/encyclopedia/views/guides_view.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(UNITY_CONTROL_SIZES_PX["guide_tree_state_width"], 18)
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX
        components = (REPO_ROOT / "app/ui/components.py").read_text(encoding="utf-8")
        self.assertEqual(UNITY_MODULE_GEOMETRY_PX["quest_detail"]["prerequisite_marker_width"],
                         UNITY_CONTROL_SIZES_PX["guide_tree_state_width"])
        self.assertEqual(
            components.count('marker.setFixedWidth(UNITY_CONTROL_SIZES_PX["guide_tree_state_width"])'),
            1,
        )
        self.assertIn("marker = atlas_guide_state_marker(", source)
        self.assertIn("marker = atlas_guide_state_marker(", components)
        self.assertNotIn('setObjectName("GuideTreeState")', source)
        self.assertNotIn("marker.setFixedWidth(18)", source)

    def test_nested_encyclopedia_widget_owners_are_registered(self):
        # These widgets are built behind the page owners and were previously
        # absent from the audit. Tracking paths is not a new component class.
        expected = {
            "Quêtes": {"app/modules/encyclopedia/widgets/quest_detail_view.py"},
            "Guides": {
                "app/modules/encyclopedia/widgets/quest_detail_view.py",
                "app/modules/encyclopedia/widgets/guide_card.py",
            },
            "Succès": {
                "app/modules/encyclopedia/widgets/filter_panel.py",
                "app/modules/encyclopedia/widgets/achievement_entity_section.py",
            },
        }
        for module, owners in expected.items():
            with self.subTest(module=module):
                actual = set(UI_CONSUMER_INDEX[module]["paths"])
                self.assertTrue(owners <= actual, owners - actual)
                for path in owners:
                    self.assertTrue((REPO_ROOT / path).is_file(), path)

    def test_eighteen_needs_reuse_existing_family_index_and_measured_sources(self):
        self.assertEqual(len(UI_MUTUALIZATION_TARGETS), 18)
        audit = inspect_ui_mutualization_sources(REPO_ROOT)
        self.assertEqual(len(audit), 18)
        self.assertEqual(
            {entry["label"] for entry in audit},
            {entry[0] for entry in UI_MUTUALIZATION_TARGETS},
        )
        for entry in audit:
            with self.subTest(item=entry["label"]):
                self.assertIn(entry["family"], UNITY_UI_FAMILY_INDEX)
                self.assertEqual(
                    entry["style_owner"],
                    UNITY_UI_FAMILY_INDEX[entry["family"]]["style_owner"],
                )
                self.assertNotIn("Dev UI", entry["source_consumers"])
                self.assertNotIn("Popups et dialogues", entry["source_consumers"])
                self.assertEqual(entry["unreadable_consumers"], ())
        craft = next(entry for entry in audit if entry["family"] == "dialogs")
        self.assertIn("Craft", craft["source_consumers"])
        self.assertEqual(craft["craft_shared_dialogs"], 4)
        self.assertEqual(craft["craft_local_qdialogs"], 0)
        # Extend the AST inventory beyond button/combobox clones, without
        # treating every geometry override as a duplicate by default.
        by_label = {entry["label"]: entry for entry in audit}
        qss = by_label["Bordures et arrondis"]
        self.assertEqual(qss["local_style_calls"], ())
        widths = by_label["Scrollbars et resize"]
        self.assertIsInstance(widths["literal_width_calls"], tuple)
        self.assertTrue(all(
            width > 0 and (REPO_ROOT / path).is_file() and line > 0
            for path, line, width in widths["literal_width_calls"]
        ))
        dialogs = by_label["Fenêtres et popups classiques"]
        self.assertIsInstance(dialogs["native_dialog_calls"], tuple)
        self.assertEqual(dialogs["native_dialog_calls"], ())
        checks = {
            "Boutons": "QPushButton",
            "Menus de sélection": "QComboBox",
        }
        import ast
        for label, constructor in checks.items():
            row = next(entry for entry in audit if entry["label"] == label)
            self.assertIsInstance(row["raw_qt_constructors"], tuple)
            self.assertEqual(
                row["raw_qt_constructors"], (),
                f"{label}: native constructors still used in registered Qt modules",
            )
            for path, line in row["raw_qt_constructors"]:
                with self.subTest(label=label, path=path, line=line):
                    self.assertGreater(line, 0)
                    source = (REPO_ROOT / path).read_text(encoding="utf-8")
                    tree = ast.parse(source)
                    self.assertTrue(any(
                        isinstance(node, ast.Call)
                        and node.lineno == line
                        and (
                            (isinstance(node.func, ast.Name)
                             and node.func.id == constructor)
                            or (isinstance(node.func, ast.Attribute)
                                and node.func.attr == constructor)
                        )
                        for node in ast.walk(tree)
                    ))
        self.assertNotIn(
            "app/storage.py",
            {path for path, _ in next(entry for entry in audit
                if entry["label"] == "Boutons")["raw_qt_constructors"]},
        )

    def test_dev_ui_indexes_actual_nav_and_quest_hierarchy_styles(self):
        # These real controls were already in the gallery but missing from
        # its auditable family index (including the active top tab).
        source = (REPO_ROOT / "app/pages/dev_ui_page.py").read_text(
            encoding="utf-8"
        )
        cases = (
            ("buttons", "TopNavButtonActive", "#TopNavButtonActive"),
            ("breadcrumbs", "GuideBreadcrumbCurrentStrong",
             "QLabel#GuideBreadcrumbCurrentStrong"),
            ("data_views", "QuestHierarchyTree", "QTreeWidget#QuestHierarchyTree"),
        )
        qss = atlas_stylesheet()
        for family, name, selector in cases:
            with self.subTest(name=name):
                self.assertIn(name, UNITY_UI_FAMILY_INDEX[family]["components"])
                self.assertIn(selector, UI_FAMILY_QSS_SELECTORS[family])
                self.assertIn(selector, qss)
        self.assertIn('self.preview_tree.setObjectName("QuestHierarchyTree")', source)

    def test_world_map_preview_and_interaction_states_are_indexed(self):
        expected = {
            "navigation": (
                "WorldMenu", "WorldMenuItem", "WorldMenuItemActive",
            ),
            "data_views": ("MapViewTree",),
            "surfaces": (
                "MapToolbar", "WorldDetailPanel",
                "WorldDetailValue", "MapDetailValue",
            ),
        }
        for family, names in expected.items():
            for name in names:
                self.assertIn(name, UNITY_UI_FAMILY_INDEX[family]["components"])
                self.assertIn("#" + name, UI_FAMILY_QSS_SELECTORS[family])
                self.assertIn("#" + name, atlas_stylesheet())
        self.assertIn("#WorldMenuItem:hover",
                      UI_INTERACTION_QSS_SELECTORS["navigation"])
        self.assertIn("#MapViewTree::item:selected",
                      UI_INTERACTION_QSS_SELECTORS["data_views"])

    def test_guide_catalog_materials_are_fully_indexed_in_dev_ui(self):
        gallery_source = (
            REPO_ROOT / "app/pages/dev_ui_page.py"
        ).read_text(encoding="utf-8")
        # Contract tests are Qt-free: the real QApplication and interactions
        # are exercised separately in tests/test_dev_ui_page.py.
        for name, attribute in (
            ("GuideHeader", "guide_sample_header"),
            ("GuidesHomeCategory", "guide_sample_category"),
            ("GuideDofusCard", "guide_sample_dofus_card"),
            ("GuideQuestLineActive", "guide_sample_active_route"),
            ("GuideCompactHeader", "guide_sample_compact_header"),
        ):
            self.assertIn(name, UNITY_UI_FAMILY_INDEX["guides"]["components"])
            self.assertIn("#" + name, UI_FAMILY_QSS_SELECTORS["guides"])
            self.assertIn("#" + name, atlas_stylesheet())
            if attribute == "guide_sample_compact_header":
                self.assertIn("self.guide_sample_compact_header = AtlasGuideReadingHeader(", gallery_source)
            else:
                self.assertIn(
                    f'self.{attribute}.setObjectName("{name}")',
                    gallery_source,
                )
        self.assertIn("guides", UI_INTERACTION_QSS_SELECTORS)
        self.assertIn("AlmanaxCalendar",
                      UNITY_UI_FAMILY_INDEX["advanced_fields"]["components"])
        self.assertIn("QCalendarWidget#AlmanaxCalendar",
                      UI_FAMILY_QSS_SELECTORS["advanced_fields"])

    def test_all_unity_design_tokens_have_one_qt_free_owner(self):
        from app.ui import theme
        from app.ui.unity_palette import (
            UNITY_SPACING_PX, UNITY_TYPOGRAPHY, UNITY_SIZES_PX,
            resolve_unity_colors,
        )
        self.assertEqual(theme.PALETTE, resolve_unity_colors())
        self.assertEqual(theme.TYPOGRAPHY, UNITY_TYPOGRAPHY)
        self.assertEqual(theme.SPACING, {
            f"SPACE_{role.upper()}": f"{px}px"
            for role, px in UNITY_SPACING_PX.items()
        })
        self.assertEqual(
            theme.SIZES["TOP_NAV_HEIGHT"],
            f'{UNITY_SIZES_PX["top_nav_height"]}px',
        )
        self.assertEqual(theme.PALETTE["RED"], "#D71920")
        self.assertEqual(theme.PALETTE["YELLOW"], "#D6B22D")

    def test_one_compiled_qss_covers_every_real_visual_family(self):
        qss = atlas_stylesheet()
        self.assertNotIn("@GLASS_BUTTON", qss)
        self.assertNotIn("@GLASS_HOVER", qss)
        self.assertNotIn("@GLASS_GREEN", qss)
        for family, selectors in UI_FAMILY_QSS_SELECTORS.items():
            with self.subTest(family=family):
                if family in {"metrics", "motion", "coverage", "palette"}:
                    self.assertFalse(selectors)
                    continue
                self.assertTrue(selectors)
                for selector in selectors:
                    self.assertIn(selector, qss)
        for family, selectors in UI_INTERACTION_QSS_SELECTORS.items():
            with self.subTest(states=family):
                for selector in selectors:
                    self.assertIn(selector, qss)

    def test_dialog_menu_and_scroll_composition_is_visible_in_dev_ui_index(self):
        patterns = {row[0]: re.compile(row[3]) for row in UI_MUTUALIZATION_TARGETS}
        for name, sample in (
            ("Fenêtres et popups classiques", "dialog.add_action_row(close)"),
            ("Fenêtres et popups classiques", "dialog.add_scroll_rows()"),
            ("Fenêtres et popups classiques", "AtlasImagePopup(source, parent)"),
            ("Fenêtres et popups classiques", "present_transient_dialog(owner, slot, dialog)"),
            ("Titres et sous-titres", "dialog.add_header('Titre')"),
            ("Onglets et sous-menus", "fill_unity_navigation_menu(menu, entries, open_tab)"),
            ("Scrollbars et resize", "self.add_scroll_rows()"),
            ("Scrollbars et resize", "configure_unity_scroll_area(QScrollArea())"),
        ):
            with self.subTest(name=name, sample=sample):
                self.assertRegex(sample, patterns[name])
        for module, source_snippet in (
            ("app/pages/craft_page.py", "configure_unity_scroll_area("),
            ("app/pages/organizer/organizer_ui.py", "configure_unity_scroll_area("),
            ("app/pages/dev_ui_page.py", "configure_unity_scroll_area("),
            ("app/modules/encyclopedia/views/shared_manual_guide_view.py",
             "configure_unity_scroll_area("),
        ):
            with self.subTest(consumer=module):
                content = (Path(__file__).resolve().parents[1] / module).read_text(
                    encoding="utf-8"
                )
                self.assertIn(source_snippet, content)
        self.assertIn("app/pages/craft_page.py", UI_CONSUMER_INDEX["Craft"]["paths"])
        self.assertIn("main.py", UI_CONSUMER_INDEX["Paramètres"]["paths"])

    def test_organizer_reuses_same_css_instead_of_widget_stylesheet(self):
        from app.pages.organizer.organizer_ui import OrganizerUiMixin
        source = inspect.getsource(OrganizerUiMixin.build_organizer_ui)
        self.assertNotIn("setStyleSheet(", source)
        self.assertIn('set_unity_widget_property(action, "atlasShortcutInset", True)', source)
        self.assertNotIn('action.setProperty("atlasShortcutInset", True)', source)
        self.assertIn("#organizerPage QFrame#card", ORGANIZER_STYLE_TEMPLATE)
        self.assertIn(
            '#organizerPage QPushButton[atlasShortcutInset="true"]',
            ORGANIZER_STYLE_TEMPLATE,
        )
        self.assertFalse(
            re.search(r"#[0-9a-fA-F]{6}\\b", ORGANIZER_STYLE_TEMPLATE),
            "Organizer is only allowed to use the canonical Unity color tokens",
        )
        self.assertIn("#organizerPage QFrame#card", atlas_stylesheet())

    def test_all_qt_consumers_inherit_global_qss_without_local_stylesheets(self):
        import ast
        for module, entry in UI_CONSUMER_INDEX.items():
            if entry["adapter"] == "tk":
                continue
            for filename in entry["paths"]:
                with self.subTest(module=module, filename=filename):
                    source = (REPO_ROOT / filename).read_text(encoding="utf-8")
                    tree = ast.parse(source)
                    local_styles = [
                        node for node in ast.walk(tree)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "setStyleSheet"
                    ]
                    if filename == "main.py":
                        # The shell owns the *application-wide* QSS, not a
                        # local skin. Splash transparency is an explicit
                        # one-off because that native window has no background.
                        permitted = {
                            'app.setStyleSheet(style)',
                            'self.setStyleSheet(style)',
                            'app.setStyleSheet(atlas_stylesheet())',
                            'splash.setStyleSheet("background: transparent;")',
                        }
                        expressions = {
                            ast.get_source_segment(source, call)
                            for call in local_styles
                        }
                        self.assertTrue(expressions <= permitted, expressions)
                        self.assertEqual(expressions, permitted)
                    else:
                        self.assertFalse(
                            local_styles, f"{filename}: local QSS bypasses UI Dev"
                        )
        self.assertNotIn("background: @GLASS_GREEN;", ORGANIZER_STYLE_TEMPLATE)
        self.assertNotIn("background: @ACTIVE_GRADIENT;", ORGANIZER_STYLE_TEMPLATE)
        self.assertNotIn("background: @RED_DARK;", ORGANIZER_STYLE_TEMPLATE)
        self.assertNotIn("#organizerPage QPushButton#primaryButton:hover",
                         ORGANIZER_STYLE_TEMPLATE)

    def test_glass_relief_is_consumed_in_actual_static_panels(self):
        from app.ui.unity_palette import UNITY_PANEL_SHADOW
        from app.ui.unity_skin import apply_unity_panel_shadow
        self.assertEqual(UNITY_PANEL_SHADOW, {
            "blur": 17, "vertical": 5, "alpha": 135,
        })
        signatures = {
            "app/pages/home_page.py": ("apply_unity_panel_shadow(card)",),
            "app/pages/craft_page.py": (
                "apply_unity_panel_shadow(self.craft_left_panel)",
                "apply_unity_panel_shadow(self.craft_right_panel)",
                "apply_unity_panel_shadow(self.jobs_panel)",
            ),
            "app/ui/world_scan_panel.py": (
                "apply_unity_panel_shadow(toolbar)",
                "apply_unity_panel_shadow(self.detail_panel)",
            ),
            "app/modules/encyclopedia/views/achievements_view.py": (
                "apply_unity_panel_shadow(panel)",
            ),
            "app/modules/encyclopedia/views/shared_manual_guide_view.py": (
                "AtlasGuideReadingNav(",
                "AtlasGuidePreparationPanel(",
                "AtlasGuideReadingHeader(",
                "AtlasGuideSheetHeader(",
            ),
            "app/ui/components.py": (
                "apply_unity_panel_shadow(self)",
            ),
        }
        for path, calls in signatures.items():
            content = (REPO_ROOT / path).read_text(encoding="utf-8")
            for call in calls:
                with self.subTest(path=path, call=call):
                    self.assertIn(call, content)
        self.assertIn("apply_unity_panel_shadow(panel)",
                      (REPO_ROOT / "app/pages/organizer/organizer_ui.py").read_text(encoding="utf-8"))

    def test_tk_launcher_keeps_unity_color_and_font_adapter(self):
        from app.distribution.launcher_ui import COLORS, FONT_FAMILY, button_options
        from app.ui.unity_palette import UNITY_PALETTE, UNITY_TYPOGRAPHY
        self.assertEqual(FONT_FAMILY, "Lexend")
        self.assertIn(FONT_FAMILY, UNITY_TYPOGRAPHY["FONT_FAMILY"])
        opts = button_options()
        self.assertEqual(opts["bg"], UNITY_PALETTE["PANEL_2"])
        self.assertEqual(opts["activebackground"], UNITY_PALETTE["PANEL_HOVER"])
        self.assertEqual(opts["activeforeground"], UNITY_PALETTE["GREEN"])
        self.assertEqual(COLORS["button_focus"], UNITY_PALETTE["GREEN_BORDER"])

    def test_sidebar_states_use_the_shared_16_percent_glass(self):
        """Sidebar and Dev UI preview must share one translucent state system."""
        qss = atlas_stylesheet()
        section = qss.split("/* Compact side-nav states", 1)[1].split(
            "#NavSeparator", 1
        )[0]
        glass = unity_glass_gradient()
        hover = unity_glass_gradient(
            "PANEL_HOVER", "PANEL_ACTIVE",
            top_alpha=199, bottom_alpha=206,
        )
        # Ordinary, active, hovered, pressed and disabled navigation
        # must not fall back to old opaque, per-sidebar color blocks.
        self.assertEqual(section.count(f"background: {glass};"), 2)
        self.assertEqual(section.count(f"background: {hover};"), 4)
        self.assertNotIn("background: #344978;", section)
        self.assertNotIn("background: #213154;", section)
        self.assertIn("border-bottom: 2px solid", section)

    def test_glass_gradient_is_shared_and_override_aware(self):
        from app.pages.organizer.glass_material import (
            GLASS_INTENSITY, unity_glass_gradient as organizer_gradient,
        )

        self.assertEqual(GLASS_INTENSITY, UNITY_GLASS_INTENSITY)
        self.assertEqual(organizer_gradient(), unity_glass_gradient())
        style = atlas_stylesheet({
            "PANEL_ACTIVE": "#112233",
            "PANEL_2": "#223344",
            "PANEL_HOVER": "#334455",
        })
        self.assertIn("stop:0 rgba(17, 34, 51, 243)", style)
        self.assertIn("stop:1 rgba(34, 51, 68, 246)", style)
        self.assertIn("stop:0 rgba(51, 68, 85, 246)", style)
        self.assertIn("#primaryButton:hover", style)
        self.assertNotIn("#organizerPage QPushButton#primaryButton:hover", style)


if __name__ == "__main__":
    unittest.main()
