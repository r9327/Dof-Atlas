from __future__ import annotations

import unittest
from unittest.mock import patch

import app.ui.theme as theme


class ThemeRuntimeCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        theme.clear_theme_cache()

    def tearDown(self) -> None:
        theme.clear_theme_cache()

    def test_renderer_is_canonical_in_theme_module(self) -> None:
        self.assertEqual(theme.render_theme_template.__module__, "app.ui.theme")

    def test_static_template_is_rendered_only_once(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_renderer(template: str, overrides=None) -> str:
            calls.append((template, overrides))
            return f"rendered:{template}"

        with patch.object(theme, "_render_theme_template", side_effect=fake_renderer):
            first = theme.render_theme_template("color:@TEXT;")
            second = theme.render_theme_template("color:@TEXT;")

        self.assertEqual(first, "rendered:color:@TEXT;")
        self.assertEqual(second, first)
        self.assertEqual(calls, [("color:@TEXT;", None)])

    def test_dynamic_overrides_bypass_static_cache(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_renderer(template: str, overrides=None) -> str:
            calls.append((template, overrides))
            return "dynamic"

        overrides = {"TEXT": "#ffffff"}

        with patch.object(theme, "_render_theme_template", side_effect=fake_renderer):
            self.assertEqual(theme.render_theme_template("color:@TEXT;", overrides), "dynamic")
            self.assertEqual(theme.render_theme_template("color:@TEXT;", overrides), "dynamic")
        self.assertEqual(len(calls), 2)
        self.assertIs(calls[0][1], overrides)
        self.assertIs(calls[1][1], overrides)

    def test_atlas_stylesheet_reuses_cached_static_template(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_renderer(template: str, overrides=None) -> str:
            calls.append((template, overrides))
            return "atlas-style"

        with patch.object(theme, "_render_theme_template", side_effect=fake_renderer):
            self.assertEqual(theme.atlas_stylesheet(), "atlas-style")
            self.assertEqual(theme.atlas_stylesheet(), "atlas-style")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0][1])


if __name__ == "__main__":
    unittest.main()
