from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib import certification_policy as policy
from tools.atlas_doctor_lib import certification_passport as passports
from tools.atlas_doctor_lib.certification_engine import fingerprint

BASE = "a" * 40
HEAD = "b" * 40


class PolicyAndPassportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "tests").mkdir()
        for module in {name for value in policy.SCENARIOS.values() for name in value["tests"]}:
            target = self.root / Path(*module.split(".")).with_suffix(".py")
            target.write_text("pass\n", encoding="utf-8")
        (self.root / "requirements-pyside.txt").write_text("dependency-hash-source\n", encoding="utf-8")

    def sample(self, *, status="READY_TO_RUN_SCOPED", scenarios=None,
               modules=None, execution=None):
        obligations = policy.obligations(
            self.root, ["app/modules/encyclopedia/widgets/__init__.py"], []
        ) if scenarios is None else scenarios
        selected = list(modules if modules is not None else obligations["required_tests"])
        report = {
            "candidate_sha": HEAD,
            "base_sha": BASE,
            "status": status,
            "profile": "SMART" if status == "READY_TO_RUN_SCOPED" else "FULL_REQUIRED",
            "validation": {
                "certified": False,
                "phase_certified": False,
                "full_suite_waived": False,
            },
            "independent_policy": obligations,
            "test_modules": selected,
            "reasons": [] if status == "READY_TO_RUN_SCOPED" else ["FULL_REQUIRED"],
            "source_impact": {"status": "SOURCE_CONFIRMED"},
            "test_selection_explanations": {},
            "execution": execution or {"status": "NOT_RUN", "exit_code": None},
        }
        report["plan_fingerprint"] = fingerprint(report)
        report["independent_verdict"] = policy.enforce(report)
        return report

    def test_scenario_registry_references_runnable_contracts(self):
        out = policy.obligations(self.root, ["app/modules/encyclopedia/widgets/__init__.py"], [])
        self.assertEqual(out["missing_contracts"], [])
        self.assertIn("memory_and_preload", out["scenarios"])
        self.assertIn("qt_lifecycle", out["scenarios"])
        self.assertEqual(out["scenarios"]["memory_and_preload"]["status"],
                         "PLANNED_NOT_EXECUTED")
        self.assertIn("process_tree_peak", out["required_metrics"])
        self.assertFalse(out["benchmarks_executed"])

    def test_impact_only_consumers_select_scenario(self):
        out = policy.obligations(
            self.root, ["tools/ci_dev_tests.py"], ["app/modules/encyclopedia/widgets/__init__.py"]
        )
        self.assertIn("memory_and_preload", out["scenarios"])

    def test_data_rules_need_data_integrity_proof(self):
        out = policy.obligations(self.root, ["data/encyclopedia/example.json"], [])
        self.assertIn("data_integrity", out["scenarios"])
        self.assertIn("DATA_INTEGRITY", out["integrity_groups_affected"])
        self.assertIn("tests.test_critical_json_schema", out["required_tests"])
        self.assertIn("data_integrity", out["required_metrics"])

    def test_missing_required_contract_and_invalid_downgrade_are_blocked(self):
        (self.root / "tests/test_performance_guardrails.py").unlink()
        obligations = policy.obligations(
            self.root, ["app/modules/encyclopedia/widgets/__init__.py"], []
        )
        self.assertIn("tests.test_performance_guardrails", obligations["missing_contracts"])
        plan = self.sample(scenarios=obligations)
        self.assertIn("UNSAFE_SCOPE_DOWNGRADE", policy.enforce(plan)["errors"])

    def test_policy_must_see_all_required_tests(self):
        p = self.sample(modules=["tests.test_encyclopedia_on_demand_loading"])
        self.assertIn("REQUIRED_SCENARIO_TESTS_OMITTED", policy.enforce(p)["errors"])

    def test_policy_no_full_or_phase_waiver_even_with_green_tests(self):
        p = self.sample()
        p["validation"]["phase_certified"] = True
        self.assertIn("PHASE_FULL_CANNOT_BE_WAIVED", policy.enforce(p)["errors"])
        p["validation"]["phase_certified"] = False
        p["validation"]["full_suite_waived"] = True
        self.assertIn("FULL_SUITE_WAIVER_PROHIBITED", policy.enforce(p)["errors"])

    def test_passport_distinguishes_scoped_tests_and_memory_benchmarks(self):
        p = self.sample()
        p["execution"] = {
            "status": "SCOPED_TESTS_PASS", "executed_modules": p["test_modules"],
            "exit_code": 0, "duration_seconds": 3.2,
        }
        certificate = passports.build_passport(p, root=self.root)
        self.assertEqual(certificate["verdict"], "SCOPED_PASS_NOT_FULL")
        self.assertFalse(certificate["phase_certified"])
        self.assertFalse(certificate["merge_authorized"])
        self.assertEqual(certificate["scenario_evidence"]["memory_and_preload"]["metrics_status"],
                         "NOT_RUN")
        self.assertIn("steady_rss_home", certificate["metrics_required"])
        self.assertEqual(passports.verify_passport(
            certificate, head_sha=HEAD,
            plan_fingerprint=p["plan_fingerprint"],
            runner_environment=passports.environment(self.root),
        )["status"], "INTEGRITY_CHECKED_NOT_ATTESTED")

    def test_passport_requires_real_test_completion(self):
        p = self.sample()
        cert = passports.build_passport(p, root=self.root)
        self.assertEqual(cert["verdict"], "BLOCKED")
        p = self.sample(status="FULL_REQUIRED")
        self.assertEqual(passports.build_passport(p, root=self.root)["verdict"], "FULL_PENDING")

    def test_passport_invalidation_for_changed_sha_or_environment(self):
        p = self.sample(status="FULL_REQUIRED")
        cert = passports.build_passport(p, root=self.root)
        for mutation in (
            lambda c: c.update(candidate_sha="c" * 40),
            lambda c: c["environment"].update(python="0.0"),
            lambda c: c.update(phase_certified=True),
            lambda c: c["scenario_evidence"].clear(),
        ):
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(cert)
                mutation(altered)
                checked = passports.verify_passport(
                    altered, head_sha=HEAD,
                    plan_fingerprint=p["plan_fingerprint"],
                    runner_environment=passports.environment(self.root),
                )
                self.assertEqual(checked["status"], "BLOCKED")
        self.assertEqual(passports.verify_passport(
            cert, head_sha="c" * 40,
            plan_fingerprint=p["plan_fingerprint"],
            runner_environment=passports.environment(self.root),
        )["status"], "BLOCKED")

    def test_read_passport_rejects_oversized_and_nonobject(self):
        target = self.root / "passport.json"
        target.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            passports.load_passport(target)
        target.write_text(json.dumps({"kind": "doctor_certification_passport"}), encoding="utf-8")
        self.assertEqual(passports.load_passport(target)["kind"], "doctor_certification_passport")
        target.write_text("x" * (passports.MAX_PASSPORT_BYTES + 1), encoding="utf-8")
        with self.assertRaises(ValueError):
            passports.load_passport(target)

    def test_historical_comparison_is_not_reuse(self):
        before = passports.build_passport(self.sample(status="FULL_REQUIRED"), root=self.root)
        after = copy.deepcopy(before)
        after["candidate_sha"] = "c" * 40
        after["scenario_evidence"].pop("memory_and_preload")
        outcome = passports.compare_passports(before, after)
        self.assertIn("memory_and_preload", outcome["removed_scenarios"])
        self.assertFalse(outcome["proof_of_non_regression"])
        self.assertFalse(outcome["cross_sha_evidence_reuse"])

    def test_advisory_workflow_writes_both_artifacts(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/doctor-certification.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("--passport-output", workflow)
        self.assertIn("passport.json", workflow)
        self.assertIn("tests.test_doctor_certification_policy", workflow)
        source = (root / "tools/doctor_certification.py").read_text(encoding="utf-8")
        self.assertIn("verify_passport", source)
        self.assertIn("verify_scoped_evidence", source)
        engine = (root / "tools/atlas_doctor_lib/certification_engine.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SCOPED_TESTS_PASS", engine)

    def test_phase_draft_does_not_auto_launch_full(self):
        root = Path(__file__).resolve().parents[1]
        phase = (root / ".github/workflows/phase-certification.yml").read_text(
            encoding="utf-8"
        )
        docs = (root / "PHASE_CERTIFICATION.md").read_text(encoding="utf-8")
        self.assertIn("github.event.pull_request.draft == false", phase)
        self.assertIn("ready_for_review", phase)
        self.assertIn("github.event_name == 'push'", phase)
        self.assertIn("tools.atlas_integrity full", phase)
        self.assertIn("Une **PR Phase en brouillon**", docs)
        self.assertIn("FULL Phase n'est pas lancée automatiquement", docs)


if __name__ == "__main__":
    unittest.main()
