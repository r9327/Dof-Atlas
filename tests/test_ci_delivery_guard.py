from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.ci_delivery_guard import (
    CONTRACT_END, CONTRACT_START, REPORT_END, REPORT_START,
    DeliveryError, enclosed_json, exact_changed_files, run, validate,
)

HEAD = "b" * 40
BASE = "a" * 40


def contract():
    return {
        "schema_version": 1, "requirements": [
            {"id": "DG-001", "description": "Implement a checked feature", "kind": "code"},
            {"id": "DG-002", "description": "Write usage documentation", "kind": "docs"},
            {"id": "DG-003", "description": "Validate Windows on real PC", "kind": "manual"},
        ],
    }


def report():
    return {
        "schema_version": 1, "delivery_issue": 22, "head_sha": HEAD,
        "requirements": [
            {"id": "DG-001", "status": "DONE",
             "evidence_files": ["tools/example.py"], "test_files": ["tests/test_example.py"]},
            {"id": "DG-002", "status": "DONE",
             "evidence_files": ["docs/example.md"]},
            {"id": "DG-003", "status": "DEFERRED", "followup_issue": 23,
             "safety_evidence": "Not shipped as certified; needs true Windows validation."},
        ],
    }


class DeliveryGuardTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        for path in ("tools/example.py", "tests/test_example.py", "docs/example.md"):
            loc = self.root / path
            loc.parent.mkdir(parents=True, exist_ok=True)
            loc.write_text("test", encoding="utf-8")
        self.changed = {"tools/example.py", "tests/test_example.py", "docs/example.md"}

    def followup(self, number):
        return {"number": number, "state": "open",
                "body": "Follow-up for DG-003: Windows acceptance and rollback"}

    def check(self, r=None, c=None, fetch=None, changed=None):
        return validate(
            c if c is not None else contract(),
            r if r is not None else report(),
            changed=self.changed if changed is None else changed,
            checkout=self.root, head_sha=HEAD,
            fetch_followup=fetch if fetch is not None else self.followup,
        )

    def test_partial_is_accounted_not_certified(self):
        result = self.check()
        self.assertEqual(result["status"], "TRACKED_PARTIAL")
        self.assertFalse(result["manual_certified"])
        self.assertFalse(result["full_certified"])
        self.assertFalse(result["merge_authorized"])
        self.assertFalse(result["tests_executed_by_this_gate"])
        self.assertEqual(result["deferred"], [{"id": "DG-003", "issue": 23}])

    def test_numeric_phase_prefix_keeps_accounting_and_manual_deferral_strict(self):
        # Actual #286 uses LV2-001..LV2-014; the trusted base must accept
        # them without rewriting immutable source issue requirement IDs.
        c = contract()
        r = report()
        for i, (spec, row) in enumerate(zip(c["requirements"], r["requirements"]), 1):
            key = f"LV2-{i:03d}"
            spec["id"] = key
            row["id"] = key
        followed = lambda _: {"state": "open", "body": "LV2-003: native Windows required"}
        result = self.check(c=c, r=r, fetch=followed)
        self.assertEqual(result["status"], "TRACKED_PARTIAL")
        self.assertEqual(result["done_ids"], ["LV2-001", "LV2-002"])
        self.assertEqual(result["deferred"], [{"id": "LV2-003", "issue": 23}])
        self.assertFalse(result["full_certified"])
        self.assertFalse(result["merge_authorized"])
        r["requirements"][0]["status"] = "PENDING"
        with self.assertRaisesRegex(DeliveryError, "only DONE"):
            self.check(c=c, r=r, fetch=followed)

    def test_numeric_phase_prefix_rejects_malformed_ids(self):
        for bad in (
            "LV2-1", "L2-001", "L1V-001", "LV2222-001", "lv2-001",
            "LV2_001", "LV2-0000000", "LV2-001x", "2LV-001",
        ):
            with self.subTest(value=bad):
                c, r = contract(), report()
                c["requirements"][0]["id"] = bad
                r["requirements"][0]["id"] = bad
                with self.assertRaisesRegex(
                    DeliveryError, "Invalid originating contract requirement"
                ):
                    self.check(c=c, r=r)

    def test_all_accounted_code_and_docs_are_not_phase_certification(self):
        c = contract()
        c["requirements"].pop()
        r = report()
        r["requirements"].pop()
        result = self.check(r=r, c=c)
        self.assertEqual(result["status"], "ACCOUNTED_NOT_CERTIFIED")
        self.assertFalse(result["full_certified"])

    def test_missing_or_unknown_or_duplicate_requirements_fail(self):
        for modification in ("missing", "unknown", "duplicate"):
            with self.subTest(modification=modification):
                r = report()
                if modification == "missing":
                    r["requirements"].pop(0)
                elif modification == "unknown":
                    r["requirements"][0]["id"] = "DG-999"
                else:
                    r["requirements"].append(copy.deepcopy(r["requirements"][0]))
                with self.assertRaises(DeliveryError):
                    self.check(r=r)

    def test_bad_sha_blocks_old_commit_evidence(self):
        r = report()
        r["head_sha"] = BASE
        with self.assertRaisesRegex(DeliveryError, "exact PR HEAD"):
            self.check(r=r)

    def test_fabricated_evidence_or_no_test_file_fails(self):
        for paths, tests in [
            (["tools/not_changed.py"], ["tests/test_example.py"]),
            (["tools/example.py"], ["tests/test_missing.py"]),
            (["tools/example.py"], []),
            (["../secrets.txt"], ["tests/test_example.py"]),
        ]:
            with self.subTest(paths=paths, tests=tests):
                r = report()
                r["requirements"][0].update(evidence_files=paths, test_files=tests)
                with self.assertRaises(DeliveryError):
                    self.check(r=r)

    def test_deferred_requires_live_issue_id_and_safety_note(self):
        for update in [
            {"followup_issue": None},
            {"followup_issue": True},
            {"safety_evidence": "later"},
        ]:
            with self.subTest(update=update):
                r = report()
                r["requirements"][2].update(update)
                with self.assertRaises(DeliveryError):
                    self.check(r=r)
        for issue in [
            {"state": "closed", "body": "DG-003"},
            {"state": "open", "body": "something else"},
            {"state": "open", "body": "DG-003", "pull_request": {}},
        ]:
            with self.subTest(issue=issue):
                with self.assertRaises(DeliveryError):
                    self.check(fetch=lambda _n: issue)

    def test_code_deferral_needs_source_issue_owner_permission(self):
        r = report()
        r["requirements"][0] = {
            "id": "DG-001", "status": "DEFERRED", "followup_issue": 51,
            "safety_evidence": "Feature is disabled and kept out of Stable until follow-up.",
        }
        with self.assertRaisesRegex(DeliveryError, "did not explicitly authorize"):
            self.check(r=r)
        c = contract()
        c["requirements"][0]["allow_deferral"] = True
        def valid_followup(number):
            return {"state": "open", "body": "DG-001: safe partial feature; DG-003: Windows acceptance pending"}
        self.assertEqual(
            self.check(c=c, r=r, fetch=valid_followup)["status"], "TRACKED_PARTIAL"
        )

    def test_manual_pass_claim_is_rejected(self):
        r = report()
        r["requirements"][2] = {
            "id": "DG-003", "status": "DONE",
            "evidence_files": ["docs/example.md"], "test_files": ["tests/test_example.py"],
        }
        with self.assertRaisesRegex(DeliveryError, "cannot self-certify"):
            self.check(r=r)

    def test_unknown_or_pending_status_fails_closed(self):
        for status in ("PENDING", "NOT_TESTED", "PASSED", "SKIPPED", "NOT_RUN"):
            with self.subTest(status=status):
                r = report()
                r["requirements"][0]["status"] = status
                with self.assertRaises(DeliveryError):
                    self.check(r=r)

    def test_issue_cannot_silently_downgrade_manual_kind(self):
        r = report()
        r["requirements"][2]["kind"] = "code"
        r["requirements"][2]["status"] = "DONE"
        with self.assertRaisesRegex(DeliveryError, "cannot self-certify"):
            self.check(r=r)

    def test_conflicting_source_ids_fail(self):
        c = contract()
        c["requirements"].append(copy.deepcopy(c["requirements"][0]))
        with self.assertRaisesRegex(DeliveryError, "Duplicate requirement"):
            self.check(c=c)

    def test_json_markers_are_unique_and_strict(self):
        source = CONTRACT_START + "\n" + __import__("json").dumps(contract()) + "\n" + CONTRACT_END
        self.assertEqual(enclosed_json(source, CONTRACT_START, CONTRACT_END), contract())
        for candidate in ("{}", source + CONTRACT_START, source.replace('"schema_version": 1', '"schema_version": 2')):
            with self.subTest(candidate=candidate[-60:]):
                with self.assertRaises(DeliveryError):
                    enclosed_json(candidate, CONTRACT_START, CONTRACT_END)
        self.assertRaises(DeliveryError, enclosed_json, source, REPORT_START, REPORT_END)

    def test_exact_git_diff_requires_actual_head(self):
        with patch("tools.ci_delivery_guard.subprocess.check_output", return_value=BASE + "\n"):
            with self.assertRaisesRegex(DeliveryError, "Wrong checkout"):
                exact_changed_files(BASE, HEAD, checkout=self.root)

    def test_runner_stays_in_trusted_checkout_with_token(self):
        workflow = (Path(__file__).resolve().parents[1]
                    / ".github/workflows/delivery-guard.yml").read_text(encoding="utf-8")
        self.assertIn("working-directory: trusted", workflow)
        self.assertIn('--checkout "$GITHUB_WORKSPACE/candidate"', workflow)
        self.assertNotIn("working-directory: candidate", workflow)

    def test_workflow_event_fails_on_fork(self):
        import json
        event = {
            "number": 10,
            "repository": {"full_name": "r9327/Dof-Atlas"},
            "pull_request": {
                "body": REPORT_START + json.dumps(report()) + REPORT_END,
                "base": {"sha": BASE, "repo": {"full_name": "r9327/Dof-Atlas"}},
                "head": {"sha": HEAD, "repo": {"full_name": "someone/fork"}},
            },
        }
        with self.assertRaisesRegex(DeliveryError, "Foreign/forked"):
            run(event, checkout=self.root, repo="r9327/Dof-Atlas")


if __name__ == "__main__":
    unittest.main()
