from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def timing_script() -> str:
    workflow = (ROOT / ".github/workflows/phase-certification.yml").read_text(encoding="utf-8")
    section = workflow.split("          python - <<'PYTIMINGS'\n", 1)[1].split(
        "          PYTIMINGS", 1
    )[0]
    return textwrap.dedent(section)


def observation(name, *, start="2026-10-24T23:01:00Z",
                end="2026-10-24T23:02:00Z", result="success"):
    return {"name": name, "status": "completed", "conclusion": result,
            "started_at": start, "completed_at": end}


class JobTimingObserverTests(unittest.TestCase):
    def execute(self, jobs):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = root / "summary.md"
            response = {"total_count": len(jobs), "jobs": jobs}
            stdout = io.BytesIO(json.dumps(response).encode("utf-8"))
            env = {
                **os.environ, "GITHUB_REPOSITORY": "r9327/Dof-Atlas",
                "GITHUB_RUN_ID": "40140997450", "GITHUB_TOKEN": "placeholder",
                "GITHUB_STEP_SUMMARY": str(summary),
            }
            original = os.getcwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, env, clear=True), patch(
                    "urllib.request.urlopen", return_value=stdout
                ):
                    exec(compile(timing_script(), "<ci-timing-observer>", "exec"), {})
                text = summary.read_text(encoding="utf-8")
                report = json.loads((root / "artifacts/doctor_ci/job_timings.json").read_text())
            finally:
                os.chdir(original)
        return report, text

    def test_skipped_job_negative_timestamp_does_not_discard_good_measurements(self):
        rows = [
            observation("Doctor / CI Plan"),
            observation("Windows bundle (skipped)", result="skipped",
                        start="2026-10-24T23:01:56Z",
                        end="2026-10-24T23:01:55Z"),
            observation("Doctor / PR FAST", result="failure",
                        end="2026-10-24T23:03:00Z"),
        ]
        report, summary = self.execute(rows)
        self.assertEqual(report["skipped_jobs"], 1)
        self.assertEqual(report["measured_jobs"], 2)
        self.assertEqual(report["sum_completed_job_seconds"], 180.0)
        self.assertEqual(report["first_failed_job"], "Doctor / PR FAST")
        self.assertNotIn("Windows bundle (skipped)", summary)
        self.assertIn("Summed completed job durations", summary)
        self.assertFalse(report["certified"])

    def test_non_skipped_invalid_interval_is_visible_not_coerced_to_zero(self):
        report, summary = self.execute([
            observation("Valid"),
            observation("Bad", end="2026-10-24T23:00:59Z"),
        ])
        self.assertEqual(report["status"], "ADVISORY_PARTIAL")
        self.assertEqual(report["measured_jobs"], 1)
        self.assertEqual(len(report["excluded"]), 1)
        self.assertIn("Bad", summary)
        self.assertEqual(report["sum_completed_job_seconds"], 60.0)

    def test_unknown_or_pending_job_remains_visible_as_incomplete(self):
        p = observation("Job pending")
        p["status"] = "in_progress"
        report, summary = self.execute([observation("Completed"), p])
        self.assertEqual(report["status"], "ADVISORY_PARTIAL")
        self.assertIn("Job pending", summary)
        self.assertEqual(report["measured_jobs"], 1)


if __name__ == "__main__":
    unittest.main()
