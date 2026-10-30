from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.cost_attribution import cost_attribution
from tools.atlas_doctor_lib.evidence_hub import summarize_sources
from tools.atlas_doctor_lib.actions_step_costs import step_costs


SHA = "a" * 40
OTHER = "b" * 40


class DoctorPercentAttributionTests(unittest.TestCase):
    def test_disjoint_spans_have_meaningful_percent_denominators(self):
        report = {
            "elapsed_seconds": 1.0, "process_cpu_total_ms": 500,
            "constructor_to_visible_ms": 100, "constructor_cpu_ms": 100,
            "preload_ms": 200, "preload_cpu_ms": 150,
            "routes": [
                {"id": "quests", "cycle": 1, "status": "PASS",
                 "open_ms": 100, "open_cpu_ms": 50,
                 "return_home_ms": 300, "return_home_cpu_ms": 100},
            ],
            "peak_process_tree_rss_mib": 180, "worst_tree_phase": "quests:cycle1",
        }
        x = cost_attribution(report)
        self.assertEqual(x["status"], "OBSERVED")
        shares = {r["phase"]: r for r in x["shares"]}
        self.assertEqual(shares["functional_preload"]["wall_pct_of_entire_probe"], 20.0)
        self.assertEqual(shares["functional_preload"]["cpu_pct_of_measured_process_cpu"], 30.0)
        self.assertEqual(shares["other_or_uninstrumented"]["wall_pct_of_entire_probe"], 30.0)
        self.assertAlmostEqual(sum(r["wall_pct_of_entire_probe"] for r in x["shares"]), 100, delta=0.1)
        self.assertAlmostEqual(sum(r["cpu_pct_of_measured_process_cpu"] for r in x["shares"]), 100, delta=0.1)
        self.assertIsNone(x["memory"]["rss_percent_split"])

    def test_overlapping_timers_block_percentages(self):
        report = {"elapsed_seconds": 1, "process_cpu_total_ms": 100,
                  "preload_ms": 1200, "preload_cpu_ms": 200, "routes": []}
        self.assertEqual(cost_attribution(report)["status"], "BLOCKED")

    def test_repeat_cost_is_a_suspect_not_a_proven_source_duplicate(self):
        x = cost_attribution({
            "elapsed_seconds": 4, "process_cpu_total_ms": 2000,
            "routes": [{"id": "quests", "cycle": c, "status": "PASS",
                        "open_ms": n, "open_cpu_ms": 30}
                       for c, n in [(1, 900), (2, 450), (3, 420)]],
        })
        self.assertEqual(len(x["repeated_work_suspects"]), 1)
        self.assertIn("NOT_PROVEN", x["repeated_work_suspects"][0]["classification"])


class DoctorEvidenceHubTests(unittest.TestCase):
    def test_stale_tool_cannot_certify_new_commit(self):
        x = summarize_sources(
            sha=SHA, required=("app_navigation", "distribution"),
            job_results={"app": "success"},
            inputs=[
                ("app_navigation", "artifacts/app.json",
                 {"kind": "atlas_quick_full_app_navigation", "git_head": OTHER, "status": "PASS"}),
                ("distribution", "artifacts/dist.json",
                 {"git_head": SHA, "status": "PASS"}),
            ])
        self.assertEqual(x["status"], "BLOCKED")
        self.assertEqual(x["coverage"]["app_navigation"]["status"], "STALE")
        self.assertEqual(x["coverage"]["distribution"]["status"], "PASS")

    def test_unexecuted_ui_cannot_be_inferred_from_green_navigation(self):
        x = summarize_sources(
            sha=SHA, inputs=[("app_navigation", "artifacts/app.json",
                             {"git_head": SHA, "status": "PASS"})])
        self.assertEqual(x["coverage"]["qt_ui"]["status"], "NOT_RUN")
        self.assertIn("qt_ui", x["required_missing_or_bad"])

    def test_conflicting_failed_specialist_blocks_even_with_success_peer(self):
        x = summarize_sources(
            sha=SHA, required=("app_navigation",),
            inputs=[
                ("app_navigation", "artifacts/one.json", {"git_head": SHA, "status": "PASS"}),
                ("app_navigation", "artifacts/two.json", {"git_head": SHA, "status": "FAIL"}),
            ])
        self.assertEqual(x["coverage"]["app_navigation"]["status"], "FAIL")
        self.assertEqual(x["status"], "BLOCKED")

    def test_collects_cost_and_deduplicates_repeated_suspect(self):
        cost = {"shares": [{"phase": "guide", "wall_pct_of_entire_probe": 34.5}],
                "repeated_work_suspects": [{"route": "guide",
                                            "classification": "REPEATED_EXPENSIVE_ROUTE_NOT_PROVEN_DUPLICATE"}]}
        x = summarize_sources(
            sha=SHA, required=("app_navigation",),
            inputs=[("app_navigation", "a.json", {"git_head": SHA, "status": "PASS",
                                                   "cost_attribution": cost}),
                    ("app_navigation", "b.json", {"git_head": SHA, "status": "PASS",
                                                   "cost_attribution": cost})])
        self.assertEqual(len(x["duplicate_work_suspects"]), 1)
        self.assertEqual(len(x["cost_shares"]), 2)


