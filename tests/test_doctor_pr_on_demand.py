from __future__ import annotations

import unittest
from pathlib import Path

from tools.doctor_pr_on_demand import RequestRejected, parse_request, resolve


ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40
BASE = "b" * 40
REPO = "r9327/Dof-Atlas"


def pr(*, draft=True, state="open", repository=REPO, head=HEAD):
    return {
        "state": state,
        "draft": draft,
        "head": {"sha": head, "repo": {"full_name": repository}},
        "base": {"sha": BASE, "repo": {"full_name": REPO}},
    }


def comment(body="/atlas doctor", role="OWNER", number=325):
    return {
        "issue": {"number": number, "pull_request": {"url": "https://example.invalid"}},
        "comment": {"body": body, "author_association": role},
    }


class OnDemandRequestTests(unittest.TestCase):
    def test_issue_comment_draft_and_exact_sha(self):
        report = resolve(REPO, "issue_comment", comment(), lambda _: pr())
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["candidate_sha"], HEAD)
        self.assertEqual(report["base_sha"], BASE)
        self.assertTrue(report["draft"])
        self.assertEqual(report["mode"], "doctor")
        self.assertFalse(report["certified"])
        self.assertFalse(report["full_suite_executed"])

    def test_manual_dispatch_and_graph(self):
        event = {"inputs": {
            "pr_number": "363", "mode": "graphify", "expected_sha": HEAD.upper(),
        }}
        report = resolve(REPO, "workflow_dispatch", event, lambda _: pr())
        self.assertEqual(report["mode"], "graphify")
        self.assertEqual(report["pr_number"], 363)

    def test_exact_sha_rejects_stale_request(self):
        with self.assertRaisesRegex(RequestRejected, "stale"):
            resolve(REPO, "issue_comment", comment("/atlas doctor " + "c" * 40), lambda _: pr())

    def test_comment_authorization_and_garbage(self):
        for role in ("NONE", "FIRST_TIME_CONTRIBUTOR", "CONTRIBUTOR", ""):
            with self.subTest(role=role), self.assertRaises(RequestRejected):
                parse_request("issue_comment", comment(role=role))
        for body in (
            "/atlas doctor --force", "/atlas graphify && echo hi", "/atlas doctor/graphify",
            "/atlas doctor " + "A" * 39, "hello", "/atlas Doctor",
        ):
            with self.subTest(body=body), self.assertRaises(RequestRejected):
                parse_request("issue_comment", comment(body=body))

    def test_comment_only_works_on_pull_requests(self):
        with self.assertRaisesRegex(RequestRejected, "pull-request"):
            parse_request("issue_comment", {"issue": {"number": 1}, "comment": {
                "body": "/atlas doctor", "author_association": "OWNER",
            }})

    def test_bad_dispatch_inputs_rejected(self):
        for data in (
            {"pr_number": "0", "mode": "doctor"},
            {"pr_number": "abc", "mode": "doctor"},
            {"pr_number": "2", "mode": "all"},
            {"pr_number": "2", "mode": "graphify", "expected_sha": "invalid"},
        ):
            with self.subTest(data=data), self.assertRaises(RequestRejected):
                parse_request("workflow_dispatch", {"inputs": data})

    def test_fork_and_closed_pr_are_blocked(self):
        for source in (
            pr(repository="external/fork"),
            pr(state="closed"),
            pr(head="bad-sha"),
        ):
            with self.subTest(source=source), self.assertRaises(RequestRejected):
                resolve(REPO, "issue_comment", comment(), lambda _: source)

    def test_reject_other_events_or_repositories(self):
        with self.assertRaises(RequestRejected):
            parse_request("push", {})
        with self.assertRaises(RequestRejected):
            resolve("../bad", "issue_comment", comment(), lambda _: pr())

    def test_doctor_lot_exact_sha_and_draft(self):
        report = resolve(
            REPO, "issue_comment",
            comment("/atlas doctor-lot " + "c" * 40 + " " + HEAD),
            lambda _: pr(),
        )
        self.assertEqual(report["mode"], "doctor-lot")
        self.assertEqual(report["lot_base_sha"], "c" * 40)
        self.assertEqual(report["candidate_sha"], HEAD)
        self.assertTrue(report["draft"])
        self.assertFalse(report["full_suite_executed"])

    def test_doctor_lot_manual_and_invalid_requests(self):
        event = {"inputs": {
            "pr_number": "325", "mode": "doctor-lot",
            "expected_sha": HEAD, "lot_base_sha": "c" * 40,
        }}
        report = resolve(REPO, "workflow_dispatch", event, lambda _: pr())
        self.assertEqual(report["lot_base_sha"], "c" * 40)
        invalid = (
            "/atlas doctor-lot",
            "/atlas doctor-lot " + "c" * 40,
            "/atlas doctor-lot " + "c" * 40 + " " + HEAD + " && whoami",
            "/atlas doctor-lot " + "c" * 40 + " " + "c" * 40,
        )
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(RequestRejected):
                parse_request("issue_comment", comment(body))
        with self.assertRaises(RequestRejected):
            parse_request("workflow_dispatch", {"inputs": {
                "pr_number": "325", "mode": "doctor-lot",
                "expected_sha": HEAD,
            }})
        with self.assertRaises(RequestRejected):
            parse_request("issue_comment", comment(
                "/atlas doctor-lot " + "c" * 40 + " " + HEAD,
                role="CONTRIBUTOR",
            ))

    def test_doctor_lot_stale_head_and_fork_remain_forbidden(self):
        event = comment("/atlas doctor-lot " + "c" * 40 + " " + HEAD)
        with self.assertRaisesRegex(RequestRejected, "stale"):
            resolve(REPO, "issue_comment", event, lambda _: pr(head="d" * 40))
        with self.assertRaisesRegex(RequestRejected, "Fork"):
            resolve(REPO, "issue_comment", event,
                    lambda _: pr(repository="outside/fork"))

    def test_comments_accept_exact_sha_and_trusted_roles(self):
        for role in ("OWNER", "MEMBER", "COLLABORATOR"):
            with self.subTest(role=role):
                number, mode, expected, lot_base = parse_request(
                    "issue_comment", comment("/atlas graphify " + HEAD, role=role))
                self.assertEqual(
                    (number, mode, expected, lot_base),
                    (325, "graphify", HEAD, ""),
                )


