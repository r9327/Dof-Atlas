from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tools import atlas_doctor
from tools.atlas_doctor_lib.agent_protocol import PROTOCOL, run_agent_action


class DoctorAgentProtocolTests(unittest.TestCase):
    def plan(self):
        return {
            "status": "READY", "automation_safe": True,
            "paths": ["app/example.py"], "level": "SOFT",
            "minimum_integrity_mode": "FAST",
            "execution_tests": ["tests.test_example"],
            "rules": ["AGENTS.md"],
            "risk": {"risk": "LOW"},
            "architecture_preflight": {"required": False, "status": "OPTIONAL"},
        }

    def test_plan_is_compact_exact_sha_contract(self):
        state = {"head": "a" * 40, "dirty": False, "dirty_digest": ""}
        with mock.patch("tools.agent.plan_payload", return_value=self.plan()), mock.patch(
            "tools.atlas_doctor_lib.agent_protocol.git_state", return_value=state
        ):
            result = run_agent_action(Path("."), action="plan",
                                      paths=["app/example.py"])
        self.assertEqual(result["protocol"], PROTOCOL)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["certification"]["full_certified"])
        self.assertTrue(result["edit_contract"]["expansion_requires_replan"])
        self.assertIn("data/local/zaaps.json", result["edit_contract"]["protected_paths"])
        self.assertEqual(result["guardians"]["selected_ids"], ["core", "simplicity"])
        self.assertTrue(result["guardians"]["execution"]["deduplicated"])

    def test_agent_json_preserves_source_lines_without_inventing_corroboration(self):
        state = {"head": "e" * 40, "dirty": False, "dirty_digest": ""}
        plan = {**self.plan(), "source_diagnostics": {
            "status": "FAIL", "files": [
                {"path": "app/example.py", "symbols": [
                    {"name": "compute", "kind": "function", "line": 42}],
                 "status": "FAIL", "reason": "Cannot parse file"},
            ]}}
        with mock.patch("tools.agent.plan_payload", return_value=plan), mock.patch(
            "tools.atlas_doctor_lib.agent_protocol.git_state", return_value=state
        ):
            payload = run_agent_action(Path("."), action="plan", paths=["app/example.py"])
        evidence = payload["source_evidence"]
        self.assertEqual(evidence["source_sha"], "e" * 40)
        self.assertEqual(evidence["source_anchors"][0]["line"], 42)
        self.assertEqual(evidence["source_anchors"][0]["symbol"], "compute")
        self.assertEqual(evidence["source_anchors"][0]["evidence_level"], "SOURCE_DEFINITION_ONLY")
        self.assertEqual(evidence["diagnostics"][0]["status"], "FAIL")
        self.assertEqual(evidence["diagnostics"][0]["priority"], "UNASSESSED")
        self.assertIsNone(evidence["diagnostics"][0]["ci_run_url"])
        self.assertFalse(evidence["independent_ci_attested"])
        self.assertFalse(payload["certification"]["full_certified"])

    def test_empty_path_request_fails_closed(self):
        result = run_agent_action(Path("."), action="plan", paths=[])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["exit_code"], 2)
        self.assertFalse(result["source_evidence"]["independent_ci_attested"])

    def test_validate_pass_is_scoped_not_full(self):
        state = {"head": "b" * 40, "dirty": True, "dirty_digest": "digest"}
        verified = {"status": "PASS", "checks": [], "tests_executed": ["x"],
                    "duration_ms": 12}
        prepared = self.plan()
        with mock.patch("tools.agent.plan_payload", return_value=prepared), mock.patch(
            "tools.agent.verify_payload", return_value=verified
        ) as verify, mock.patch(
            "tools.atlas_doctor_lib.agent_protocol.git_state", return_value=state
        ):
            result = run_agent_action(Path("."), action="validate",
                                      paths=["app/example.py"])
        self.assertEqual(result["certification"]["status"], "SCOPED_VALIDATED")
        self.assertFalse(result["certification"]["full_certified"])
        self.assertIs(verify.call_args.kwargs["prepared_plan"], prepared)
        self.assertIn("await required CI", result["next_actions"][0])

    def test_review_never_advises_editing_and_explains_blockers(self):
        state = {"head": "c" * 40, "dirty": False, "dirty_digest": ""}
        plan = {
            **self.plan(), "status": "REVIEW_REQUIRED", "automation_safe": False,
            "ownership": {"unowned_paths": ["misc/new.py"], "ambiguous_paths": []},
            "unsafe_recommended_tools": ["tools/unsafe.py"],
            "non_automated_recommended_tools": [], "missing_validation_tools": [],
        }
        with mock.patch("tools.agent.plan_payload", return_value=plan), mock.patch(
            "tools.atlas_doctor_lib.agent_protocol.git_state", return_value=state
        ):
            result = run_agent_action(Path("."), action="plan", paths=["misc/new.py"])
        self.assertEqual(result["status"], "REVIEW")
        actions = " ".join(result["next_actions"])
        self.assertIn("Resolve scope ownership", actions)
        self.assertIn("Unsafe tools require review", actions)
        self.assertNotIn("Apply only", actions)

    def test_focused_check_is_pass_but_not_certified(self):
        state = {"head": "d" * 40, "dirty": True, "dirty_digest": "work"}
        checked = {
            "status": "FOCUSED_CHECKED", "checks": [],
            "tests_executed": True, "duration_ms": 10,
            "targeted_test_selection": {
                "status": "READY", "selected": ["tests.test_example"],
            },
            "targeted_test_execution": {
                "status": "PASS", "exit_code": 0, "tests_executed": True,
                "modules": ["tests.test_example"],
            },
        }
        with mock.patch("tools.agent.plan_payload", return_value=self.plan()), mock.patch(
            "tools.atlas_doctor_lib.development_preflight.development_preflight",
            return_value=checked,
        ), mock.patch(
            "tools.atlas_doctor_lib.agent_protocol.git_state", return_value=state
        ):
            result = run_agent_action(Path("."), action="check",
                                      paths=["app/example.py"], run_tests=True)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["execution"]["tests_executed"], ["tests.test_example"])
        self.assertEqual(result["certification"]["status"], "NOT_RUN")
        self.assertIn("run `doctor agent validate`", result["next_actions"][0])

    def test_unverified_or_forged_focused_test_proof_downgrades_to_review(self):
        from copy import deepcopy
        valid = {
            "status": "FOCUSED_CHECKED", "tests_executed": True,
            "targeted_test_selection": {
                "status": "READY", "selected": ["tests.test_example"],
            },
            "targeted_test_execution": {
                "status": "PASS", "tests_executed": True, "exit_code": 0,
                "modules": ["tests.test_example"],
            },
        }
        mutations = (
            ("missing_selection", lambda x: x.pop("targeted_test_selection")),
            ("missing_execution", lambda x: x.pop("targeted_test_execution")),
            ("boolean_without_named_proof", lambda x: x["targeted_test_execution"].update(modules=True)),
            ("module_substitution", lambda x: x["targeted_test_execution"].update(modules=["tests.test_other"])),
            ("duplicate_modules", lambda x: (x["targeted_test_selection"].update(
                selected=["tests.test_example"] * 2), x["targeted_test_execution"].update(
                modules=["tests.test_example"] * 2))),
            ("non_tests_module", lambda x: (x["targeted_test_selection"].update(
                selected=["app.secrets"]), x["targeted_test_execution"].update(
                modules=["app.secrets"]))),
            ("nonzero_exit", lambda x: x["targeted_test_execution"].update(exit_code=1)),
            ("failed_execution", lambda x: x["targeted_test_execution"].update(status="FAIL")),
            ("selection_review", lambda x: x["targeted_test_selection"].update(status="REVIEW")),
            ("boolean_false", lambda x: x.update(tests_executed=False)),
        )
        state = {"head": "d" * 40, "dirty": True, "dirty_digest": "work"}
        for name, mutate in mutations:
            checked = deepcopy(valid)
            mutate(checked)
            with self.subTest(name=name), mock.patch(
                "tools.agent.plan_payload", return_value=self.plan()
            ), mock.patch(
                "tools.atlas_doctor_lib.development_preflight.development_preflight",
                return_value=checked
            ), mock.patch(
                "tools.atlas_doctor_lib.agent_protocol.git_state", return_value=state
            ):
                result = run_agent_action(Path("."), action="check",
                                          paths=["app/example.py"], run_tests=True)
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["execution"]["tests_executed"], [])
            self.assertEqual(result["certification"]["status"], "NOT_RUN")
            self.assertFalse(result["certification"]["full_certified"])

    def test_cli_exposes_four_agent_actions(self):
        parser = atlas_doctor.build_parser()
        for action in ("plan", "check", "validate", "explain"):
            args = parser.parse_args(["agent", action, "app/example.py"])
            self.assertEqual(args.agent_action, action)

    def test_every_ai_adapter_points_to_canonical_entrypoint(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md",
            ".cursor/rules/atlas-doctor.mdc",
            "tools/skills/dofus-atlas-tools/SKILL.md",
        ):
            with self.subTest(relative=relative):
                self.assertIn("AI_ENTRYPOINT.md", (root / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
