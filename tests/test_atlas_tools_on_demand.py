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
                        self.assertTrue(str(evidence).startswith("artifacts/"))
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
        self.assertIn("python -m tools.atlas_tools_on_demand", new)
        self.assertIn("\n  freshness:\n", new)
        self.assertIn("needs: [resolve, light, windows-bench]", new)
        code_jobs = new.split("\n  light:\n", 1)[1].split("\n  freshness:\n", 1)[0]
        self.assertNotIn("GH_TOKEN", code_jobs)
        self.assertNotIn("needs.resolve.outputs.mode == 'bench-full' ||", old)
        self.assertIn("startsWith(github.event.comment.body, '/atlas doctor')", old)
        self.assertIn("startsWith(github.event.comment.body, '/atlas graphify')", old)


if __name__ == "__main__":
    unittest.main()
