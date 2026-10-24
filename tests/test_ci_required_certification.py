from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.ci_required_certification import (
    _REQUIRED_FULL_STEPS, _SCOPED_HIGH_STEPS, classify_merge_route, evaluate_merge,
    retrieve_full_proofs, validate_full_run, validate_scoped_high_run,
)

NOW = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)
HEAD = "a" * 40
BASE = "b" * 40
REPO = "r9327/Dof-Atlas"


def full_record():
    return {
        "id": 418,
        "head_sha": HEAD,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "path": "r9327/Dof-Atlas/.github/workflows/phase-certification.yml@refs/heads/feature",
        "repository": {"full_name": REPO},
        "created_at": (NOW - timedelta(hours=2)).isoformat(),
        "updated_at": (NOW - timedelta(hours=1)).isoformat(),
    }


def full_job():
    return {
        "run_id": 418,
        "name": "Phase Certification / Full Validation",
        "status": "completed",
        "conclusion": "success",
        "steps": [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in _REQUIRED_FULL_STEPS
        ],
    }


def decide(paths, *, runs=None, jobs=None, safe="success"):
    return evaluate_merge(
        candidate_sha=HEAD, base_sha=BASE, paths=paths,
        safe_validation=safe, repo=REPO, now=NOW,
        runs=runs, jobs_by_run=jobs,
    )


