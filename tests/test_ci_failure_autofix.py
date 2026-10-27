from __future__ import annotations

"""Tests are pure stdlib/offline; never require a GitHub token or Qt."""

import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.atlas_doctor_lib.ci_failure_autofix import (
    INDEX, MARKER, JOB, STEP, classify_failure, regenerate_index,
)

REPO = "r9327/Dof-Atlas"
SHA = "a" * 40


def valid_host_data():
    run = {
        "id": 4321, "event": "pull_request", "status": "completed",
        "conclusion": "failure", "repository": {"full_name": REPO},
        "head_sha": SHA,
    }
    pr = {
        "number": 274, "state": "open",
        "head": {"sha": SHA, "ref": "agent-pr",
                 "repo": {"full_name": REPO}},
        "base": {"ref": "main", "repo": {"full_name": REPO}},
    }
    jobs = {
        "total_count": 1,
        "jobs": [{"id": 123, "name": JOB, "conclusion": "failure",
                  "steps": [{"name": STEP, "conclusion": "failure"}]}],
    }
    return run, jobs, pr


def classify(run=None, jobs=None, pr=None, log=None):
    base = valid_host_data()
    return classify_failure(run if run is not None else base[0],
                            jobs if jobs is not None else base[1],
                            pr if pr is not None else base[2],
                            MARKER if log is None else log,
                            repo=REPO, run_id=4321, pr_number=274)


def git(root: Path, *argv: str) -> str:
    result = subprocess.run(["git", *argv], cwd=root, text=True,
                            capture_output=True, check=True, timeout=10)
    return result.stdout.strip()


class BoundedCIFailureTriageTests(unittest.TestCase):
    def test_exact_host_run_failed_job_failed_step_log_and_sha_required(self):
        report = classify()
        self.assertTrue(report["eligible"], report)
        self.assertEqual(report["allowed_patch_paths"], [INDEX])
        self.assertEqual(report["candidate_sha"], SHA)
        self.assertFalse(report["tests_executed_here"])
        self.assertFalse(report["full_suite_executed"])
        self.assertFalse(report["phase_certified"])
        self.assertFalse(report["merge_authorized"])

    def test_never_repair_other_failed_step_or_log(self):
        run, jobs, pr = valid_host_data()
        cases = [
            (run, jobs, pr, "random test traceback"),
            (run, {"total_count": 1, "jobs": [
                {"id": 123, "name": JOB, "conclusion": "failure",
                 "steps": [{"name": "Run targeted ROAD IA tests", "conclusion": "failure"}]}]}, pr, MARKER),
            (run, {"total_count": 1, "jobs": [
                {"id": 123, "name": "Phase Certification / Domain or Release Validation",
                 "conclusion": "failure", "steps": []}]}, pr, MARKER),
        ]
        for candidate_run, candidate_jobs, candidate_pr, log in cases:
            with self.subTest(log=log, jobs=candidate_jobs):
                result = classify(candidate_run, candidate_jobs, candidate_pr, log)
                self.assertFalse(result["eligible"])
                self.assertEqual(result["allowed_patch_paths"], [])
                self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_reject_fork_stale_sha_healthy_or_pending_run(self):
        for mutation in (
            lambda r, j, p: p["head"]["repo"].update(full_name="attacker/fork"),
            lambda r, j, p: p["head"].update(sha="b" * 40),
            lambda r, j, p: r.update(conclusion="success"),
            lambda r, j, p: r.update(status="in_progress"),
            lambda r, j, p: r.update(event="workflow_dispatch"),
            lambda r, j, p: r["repository"].update(full_name="different/repo"),
            lambda r, j, p: p.update(state="closed"),
            lambda r, j, p: p["head"].update(ref="main"),
            lambda r, j, p: j.update(total_count=101),
        ):
            run, jobs, pr = valid_host_data()
            mutation(run, jobs, pr)
            self.assertFalse(classify(run, jobs, pr)["eligible"])

    def test_no_proof_from_skipped_or_cancelled(self):
        for state in ("skipped", "cancelled", "neutral", None):
            run, jobs, pr = valid_host_data()
            jobs["jobs"][0]["steps"][0]["conclusion"] = state
            self.assertFalse(classify(run, jobs, pr)["eligible"])

    def test_duplicate_matching_jobs_do_not_authorize_repair(self):
        run, jobs, pr = valid_host_data()
        jobs["jobs"].append(copy.deepcopy(jobs["jobs"][0]))
        jobs["total_count"] = 2
        self.assertFalse(classify(run, jobs, pr)["eligible"])

    def test_repair_refuses_untrusted_report_and_dirty_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init")
            git(root, "config", "user.email", "atlas-tests@example.invalid")
            git(root, "config", "user.name", "Atlas CI Test")
            (root / "app").mkdir()
            (root / "app" / "example.py").write_text("print('hello')\n")
            (root / ".ai").mkdir()
            (root / INDEX).write_text('{"stale":true}\n')
            git(root, "add", ".")
            git(root, "commit", "-m", "fixture")
            real_sha = git(root, "rev-parse", "HEAD")
            report = classify()
            report["candidate_sha"] = real_sha
            blocked = dict(report, eligible=False)
            with self.assertRaises(ValueError):
                regenerate_index(root, blocked)
            with self.assertRaises(ValueError):
                regenerate_index(root, dict(report, candidate_sha="b" * 40))
            (root / "untracked.txt").write_text("dirty\n")
            with self.assertRaises(ValueError):
                regenerate_index(root, report)
            (root / "untracked.txt").unlink()
            repaired = regenerate_index(root, report)
            self.assertEqual((root / INDEX).read_bytes(), repaired)
            self.assertEqual(git(root, "status", "--porcelain"), f"M {INDEX}")
            # A second attempt cannot modify the index twice or claim success.
            with self.assertRaises(ValueError):
                regenerate_index(root, report)

    def test_index_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            git(root, "init")
            git(root, "config", "user.email", "atlas-tests@example.invalid")
            git(root, "config", "user.name", "Atlas CI Test")
            (root / "app").mkdir()
            (root / "app" / "example.py").write_text("pass\n")
            git(root, "add", ".")
            git(root, "commit", "-m", "fixture")
            other = Path(tmp) / "external.txt"
            other.write_text("unchanged")
            (root / ".ai").mkdir()
            (root / INDEX).symlink_to(other)
            report = classify()
            report["candidate_sha"] = git(root, "rev-parse", "HEAD")
            with self.assertRaises(ValueError):
                regenerate_index(root, report)
            self.assertEqual(other.read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