class OnDemandWorkflowTests(unittest.TestCase):
    def test_workflow_only_runs_when_requested(self):
        text = (ROOT / ".github/workflows/atlas-doctor-on-demand.yml").read_text(
            encoding="utf-8")
        trigger = text.split("permissions:", 1)[0]
        self.assertIn("issue_comment:", trigger)
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotIn("\n  pull_request:", trigger)
        self.assertNotIn("\n  push:", trigger)
        self.assertNotIn("pull_request_target", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", text)
        self.assertIn("ref: ${{ env.HEAD_SHA }}", text)
        self.assertIn("python -I tools/doctor_pr_on_demand.py", text)
        self.assertIn('gh api "repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER"', text)
        self.assertIn("tools.doctor_certification", text)
        self.assertIn("tools.doctor_dev_lot", text)
        self.assertIn("doctor-lot", text)
        self.assertIn("LOT_BASE_SHA", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("tools.atlas_doctor graph --rebuild", text)
        self.assertIn("graphifyy==0.9.72", text)
        self.assertIn("provenance.json", text)
        self.assertIn("\n  freshness:\n", text)
        self.assertIn("needs: [resolve, diagnostic]", text)
        diagnostic = text.split("\n  diagnostic:\n", 1)[1].split("\n  freshness:\n", 1)[0]
        self.assertNotIn("GH_TOKEN", diagnostic)
        self.assertIn("Doctor rejected graph generation", text)
        self.assertIn("Confirmed structural blocking findings", text)
        self.assertIn("actions/upload-artifact@", text)
        self.assertIn("Phase certified: **NO**", text)
        self.assertNotIn("phase-certification.yml", text)


if __name__ == "__main__":
    unittest.main()
