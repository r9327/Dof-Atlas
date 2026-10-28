from __future__ import annotations

"""Pure stdlib regression checks; no Git checkout, Qt launch or FULL claims."""

import copy
import json
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.ci_decision_arena import replay_cases, MAX_CASES

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "tools/atlas_doctor_lib/ci_decision_arena_cases.json"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


class DoctorCiDecisionArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            raise ValueError("Scenario schema changed")
        cls.cases = manifest["cases"]

    def replay(self, cases):
        return replay_cases(ROOT, cases, base_sha=BASE_SHA, candidate_sha=HEAD_SHA)

    def test_32_scenarios_replay_against_real_domain_and_ui_decisions(self):
        self.assertEqual(len(self.cases), MAX_CASES)
        report = self.replay(self.cases)
        self.assertEqual(report["status"], "MATCHED_ADVISORY_NOT_CERTIFIED", [
            row for row in report["results"] if row["status"] != "MATCH"
        ])
        self.assertEqual(report["matched"], 32)
        self.assertFalse(report["tests_executed"])
        self.assertFalse(report["full_suite_executed"])
        self.assertFalse(report["phase_certified"])
        self.assertFalse(report["merge_authorized"])
        self.assertFalse(any(row["independent_host_attestation"] for row in report["results"]))

    def test_wrong_expected_owner_is_a_detected_regression(self):
        case = copy.deepcopy(next(c for c in self.cases if c["id"] == "ui-theme"))
        case["expected"]["domains"] = ["ci"]
        report = self.replay([case])
        self.assertEqual(report["status"], "MISMATCH")
        self.assertIn("domain_owners", report["results"][0]["deviations"])

    def test_missing_required_specialist_is_not_tolerated(self):
        case = copy.deepcopy(next(c for c in self.cases if c["id"] == "ci-domain-router"))
        case["expected"]["required_jobs"].append("doctor-ui")
        report = self.replay([case])
        self.assertEqual(report["status"], "MISMATCH")
        self.assertIn("missing_job:doctor-ui", report["results"][0]["deviations"])

    def test_forbidden_unrelated_specialist_is_reported(self):
        case = copy.deepcopy(next(c for c in self.cases if c["id"] == "ui-theme"))
        case["expected"]["excluded_jobs"] = ["doctor-ui"]
        report = self.replay([case])
        self.assertEqual(report["status"], "MISMATCH")
        self.assertIn("unjustified_job:doctor-ui", report["results"][0]["deviations"])

    def test_blocked_unknown_skill_and_deleted_source_never_become_ready(self):
        cases = [
            copy.deepcopy(next(c for c in self.cases if c["id"] == ident))
            for ident in ("unknown-ai-skill", "deleted-guide", "unknown-python")
        ]
        report = self.replay(cases)
        self.assertEqual(report["status"], "MATCHED_ADVISORY_NOT_CERTIFIED")
        self.assertEqual([row["domain_status"] for row in report["results"]],
                         ["BLOCKED", "BLOCKED", "BLOCKED"])
        self.assertFalse(report["merge_authorized"])

    def test_invalid_identity_duplicate_cases_and_paths_fail_closed(self):
        case = copy.deepcopy(self.cases[0])
        for candidates in ([], [case, case], [{"id": "x", "paths": ["a"]}],
                           [dict(case, paths=["../escape.py"])]):
            with self.subTest(candidates=candidates), self.assertRaises(ValueError):
                self.replay(candidates)
        with self.assertRaises(ValueError):
            replay_cases(ROOT, [case], base_sha="bad", candidate_sha=HEAD_SHA)

    def test_arena_is_never_a_substitute_for_host_attestation(self):
        report = self.replay([copy.deepcopy(self.cases[0])])
        self.assertTrue(report["status"].endswith("NOT_CERTIFIED"))
        self.assertNotIn("CERTIFIED", report["kind"])
        self.assertIn("not independent", report["limitations"].lower())


if __name__ == "__main__":
    unittest.main()
