from __future__ import annotations

import unittest
from unittest.mock import patch
from subprocess import CalledProcessError

from tools.ci_domain_certification import (
    plan_domains, owners_for, exact_git_diff,
)

B = "a" * 40
H = "b" * 40


class ModularDomainRoutingTests(unittest.TestCase):
    def route(self, paths, deleted=()):
        return plan_domains(base_sha=B, candidate_sha=H, paths=paths, deleted=list(deleted))

    def test_ci_policy_change_never_fans_out_into_quests_or_guides(self):
        plan = self.route([
            ".github/workflows/phase-certification.yml",
            "tools/atlas_doctor_lib/ci_orchestrator.py",
            "tests/test_ci_runner_guardrails.py",
            ".ai/context_index.json",
        ])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci"])
        self.assertFalse(plan["full_suite_executed"])
        self.assertFalse(plan["phase_certified"])
        self.assertFalse(plan["merge_authorized"])

    def test_craft_and_policy_changes_require_both_and_not_quests(self):
        plan = self.route(["app/local_data_cache.py", "tools/ci_scope_gate.py",
                           "tests/test_craft_adapter_release.py"])
        self.assertEqual(plan["domains"], ["ci", "craft"])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertFalse(any(x in plan["domains"] for x in ("quests", "guides")))

    def test_real_quest_owner_selects_quests(self):
        self.assertEqual(self.route(["app/quest_catalog.py"])["domains"], ["quests"])
        self.assertEqual(self.route(["app/pages/quest_page.py"])["domains"], ["ui"])
        self.assertEqual(self.route(["main.py"])["domains"],
                         ["craft", "quests", "guides", "ui", "startup"])

    def test_unknown_owner_blocks_instead_of_launching_full(self):
        plan = self.route(["app/new_cross_domain_provider.py"])
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertEqual(plan["unknown_paths"], ["app/new_cross_domain_provider.py"])
        self.assertNotIn("FULL_SUITE", plan["domains"])

    def test_removal_and_type_changes_cannot_downscope(self):
        path = "tools/atlas_doctor_lib/ci_orchestrator.py"
        plan = self.route([path], [path])
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertIn("REMOVAL_OR_RENAME_REQUIRES_REVIEW", plan["reasons"])

    def test_unsafe_duplicate_missing_identity_fails(self):
        for paths in ([], ["docs/a.md", "docs/a.md"], ["../escape.py"], ["a\\b.py"]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.route(paths)
        with self.assertRaises(ValueError):
            plan_domains(base_sha="bad", candidate_sha=H, paths=["tools/ci_scope_gate.py"])
        with self.assertRaises(ValueError):
            self.route(["tools/ci_scope_gate.py"], ["app/missing.py"])

    def test_git_diff_uses_merge_base_and_zero_terminated_status(self):
        from tools import ci_domain_certification as domain
        with patch.object(domain, "_git", return_value="D\0docs/old.md\0A\0docs/new.md\0"):
            changed, deleted = exact_git_diff(B, H)
            self.assertEqual(changed, ["docs/old.md", "docs/new.md"])
            self.assertEqual(deleted, ["docs/old.md"])
        with patch.object(domain, "_git", return_value="R100\0old.py\0new.py\0"):
            with self.assertRaises(ValueError):
                exact_git_diff(B, H)

    def test_a_metadata_only_diff_is_not_application_certification(self):
        plan = self.route(["docs/readme.md", ".ai/context_index.json"])
        self.assertEqual(plan["domains"], ["metadata"])
        self.assertFalse(plan["phase_certified"])


if __name__ == "__main__":
    unittest.main()
