from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "install_rtk.ps1"


class InstallRtkTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "RTK installer is Windows-only")
    def test_existing_rtk_needs_no_winget_when_ripgrep_is_skipped(self) -> None:
        powershell = shutil.which("powershell.exe")
        self.assertIsNotNone(powershell, "Windows PowerShell is required for this test")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "rtk.cmd"
            logfile = root / "rtk.log"
            executable.write_bytes(
                b'@echo off\r\necho %*>>"%ATLAS_RTK_TEST_LOG%"\r\nexit /b 0\r\n'
            )

            environment = os.environ.copy()
            environment["ATLAS_RTK_TEST_COMMAND"] = str(executable)
            environment["ATLAS_RTK_TEST_SCRIPT"] = str(SCRIPT)
            environment["ATLAS_RTK_TEST_LOG"] = str(logfile)
            ps_command = """
$ErrorActionPreference = 'Stop'
function Get-Command {
    param([string]$Name, [string]$ErrorAction)
    if ($Name -eq 'winget') { return $null }
    if ($Name -eq 'rtk') {
        return [pscustomobject]@{ Source = $env:ATLAS_RTK_TEST_COMMAND }
    }
    Microsoft.PowerShell.Core\\Get-Command -Name $Name -ErrorAction SilentlyContinue
}
& $env:ATLAS_RTK_TEST_SCRIPT -Project -SkipRipgrep
"""
            completed = subprocess.run(
                [
                    powershell, "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-Command", ps_command,
                ],
                env=environment,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(
                completed.returncode, 0,
                completed.stdout + "\n" + completed.stderr,
            )
            self.assertTrue(logfile.is_file(), "Mocked RTK was not invoked")
            self.assertEqual(
                [line.strip() for line in logfile.read_text(encoding="utf-8").splitlines()],
                ["--version", "gain", "init --codex"],
            )


if __name__ == "__main__":
    unittest.main()