class CertificationMergeGateTests(unittest.TestCase):
    def test_doc_only_low_passes_without_full_and_carries_why(self):
        result = decide(["docs/readme.md", ".ai/context_index.json"])
        self.assertEqual(result["status"], "PASS_SCOPED_NOT_FULL")
        self.assertTrue(result["route"]["docs_only"])
        self.assertEqual(result["route"]["route"], "SCOPED")
        self.assertIsNone(result["full_evidence_run"])

    def test_high_smart_merge_needs_real_exact_sha_scoped_host_proof(self):
        from tools.atlas_doctor_lib.high_smart_scope import HIGH_SOURCE, REQUIRED_TESTS
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / HIGH_SOURCE
            source.parent.mkdir(parents=True)
            source.write_text("pass\n")
            for module in REQUIRED_TESTS:
                path = root / Path(*module.split(".")).with_suffix(".py")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("def test_real(): pass\n")
            route = classify_merge_route([HIGH_SOURCE], root=root, base_sha=BASE)
            self.assertEqual(route["risk"], "HIGH")
            self.assertEqual(route["route"], "SMART")
            self.assertTrue(route["smart_requires_host_proof"])
            args = dict(candidate_sha=HEAD, base_sha=BASE, paths=[HIGH_SOURCE],
                        safe_validation="success", repo=REPO, now=NOW, root=root)
            self.assertEqual(evaluate_merge(**args)["status"], "BLOCKED")
            record = full_record()
            record["event"] = "pull_request"
            proof = full_job()
            proof["steps"] = [
                {"name": name, "status": "completed", "conclusion": "success"}
                for name in _SCOPED_HIGH_STEPS
            ] + [{
                "name": "Run full Atlas phase certification gate",
                "status": "completed", "conclusion": "skipped",
            }]
            accepted = evaluate_merge(**args, runs=[record], jobs_by_run={418: [proof]})
            self.assertEqual(accepted["status"], "PASS_SMART_AUTHENTICATED_NOT_FULL")
            self.assertIsNone(accepted["full_evidence_run"])
            self.assertEqual(accepted["scoped_evidence_run"], 418)
            for mutation in ("wrong_sha", "wrong_repo", "wrong_event", "skipped_test",
                             "real_full", "failed_job"):
                with self.subTest(mutation=mutation):
                    bad_run = {**record, "repository": dict(record["repository"])}
                    bad_job = {**proof, "steps": [dict(step) for step in proof["steps"]]}
                    if mutation == "wrong_sha": bad_run["head_sha"] = BASE
                    if mutation == "wrong_repo": bad_run["repository"]["full_name"] = "attacker/repo"
                    if mutation == "wrong_event": bad_run["event"] = "workflow_dispatch"
                    if mutation == "skipped_test": bad_job["steps"][2]["conclusion"] = "skipped"
                    if mutation == "real_full": bad_job["steps"][-1]["conclusion"] = "success"
                    if mutation == "failed_job": bad_job["conclusion"] = "failure"
                    self.assertEqual(evaluate_merge(**args, runs=[bad_run],
                                      jobs_by_run={418: [bad_job]})["status"], "BLOCKED")
            self.assertEqual(classify_merge_route([HIGH_SOURCE, "tools/ci_scope_gate.py"],
                                                   root=root)["route"], "FULL_REQUIRED")
            self.assertEqual(classify_merge_route([HIGH_SOURCE, "app/core/json_store.py"],
                                                   root=root)["route"], "FULL_REQUIRED")
            self.assertEqual(evaluate_merge(**{**args, "safe_validation": "failure"},
                runs=[record], jobs_by_run={418: [proof]})["status"], "BLOCKED")
            source.unlink()
            self.assertEqual(classify_merge_route([HIGH_SOURCE], root=root)["route"], "FULL_REQUIRED")

    def test_required_full_without_proof_fails_closed(self):
        result = decide(["tools/atlas_integrity.py"])
        self.assertEqual(result["route"]["route"], "FULL_REQUIRED")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("no successful", result["reasons"][0])

    def test_uncertified_policy_and_ruleset_still_need_full(self):
        for path in (".github/rulesets/integration-branch.json",
                     "PHASE_CERTIFICATION.md"):
            with self.subTest(path=path):
                self.assertEqual(classify_merge_route([path])["route"], "FULL_REQUIRED")

    def test_known_ci_tooling_requires_successful_safe_validation_without_full_claim(self):
        path = '.github/workflows/phase-certification.yml'
        result = decide([path])
        self.assertTrue(result['route']['tooling_only'])
        self.assertEqual(result['status'], 'PASS_SCOPED_NOT_FULL')
        self.assertEqual(decide([path], safe='failure')['status'], 'BLOCKED')
        self.assertEqual(classify_merge_route([path, 'app/core/json_store.py'])['route'], 'FULL_REQUIRED')

    def test_safe_validation_failed_blocks_even_valid_full(self):
        result = decide(["tools/atlas_integrity.py"],
                        runs=[full_record()], jobs={418: [full_job()]}, safe="failure")
        self.assertEqual(result["status"], "BLOCKED")

    def test_full_exact_head_complete_stage_success(self):
        result = decide(["tools/atlas_integrity.py"],
                        runs=[full_record()], jobs={418: [full_job()]})
        self.assertEqual(result["status"], "PASS_FULL_AUTHENTICATED")
        self.assertEqual(result["full_evidence_run"], 418)

    def test_wrong_head_failed_full_and_skipped_required_stage_fail(self):
        invalid = full_record()
        invalid["head_sha"] = "c" * 40
        self.assertEqual(decide(["tools/atlas_integrity.py"],
                                runs=[invalid], jobs={418: [full_job()]})["status"], "BLOCKED")
        failed = full_record()
        failed["conclusion"] = "failure"
        self.assertEqual(decide(["tools/atlas_integrity.py"],
                                runs=[failed], jobs={418: [full_job()]})["status"], "BLOCKED")
        step = full_job()
        step["steps"][3]["conclusion"] = "skipped"
        self.assertEqual(decide(["tools/atlas_integrity.py"],
                                runs=[full_record()], jobs={418: [step]})["status"], "BLOCKED")

    def test_unauthorized_repo_job_and_workflow_rejected(self):
        for mutation in ("repo", "workflow", "job", "event"):
            with self.subTest(mutation=mutation):
                run = full_record()
                job = full_job()
                if mutation == "repo":
                    run["repository"]["full_name"] = "attacker/repo"
                elif mutation == "workflow":
                    run["path"] = "attacker/.github/workflows/public-pr-ci.yml@main"
                elif mutation == "job":
                    job["run_id"] = 9
                else:
                    run["event"] = "push"
                with self.assertRaises(ValueError):
                    validate_full_run(run, [job], candidate_sha=HEAD, repo=REPO, now=NOW)

    def test_stale_and_future_full_do_not_certify(self):
        for created, updated in (
            (NOW - timedelta(days=9), NOW - timedelta(days=8)),
            (NOW + timedelta(days=1), NOW + timedelta(days=1)),
            (NOW - timedelta(hours=2), NOW - timedelta(hours=3)),
        ):
            with self.subTest(updated=updated):
                run = full_record()
                run["created_at"] = created.isoformat()
                run["updated_at"] = updated.isoformat()
                self.assertEqual(decide(["tools/atlas_integrity.py"],
                                        runs=[run], jobs={418: [full_job()]})["status"], "BLOCKED")

    def test_github_unavailable_and_incomplete_listing_fail_closed(self):
        with patch("tools.ci_required_certification.github_get", side_effect=ValueError("403")):
            with self.assertRaisesRegex(ValueError, "403"):
                retrieve_full_proofs(REPO, HEAD, "token")
        with patch("tools.ci_required_certification.github_get", return_value={
            "workflow_runs": [], "total_count": 101
        }):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                retrieve_full_proofs(REPO, HEAD, "token")

    def test_no_merge_on_missing_diff_or_non_hex_identity(self):
        with self.assertRaises(ValueError):
            decide([])
        with self.assertRaises(ValueError):
            evaluate_merge(candidate_sha="bad", base_sha=BASE,
                           paths=["docs/readme.md"], safe_validation="success",
                           repo=REPO, now=NOW)


if __name__ == "__main__":
    unittest.main()
