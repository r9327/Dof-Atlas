from __future__ import annotations
import unittest
from unittest.mock import patch

from tools.ci_verified_pr_full import (
    MANDATORY_STEPS, verify_merge, verify_job, verify_pr, verify_run,
)
from tools.ci_main_phase_evidence import REQUIRED_STEPS, verify_jobs

REPO = "r9327/Dof-Atlas"
BASE = "a" * 40
PR_HEAD = "b" * 40
MAIN = "c" * 40
IDENTITY = {"base_sha": BASE, "pr_head_sha": PR_HEAD, "main_sha": MAIN,
            "git_tree": "d" * 40}
PR = {"number": 152, "merged_at": "2026-10-12T15:11:02Z",
      "merge_commit_sha": MAIN,
      "base": {"sha": BASE, "repo": {"full_name": REPO}},
      "head": {"sha": PR_HEAD, "ref": "example/pr", "repo": {"full_name": REPO}}}
RUN = {"name": "Phase Certification",
       "path": ".github/workflows/phase-certification.yml",
       "event": "pull_request", "head_sha": PR_HEAD, "head_branch": "example/pr",
       "conclusion": "success", "status": "completed",
       "updated_at": "2026-10-12T15:08:31Z",
       "repository": {"full_name": REPO},
       "head_repository": {"full_name": REPO}}


def result(steps, head=MAIN):
    return {"total_count": 1, "jobs": [{
        "name": "Phase Certification / Full Validation",
        "head_sha": head, "conclusion": "success", "status": "completed",
        "steps": [{"name": name, "conclusion": state} for name, state in steps.items()],
    }]}


class VerifiedMainFullReuseTests(unittest.TestCase):
    def test_identical_tree_merge_has_verified_identity(self):
        with patch("tools.ci_verified_pr_full.git",
                   side_effect=[MAIN, BASE + " " + PR_HEAD,
                                "d" * 40, "d" * 40, ""]):
            self.assertEqual(verify_merge(MAIN), IDENTITY)
        self.assertEqual(verify_pr([PR], IDENTITY, REPO)["number"], 152)
        verify_run(RUN, PR, IDENTITY, REPO)

    def test_modified_trust_or_unrelated_merge_cannot_reuse(self):
        with patch("tools.ci_verified_pr_full.git",
                   side_effect=[MAIN, BASE + " " + PR_HEAD,
                                "d" * 40, "d" * 40,
                                ".github/workflows/phase-certification.yml"]):
            with self.assertRaises(ValueError):
                verify_merge(MAIN)
        with patch("tools.ci_verified_pr_full.git",
                   side_effect=[MAIN, BASE]):
            with self.assertRaises(ValueError):
                verify_merge(MAIN)
        with self.assertRaises(ValueError):
            verify_pr([{**PR, "merge_commit_sha": PR_HEAD}], IDENTITY, REPO)

    def test_prior_full_requires_real_host_steps_not_scoped(self):
        statuses = {name: "success" for name in MANDATORY_STEPS}
        verify_job(result(statuses, PR_HEAD), PR_HEAD)
        for name in MANDATORY_STEPS:
            fail = {**statuses, name: "skipped"}
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_job(result(fail, PR_HEAD), PR_HEAD)

    def test_reject_stale_or_foreign_success(self):
        for changed in ({"event": "push"}, {"conclusion": "skipped"},
                        {"updated_at": "2026-10-12T15:12:31Z"},
                        {"head_sha": MAIN}, {"head_branch": "other"},
                        {"path": ".github/workflows/fake.yml"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                verify_run({**RUN, **changed}, PR, IDENTITY, REPO)

    def test_main_application_distinguishes_full_reuse_and_scoped(self):
        reused = {name: "skipped" for name in REQUIRED_STEPS}
        reused.update({
            "Verify exact certification checkout": "success",
            "Check merged PR FULL provenance": "success",
            "Enforce phase certification verdict": "success",
            "Execute and verify exact-SHA targeted modules": "skipped",
        })
        proof = verify_jobs(result(reused), head_sha=MAIN)
        self.assertTrue(proof["phase_full_host_verified"])
        self.assertTrue(proof["cross_sha_reuse"])
        self.assertTrue(proof["git_tree_equivalence_host_attested"])
        with self.assertRaises(ValueError):
            verify_jobs(result({**reused, "Check merged PR FULL provenance": "skipped"}),
                        head_sha=MAIN)
        scoped = {**reused,
                  "Resolve adaptive Doctor route on exact SHA": "success",
                  "Execute and verify exact-SHA targeted modules": "success"}
        proof = verify_jobs(result(scoped), head_sha=MAIN)
        self.assertFalse(proof["phase_full_host_verified"])
        self.assertEqual(proof["kind"], "main_application_verified_scoped")


if __name__ == "__main__":
    unittest.main()
