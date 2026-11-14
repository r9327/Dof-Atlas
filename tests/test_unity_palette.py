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


    def test_dev_ui_index_covers_all_families_and_original_style_owners(self) -> None:
        from app.ui.unity_palette import (
            UNITY_UI_CONSUMERS, UNITY_UI_FAMILY_INDEX,
        )

        self.assertEqual(len(UNITY_UI_FAMILY_INDEX), 22)
        self.assertEqual(len(UNITY_UI_CONSUMERS), 12)
        self.assertEqual(len({
            item["title"] for item in UNITY_UI_FAMILY_INDEX.values()
        }), 22)
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
        self.assertEqual(UNITY_ORGANIZER_METRICS_PX, expected)
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
