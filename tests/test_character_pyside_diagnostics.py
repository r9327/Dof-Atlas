from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


class CharacterPySideDiagnosticsTests(unittest.TestCase):
    def test_legacy_character_pyside_contracts_emit_full_tracebacks(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        env.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
        env.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

        targets = [
            "tests.test_pyside_shell.PySideShellTests.test_organizer_can_move_session_to_exact_empty_slot",
            "tests.test_pyside_shell.PySideShellTests.test_organizer_clears_closed_windows_to_empty_slots",
            "tests.test_pyside_shell.PySideShellTests.test_organizer_drag_can_move_first_session_to_last_position_and_persist",
            "tests.test_pyside_shell.PySideShellTests.test_organizer_exports_switch_double_click_hotkey",
            "tests.test_pyside_shell.PySideShellTests.test_organizer_session_order_is_reapplied_after_scan",
            "tests.test_pyside_shell.PySideShellTests.test_organizer_window_event_detects_dofus_started_after_atlas",
            "tests.test_pyside_shell.PySideShellTests.test_quests_page_tracks_progress_per_character",
            "tests.test_pyside_shell.PySideShellTests.test_shell_follows_only_connected_character_without_organizer_favorite",
            "tests.test_pyside_shell.PySideShellTests.test_shell_follows_organizer_favorite_character_after_network_identity",
            "tests.test_pyside_shell.PySideShellTests.test_shell_refreshes_connected_character_name_after_organizer_scan",
        ]
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "-v", *targets],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=180,
            check=False,
        )
        output = f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        print(output, flush=True)
        self.assertEqual(completed.returncode, 0, output)


if __name__ == "__main__":
    unittest.main()
