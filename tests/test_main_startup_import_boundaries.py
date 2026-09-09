from __future__ import annotations

import os
import subprocess
import sys


_FORBIDDEN_STARTUP_MODULES = (
    "app.modules.encyclopedia.services.quest_graph_service",
    "app.modules.encyclopedia.views.encyclopedia_page",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "app.input.hotkeys",
    "app.input.mouse_hooks",
    "app.macros.auto_group",
    "app.macros.direction",
    "app.macros.switch_character",
    "app.macros.switch_click",
    "app.macros.travel",
    "app.macros.zaap",
)


def test_import_main_keeps_heavy_runtime_modules_out_of_startup() -> None:
    module_names = repr(_FORBIDDEN_STARTUP_MODULES)
    script = f"""
import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import main
names = {module_names}
loaded = [name for name in names if name in sys.modules]
if loaded:
    print('unexpected startup imports:', *loaded, sep='\\n')
    raise SystemExit(9)
raise SystemExit(0)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