class DoctorWorkflowStepCostTests(unittest.TestCase):
    def test_real_step_seconds_percentages_use_job_scope_only(self):
        report = step_costs([{
            "id": 10, "name": "Windows EXE packaging", "status": "completed",
            "steps": [
                {"name": "Compile EXE", "started_at": "2026-10-29T10:00:00Z",
                 "completed_at": "2026-10-29T10:00:30Z", "conclusion": "success"},
                {"name": "Verify SHA256", "started_at": "2026-10-29T10:00:30Z",
                 "completed_at": "2026-10-29T10:00:40Z", "conclusion": "success"},
            ],
        }], sha=SHA, run_id=123)
        self.assertEqual(report["status"], "OBSERVED")
        shares = report["jobs"][0]["steps"]
        self.assertEqual(shares[0]["percent_of_job_measured_steps"], 75.0)
        self.assertEqual(shares[1]["percent_of_job_measured_steps"], 25.0)
        self.assertIn("Parallel", report["denominator_note"])

    def test_incomplete_job_is_not_fabricated_as_completed(self):
        report = step_costs([{"id": 1, "status": "in_progress", "steps": []}],
                            sha=SHA, run_id=1)
        self.assertEqual(report["status"], "NOT_MEASURED")



class DoctorASTDuplicateEvidenceTests(unittest.TestCase):
    @staticmethod
    def inspection(*, requested=2, duplicates=0, truncated=True):
        return {
            "kind": "doctor_code_inspection", "status": "REVIEW",
            "graph_status": "MISSING",
            "source": {
                "status": "REVIEW", "requested_count": requested,
                "paths_inspected": ["app/a.py", "tests/test_a.py"],
                "parse_errors": [], "truncated": truncated,
                "counts": {"functions": 8, "duplicate_groups": duplicates,
                           "near_duplicate_groups": 0,
                           "literal_json_references": 100},
                "duplicate_bodies": [{"kind": "EXACT_AST_BODY"}] * duplicates,
                "near_duplicate_candidates": [],
                "silent_exceptions": [{"kind": "SOURCE_PATTERN_REVIEW"}],
                "budgets": {"function_limit_reached": False},
            },
        }

    def test_complete_ast_does_not_require_optional_graph_or_json_lineage(self):
        from tools.atlas_doctor_lib.duplicate_evidence import summarize_ast_duplicates
        x = summarize_ast_duplicates(self.inspection(), sha=SHA)
        self.assertEqual(x["status"], "PASS")
        self.assertEqual(x["full_code_inspection_status"], "REVIEW")
        self.assertEqual(x["graph_status"], "MISSING")
        self.assertTrue(x["full_code_inspection_truncated"])
        self.assertTrue(x["review_required"])
        self.assertIn("does NOT mean", x["coverage_statement"])

    def test_scan_with_missing_python_file_is_blocked(self):
        from tools.atlas_doctor_lib.duplicate_evidence import summarize_ast_duplicates
        x = summarize_ast_duplicates(self.inspection(requested=3), sha=SHA)
        self.assertEqual(x["status"], "BLOCKED")

    def test_exceeded_duplicate_budget_and_incomplete_function_scan_block(self):
        from tools.atlas_doctor_lib.duplicate_evidence import summarize_ast_duplicates
        x = summarize_ast_duplicates(self.inspection(duplicates=81), sha=SHA)
        self.assertEqual(x["status"], "BLOCKED")
        y = self.inspection()
        y["source"]["budgets"]["function_limit_reached"] = True
        self.assertEqual(summarize_ast_duplicates(y, sha=SHA)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
