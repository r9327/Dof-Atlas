from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class MainImportStartupBoundaryTests(unittest.TestCase):
    def test_import_main_keeps_lazy_runtime_families_unloaded(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import main
names = (
    "app.pages.quests_page",
    "app.modules.encyclopedia.views.encyclopedia_page",
    "app.modules.encyclopedia.views.guides_view",
    "app.modules.encyclopedia.views.achievements_view",
    "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service",
    "app.modules.encyclopedia.services.guide_auto_validation_contract",
    "app.modules.encyclopedia.providers.guide_provider",
    "app.modules.encyclopedia.providers.dofus_item_provider",
    "local_dofus_data.data_store",
    "local_dofus_data.repositories",
    "app.network.windows_capture",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
)
print(json.dumps({name: name in sys.modules for name in names}))
'''
        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        loaded = sorted(name for name, present in payload.items() if present)
        self.assertEqual(loaded, [])

    def test_import_main_keeps_windows_embed_api_uninitialized(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import main
import app.windows_embed as windows_embed
print(json.dumps({
    "ready": bool(getattr(windows_embed, "_WINDOWS_API_READY", False)),
    "loading": bool(getattr(windows_embed, "_WINDOWS_API_LOADING", False)),
}))
'''
        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["ready"])
        self.assertFalse(payload["loading"])


if __name__ == "__main__":
    unittest.main()
