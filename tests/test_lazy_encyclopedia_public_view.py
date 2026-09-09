from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import app.modules.encyclopedia.views as views


class LazyEncyclopediaPublicViewTests(unittest.TestCase):
    def tearDown(self) -> None:
        views._REAL_ENCYCLOPEDIA_PAGE = None

    def test_clean_public_import_does_not_load_heavy_view_modules(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.modules.encyclopedia.views import EncyclopediaPage
print(json.dumps({
    "base": "app.modules.encyclopedia.views.encyclopedia_page" in sys.modules,
    "guides": "app.modules.encyclopedia.views.guides_view" in sys.modules,
    "achievements": "app.modules.encyclopedia.views.achievements_view" in sys.modules,
    "placeholder": "app.modules.encyclopedia.views.placeholder_view" in sys.modules,
    "proxy_name": EncyclopediaPage.__name__,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["proxy_name"], "EncyclopediaPage")
        self.assertFalse(payload["base"])
        self.assertFalse(payload["guides"])
        self.assertFalse(payload["achievements"])
        self.assertFalse(payload["placeholder"])

    def test_proxy_constructor_and_isinstance_preserve_shell_contract(self) -> None:
        class RealPage:
            def __init__(self, value: int = 0) -> None:
                self.value = value

        calls = 0

        def load():
            nonlocal calls
            calls += 1
            views._REAL_ENCYCLOPEDIA_PAGE = RealPage
            return RealPage

        with patch.object(views, "_load_encyclopedia_page_class", side_effect=load):
            first = views.EncyclopediaPage(7)
            second = views.EncyclopediaPage(9)

        self.assertIsInstance(first, RealPage)
        self.assertIsInstance(second, RealPage)
        self.assertEqual(first.value, 7)
        self.assertEqual(second.value, 9)
        self.assertIsInstance(first, views.EncyclopediaPage)
        self.assertIsInstance(second, views.EncyclopediaPage)
        self.assertEqual(calls, 2)

    def test_loaded_real_class_is_reused_by_real_loader(self) -> None:
        class RealPage:
            pass

        views._REAL_ENCYCLOPEDIA_PAGE = RealPage
        with patch(
            "app.modules.encyclopedia.views.encyclopedia_page.EncyclopediaPage",
            create=True,
        ) as imported:
            self.assertIs(views._load_encyclopedia_page_class(), RealPage)
            imported.assert_not_called()

    def test_explicit_guides_access_remains_available(self) -> None:
        from app.modules.encyclopedia.views import GuidesView
        from app.modules.encyclopedia.views.guides_view import GuidesView as RealGuidesView

        self.assertIs(GuidesView, RealGuidesView)
        self.assertTrue(views._GUIDE_VIEW_LOADED)


if __name__ == "__main__":
    unittest.main()
