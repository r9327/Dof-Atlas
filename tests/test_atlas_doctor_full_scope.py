"""Regression proof for Doctor's unbounded static inventory and Unity triage."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.full_scope import (
    audit_full_scope, write_full_scope_report,
)


class DoctorFullScopeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for args in (
            ["init", "-q"], ["config", "user.email", "atlas@example.invalid"],
            ["config", "user.name", "Doctor Test"],
        ):
            subprocess.run(["git", *args], cwd=self.root, check=True,
                           capture_output=True)

    def _file(self, name: str, content: str):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _commit(self):
        for args in (["add", "-A"], ["commit", "-qm", "fixture"]):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root,
                                       text=True).strip()

    def _unity(self):
        self._file("app/ui/unity_skin.py", "UNITY_PALETTE = {'BG': '#151821'}\n")
        self._file("app/ui/theme.py", "from app.ui.unity_skin import UNITY_PALETTE\n")

    def test_more_than_150_files_4000_functions_and_512k_are_scanned(self):
        self._unity()
        for n in range(151):
            self._file("app/mod_%03d.py" % n, "def function_%d():\n    return %d\n" % (n, n))
        huge = "# " + ("padding " * 85000) + "\n"
        self._file("app/giant.py", huge + "".join(
            "def item_%d():\n    return %d\n" % (n, n) for n in range(4002)
        ))
        sha = self._commit()
        result = audit_full_scope(self.root, expected_sha=sha)
        coverage = result["source_coverage"]
        self.assertEqual(coverage["status"], "PASS")
        self.assertEqual(coverage["total"], 154)
        self.assertEqual(coverage["inspected"], 154)
        self.assertEqual(coverage["functions_inspected"], 4153)
        self.assertFalse(coverage["truncated"])
        self.assertEqual(coverage["missing"], [])
        self.assertEqual(result["status"], "REVIEW")
        self.assertFalse(result["complete_application_certified"])
        self.assertEqual(result["unity_style"]["native_windows_visual"], "NOT_RUN")

    def test_style_candidates_do_not_become_false_visual_pass(self):
        self._unity()
        self._file("app/widgets.py", '''def update(button):
    button.setStyleSheet("QPushButton { color: #FFFFFF; }")
''')
        self._file("data/quests.json", '{"quests": []}\n')
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha)
        self.assertEqual(report["tracked_file_inventory"]["categories"]["json"], 1)
        self.assertEqual(report["tracked_file_inventory"]["json_content_coverage"], "NOT_RUN")
        names = {row["kind"] for row in report["unity_style"]["static_candidates"]}
        self.assertIn("LOCAL_QSS_OVERRIDE_REVIEW", names)
        self.assertIn("LOCAL_LITERAL_QSS_COLOR_REVIEW", names)
        self.assertEqual(report["unity_style"]["status"], "REVIEW")
        self.assertFalse(report["unity_style"]["visual_certified"])
        self.assertTrue(report["worktree_clean"])

    def test_missing_or_invalid_tracked_source_blocks_full_inventory(self):
        self._unity()
        self._file("app/ok.py", "answer = 42\n")
        sha = self._commit()
        (self.root / "app/ok.py").write_text("if :\n", encoding="utf-8")
        report = audit_full_scope(self.root, expected_sha=sha)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["source_coverage"]["total"], 3)
        self.assertEqual(report["source_coverage"]["inspected"], 2)
        self.assertEqual(report["source_coverage"]["parse_errors"][0]["file"], "app/ok.py")
        self.assertFalse(report["worktree_clean"])
        (self.root / "app/ok.py").unlink()
        report = audit_full_scope(self.root, expected_sha=sha)
        self.assertEqual(report["source_coverage"]["missing"], ["app/ok.py"])

    def test_opt_in_json_inspects_every_file_and_flags_id_candidates(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file("data/quests.json", '{"quests":[{"id":1},{"id":1},{"id":2}]}')
        self._file("data/images.json", '{"items":[]}')
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        self.assertEqual(audit["counts"]["tracked"], 2)
        self.assertEqual(audit["counts"]["valid_syntax"], 2)
        self.assertEqual(audit["counts"]["duplicate_id_review_files"], 1)
        self.assertEqual(audit["status"], "REVIEW")
        self.assertEqual(audit["syntax_coverage"], "PASS")
        self.assertEqual(report["tracked_file_inventory"]["json_content_coverage"], "PASS")
        self.assertFalse(audit["semantic_links_verified"])
        self.assertEqual(audit["files"][1]["duplicate_id_candidates"][0]["ids"], ["1"])
        self.assertFalse(audit["automatic_deletion_authorized"])


    def test_json_nested_id_collisions_and_repeated_members_are_review_only(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file(
            "data/deep.json",
            '{"outer":[{"steps":[{"id":3},{"id":3},{"id":"3"}]}],'
            '"same":1,"same":2,"untouched":[{"id":1},{"id":"1"}]}',
        )
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        entry = audit["files"][0]
        self.assertEqual(entry["status"], "VALID_SYNTAX_REVIEW")
        self.assertEqual(
            entry["duplicate_id_candidates"],
            [{"collection": "outer/0/steps", "ids": ["3"], "kind": "DUPLICATE_ID_REVIEW"}],
        )
        self.assertEqual(entry["duplicate_member_candidates"], ["same"])
        self.assertEqual(audit["counts"]["nested_lists_scanned"], 3)
        self.assertEqual(audit["counts"]["duplicate_member_review_files"], 1)
        self.assertEqual(audit["counts"]["duplicate_id_review_files"], 1)
        self.assertEqual(audit["syntax_coverage"], "PASS")
        self.assertFalse(audit["semantic_links_verified"])
        self.assertFalse(audit["automatic_deletion_authorized"])


    def test_json_static_guide_catalog_links_prove_only_manifest_scope(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file(
            "data/encyclopedia/guides/catalog.json",
            json.dumps({"categories": [{"id": "dofus"}], "guides": [
                {"id": "one", "file": "one.json", "category": "dofus"}]}),
        )
        self._file(
            "data/encyclopedia/guides/one.json",
            json.dumps({"id": "one", "category": "dofus", "sections": []}),
        )
        sha = self._commit()
        audit = audit_full_scope(self.root, expected_sha=sha, with_json=True)["json_semantic_audit"]
        links = audit["guide_catalog_static_links"]
        self.assertEqual(links["status"], "STATIC_PASS")
        self.assertEqual(links["checked"], 1)
        self.assertEqual(links["issues"], [])
        self.assertFalse(links["runtime_routes_verified"])
        self.assertFalse(audit["semantic_links_verified"])

    def test_tracked_null_guide_catalog_is_not_reported_as_absent(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file("data/encyclopedia/guides/catalog.json", "null")
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        links = report["json_semantic_audit"]["guide_catalog_static_links"]
        self.assertEqual(links["status"], "REVIEW")
        self.assertEqual(report["json_semantic_audit"]["syntax_coverage"], "PASS")

    def test_json_guide_catalog_bad_ids_categories_paths_and_missing_files(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file(
            "data/encyclopedia/guides/catalog.json",
            json.dumps({"categories": [{"id": "dofus"}], "guides": [
                {"id": "one", "file": "one.json", "category": "dofus"},
                {"id": "missing", "file": "missing.json", "category": "unknown"},
                {"id": "outside", "file": "../outside.json", "category": "dofus"}]}),
        )
        self._file(
            "data/encyclopedia/guides/one.json",
            json.dumps({"id": "other", "category": "aventure"}),
        )
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        links = audit["guide_catalog_static_links"]
        self.assertEqual(links["status"], "REVIEW")
        self.assertEqual(links["checked"], 3)
        self.assertEqual(
            {row["kind"] for row in links["issues"]},
            {"GUIDE_ID_MISMATCH", "GUIDE_CATEGORY_MISMATCH",
             "UNKNOWN_GUIDE_CATEGORY", "MISSING_TRACKED_GUIDE",
             "UNSAFE_GUIDE_FILENAME"},
        )
        self.assertEqual(report["status"], "REVIEW")
        self.assertFalse(audit["semantic_links_verified"])

    def test_invalid_and_missing_tracked_json_fail_closed(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file("data/broken.json", '{"unclosed":')
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["json_semantic_audit"]["counts"]["invalid_syntax"], 1)
        (self.root / "data/broken.json").unlink()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        self.assertEqual(report["json_semantic_audit"]["counts"]["unavailable"], 1)
        self.assertEqual(report["status"], "BLOCKED")

    def test_nonfinite_json_constants_fail_closed(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file("data/not_standard.json", '{"values":[NaN, Infinity]}')
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["json_semantic_audit"]["counts"]["invalid_syntax"], 1)

    def test_json_opt_in_without_any_tracked_json_is_not_a_false_pass(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["json_semantic_audit"]["syntax_coverage"], "BLOCKED")

    def test_lfs_pointer_is_unavailable_not_a_valid_json_document(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file(
            "data/pointer.json",
            "version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:" + "a" * 64 + "\nsize 1000\n",
        )
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["json_semantic_audit"]["counts"]["unavailable"], 1)
        self.assertEqual(report["json_semantic_audit"]["files"][0]["status"], "NOT_AVAILABLE")

    def test_sha_mismatch_fails_closed(self):
        self._file("app/ok.py", "pass\n")
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha="f" * 40)
        self.assertNotEqual(sha, "f" * 40)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason"], "Expected SHA differs from exact checkout HEAD")

    def test_findings_untruncated_and_report_is_confined_to_artifacts(self):
        self._unity()
        for n in range(90):
            self._file("app/mod_%03d.py" % n, '''def reused():
    pass
''')
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha)
        groups = report["findings"]["exact_ast_duplicate_groups"]
        self.assertGreaterEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["occurrences"]), 90)
        self.assertFalse(report["findings"]["truncated"])
        target = write_full_scope_report(
            self.root, Path("artifacts/doctor/full_scope.json"), report,
        )
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["candidate_sha"], sha)
        with self.assertRaises(ValueError):
            write_full_scope_report(self.root, Path("app/overwritten.json"), report)



    def test_with_graph_requires_current_exact_sha_graph(self):
        self._unity()
        self._file("app/ok.py", "def ok():\n    return 1\n")
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_graph=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["graph_architecture_audit"]["status"], "BLOCKED")
        self.assertFalse(report["complete_application_certified"])

    def test_dirty_valid_checkout_cannot_claim_sha_bound_source_pass(self):
        self._unity()
        self._file("app/ok.py", "answer = 1\n")
        sha = self._commit()
        self._file("app/ok.py", "answer = 2\n")
        report = audit_full_scope(self.root, expected_sha=sha)
        self.assertEqual(report["source_coverage"]["status"], "BLOCKED")
        self.assertTrue(report["source_coverage"]["worktree_dirty"])

    def test_doctor_cli_exposes_full_scope_without_claiming_completion(self):
        import contextlib
        import io
        from unittest.mock import patch
        from tools import atlas_doctor
        self._unity()
        self._file("app/ok.py", "def ok():\n    return 1\n")
        self._commit()
        output = io.StringIO()
        with patch.object(atlas_doctor, "project_root", return_value=self.root):
            with contextlib.redirect_stdout(output):
                exit_code = atlas_doctor.main(["full-scope", "--json"])
        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["source_coverage"]["inspected"], 3)
        self.assertEqual(report["unity_style"]["native_windows_visual"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
