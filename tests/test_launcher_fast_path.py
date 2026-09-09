from __future__ import annotations

import unittest
from pathlib import Path


class LauncherFastPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = (
            Path(__file__).resolve().parents[1] / "Dofus_Atlas.bat"
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


if __name__ == "__main__":
    unittest.main()

