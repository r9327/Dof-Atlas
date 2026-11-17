"""Pure-Python contracts for the only Unity palette: runnable without PySide6."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.ui.unity_palette import (
    UNITY_COLOR_ALIAS_ROLES, UNITY_ICON_NAMES, UNITY_MAIN_ROLES,
    UNITY_CONTENT_TYPOGRAPHY_PX, UNITY_ORGANIZER_METRICS_PX,
    UNITY_PAINTED_UI_ROLES,
    UNITY_PALETTE, UNITY_SIZES_PX, UNITY_SPACING_PX, UNITY_TYPOGRAPHY,
    UNITY_UI_USAGE,
    launcher_colors, resolve_unity_colors, unity_painted_ui_color,
)


class UnityPaletteTests(unittest.TestCase):
    def test_all_tk_roles_follow_canonical_unity_values(self) -> None:
        self.assertEqual(launcher_colors(), {
            "background": UNITY_PALETTE["BG"],
            "panel": UNITY_PALETTE["PANEL"],
            "border": UNITY_PALETTE["BORDER"],
            "track": UNITY_PALETTE["PANEL_2"],
            "text": UNITY_PALETTE["TEXT"],
            "muted": UNITY_PALETTE["TEXT_MUTED"],
            "accent": UNITY_PALETTE["GREEN"],
            "accent_hover": UNITY_PALETTE["GREEN_HOVER"],
            "button_bg": UNITY_PALETTE["PANEL_2"],
            "button_hover": UNITY_PALETTE["PANEL_HOVER"],
            "button_fg": UNITY_PALETTE["TEXT_SOFT"],
            "button_hover_fg": UNITY_PALETTE["GREEN"],
            "button_border": UNITY_PALETTE["BORDER_SOFT"],
            "button_focus": UNITY_PALETTE["GREEN_BORDER"],
            "disabled_text": UNITY_PALETTE["TEXT_DISABLED"],
        })

    def test_override_changes_tk_colors_without_mutating_unity_palette(self) -> None:
        saved = dict(UNITY_PALETTE)
        preview = {**UNITY_PALETTE, "GREEN": "#123456", "PANEL_2": "#654321"}
        colors = launcher_colors(preview)
        self.assertEqual(colors["accent"], "#123456")
        self.assertEqual(colors["track"], "#654321")
        self.assertEqual(UNITY_PALETTE, saved)

    def test_guide_roles_follow_the_same_ui_colors(self) -> None:
        colors = resolve_unity_colors()
        self.assertEqual(
            {name: colors[name] for name in UNITY_COLOR_ALIAS_ROLES},
            {name: colors[parent] for name, parent in UNITY_COLOR_ALIAS_ROLES.items()},
        )
        self.assertLess(len(set(colors.values())), len(colors))
        preview = resolve_unity_colors({
            "PANEL": "#112233",
            "BORDER": "#334455",
        })
        self.assertEqual(preview["GUIDE_COMPACT_SURFACE"], "#112233")
        self.assertEqual(preview["GUIDE_NAV_BORDER"], "#334455")
        self.assertEqual(
            preview["GUIDE_PREPARATION_ROW"], colors["PANEL_2"]
        )
        explicit = resolve_unity_colors({
            "PANEL": "#112233", "GUIDE_COMPACT_SURFACE": "#ABCDEF"
        })
        self.assertEqual(explicit["GUIDE_COMPACT_SURFACE"], "#ABCDEF")
        self.assertEqual(UNITY_PALETTE["PANEL"], "#1B2746")

    def test_ui_places_and_sizes_use_single_source(self) -> None:
        self.assertEqual(len(UNITY_MAIN_ROLES), 10)
        self.assertTrue(set(UNITY_MAIN_ROLES).issubset(UNITY_PALETTE))
        self.assertEqual(len(UNITY_UI_USAGE), 10)
        self.assertTrue(all(
            a in UNITY_PALETTE and b in UNITY_PALETTE
            for _caption, a, b in UNITY_UI_USAGE
        ))
        self.assertEqual(UNITY_SIZES_PX["control_compact"], 24)
        self.assertEqual(UNITY_SIZES_PX["control_normal"], 32)
        self.assertEqual(UNITY_SIZES_PX["icon_large"], 24)
        self.assertEqual(UNITY_SIZES_PX["top_nav_height"], 58)
        self.assertEqual(UNITY_SPACING_PX["md"], 8)
        self.assertEqual(UNITY_SPACING_PX["3xl"], 24)
        self.assertEqual(UNITY_TYPOGRAPHY["FONT_BODY"], "12px")
        self.assertEqual(UNITY_PALETTE["YELLOW"], "#D6B22D")
        self.assertEqual(len(UNITY_ICON_NAMES), 8)



    def test_organizer_visual_geometry_has_a_single_existing_index(self) -> None:
        from app.ui.unity_palette import UNITY_ORGANIZER_METRICS_PX

        geometry = UNITY_ORGANIZER_METRICS_PX
        self.assertEqual(geometry["mode_switch_width"], 396)
        self.assertEqual(geometry["mode_button_width"], 194)
        self.assertEqual(geometry["control_panel_height"], 146)
        self.assertEqual(geometry["key_badge_width"], 52)
        self.assertEqual(geometry["root_spacing"], 12)

    def test_character_compat_geometry_is_covered_by_dev_ui(self) -> None:
        from app.ui.unity_palette import (
            UNITY_MODULE_GEOMETRY_PX, UNITY_MODULE_GEOMETRY_OWNERS,
        )
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["character_compat"]["equipment_slot_box"],
            62,
        )
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_OWNERS["character_compat"],
            "app/pages/_character_page_impl.py",
        )

    def test_guide_catalogue_card_metrics_are_indexed_without_new_dimensions(self) -> None:
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        geometry = UNITY_MODULE_GEOMETRY_PX["guide_cards"]
        self.assertEqual(geometry["featured_compact_margins"], (9, 6, 9, 6))
        self.assertEqual(geometry["featured_compact_artwork_box"], 28)
        self.assertEqual(geometry["featured_pair_horizontal_min_width"], 580)
        self.assertEqual(geometry["library_columns_horizontal_min_width"], 730)
        self.assertEqual(geometry["library_columns_spacing"], 14)
        self.assertEqual(geometry["library_left_max_width"], 295)
        self.assertEqual(geometry["library_left_stacked_max_height"], 220)

    def test_guides_and_quests_reuse_existing_unity_spacing_roles(self) -> None:
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX, UNITY_SPACING_PX

        self.assertEqual(UNITY_SPACING_PX["sm"], 6)
        self.assertEqual(UNITY_SPACING_PX["md"], 8)
        self.assertEqual(UNITY_SPACING_PX["xxs"], 2)
        detail = UNITY_MODULE_GEOMETRY_PX["quest_detail"]
        self.assertEqual(detail["prerequisite_row_spacing"], 7)
        self.assertEqual(detail["prerequisite_marker_width"], 18)
        root = Path(__file__).resolve().parents[1]
        for name in (
            "app/modules/encyclopedia/views/guide_catalog_view.py",
            "app/pages/_quests_page_impl.py",
        ):
            self.assertIn("UNITY_SPACING_PX", (root / name).read_text(encoding="utf-8"))

    def test_quest_detail_keeps_existing_splitter_sizes(self) -> None:
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        geometry = UNITY_MODULE_GEOMETRY_PX["quest_detail"]
        self.assertEqual(geometry["initial_splitter_sizes"], (680, 300))
        self.assertEqual(geometry["right_min_width"], 240)
        self.assertEqual(geometry["right_max_width"], 380)

    def test_launcher_sizes_are_indexed_as_existing_tk_values(self) -> None:
        from app.ui.unity_palette import (
            UNITY_MODULE_GEOMETRY_PX, UNITY_MODULE_GEOMETRY_OWNERS,
        )
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["launcher"]["normal_window_size"],
            (470, 252),
        )
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["launcher"]["install_window_size"],
            (520, 425),
        )
        self.assertEqual(
            set(UNITY_MODULE_GEOMETRY_PX),
            set(UNITY_MODULE_GEOMETRY_OWNERS),
        )

    def test_quests_and_achievement_filters_keep_indexed_geometry(self) -> None:
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        quests = UNITY_MODULE_GEOMETRY_PX["quests"]
        self.assertEqual(quests["hierarchy_open_width"], 300)
        self.assertEqual(quests["hierarchy_collapsed_width"], 44)
        self.assertEqual(quests["search_min_height"], 34)
        self.assertEqual(quests["detail_initial_width"], 900)
        filters = UNITY_MODULE_GEOMETRY_PX["achievement_filters"]
        self.assertEqual(filters["page_margins"], (8, 8, 8, 8))
        self.assertEqual(filters["card_margins"], (7, 6, 7, 6))

    def test_startup_and_equipment_geometry_are_indexed_without_new_sizes(self) -> None:
        from app.ui.unity_palette import (
            UNITY_MODULE_GEOMETRY_OWNERS, UNITY_MODULE_GEOMETRY_PX,
        )

        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["equipment"]["page_margins"],
            (18, 16, 18, 18),
        )
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["preload_popup"]["dialog_width"], 470,
        )
        self.assertEqual(
            UNITY_MODULE_GEOMETRY_PX["preload_popup"]["logo_box"], 64,
        )
        self.assertEqual(
            set(UNITY_MODULE_GEOMETRY_OWNERS),
            set(UNITY_MODULE_GEOMETRY_PX),
        )

    def test_home_character_world_scan_measurements_are_indexed_without_resizing(self) -> None:
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        home = UNITY_MODULE_GEOMETRY_PX["home"]
        self.assertEqual(home["tracking_icon_width"], 20)
        self.assertEqual(home["tracking_name_min_width"], 92)
        self.assertEqual(home["tracking_bar_min_width"], 62)
        self.assertEqual(home["tracking_value_min_width"], 46)
        self.assertEqual(home["left_column_spacing"], 16)
        self.assertEqual(home["right_column_spacing"], 12)
        character = UNITY_MODULE_GEOMETRY_PX["character"]
        self.assertEqual(character["equipment_panel_margins"], (8, 6, 8, 8))
        self.assertEqual(character["stats_panel_margins"], (10, 8, 10, 10))
        world = UNITY_MODULE_GEOMETRY_PX["world_scan"]
        self.assertEqual(world["toolbar_button_height"], 30)
        self.assertEqual(world["world_menu_item_height"], 28)

    def test_home_and_world_scan_extra_geometry_is_indexed(self) -> None:
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        home = UNITY_MODULE_GEOMETRY_PX["home"]
        self.assertEqual(home["identity_margins"], (0, 4, 0, 2))
        self.assertEqual(home["network_card_margins"], (15, 10, 15, 10))
        self.assertEqual(home["detail_row_margins"], (5, 9, 5, 9))
        self.assertEqual(home["detail_row_icon_width"], 28)
        world = UNITY_MODULE_GEOMETRY_PX["world_scan"]
        self.assertEqual(world["header_accent_size"], (4, 24))
        self.assertEqual(world["toolbar_margins"], (10, 8, 10, 8))
        self.assertEqual(world["detail_margins"], (12, 7, 12, 7))
        self.assertEqual(world["menu_divider_height"], 1)

    def test_window_and_layout_reference_sizes_are_qt_free(self) -> None:
        from app.constants import (
            DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT,
            MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT,
        )
        from app.ui.unity_palette import (
            UNITY_CONTROL_SIZES_PX, UNITY_LAYOUT_BREAKPOINTS_PX,
            UNITY_LAYOUT_SIZES_PX, UNITY_WINDOW_PRESETS_PX,
            unity_responsive_columns,
        )
        self.assertEqual(
            (DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT),
            UNITY_WINDOW_PRESETS_PX["standard"],
        )
        self.assertEqual(
            (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT),
            UNITY_WINDOW_PRESETS_PX["compact"],
        )
        self.assertEqual(len(UNITY_WINDOW_PRESETS_PX), 4)
        self.assertEqual(UNITY_LAYOUT_SIZES_PX["module_gap"], 10)
        self.assertEqual(UNITY_CONTROL_SIZES_PX["progress_primary"], 11)
        two = UNITY_LAYOUT_BREAKPOINTS_PX["two_columns_min"]
        three = UNITY_LAYOUT_BREAKPOINTS_PX["three_columns_min"]
        self.assertLess(two, three)
        self.assertEqual(
            [unity_responsive_columns(w) for w in (0, two - 1, two, three - 1, three)],
            [1, 1, 2, 2, 3],
        )

    def test_stable_layout_metrics_interpolate_between_four_unforced_sizes(self) -> None:
        from app.ui.unity_palette import (
            UNITY_LAYOUT_PROFILE_PX, UNITY_WINDOW_PRESETS_PX,
            unity_layout_metrics,
        )
        self.assertEqual(
            tuple(UNITY_LAYOUT_PROFILE_PX), tuple(UNITY_WINDOW_PRESETS_PX)
        )
        for name, (width, _height) in UNITY_WINDOW_PRESETS_PX.items():
            self.assertEqual(unity_layout_metrics(width), UNITY_LAYOUT_PROFILE_PX[name])
        self.assertEqual(unity_layout_metrics(0), UNITY_LAYOUT_PROFILE_PX["compact"])
        self.assertEqual(unity_layout_metrics(2500), UNITY_LAYOUT_PROFILE_PX["full_hd"])
        for left_key, right_key in zip(
            tuple(UNITY_WINDOW_PRESETS_PX)[:-1],
            tuple(UNITY_WINDOW_PRESETS_PX)[1:],
        ):
            left = UNITY_WINDOW_PRESETS_PX[left_key][0]
            right = UNITY_WINDOW_PRESETS_PX[right_key][0]
            middle = unity_layout_metrics((left + right) // 2)
            for metric in ("page_margin", "module_padding", "module_gap"):
                self.assertLessEqual(
                    UNITY_LAYOUT_PROFILE_PX[left_key][metric],
                    middle[metric],
                )
                self.assertLessEqual(
                    middle[metric], UNITY_LAYOUT_PROFILE_PX[right_key][metric]
                )


    def test_shared_combo_and_dialog_geometry_come_from_indexed_tokens(self) -> None:
        from app.ui.unity_palette import (
            UNITY_CONTROL_LIMITS, UNITY_CONTROL_SIZES_PX,
            UNITY_LAYOUT_SIZES_PX,
        )
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        code = (root / "app/ui/components.py").read_text(encoding="utf-8")
        self.assertIn('UNITY_CONTROL_LIMITS["dropdown_visible_rows"]', code)
        self.assertIn('UNITY_CONTROL_SIZES_PX["dropdown_row"]', code)
        self.assertIn('UNITY_CONTROL_SIZES_PX["dialog_header_icon_box"]', code)
        self.assertIn('UNITY_CONTROL_SIZES_PX["dialog_header_icon_artwork"]', code)
        self.assertIn('UNITY_LAYOUT_SIZES_PX["dialog_header_gap"]', code)
        self.assertEqual(UNITY_CONTROL_LIMITS["dropdown_visible_rows"], 8)
        self.assertGreater(
            UNITY_CONTROL_SIZES_PX["dialog_header_icon_box"],
            UNITY_CONTROL_SIZES_PX["dialog_header_icon_artwork"],
        )
        self.assertGreater(UNITY_LAYOUT_SIZES_PX["dialog_header_gap"], 0)


    def test_guide_disclosure_has_single_painter_and_indexed_chevron_size(self) -> None:
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX

        source = (Path(__file__).resolve().parents[1] / "app/ui/components.py").read_text(
            encoding="utf-8"
        )
        parsed = ast.parse(source)
        disclosure = next(
            node for node in parsed.body
            if isinstance(node, ast.ClassDef) and node.name == "AtlasGuideDisclosure"
        )
        painters = [
            child for child in disclosure.body
            if isinstance(child, ast.FunctionDef) and child.name == "paintEvent"
        ]
        self.assertEqual(len(painters), 1)
        paint_code = ast.get_source_segment(source, painters[0])
        self.assertIn("QIcon.Normal", paint_code)
        self.assertNotIn("QIcon.Disabled", paint_code)
        self.assertIn('UNITY_CONTROL_SIZES_PX["progress_toggle_icon"]', source)
        self.assertEqual(UNITY_CONTROL_SIZES_PX["progress_toggle_icon"], 14)

    def test_real_guide_header_and_dev_ui_share_all_progress_dimensions(self) -> None:
        """The real Guide renderer must consume the very same metrics as Dev UI."""
        from pathlib import Path
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "app/modules/encyclopedia/views/shared_manual_guide_view.py"
        ).read_text(encoding="utf-8")
        gallery = (root / "app/pages/dev_ui_page.py").read_text(encoding="utf-8")
        for key in (
            "progress_primary", "progress_secondary",
            "progress_toggle_width", "progress_toggle_height",
            "guide_quantity_width", "guide_validation_width",
        ):
            with self.subTest(token=key):
                usage = f'UNITY_CONTROL_SIZES_PX["{key}"]'
                self.assertIn(usage, source)
                self.assertIn(usage, gallery)
                self.assertGreater(UNITY_CONTROL_SIZES_PX[key], 0)

    def test_indexed_module_dimensions_match_existing_constraints(self) -> None:
        from pathlib import Path
        from app.ui.unity_palette import (
            UNITY_MODULE_GEOMETRY_OWNERS, UNITY_MODULE_GEOMETRY_PX,
            UNITY_ORGANIZER_METRICS_PX,
        )
        self.assertEqual(set(UNITY_MODULE_GEOMETRY_PX), set(UNITY_MODULE_GEOMETRY_OWNERS))
        self.assertGreaterEqual(sum(len(v) for v in UNITY_MODULE_GEOMETRY_PX.values()), 70)
        root = Path(__file__).resolve().parents[1]
        for module, values in UNITY_MODULE_GEOMETRY_PX.items():
            with self.subTest(module=module):
                self.assertTrue((root / UNITY_MODULE_GEOMETRY_OWNERS[module]).is_file())
                for key, size in values.items():
                    numbers = size if isinstance(size, tuple) else (size,)
                    self.assertTrue(all(type(n) is int and n > 0 for n in numbers), key)
        self.assertEqual(UNITY_MODULE_GEOMETRY_PX["home"]["portrait_box"], 98)
        self.assertEqual(UNITY_MODULE_GEOMETRY_PX["character"]["equipment_slot_box"], 64)
        self.assertEqual(UNITY_MODULE_GEOMETRY_PX["craft"]["leveling_dialog_size"], (660, 560))
        self.assertEqual(UNITY_MODULE_GEOMETRY_PX["achievements"]["initial_splitter_sizes"], (245, 315, 640))
        self.assertEqual(UNITY_ORGANIZER_METRICS_PX["mode_switch_width"], 396)

    def test_dev_ui_index_covers_all_families_and_original_style_owners(self) -> None:
        from app.ui.unity_palette import (
            UNITY_UI_CONSUMERS, UNITY_UI_FAMILY_INDEX,
        )

        self.assertGreaterEqual(len(UNITY_UI_FAMILY_INDEX), 23)
        self.assertEqual(len(UNITY_UI_CONSUMERS), 12)
        self.assertEqual(len({
            item["title"] for item in UNITY_UI_FAMILY_INDEX.values()
        }), len(UNITY_UI_FAMILY_INDEX))
        for family, item in UNITY_UI_FAMILY_INDEX.items():
            with self.subTest(family=family):
                self.assertTrue(item["title"])
                self.assertTrue(item["components"])
                self.assertIn("app/", item["style_owner"])
                self.assertIn(
                    item["scope"], {"shared", "module", "prototype", "audit"},
                )
        self.assertEqual(UNITY_UI_FAMILY_INDEX["motion"]["scope"], "prototype")
        self.assertEqual(UNITY_UI_FAMILY_INDEX["guides"]["scope"], "module")
        self.assertEqual(UNITY_UI_FAMILY_INDEX["palette"]["scope"], "shared")
        from app.ui.unity_palette import UNITY_UI_UNIFICATION_CONTRACT
        self.assertGreaterEqual(len(UNITY_UI_UNIFICATION_CONTRACT), 39)
        self.assertEqual({family for _label, family in
                          UNITY_UI_UNIFICATION_CONTRACT},
                         set(UNITY_UI_FAMILY_INDEX))
        self.assertIn(
            "AtlasPageTitle", UNITY_UI_FAMILY_INDEX["surfaces"]["components"],
        )
        self.assertIn("Launcher", UNITY_UI_CONSUMERS)


    def test_painted_ui_colors_are_indexed_unity_roles(self) -> None:
        from app.ui.ui_registry import UI_FAMILY_PAINTED_ROLES, validate_ui_index

        validate_ui_index()
        listed = [role for family in UI_FAMILY_PAINTED_ROLES.values()
                  for role in family]
        self.assertEqual(set(listed), set(UNITY_PAINTED_UI_ROLES))
        self.assertEqual(len(listed), len(set(listed)))
        for name, token in UNITY_PAINTED_UI_ROLES.items():
            with self.subTest(name=name):
                self.assertIn(token, UNITY_PALETTE)
                self.assertEqual(unity_painted_ui_color(name), UNITY_PALETTE[token])
        self.assertEqual(
            unity_painted_ui_color("organizer.favorite", {"YELLOW": "#123456"}),
            "#123456",
        )
        with self.assertRaises(KeyError):
            unity_painted_ui_color("not-a-real-painter")

    def test_organizer_dimensions_use_indexed_values_without_resize(self) -> None:
        expected = {
            "card_padding": 12, "card_spacing": 10,
            "button_height": 30, "input_height": 32,
            "key_badge_height": 22, "key_badge_min_width": 34,
            "favorite_chip_height": 28, "character_slot_height": 36,
            "stop_button_height": 34,
        }
        # New semantic dimensions may be indexed before their individual
        # Organizer consumers migrate. Preserve the exact historical contract
        # for the nine already-connected shared roles.
        self.assertEqual(
            {key: UNITY_ORGANIZER_METRICS_PX[key] for key in expected}, expected
        )
        source = (
            Path(__file__).resolve().parents[1]
            / "app/pages/organizer/common.py"
        ).read_text(encoding="utf-8")
        for role in expected:
            self.assertIn(f'UNITY_ORGANIZER_METRICS_PX["{role}"]', source)
        self.assertEqual(
            UNITY_ORGANIZER_METRICS_PX["input_height"],
            UNITY_SIZES_PX["control_normal"],
        )

    def test_painted_ui_does_not_use_private_hex_qcolors(self) -> None:
        # Imported Qt artwork stays in its original colors; only custom
        # QPainter UI glyphs must resolve the canonical semantic palette.
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "main.py", "app/pages/organizer/organizer_ui.py",
            "app/ui/world_scan_panel.py",
        ):
            with self.subTest(source=relative):
                source = (root / relative).read_text(encoding="utf-8")
                self.assertNotIn('QColor("#', source)
                self.assertNotIn("QColor('#", source)

    def test_world_scan_and_shell_use_indexed_shared_roles(self) -> None:
        root = Path(__file__).resolve().parents[1]
        world = (root / "app/ui/world_scan_panel.py").read_text(encoding="utf-8")
        shell = (root / "main.py").read_text(encoding="utf-8")
        for role, token in (
            ("world_scan.placeholder", "PANEL"),
            ("world_scan.planet_outline", "TEXT"),
            ("world_scan.planet_fill", "GREEN_DARK"),
        ):
            with self.subTest(role=role):
                self.assertEqual(UNITY_PAINTED_UI_ROLES[role], token)
                self.assertIn(f'unity_painted_ui_color("{role}")', world)
                self.assertEqual(
                    unity_painted_ui_color(role, {token: "#123456"}), "#123456",
                )
        self.assertIn('AtlasStatusBadge(badge, state="blocked")', shell)
        self.assertNotIn('setObjectName("HomePlaceholderBadge")', shell)

    def test_shared_button_consumers_use_canonical_variants(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = (
            "app/pages/craft_page.py",
            "app/pages/_quests_page_impl.py",
            "app/modules/encyclopedia/views/guide_ultime_universal_view.py",
        )
        for path in paths:
            with self.subTest(path=path):
                source = (root / path).read_text(encoding="utf-8")
                for name in (
                    "PrimaryActionButton", "SecondaryButton", "ActiveButton",
                    "GuideBreadcrumbButton",
                ):
                    self.assertNotIn(f'.setObjectName("{name}")', source)
        craft = (root / paths[0]).read_text(encoding="utf-8")
        quests = (root / paths[1]).read_text(encoding="utf-8")
        guides = (root / paths[2]).read_text(encoding="utf-8")
        self.assertIn('variant="primary"', craft)
        self.assertIn('variant="secondary"', craft)
        self.assertIn('button.set_variant("selected")', craft)
        self.assertEqual(quests.count('variant="guide_breadcrumb"'), 3)
        self.assertIn('variant="guide_breadcrumb"', guides)

    def test_rich_text_and_character_fonts_share_unity_metrics(self) -> None:
        self.assertEqual(UNITY_CONTENT_TYPOGRAPHY_PX, {
            "quest_h1": 22,
            "quest_h2": 15,
            "quest_h3": 13,
            "character_score_compact": 18,
            "character_score_regular": 23,
        })
        from app.ui.unity_palette import UNITY_TYPOGRAPHY
        self.assertEqual(
            UNITY_TYPOGRAPHY["FONT_CONTENT_H3"],
            f'{UNITY_CONTENT_TYPOGRAPHY_PX["quest_h3"]}px',
        )
        root = Path(__file__).resolve().parents[1]
        sources = {
            "app/pages/_quests_page_impl.py": (
                "@FONT_BODY", "@FONT_CONTENT_H1",
                "@FONT_CONTENT_H2", "@FONT_CONTENT_H3",
            ),
            "app/modules/encyclopedia/views/guides_view.py": (
                "@FONT_CONTENT_H3", "color:@TEXT_SOFT", "color:@YELLOW",
            ),
            "app/pages/character_page.py": (
                "UNITY_CONTENT_TYPOGRAPHY_PX[role]",
            ),
        }
        for relative, required in sources.items():
            with self.subTest(file=relative):
                content = (root / relative).read_text(encoding="utf-8")
                for expected in required:
                    self.assertIn(expected, content)
                self.assertNotIn("color:#eee7fb", content)
                self.assertNotIn("color:#e7bf63", content)

    def test_color_module_does_not_import_qt_or_game_runtime(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app/ui/unity_palette.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(name.startswith(("PySide6", "app.")) for name in imports))


if __name__ == "__main__":
    unittest.main()
