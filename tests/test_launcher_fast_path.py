from __future__ import annotations

import unittest
from pathlib import Path


class LauncherFastPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = (
            Path(__file__).resolve().parents[1] / "DOFUS.bat"
        ).read_text(encoding="utf-8")

    def test_launcher_uses_single_environment_and_syntax_preflight(self) -> None:
        self.assertEqual(self.launcher.count("-m app.startup_preflight"), 1)
        self.assertNotIn(":check_required_modules", self.launcher)
        self.assertNotIn('-m py_compile "%APP_SCRIPT%"', self.launcher)
        self.assertIn('call :error "MODULES_MISSING"', self.launcher)
        self.assertIn('call :error "SYNTAX_FAILED"', self.launcher)
        self.assertIn('if "%PREFLIGHT_CODE%"=="10"', self.launcher)
        self.assertIn('if "%PREFLIGHT_CODE%"=="20"', self.launcher)

    def test_launcher_does_not_import_qtwebengine_itself(self) -> None:
        marker = "from PySide6.QtWebEngineWidgets import QWebEngineView"
        self.assertNotIn(marker, self.launcher)

    def test_launcher_has_no_cosmetic_powershell_preprocess(self) -> None:
        self.assertNotIn("call :fit_console", self.launcher)
        self.assertNotIn(":fit_console", self.launcher)
        self.assertNotIn("powershell.exe", self.launcher.casefold())

    def test_launcher_keeps_the_main_ui_process_unprivileged(self) -> None:
        self.assertNotIn("call :ensure_admin", self.launcher)
        self.assertNotIn(":ensure_admin", self.launcher)
        self.assertNotIn("-Verb RunAs", self.launcher)

    def test_launcher_reuses_python_313_probe_for_version_logging(self) -> None:
        self.assertNotIn('"%PYTHON_EXE%" --version', self.launcher)
        self.assertIn("print(sys.version.split()[0]) if ok else None", self.launcher)
        self.assertIn('>> "%LOG_FILE%" 2>&1', self.launcher)

    def test_launcher_still_uses_supported_python_and_pythonw(self) -> None:
        self.assertIn('ok=sys.version_info[0] == 3 and sys.version_info[1] == 13', self.launcher)
        self.assertIn('start "" "%PYTHONW_EXE%" "%APP_SCRIPT%"', self.launcher)

    def test_launcher_hides_only_root_technical_entries_after_app_launch(self) -> None:
        self.assertIn("call :tidy_root_view", self.launcher)
        self.assertIn(":tidy_root_view", self.launcher)
        self.assertGreater(
            self.launcher.index("call :tidy_root_view"),
            self.launcher.index('start "" "%PYTHONW_EXE%" "%APP_SCRIPT%"'),
        )
        for entry in (
            "AGENTS.md",
            "AI_CONTEXT.md",
            "DEVELOPMENT_GUARDRAILS.md",
            "GRAPHIFY.md",
            "PHASE_CERTIFICATION.md",
            "ROAD_IA.md",
            "launch.py",
            "main.py",
            "requirements-pyside.txt",
            "sitecustomize.py",
        ):
            self.assertIn(f'"{entry}"', self.launcher)
        for directory in (".ai", ".githooks", ".github"):
            self.assertIn(f'"{directory}"', self.launcher)
        self.assertIn('attrib +h "%ROOT%%%~F"', self.launcher)
        self.assertIn('attrib +h "%ROOT%%%~D"', self.launcher)
        self.assertIn('attrib -h "%ROOT%DOFUS.bat"', self.launcher)

    def test_root_cleanup_preserves_canonical_root_paths(self) -> None:
        self.assertIn('set "APP_SCRIPT=%ROOT%launch.py"', self.launcher)
        self.assertNotIn("move ", self.launcher.casefold())
        self.assertNotIn("ren ", self.launcher.casefold())


if __name__ == "__main__":
    unittest.main()

