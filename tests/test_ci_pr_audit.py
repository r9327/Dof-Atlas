from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.ci_pr_audit import audit_plan, render


ROOT = Path(__file__).resolve().parents[1]
HEAD, BASE = "a" * 40, "b" * 40


def sample_plan():
    return {
        "candidate_sha": HEAD, "base_sha": BASE, "risk": "CRITICAL",
        "changed_paths": [".github/workflows/phase-certification.yml",
                          "app/pages/craft_page.py", "tests/test_craft_page.py"],
        "deleted_paths": [], "required_jobs": ["certify", "pr-fast-validation"],
        "phase_route": {"route": "FULL_REQUIRED", "reasons": ["RISK_CRITICAL"],
                        "uncovered_paths": ["app/pages/craft_page.py"]},
        "ui_plan": {"status": "UI_REQUIRED"},
        "workflows": {"doctor-ui": {"selected": True},
                      "graphify-map": {"selected": False}},
        "specialist_fallback": True,
    }


class MiniAuditTests(unittest.TestCase):
    def test_real_risk_and_test_coverage_flags_without_false_certificate(self):
        p = sample_plan()
        p["deleted_paths"] = ["app/pages/craft_page.py"]
        report = audit_plan(p)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(set(x["code"] for x in report["findings"]),
                         {"REMOVED_OR_RENAMED", "CI_TRUST_SURFACE",
                          "UNMAPPED_TESTS", "BROAD_SPECIALISTS"})
        self.assertFalse(report["phase_certified"])
        self.assertFalse(report["merge_authorized"])
        self.assertFalse(report["full_suite_waived"])
        self.assertFalse(report["tests_executed"])
        self.assertIn("test mapping unproven", render(report))

    def test_unknown_route_fails_observation_closed(self):
        p = sample_plan()
        p["phase_route"] = {}
        self.assertEqual(audit_plan(p)["status"], "REVIEW_REQUIRED")
        self.assertIn("UNKNOWN_ROUTE", [x["code"] for x in audit_plan(p)["findings"]])

    def test_rejects_missing_head_base_and_inventory(self):
        for key, value in (("candidate_sha", "bad"),
                           ("base_sha", None),
                           ("changed_paths", []),
                           ("required_jobs", None),
                           ("workflows", [])):
            p = sample_plan()
            p[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit_plan(p)

    def test_escapes_untrusted_path_text_in_summary(self):
        p = sample_plan()
        p["changed_paths"].append("docs/line\nbreak|pipe.md")
        report = audit_plan(p)
        text = render(report)
        self.assertIn("docs/line break/pipe.md", text)
        self.assertNotIn("line\nbreak", text)

    def test_cli_creates_machine_readable_artifact_and_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan = root / "plan.json"
            report = root / "report.json"
            summary = root / "summary.md"
            plan.write_text(json.dumps(sample_plan()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "tools.ci_pr_audit",
                 "--plan", str(plan), "--report", str(report),
                 "--summary", str(summary)],
                cwd=ROOT, capture_output=True, text=True, check=False,
                env=os.environ.copy(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(saved["candidate_sha"], HEAD)
            self.assertEqual(saved["status"], "REVIEW_REQUIRED")
            self.assertIn("PR mini-audit", summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
