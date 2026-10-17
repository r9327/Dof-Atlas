from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.capability_evidence import (
    _digest, run_capability_witnesses, validate_capability_evidence,
)
from tools.atlas_doctor_lib.capability_matrix import capability_inventory, capability_test_ids, capability_control_ids


class DoctorCapabilityEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.state = {
            "head": "a" * 40, "branch": "test", "remote": "origin",
            "dirty": False, "dirty_digest": "b" * 64, "status_lines": [],
        }

    def _passing_log(self):
        tests = sorted([*capability_test_ids(self.root).values(),
                        *capability_control_ids(self.root).values()])
        lines = [f"{test.rsplit('.', 1)[1]} ({test.rsplit('.', 1)[0]}) ... ok"
                 for test in tests]
        return "\n".join(lines) + f"\n\nRan {len(tests)} tests in 0.1s\n\nOK\n"

    def _passing_evidence(self):
        test_ids = capability_test_ids(self.root)
        control_ids = capability_control_ids(self.root)
        tests = sorted([*test_ids.values(), *control_ids.values()])
        payload = {
            "schema_version": 2,
            "kind": "doctor_capability_test_evidence",
            "status": "PASS",
            "candidate_sha": self.state["head"],
            "dirty": False,
            "dirty_digest": self.state["dirty_digest"],
            "worktree_unchanged": True,
            "return_code": 0,
            "timed_out": False,
            "log_truncated": False,
            "command": [__import__("sys").executable, "-m", "unittest", "-v", *tests],
            "stderr_tail": self._passing_log(),
            "witnesses": [
                {"capability_id": ident, "test_id": test_ids[ident], "result": "PASS"}
                for ident in sorted(test_ids)
            ],
            "control_witnesses": [
                {"capability_id": ident, "test_id": control_ids[ident], "result": "PASS"}
                for ident in sorted(control_ids)
            ],
            "certification": "NOT_CERTIFIED",
        }
        payload["evidence_digest"] = _digest(payload)
        return payload

    @patch("tools.atlas_doctor_lib.capability_evidence.git_state")
    def test_exact_evidence_promotes_tests_but_never_certification(self, state):
        state.return_value = self.state
        payload = self._passing_evidence()
        checked = validate_capability_evidence(self.root, payload)
        self.assertEqual(checked["status"], "PASS")
        with patch("tools.atlas_doctor_lib.capability_evidence.git_state", return_value=self.state):
            inventory = capability_inventory(self.root, evidence=payload)
        self.assertEqual(inventory["tested_count"], 18)
        self.assertEqual(inventory["certified_count"], 0)
        self.assertEqual(inventory["status"], "TESTED_NOT_CERTIFIED")
        self.assertTrue(all(row["proof_level"] == "TESTED"
                            for row in inventory["capabilities"]))

    @patch("tools.atlas_doctor_lib.capability_evidence.git_state")
    def test_tampering_or_another_worktree_is_rejected(self, state):
        state.return_value = self.state
        payload = self._passing_evidence()
        tampered = copy.deepcopy(payload)
        tampered["witnesses"][0]["result"] = "FAIL"
        self.assertIn("EVIDENCE_DIGEST_MISMATCH",
                      validate_capability_evidence(self.root, tampered)["errors"])
        moved = self._passing_evidence()
        moved["dirty_digest"] = "c" * 64
        moved["evidence_digest"] = _digest(moved)
        self.assertIn("WORKTREE_DIGEST_MISMATCH",
                      validate_capability_evidence(self.root, moved)["errors"])
        with patch("tools.atlas_doctor_lib.capability_evidence.git_state", return_value=self.state):
            inventory = capability_inventory(self.root, evidence=moved)
        self.assertEqual(inventory["status"], "BLOCKED")
        self.assertEqual(inventory["tested_count"], 0)

    @patch("tools.atlas_doctor_lib.capability_evidence.subprocess.run")
    @patch("tools.atlas_doctor_lib.capability_evidence.git_state")
    def test_runner_uses_one_bounded_suite_and_records_snapshot(self, state, run):
        state.return_value = self.state
        run.return_value.returncode = 0
        run.return_value.stdout = "ok"
        run.return_value.stderr = self._passing_log()
        payload = run_capability_witnesses(self.root, timeout=42)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(len(payload["witnesses"]), 18)
        self.assertEqual(len(payload["control_witnesses"]), 18)
        self.assertEqual(payload["certification"], "NOT_CERTIFIED")
        self.assertEqual(run.call_count, 1)
        self.assertIn("-v", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["timeout"], 42)
        self.assertEqual(payload["evidence_digest"], _digest(payload))

    @patch("tools.atlas_doctor_lib.capability_evidence.subprocess.run")
    @patch("tools.atlas_doctor_lib.capability_evidence.git_state")
    def test_zero_exit_with_skipped_witness_is_not_passing_evidence(self, state, run):
        state.return_value = self.state
        run.return_value.returncode = 0
        run.return_value.stdout = ""
        run.return_value.stderr = self._passing_log().replace("\n\nOK\n", "\n\nOK (skipped=1)\n")
        payload = run_capability_witnesses(self.root)
        self.assertEqual(payload["status"], "FAIL")
        self.assertTrue(all(row["result"] == "UNVERIFIED" for row in payload["witnesses"]))
        self.assertEqual(validate_capability_evidence(self.root, payload)["status"], "BLOCKED")

    @patch("tools.atlas_doctor_lib.capability_evidence.subprocess.run")
    @patch("tools.atlas_doctor_lib.capability_evidence.git_state")
    def test_missing_incomplete_or_expected_failure_summary_is_not_pass(self, state, run):
        state.return_value = self.state
        run.return_value.returncode = 0
        run.return_value.stdout = ""
        for summary in ("", "Ran 0 tests in 0.1s\n\nOK\n",
                        "Ran 35 tests in 0.1s\n\nOK\n",
                        "Ran 36 tests in 0.1s\n\nOK (expected failures=1)\n"):
            with self.subTest(summary=summary):
                run.return_value.stderr = summary
                self.assertEqual(run_capability_witnesses(self.root)["status"], "FAIL")

    @patch("tools.atlas_doctor_lib.capability_evidence.git_state")
    def test_missing_or_tampered_negative_control_fails_closed(self, state):
        state.return_value = self.state
        payload = self._passing_evidence()
        payload["control_witnesses"].pop()
        payload["evidence_digest"] = _digest(payload)
        self.assertEqual(validate_capability_evidence(self.root, payload)["status"], "BLOCKED")
        payload = self._passing_evidence()
        test_id = payload["control_witnesses"][0]["test_id"]
        payload["stderr_tail"] = payload["stderr_tail"].replace(
            f"{test_id.rsplit('.', 1)[1]} ({test_id.rsplit('.', 1)[0]}) ... ok",
            f"{test_id.rsplit('.', 1)[1]} ({test_id.rsplit('.', 1)[0]}) ... skipped 'disabled'",
        )
        payload["evidence_digest"] = _digest(payload)
        self.assertIn("WITNESS_VERBOSE_VERDICTS_INCOMPLETE",
                      validate_capability_evidence(self.root, payload)["errors"])

    @patch("tools.atlas_doctor_lib.capability_evidence.git_state")
    def test_reader_rejects_skip_hidden_by_passing_fields_and_valid_digest(self, state):
        state.return_value = self.state
        payload = self._passing_evidence()
        payload["stderr_tail"] = self._passing_log().replace("\n\nOK\n", "\n\nOK (skipped=1)\n")
        payload["evidence_digest"] = _digest(payload)
        checked = validate_capability_evidence(self.root, payload)
        self.assertEqual(checked["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
