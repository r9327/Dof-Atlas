from __future__ import annotations

import unittest
from pathlib import Path

from tools.ci_main_phase_evidence import REQUIRED_STEPS, verify_event, verify_jobs

SHA = "a" * 40
REPO = "r9327/Dof-Atlas"


def event(*, status="completed", conclusion="success", branch="main",
          event_type="push", sha=SHA, name="Phase Certification"):
    return {
        "repository": {"full_name": REPO},
        "workflow_run": {
            "id": 123,
            "name": name,
            "path": "r9327/Dof-Atlas/.github/workflows/phase-certification.yml@main",
            "event": event_type,
            "status": status,
            "conclusion": conclusion,
            "head_sha": sha,
            "head_branch": branch,
            "head_repository": {"full_name": REPO},
            "repository": {"full_name": REPO},
        },
    }


def jobs(*, failed_step=None, skipped_full=False):
    steps = [
        {"name": name, "conclusion": "failure" if name == failed_step else "success"}
        for name in REQUIRED_STEPS
    ]
    if skipped_full:
        next(x for x in steps if x["name"] == "Run full Atlas phase certification gate")[
            "conclusion"
        ] = "skipped"
    steps.append({"name": "Execute and verify exact-SHA targeted modules",
                  "conclusion": "skipped"})
    return {
        "total_count": 1,
        "jobs": [{
            "name": "Phase Certification / Full Validation",
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "steps": steps,
        }],
    }


class MainPhaseEvidenceTests(unittest.TestCase):
    def test_full_proof_with_doctor_jobs_still_requires_unique_complete_full(self):
        body = jobs()
        body['jobs'].insert(0, {'name': 'Doctor / CI Plan', 'conclusion': 'success'})
        body['total_count'] = 2
        self.assertTrue(verify_jobs(body, head_sha=SHA)['phase_full_host_verified'])
        body['jobs'].append(body['jobs'][1].copy())
        body['total_count'] = 3
        with self.assertRaises(ValueError):
            verify_jobs(body, head_sha=SHA)

    def test_verified_exact_sha_host_success_reuses_only_full(self):
        run_id = verify_event(event(), repository=REPO, head_sha=SHA)
        proof = verify_jobs(jobs(), head_sha=SHA)
        self.assertEqual(run_id, 123)
        self.assertTrue(proof["phase_full_host_verified"])
        self.assertFalse(proof["application_full_suite_executed"])
        self.assertFalse(proof["cross_sha_reuse"])
        self.assertTrue(proof["application_unique_lifecycle_pending"])

    def test_event_rejects_foreign_source_pr_stale_or_failed_phase(self):
        bad = [
            {"conclusion": "failure"}, {"status": "in_progress"},
            {"branch": "feature/x"}, {"event_type": "pull_request"},
            {"sha": "b" * 40}, {"name": "Different Workflow"},
        ]
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                verify_event(event(**changes), repository=REPO, head_sha=SHA)
        altered = event()
        altered["workflow_run"]["head_repository"] = {"full_name": "attacker/repo"}
        with self.assertRaises(ValueError):
            verify_event(altered, repository=REPO, head_sha=SHA)
        altered = event()
        altered["workflow_run"]["path"] = "r9327/Dof-Atlas/.github/workflows/fake.yml@main"
        with self.assertRaises(ValueError):
            verify_event(altered, repository=REPO, head_sha=SHA)

    def test_fails_closed_on_missing_failed_or_skipped_full_step(self):
        for step in REQUIRED_STEPS:
            with self.subTest(step=step), self.assertRaises(ValueError):
                verify_jobs(jobs(failed_step=step), head_sha=SHA)
        with self.assertRaises(ValueError):
            verify_jobs(jobs(skipped_full=True), head_sha=SHA)
        forged = jobs()
        forged["jobs"][0]["steps"][-1]["conclusion"] = "success"
        with self.assertRaises(ValueError):
            verify_jobs(forged, head_sha=SHA)

    def test_missing_duplicate_or_partial_job_evidence_never_passes(self):
        partial = jobs()
        partial["total_count"] = 2
        with self.assertRaises(ValueError):
            verify_jobs(partial, head_sha=SHA)
        duplicate = jobs()
        duplicate["jobs"][0]["steps"].append({"name": REQUIRED_STEPS[0],
                                                 "conclusion": "success"})
        with self.assertRaises(ValueError):
            verify_jobs(duplicate, head_sha=SHA)
        wrong_sha = jobs()
        wrong_sha["jobs"][0]["head_sha"] = "b" * 40
        with self.assertRaises(ValueError):
            verify_jobs(wrong_sha, head_sha=SHA)
        not_done = jobs()
        not_done["jobs"][0]["conclusion"] = "failure"
        with self.assertRaises(ValueError):
            verify_jobs(not_done, head_sha=SHA)

    def test_workflow_retains_manual_full_and_main_fast_separate(self):
        src = (Path(__file__).resolve().parents[1]
               / ".github/workflows/app-ci.yml").read_text(encoding="utf-8")
        self.assertIn('workflows: ["Phase Certification"]', src)
        self.assertIn("types: [completed]", src)
        self.assertIn("actions: read", src)
        self.assertIn("if: github.event_name != 'workflow_run'", src)
        self.assertIn("github.event_name == 'workflow_dispatch'", src)
        self.assertNotIn("needs.code-validation.outputs.full_required == 'true'", src)
        self.assertIn("tools.ci_main_phase_evidence", src)
        self.assertIn("Run unique same-process lifecycle contracts", src)
        self.assertIn('unittest discover -v -s tests -p "test_*.py"', src)
        self.assertIn("Run canonical Guide and data integrity runner", src)


if __name__ == "__main__":
    unittest.main()
