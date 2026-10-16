from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.ci_guide_full_evidence import prove, REUSED_MODULES


def _expected():
    return {
        "11_existing_guides_tests": ["tests.test_guides_phase3.G.test_a"],
        "12_existing_success_tests": ["tests.test_achievements_lot7.A.test_b"],
        "13_existing_shell_tests": ["tests.test_pyside_shell.S.test_c"],
    }


def _full(*, line_a="... ok", suffix="OK"):
    return (
        "test_a (test_guides_phase3.G.test_a) " + line_a + "\n"
        "test_b (test_achievements_lot7.A.test_b) ... ok\n"
        "test_c (test_pyside_shell.S.test_c) ... ok\n"
        "----------------------------------------------------------------------\n"
        "Ran 3 tests in 0.002s\n\n" + suffix + "\n"
    )


class GuideExactFullEvidenceTests(unittest.TestCase):
    def test_failed_proof_cannot_authorize_reuse_when_stale_file_cannot_be_deleted(self):
        from tools import ci_guide_full_evidence as evidence
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof = root / "full.json"
            proof.write_text('{}', encoding="utf-8")
            output = root / "reuse.json"
            stale = {"status": "PROVEN", "head": "a" * 40}
            output.write_text(json.dumps(stale), encoding="utf-8")
            with patch.dict("os.environ", ATLAS_FULL_SUITE_SUCCESS="failure"), patch.object(Path, "unlink", side_effect=PermissionError("locked")):
                code = evidence.main(["--root", str(root), "--proof", str(proof), "--sha", "a" * 40, "--out", str(output)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), stale)
            # The PowerShell caller must require both exit code zero and a file.
            caller = (Path(__file__).resolve().parents[1] / "tools/run_guide_ultime_ci.ps1").read_text(encoding="utf-8-sig")
            self.assertIn('if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $proofPath))', caller)

    def test_complete_full_exact_ids_can_be_reused(self):
        self.assertEqual(
            prove(_full(), _expected()),
            {name: 1 for name in REUSED_MODULES},
        )

    def test_windows_crlf_log_is_validated_exactly(self):
        self.assertEqual(
            prove(_full().replace("\n", "\r\n"), _expected()),
            {name: 1 for name in REUSED_MODULES},
        )

    def test_failed_full_cannot_be_reused(self):
        with self.assertRaises(ValueError):
            prove(_full(suffix="FAILED (failures=1)"), _expected())

    def test_skipped_target_test_cannot_be_reused(self):
        with self.assertRaises(ValueError):
            prove(_full(line_a="... skipped 'reason'"), _expected())

    def test_missing_target_test_cannot_be_reused(self):
        changed = _full().replace(
            "test_b (test_achievements_lot7.A.test_b) ... ok\n", ""
        )
        with self.assertRaises(ValueError):
            prove(changed, _expected())

    def test_duplicate_or_different_target_test_cannot_be_reused(self):
        with self.assertRaises(ValueError):
            prove(_full().replace(
                "test_c (test_pyside_shell.S.test_c) ... ok",
                "test_c (test_pyside_shell.S.test_unknown) ... ok",
            ), _expected())

    def test_recursively_repeated_successful_tests_do_not_invalidate_proof(self):
        line = "test_c (test_pyside_shell.S.test_c) ... ok\n"
        repeated = _full().replace(line, line + line)
        self.assertEqual(
            prove(repeated, _expected()),
            {name: 1 for name in REUSED_MODULES},
        )

    def test_incomplete_discovery_cannot_be_reused(self):
        incomplete = _expected()
        incomplete["12_existing_success_tests"] = []
        with self.assertRaises(ValueError):
            prove(_full(), incomplete)


if __name__ == "__main__":
    unittest.main()
