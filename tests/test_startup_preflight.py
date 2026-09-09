from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import startup_preflight


class StartupPreflightTests(unittest.TestCase):
    def test_environment_check_uses_spec_probes_without_runtime_imports(self) -> None:
        probed: list[str] = []

        def fake_find_spec(name: str):
            probed.append(name)
            return object()

        with patch.object(startup_preflight.importlib.util, "find_spec", side_effect=fake_find_spec):
            ok, error = startup_preflight.check_environment()

        self.assertTrue(ok, error)
        self.assertEqual(
            probed,
            ["PySide6", "win32gui", "PySide6.QtWebEngineWidgets"],
        )

    def test_environment_check_reports_missing_required_module(self) -> None:
        def fake_find_spec(name: str):
            return None if name == "win32gui" else object()

        with patch.object(startup_preflight.importlib.util, "find_spec", side_effect=fake_find_spec):
            ok, error = startup_preflight.check_environment()

        self.assertFalse(ok)
        self.assertIn("required module unavailable: win32gui", error)

    def test_environment_check_reports_probe_errors(self) -> None:
        with patch.object(
            startup_preflight.importlib.util,
            "find_spec",
            side_effect=RuntimeError("probe failed"),
        ):
            ok, error = startup_preflight.check_environment()

        self.assertFalse(ok)
        self.assertIn("module probe failed: PySide6: RuntimeError: probe failed", error)

    def test_compile_script_accepts_valid_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valid.py"
            path.write_text("value = 1\n", encoding="utf-8")
            ok, error = startup_preflight.compile_script(path)
        self.assertTrue(ok, error)

    def test_compile_script_reports_syntax_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.py"
            path.write_text("if True print('broken')\n", encoding="utf-8")
            ok, error = startup_preflight.compile_script(path)
        self.assertFalse(ok)
        self.assertTrue(error)

    def test_main_preserves_distinct_environment_and_syntax_exit_codes(self) -> None:
        with patch.object(startup_preflight, "check_environment", return_value=(False, "env")):
            self.assertEqual(startup_preflight.main(["main.py"]), startup_preflight.EXIT_ENVIRONMENT)

        with (
            patch.object(startup_preflight, "check_environment", return_value=(True, "")),
            patch.object(startup_preflight, "compile_script", return_value=(False, "syntax")),
        ):
            self.assertEqual(startup_preflight.main(["main.py"]), startup_preflight.EXIT_SYNTAX)

        with (
            patch.object(startup_preflight, "check_environment", return_value=(True, "")),
            patch.object(startup_preflight, "compile_script", return_value=(True, "")),
        ):
            self.assertEqual(startup_preflight.main(["main.py"]), startup_preflight.EXIT_OK)


if __name__ == "__main__":
    unittest.main()
