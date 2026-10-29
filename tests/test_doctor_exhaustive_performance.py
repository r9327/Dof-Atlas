"""Contract tests: Doctor must control all exhaustive perf runs and verdicts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.atlas_doctor_lib.exhaustive_performance import (
    output_under_artifacts, review_evidence, run_doctor_lab,
)
from tools.atlas_perf_attribution import SpanAttributor, io_delta, render_report


class DoctorDeepPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "schema_version": 1, "git_head": "abc", "status": "PASS",
            "coverage_complete": True,
            "atlas_guide_ids": ["a", "b"],
            "manifest_enabled_guide_ids": ["a", "b"],
            "samples": [
                {"guide_id": ident, "cycle": cycle, "status": "PASS", "open_ms": 12}
                for cycle in range(1, 3) for ident in ("a", "b")
            ],
            "timeline": {"functional_preload_ms": 140},
            "peak_process_tree_mb": 200,
        }

    def test_exact_candidate_and_full_coverage_are_mandatory(self):
        ok = review_evidence(self.payload, expected_sha="abc", cycles=2, process_exit=0)
        self.assertEqual(ok["status"], "PASS")
        self.assertFalse(ok["is_certification"])
        stale = review_evidence(self.payload, expected_sha="def", cycles=2, process_exit=0)
        self.assertIn("WRONG_COMMIT_SHA", stale["blocking_reasons"])
        incomplete = dict(self.payload)
        incomplete["samples"] = self.payload["samples"][:-1]
        missing = review_evidence(incomplete, expected_sha="abc", cycles=2, process_exit=0)
        self.assertIn("MISSING_OR_DUPLICATED_GUIDE_MEASURES", missing["blocking_reasons"])

    def test_failed_guide_never_passes_even_when_subprocess_exits_zero(self):
        broken = dict(self.payload)
        broken["samples"] = [*self.payload["samples"]]
        broken["samples"][0] = dict(broken["samples"][0], status="FAIL", error="Timeout")
        report = review_evidence(broken, expected_sha="abc", cycles=2, process_exit=0)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["failures"][0]["guide_id"], "a")

    def test_output_must_stay_under_artifacts(self):
        with tempfile.TemporaryDirectory() as home:
            # Windows temp paths may contain 8.3 aliases (RUNNER~1); compare
            # canonical paths, not their original user-home spellings.
            root = Path(home).resolve()
            self.assertEqual(output_under_artifacts(root, Path("artifacts/x.json")),
                             (root / "artifacts/x.json").resolve())
            for output in (Path("../secrets.json"), Path("reports/x.json"),
                           Path("artifacts/../config.json"), Path("artifacts/x.py")):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    output_under_artifacts(root, output)

    def test_doctor_calls_internal_engine_with_exact_args_and_checks_report(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            actual = root / "artifacts/atlas_exhaustive/guides.json"

            def fake_run(argv, **kwargs):
                actual.parent.mkdir(parents=True, exist_ok=True)
                actual.write_text(json.dumps(self.payload), encoding="utf-8")
                self.assertIn("tools.benchmark_atlas_exhaustive", argv)
                return SimpleNamespace(returncode=0)

            with patch("subprocess.run", side_effect=fake_run), patch(
                "tools.atlas_doctor_lib.runtime_benchmark.git_head", return_value="abc"
            ):
                report = run_doctor_lab(root, cycles=2,
                                        output=Path("artifacts/atlas_exhaustive/guides.json"))
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(actual.with_name("guides.doctor.json").is_file())

    def test_span_timer_exclusive_accounting_and_restore(self):
        class Page:
            def outer(self):
                self.inner()

            def inner(self):
                return True

        original = Page.outer
        timer = SpanAttributor()
        with timer.instrument(Page, ("outer", "inner")):
            with timer.active("cycle:guide"):
                self.assertIs(True, Page().outer() is None)
        self.assertIs(original, Page.outer)
        results = timer.top("cycle:guide")
        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(sum(x["inclusive_ms"] for x in results), 0)

    def test_single_doctor_perf_entrypoint_no_second_benchmark_command(self):
        from tools.atlas_doctor import build_parser
        parser = build_parser()
        help_text = parser.format_help()
        self.assertIn("perf", help_text)
        self.assertNotIn("perf-lab", help_text)
        self.assertTrue(parser.parse_args(["perf", "--deep", "--cycles", "5"]).deep)
        self.assertFalse(parser.parse_args(["perf"]).deep)
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/atlas-exhaustive-benchmark.yml").read_text(encoding="utf-8")
        self.assertIn("tools.atlas_doctor perf --deep", workflow)
        self.assertNotIn("tools.benchmark_atlas_exhaustive --cycles", workflow)

    def test_io_is_nonnegative_and_report_escapes_errors(self):
        self.assertEqual(io_delta({"read_bytes": 20}, {"read_bytes": 25}), {"read_bytes": 5})
        self.assertEqual(io_delta({"read_bytes": 20}, {"read_bytes": 15}), {"read_bytes": 0})
        html = render_report({
            "git_head": "<bad>", "status": "FAIL", "timeline": {},
            "samples": [{"guide_id": "<script>", "cycle": 1, "status": "FAIL",
                         "error": "<img src=x>", "open_ms": 21}],
        })
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;img src=x&gt;", html)


if __name__ == "__main__":
    unittest.main()
