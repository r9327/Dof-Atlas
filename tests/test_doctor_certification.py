from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.atlas_doctor_lib import certification_engine as engine

BASE = "a" * 40
HEAD = "b" * 40


def source(*, consumers=(), status="SOURCE_CONFIRMED", dynamic=(), truncated=False):
    return {
        "status": status, "truncated": truncated,
        "consumer_files": [{"path": name, "depth": 1} for name in consumers],
        "literal_dynamic_import_candidates": list(dynamic),
        "source_errors": [],
    }


class AdaptiveCertificationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "tests").mkdir()
        for name in ("test_ci_dev_tests", "test_guide_prerequisite_lookup",
                     "test_encyclopedia_on_demand_loading",
                     "test_encyclopedia_tab_demand_loading"):
            (self.root / "tests" / (name + ".py")).write_text("pass\n", encoding="utf-8")

    def scoped(self, root, paths, **kwargs):
        return {
            "status": "TARGETED", "full_required": False,
            "modules": ["tests.test_ci_dev_tests"], "reasons": [],
        }

    def build(self, paths=None, *, impact=None, deleted=None):
        with mock.patch.object(engine.ci_scope_gate, "classify_diff", side_effect=self.scoped):
            return engine.plan(
                self.root, paths or ["tools/ci_dev_tests.py"],
                base_sha=BASE, head_sha=HEAD,
                deleted_paths=deleted,
                impact_provider=lambda *_: impact if impact is not None else source(),
            )

    def test_tiny_known_change_is_fast_without_full_claim(self):
        result = self.build()
        self.assertEqual(result["profile"], "FAST")
        self.assertEqual(result["status"], "READY_TO_RUN_SCOPED")
        self.assertEqual(result["test_modules"], ["tests.test_ci_dev_tests"])
        self.assertFalse(result["validation"]["certified"])
        self.assertFalse(result["validation"]["full_suite_waived"])
        self.assertFalse(result["validation"]["phase_certified"])
        self.assertFalse(result["tests_executed"])

    def test_widget_change_adds_real_boundary_contracts_and_smart(self):
        with mock.patch.object(engine.ci_scope_gate, "_path_has_direct_test_coverage", return_value=True):
            result = self.build(["app/modules/encyclopedia/widgets/__init__.py"],
                                impact=source(consumers=["app/modules/encyclopedia/views/page.py"]))
        self.assertEqual(result["profile"], "SMART")
        self.assertIn("tests.test_encyclopedia_on_demand_loading", result["test_modules"])
        self.assertIn("tests.test_encyclopedia_tab_demand_loading", result["test_modules"])
        self.assertIn("qt_lifecycle", result["domains"])

    def test_missing_boundary_contract_escapes_to_full(self):
        (self.root / "tests/test_encyclopedia_on_demand_loading.py").unlink()
        result = self.build(["app/modules/encyclopedia/widgets/__init__.py"])
        self.assertEqual(result["status"], "FULL_REQUIRED")
        self.assertIn("BOUNDARY_CONTRACT_UNAVAILABLE", result["reasons"])
        self.assertEqual(result["test_modules"], [])

    def test_unmapped_consumer_not_hidden_by_file_test(self):
        result = self.build(["app/services/bridge.py"],
                            impact=source(consumers=["app/modules/encyclopedia/views/uncertified.py"]))
        self.assertIn("UNMAPPED_TRANSITIVE_CONSUMER", result["reasons"])
        self.assertEqual(result["profile"], "FULL_REQUIRED")

    def test_dynamic_import_is_not_proof_of_no_consumer(self):
        result = self.build(["app/services/bridge.py"], impact=source(dynamic=[{"importer": "x.py"}]))
        self.assertIn("UNPROVEN_DYNAMIC_CONSUMERS", result["reasons"])

    def test_incomplete_source_scan_escalates(self):
        for impact in (source(status="REVIEW"), source(truncated=True), source(status="BLOCKED")):
            with self.subTest(impact=impact["status"]):
                result = self.build(["app/services/bridge.py"], impact=impact)
                self.assertIn("INCOMPLETE_SOURCE_IMPACT", result["reasons"])

    def test_exception_in_source_scan_escalates(self):
        with mock.patch.object(engine.ci_scope_gate, "classify_diff", side_effect=self.scoped):
            result = engine.plan(
                self.root, ["app/services/foo.py"],
                base_sha=BASE, head_sha=HEAD,
                impact_provider=lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
            )
        self.assertIn("SOURCE_IMPACT_UNAVAILABLE", result["reasons"])

    def test_canonical_full_cannot_be_downgraded(self):
        with mock.patch.object(engine.ci_scope_gate, "classify_diff", return_value={
            "status": "FULL_REQUIRED", "full_required": True,
            "reasons": ["INSUFFICIENT_PATH_COVERAGE"], "modules": [],
        }):
            result = engine.plan(self.root, ["app/modules/encyclopedia/unknown.py"],
                                 base_sha=BASE, head_sha=HEAD)
        self.assertEqual(result["profile"], "FULL_REQUIRED")
        self.assertIn("CANONICAL_SCOPE_REQUIRES_FULL", result["reasons"])

    def test_policy_self_change_requires_full_independent_of_router(self):
        for path in engine.CRITICAL_PATHS:
            with self.subTest(path=path):
                result = self.build([path])
                self.assertIn("CERTIFICATION_ROOT_OF_TRUST_CHANGE", result["reasons"])
                self.assertEqual(result["test_modules"], [])

    def test_deletion_and_invalid_path_escalate(self):
        self.assertEqual(self.build(["../escape.py"])["profile"], "FULL_REQUIRED")
        with mock.patch.object(engine.ci_scope_gate, "classify_diff", return_value={
            "status": "FULL_REQUIRED", "full_required": True,
            "modules": [], "reasons": ["REMOVED_OR_RENAMED_FILES"]
        }):
            result = engine.plan(self.root, ["tools/ci_dev_tests.py"],
                                 base_sha=BASE, head_sha=HEAD, deleted_paths=["tools/old.py"])
        self.assertEqual(result["profile"], "FULL_REQUIRED")

    def test_untrusted_sha_escalates(self):
        result = engine.plan(self.root, ["tools/ci_dev_tests.py"],
                             base_sha="bad", head_sha=HEAD)
        self.assertIn("INVALID_EXACT_SHA", result["reasons"])

    def test_empty_diff_escalates(self):
        result = engine.plan(self.root, [], base_sha=BASE, head_sha=HEAD)
        self.assertEqual(result["status"], "FULL_REQUIRED")

    def test_missing_test_module_escalates(self):
        with mock.patch.object(engine.ci_scope_gate, "classify_diff", return_value={
            "status": "TARGETED", "full_required": False, "modules": ["tests.test_missing"],
        }):
            result = engine.plan(self.root, ["tools/ci_dev_tests.py"],
                                 base_sha=BASE, head_sha=HEAD,
                                 impact_provider=lambda *_: source())
        self.assertIn("SELECTED_TEST_MISSING", result["reasons"])

    def test_full_cannot_accept_scoped_evidence(self):
        plan = self.build(["../escape.py"])
        evidence = {
            "candidate_sha": HEAD, "base_sha": BASE,
            "plan_fingerprint": plan["plan_fingerprint"],
            "executed_modules": [], "exit_code": 0, "completed": True,
        }
        result = engine.verify_scoped_evidence(plan, evidence)
        self.assertEqual(result["status"], "BLOCKED")

    def test_evidence_needs_complete_exact_execution(self):
        plan = self.build()
        evidence = {
            "candidate_sha": HEAD, "base_sha": BASE,
            "plan_fingerprint": plan["plan_fingerprint"],
            "executed_modules": list(plan["test_modules"]), "exit_code": 0,
            "completed": True,
        }
        self.assertEqual(engine.verify_scoped_evidence(plan, evidence)["status"],
                         "SCOPED_TESTS_PASS")
        for field, value in (
            ("candidate_sha", "c" * 40), ("base_sha", "c" * 40),
            ("plan_fingerprint", "incorrect"), ("executed_modules", []),
            ("exit_code", 1), ("completed", False),
        ):
            with self.subTest(field=field):
                invalid = dict(evidence, **{field: value})
                self.assertEqual(engine.verify_scoped_evidence(plan, invalid)["status"],
                                 "BLOCKED")

    def test_cross_sha_reuse_is_never_accepted(self):
        plan = self.build()
        proof = {
            "status": "SCOPED_TESTS_PASS", "candidate_sha": "c" * 40,
            "plan_fingerprint": plan["plan_fingerprint"],
            "environment": {"os": __import__("os").name,
                            "python": __import__("sys").version.split()[0]},
        }
        self.assertFalse(engine.historical_evidence_usable(plan, proof))
        proof["candidate_sha"] = HEAD
        self.assertTrue(engine.historical_evidence_usable(plan, proof))
        proof["environment"] = {"os": "different", "python": "9.9"}
        self.assertFalse(engine.historical_evidence_usable(plan, proof))

    def test_plan_is_deterministic(self):
        a = self.build()
        b = self.build()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(a["plan_fingerprint"], b["plan_fingerprint"])

    def test_exact_profiles_are_explicit(self):
        self.assertEqual(set(engine.DOMAINS), {
            "functional", "architecture", "qt_lifecycle", "performance",
            "data", "security", "regression",
        })


class WorkflowContractTests(unittest.TestCase):
    def test_new_certification_cannot_replace_phase_full(self):
        root = Path(__file__).resolve().parents[1]
        phase = (root / ".github/workflows/phase-certification.yml").read_text(encoding="utf-8")
        smart = (root / ".github/workflows/doctor-certification.yml").read_text(encoding="utf-8")
        self.assertIn("tools.atlas_integrity full", phase)
        self.assertIn("tools.phase_certification_verdict", phase)
        self.assertIn("tools.doctor_certification", smart)
        self.assertIn("--expected-sha", smart)
        self.assertIn("--run", smart)
        self.assertIn("SCOPED_TESTS_PASS", smart)
        self.assertIn("FULL_REQUIRED", smart)
        self.assertIn("Full certification remains mandatory", smart)
        self.assertNotIn("tools.atlas_integrity full", smart)
        self.assertNotIn("continue-on-error: true", smart)


if __name__ == "__main__":
    unittest.main()
