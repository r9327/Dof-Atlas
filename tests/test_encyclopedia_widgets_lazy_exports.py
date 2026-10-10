from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WIDGETS_INIT = ROOT / "app/modules/encyclopedia/widgets/__init__.py"


class EncyclopediaWidgetLazyExportsTests(unittest.TestCase):
    def _module_without_qt(self) -> types.ModuleType:
        module = types.ModuleType("app.modules.encyclopedia.widgets")
        module.__file__ = str(WIDGETS_INIT)
        module.__path__ = [str(WIDGETS_INIT.parent)]
        source = WIDGETS_INIT.read_text(encoding="utf-8")
        exec(compile(source, str(WIDGETS_INIT), "exec"), module.__dict__)
        return module

    def test_public_widget_api_is_complete_without_importing_any_widget(self):
        # The facade module can be evaluated without PySide6 and without
        # importing one of its 19 concrete widgets.
        with patch("importlib.import_module") as imported:
            module = self._module_without_qt()
            imported.assert_not_called()
            self.assertEqual(len(module.__all__), 42)
            self.assertEqual(set(module.__all__), set(module._LAZY_EXPORT_MODULES))
            self.assertEqual(len(set(module._LAZY_EXPORT_MODULES.values())), 19)
            self.assertIn("QuestDetailView", dir(module))
            self.assertIn("AchievementDetailWidget", dir(module))

    def test_public_attribute_imports_once_and_preserves_type_identity(self):
        module = self._module_without_qt()
        canonical = object()
        with patch.object(module, "import_module", return_value=types.SimpleNamespace(
                QuestDetailView=canonical)) as imported:
            self.assertIs(getattr(module, "QuestDetailView"), canonical)
            self.assertIs(getattr(module, "QuestDetailView"), canonical)
            imported.assert_called_once_with(
                "app.modules.encyclopedia.widgets.quest_detail_view")
        with patch.object(module, "import_module") as imported:
            with self.assertRaises(AttributeError):
                getattr(module, "MissingAtlasWidget")
            imported.assert_not_called()

    def test_import_package_does_not_eager_load_ui_modules(self):
        code = (
            "import sys\n"
            "import app.modules.encyclopedia.widgets as widgets\n"
            "assert widgets.__all__\n"
            "assert 'app.modules.encyclopedia.widgets.quest_detail_view' not in sys.modules\n"
            "assert 'app.modules.encyclopedia.widgets.achievement_detail_widget' not in sys.modules\n"
            "assert 'app.modules.encyclopedia.widgets.dashboard' not in sys.modules\n"
        )
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                           text=True, timeout=20, env=os.environ.copy())
        self.assertEqual(p.returncode, 0, p.stdout + "\n" + p.stderr)

    @unittest.skipUnless(importlib.util.find_spec("PySide6") is not None,
                         "Real Qt contract needs installed PySide6")
    def test_representative_real_widget_exports_match_concrete_classes(self):
        from app.modules.encyclopedia import widgets
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView
        from app.modules.encyclopedia.widgets.guide_card import GuideCardDelegate
        from app.modules.encyclopedia.widgets.dashboard import FixedColumnSplitter

        self.assertIs(widgets.QuestDetailView, QuestDetailView)
        self.assertIs(widgets.GuideCardDelegate, GuideCardDelegate)
        self.assertIs(widgets.FixedColumnSplitter, FixedColumnSplitter)


if __name__ == "__main__":
    unittest.main()
