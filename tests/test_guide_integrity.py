from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.guide_integrity import CHECKS, checks_for_mode, run


class GuideIntegrityTests(unittest.TestCase):
    def test_fast_mode_is_small_but_keeps_core_contracts(self) -> None:
        self.assertEqual(
            [check.key for check in checks_for_mode("fast")],
            [
                "canonical_lock",
                "canonical_dependencies",
                "manual_bundle",
                "transversals",
                "action_quality",
                "player_contract_7e",
            ],
        )

    def test_full_mode_keeps_every_active_guide_audit(self) -> None:
        full = checks_for_mode("full")
        self.assertEqual(full, CHECKS)
        self.assertEqual(
            {check.key for check in full},
            {
                "canonical_lock",
                "canonical_dependencies",
                "manual_bundle",
                "transversals",
                "route_hooks",
                "prerequisites",
                "coverage_light",
                "coverage_final",
                "runtime",
                "action_quality",
                "player_contract_7e",
            },
        )

    def test_run_continues_after_failure_and_reports_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outcomes = [0, 1, 0, 0, 0, 0]
            with patch(
                "tools.guide_integrity.subprocess.run",
                side_effect=[SimpleNamespace(returncode=code) for code in outcomes],
            ) as mocked_run:
                report = run("fast", root=Path(directory))

        self.assertEqual(mocked_run.call_count, 6)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["check_count"], 6)
        self.assertEqual(report["failed_check_count"], 1)
        self.assertEqual(report["checks"][1]["key"], "canonical_dependencies")
        self.assertEqual(report["checks"][1]["exit_code"], 1)

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            checks_for_mode("deep")


if __name__ == "__main__":
    unittest.main()
