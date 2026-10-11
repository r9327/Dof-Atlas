from __future__ import annotations

import unittest

from tools import doctor_policy_authority as trust

SHA = "a" * 40
MAIN = "b" * 40


def same_blobs():
    return {path: ("c" * 40) for path in trust.TRUST_PATHS}


def protected():
    return {
        "enabled_by_host": True,
        "required_pr_reviews": True,
        "required_status_checks": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


class IndependentAuthorityTests(unittest.TestCase):
    def assess(self, *, candidate=None, trusted=None, protection=None):
        return trust.assess_policy_authority(
            candidate_sha=SHA, trusted_main_sha=MAIN,
            candidate_blobs=same_blobs() if candidate is None else candidate,
            trusted_blobs=same_blobs() if trusted is None else trusted,
            protection=protected() if protection is None else protection,
        )

    def test_code_identical_to_protected_main_still_never_waives_full(self):
        result = self.assess()
        self.assertEqual(result["status"], "SAME_CODE_ON_PROTECTED_MAIN")
        self.assertTrue(result["source_code_identical_to_protected_main"])
        self.assertFalse(result["automated_test_reuse_authorized"])
        self.assertFalse(result["policy_complete_for_dynamic_dependencies"])
        self.assertFalse(result["full_suite_waived"])

    def test_changed_pr_policy_is_untrusted(self):
        changed = same_blobs()
        changed["tools/atlas_doctor_lib/certification_policy.py"] = "d" * 40
        out = self.assess(candidate=changed)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertIn("CANDIDATE_POLICY_DIFFERS_FROM_MAIN", out["errors"])
        self.assertIn("tools/atlas_doctor_lib/certification_policy.py", out["divergent"])

    def test_missing_policy_is_unverified(self):
        changed = same_blobs()
        del changed["tools/ci_scope_gate.py"]
        result = self.assess(candidate=changed)
        self.assertIn("POLICY_FILES_UNVERIFIED", result["errors"])
        self.assertIn("tools/ci_scope_gate.py", result["missing"])

    def test_unprotected_main_fails_closed(self):
        for invalid in (
            {},
            dict(protected(), enabled_by_host=False),
            dict(protected(), required_pr_reviews=False),
            dict(protected(), required_status_checks=False),
            dict(protected(), allow_force_pushes=True),
            dict(protected(), allow_deletions=True),
        ):
            with self.subTest(invalid=invalid):
                out = self.assess(protection=invalid)
                self.assertEqual(out["status"], "BLOCKED")

    def test_unknown_branch_is_not_canonical(self):
        out = trust.assess_policy_authority(
            candidate_sha=SHA, trusted_main_sha=MAIN,
            candidate_blobs=same_blobs(), trusted_blobs=same_blobs(),
            protection=protected(), trusted_branch="my-pr",
        )
        self.assertEqual(out["status"], "BLOCKED")
        self.assertIn("NOT_CANONICAL_PROTECTED_MAIN", out["errors"])

    def test_all_runtime_certification_sources_are_covered(self):
        required = {
            "tools/doctor_certification.py",
            "tools/atlas_doctor_lib/certification_evidence.py",
            "tools/doctor_github_provenance.py",
            "tools/doctor_scenario_runner.py",
            ".github/workflows/doctor-certification.yml",
            "tools/atlas_integrity_policy.json",
            "tools/ci_scope_gate.py",
        }
        self.assertTrue(required.issubset(trust.TRUST_PATHS))


if __name__ == "__main__":
    unittest.main()
