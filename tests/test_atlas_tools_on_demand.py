from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import atlas_tools_on_demand as subject
from tools.doctor_pr_on_demand import RequestRejected, parse_request, resolve

B = "b" * 40
H = "a" * 40
REPO = "r9327/Dof-Atlas"


def comment(body: str, *, role: str = "OWNER") -> dict:
    return {"issue": {"number": 325, "pull_request": {"url": "pr"}},
            "comment": {"author_association": role, "body": body}}


def pr() -> dict:
    return {"state": "open", "draft": True,
            "head": {"sha": H, "repo": {"full_name": REPO}},
            "base": {"sha": B, "repo": {"full_name": REPO}}}


class OnDemandToolModeTests(unittest.TestCase):
    def test_exact_commands_and_sha(self):
        modes = {
            "tools": "tools", "audit": "audit", "ponytail": "ponytail",
            "oss": "oss", "bench quick": "bench-quick",
            "bench runtime": "bench-runtime", "bench memory": "bench-memory",
            "bench preload": "bench-preload", "bench 8": "bench-8",
            "bench full": "bench-full",
        }
        for entered, mode in modes.items():
            with self.subTest(entered=entered):
                number, parsed, expected = parse_request(
                    "issue_comment", comment("/atlas " + entered + " " + H))
                self.assertEqual((number, parsed, expected), (325, mode, H))
                report = resolve(REPO, "issue_comment",
                                 comment("/atlas " + entered + " " + H), lambda _: pr())
                self.assertEqual(report["candidate_sha"], H)
                self.assertEqual(report["mode"], mode)
                self.assertFalse(report["certified"])

    def test_dispatch_and_untrusted_input_rejected(self):
        for mode in sorted(subject.MODES):
            n, parsed, expected = parse_request("workflow_dispatch", {
                "inputs": {"pr_number": 325, "mode": mode, "expected_sha": H.upper()}})
            self.assertEqual((n, parsed, expected), (325, mode, H))
        for value in (
            "/atlas bench 9", "/atlas bench full --unsafe", "/atlas shell",
            "/atlas tools; echo leak", "/atlas bench full " + "c" * 39,
            "/atlas oss --unsafe",
        ):
            with self.subTest(value=value), self.assertRaises(RequestRejected):
                parse_request("issue_comment", comment(value))
        with self.assertRaises(RequestRejected):
            parse_request("issue_comment", comment("/atlas bench full", role="CONTRIBUTOR"))
        with self.assertRaisesRegex(RequestRejected, "stale"):
            resolve(REPO, "issue_comment", comment("/atlas bench full " + "c" * 40),
                    lambda _: pr())

    def test_plans_only_canonical_engines(self):
        for mode in sorted(subject.MODES - {"oss"}):
            with self.subTest(mode=mode):
                plan = subject.command_plan(mode, B, H)
                self.assertGreaterEqual(len(plan), 1)
                for name, args, evidence in plan:
                    self.assertTrue(name)
                    self.assertEqual(args[0], subject.sys.executable)
                    self.assertNotIn("shell", args)
                    self.assertNotIn("sudo", args)
                    self.assertFalse(any("phase-certification" in a.lower() for a in args))
                    if evidence:
                        self.assertEqual(Path(evidence).parts[0], "artifacts")
        self.assertEqual(len(subject.command_plan("bench-full", B, H)), 5)
        self.assertEqual(subject.command_plan("oss", B, H, []), [])
        with self.assertRaises(ValueError):
            subject.command_plan("run-anything", B, H)
        with self.assertRaises(ValueError):
            subject.command_plan("tools", "invalid", H)
        with self.assertRaises(ValueError):
            subject.command_plan("oss", B, H, ["x.py"] * 17)

    def test_bench_and_oss_are_not_host_faked(self):
        self.assertTrue(subject.WINDOWS_MODES.isdisjoint(subject.LIGHT_MODES))
        self.assertEqual(subject.WINDOWS_MODES | subject.LIGHT_MODES, subject.MODES)
        self.assertEqual({name for name, _, _ in subject.command_plan("bench-8", B, H)}, {"eight"})
        self.assertTrue(any("--parallel-instances" in argv
                            for _, argv, _ in subject.command_plan("bench-8", B, H)))
        self.assertEqual(subject.command_plan("oss", B, H, ["tools/a.py"])[0][0], "oss")

    def test_oss_files_only_changed_existing_and_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for p in ("tools/good.py", "tests/example.py",
                      ".github/workflows/valid.yml", "docs/manual.md", "secret.py"):
                target = root / p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")
            data = "\n".join(["tools/good.py", "tests/example.py",
                              ".github/workflows/valid.yml", "docs/manual.md",
                              "../escape.py", "secret.py", "tools/missing.py"])
            with patch.object(subject, "_git", return_value=data):
                selected = subject.changed_oss_files(B, H, root)
            self.assertEqual(selected, [".github/workflows/valid.yml",
                                        "tests/example.py", "tools/good.py"])

    def test_dry_run_provenance_and_stale_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(subject, "_git", side_effect=[H, ""]):
                result = subject.run("bench-full", B, H, root=root, dry_run=True)
            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(len(result["commands"]), 5)
            self.assertFalse(result["phase_certified"])
            self.assertFalse(result["full_suite_executed"])
            self.assertFalse(result["live_dofus_accounts_tested"])
            self.assertIn("eight_atlas_processes", result["benchmark_kind"])
            with patch.object(subject, "_git", return_value="c" * 40):
                with self.assertRaisesRegex(ValueError, "STALE"):
                    subject.run("tools", B, H, root=root)

    def test_no_oss_matches_cannot_be_called_a_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(subject, "_git", side_effect=[H, "", ""]):
                result = subject.run("oss", B, H, root=root)
            self.assertEqual(result["status"], "NOT_APPLICABLE")
            self.assertEqual(result["commands"], [])
            self.assertTrue((root / subject.OUTPUT_ROOT / "report.json").is_file())

    def test_subtool_not_run_cannot_be_promoted_to_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = subject.subprocess.CompletedProcess(
                args=["fake-tool"], returncode=0,
                stdout='{"status":"NOT_RUN"}', stderr="")
            with patch.object(subject, "_git", return_value=H), \
                    patch.object(subject.subprocess, "run", return_value=result):
                report = subject.run("ponytail", B, H, root=root)
            self.assertEqual(report["status"], "NOT_RUN")
            self.assertEqual(report["commands"][0]["status"], "NOT_RUN")
            with patch.object(subject, "run", return_value=report):
                self.assertEqual(subject.main([
                    "--mode", "ponytail", "--base-sha", B, "--head-sha", H
                ]), 2)

    def test_not_applicable_subtool_is_not_reported_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subject.subprocess.CompletedProcess(
                args=["fake-tool"], returncode=0,
                stdout='{"status":"NOT_APPLICABLE"}', stderr="")
            with patch.object(subject, "_git", return_value=H), \
                    patch.object(subject.subprocess, "run", return_value=result):
                report = subject.run("ponytail", B, H, root=Path(temp))
            self.assertEqual(report["status"], "NOT_APPLICABLE")
            self.assertNotEqual(report["status"], "EXECUTED_NOT_CERTIFIED")

    def test_review_required_warning_and_unknown_status_stay_review(self):
        for upstream in ("REVIEW_REQUIRED", "WARN", "SOMETHING_UNRECOGNIZED"):
            with self.subTest(upstream=upstream), tempfile.TemporaryDirectory() as temp:
                catalog = subject.subprocess.CompletedProcess(
                    args=["fake-catalog"], returncode=0,
                    stdout='{"status":"PASS"}', stderr="")
                audit = subject.subprocess.CompletedProcess(
                    args=["fake-audit"], returncode=0,
                    stdout=json.dumps({"status": upstream}), stderr="")
                with patch.object(subject, "_git", return_value=H), \
                        patch.object(subject.subprocess, "run",
                                     side_effect=[catalog, audit]) as call:
                    report = subject.run("tools", B, H, root=Path(temp))
                self.assertEqual(call.call_count, 2)
                self.assertEqual(report["status"], "REVIEW")
                self.assertEqual(report["commands"][-1]["status"], upstream)
                self.assertFalse(report["phase_certified"])

    def test_failed_stage_stops_benchmark_chain_and_records_not_run(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subject.subprocess.CompletedProcess(
                args=["fake-tool"], returncode=1,
                stdout="", stderr="Simulated failure")
            with patch.object(subject, "_git", return_value=H), \
                    patch.object(subject.subprocess, "run", return_value=result) as call:
                report = subject.run("tools", B, H, root=Path(temp))
            self.assertEqual(call.call_count, 1)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual([item["status"] for item in report["commands"]],
                             ["FAIL", "NOT_RUN"])

    def test_quick_warn_and_code_inspect_review_are_not_execution_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            quick = subject.subprocess.CompletedProcess(
                args=["doctor", "quick"], returncode=1,
                stdout=json.dumps({
                    "kind": "audit", "summary": {"verdict": "WARN", "issues_total": 2},
                }), stderr="")
            inspect = subject.subprocess.CompletedProcess(
                args=["doctor", "code-inspect"], returncode=1,
                stdout=json.dumps({"status": "REVIEW"}), stderr="")
            with patch.object(subject, "_git", return_value=H), \
                    patch.object(subject.subprocess, "run", side_effect=[quick, inspect]) as call:
                report = subject.run("audit", B, H, root=Path(temp))
            self.assertEqual(call.call_count, 2)
            self.assertEqual(report["status"], "REVIEW")
            self.assertEqual([item["status"] for item in report["commands"]], ["WARN", "REVIEW"])
            self.assertEqual([item["exit_code"] for item in report["commands"]], [1, 1])
            self.assertFalse(report["phase_certified"])
            with patch.object(subject, "run", return_value=report):
                self.assertEqual(subject.main([
                    "--mode", "audit", "--base-sha", B, "--head-sha", H
                ]), 0)

    def test_ponytail_review_with_exit_one_stays_review(self):
        with tempfile.TemporaryDirectory() as temp:
            cmd = subject.subprocess.CompletedProcess(
                args=["doctor", "ponytail"], returncode=1,
                stdout=json.dumps({"kind": "ponytail_policy", "status": "REVIEW"}),
                stderr="")
            with patch.object(subject, "_git", return_value=H), \
                    patch.object(subject.subprocess, "run", return_value=cmd):
                report = subject.run("ponytail", B, H, root=Path(temp))
            self.assertEqual(report["status"], "REVIEW")
            self.assertEqual(report["commands"][0]["status"], "REVIEW")
            self.assertEqual(report["commands"][0]["exit_code"], 1)

    def test_advisory_escape_hatch_is_strictly_bounded(self):
        cases = [
            ("ponytail", 2, {"kind": "ponytail_policy", "status": "REVIEW"}),
            ("ponytail", 1, {"kind": "wrong", "status": "REVIEW"}),
            ("ponytail", 1, {"kind": "ponytail_policy", "status": "FAIL"}),
            ("audit", 1, {"kind": "audit", "summary": {"verdict": "FAIL"}}),
            ("audit", 1, {"kind": "bad", "summary": {"verdict": "WARN"}}),
            ("audit", 1, {"status": "WARN"}),
        ]
        for mode, code, payload in cases:
            with self.subTest(mode=mode, code=code, payload=payload):
                with tempfile.TemporaryDirectory() as temp:
                    cmd = subject.subprocess.CompletedProcess(
                        args=["fake-tool"], returncode=code,
                        stdout=json.dumps(payload), stderr="")
                    with patch.object(subject, "_git", return_value=H), \
                            patch.object(subject.subprocess, "run", return_value=cmd) as call:
                        report = subject.run(mode, B, H, root=Path(temp))
                    self.assertEqual(call.call_count, 1)
                    self.assertEqual(report["status"], "FAIL")
                    self.assertEqual(report["commands"][0]["status"], "FAIL")
                    if mode == "audit":
                        self.assertEqual(report["commands"][1]["status"], "NOT_RUN")

    def test_workflow_trust_boundary_and_full_opt_in(self):
        root = Path(__file__).resolve().parents[1]
        new = (root / ".github/workflows/atlas-tools-on-demand.yml").read_text(encoding="utf-8")
        old = (root / ".github/workflows/atlas-doctor-on-demand.yml").read_text(encoding="utf-8")
        self.assertIn("issue_comment:", new)
        self.assertIn("workflow_dispatch:", new)
        self.assertNotIn("\n  pull_request:", new)
        self.assertNotIn("\n  push:", new)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", new)
        self.assertIn("ref: ${{ env.HEAD_SHA }}", new)
        self.assertIn("persist-credentials: false", new)
        self.assertIn("ruff==0.17.3", new)
        self.assertIn("zizmor==1.30.1", new)
        self.assertIn("requirements-pyside.txt", new)
        self.assertIn("$attempt -le 3", new)
        self.assertIn("Pinned asset materialization failed after three attempts", new)
        self.assertIn("python -I .atlas_tools_runner/tools/atlas_tools_on_demand.py", new)
        self.assertEqual(new.count("Checkout trusted tool dispatcher"), 2)
        self.assertIn("sparse-checkout: |", new)
        self.assertIn("path: .atlas_tools_runner", new)
        self.assertIn("\n  freshness:\n", new)
        self.assertIn("needs: [resolve, light, windows_bench]", new)
        code_jobs = new.split("\n  light:\n", 1)[1].split("\n  freshness:\n", 1)[0]
        self.assertNotIn("GH_TOKEN", code_jobs)
        self.assertNotIn("issues: write", code_jobs)
        freshness = new.split("\n  freshness:\n", 1)[1]
        self.assertIn("pull-requests: write", freshness)
        self.assertNotIn("issues: write", freshness)
        self.assertNotIn("pull-requests: write", code_jobs)
        self.assertIn("id: verify", freshness)
        self.assertIn("if: ${{ always() }}", freshness)
        self.assertIn("FRESHNESS_RESULT: ${{ steps.verify.outcome }}", freshness)
        self.assertIn('gh api --include "repos/$GITHUB_REPOSITORY/issues/$PR_NUMBER/comments"', freshness)
        self.assertIn("This receipt is NOT a PASS or certification", freshness)
        self.assertIn("if gh api --include", freshness)
        self.assertIn("receipt_http_status", freshness)
        self.assertIn("receipt_request_id", freshness)
        self.assertIn("RECEIPT_HTTP_STATUS", freshness)
        self.assertIn("RECEIPT_REQUEST_ID", freshness)
        self.assertIn("http_status=UNKNOWN", freshness)
        self.assertIn("${request_id:-UNAVAILABLE}", freshness)
        self.assertIn("tr -cd", freshness)
        self.assertIn("use run-scoped JSON artifact", freshness)
        self.assertIn("delivery=COMMENT_UNAVAILABLE", freshness)
        self.assertIn("receipt_delivery", freshness)
        self.assertIn("atlas-tools-receipt-${{ github.run_id }}", freshness)
        self.assertIn("Archive run receipt even when GitHub denies comment permissions", freshness)
        self.assertIn("test \"$now\" = \"$EXPECTED_SHA\"", freshness)
        self.assertIn("Tool execution was not successful", freshness)
        self.assertNotIn("continue-on-error: true", freshness)
        self.assertNotIn("Checkout exact PR candidate", freshness)
        self.assertNotIn("needs.resolve.outputs.mode == 'bench-full' ||", old)
        self.assertIn("startsWith(github.event.comment.body, '/atlas doctor')", old)
        self.assertIn("startsWith(github.event.comment.body, '/atlas graphify')", old)


if __name__ == "__main__":
    unittest.main()
