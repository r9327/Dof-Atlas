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

    def test_nested_json_duplicate_keys_are_reported_without_false_semantic_pass(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file(
            "data/duplicate.json",
            '{"meta":{"version":1,"version":2,"version":3},'
            '"rows":[{"id":1,"name":"a","name":"b"},{"id":2}]}',
        )
        # Reusing the same member names in different objects is not a collision.
        self._file("data/normal.json", '{"rows":[{"id":1,"name":"a"},{"id":2,"name":"b"}]}')
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        by_file = {entry["file"]: entry for entry in audit["files"]}
        self.assertEqual(audit["counts"]["tracked"], 2)
        self.assertEqual(audit["counts"]["valid_syntax"], 2)
        self.assertEqual(audit["counts"]["duplicate_key_review_files"], 1)
        self.assertEqual(by_file["data/duplicate.json"]["duplicate_key_candidates"], [
            {"key": "name", "occurrences": 1, "kind": "DUPLICATE_KEY_REVIEW",
             "json_path": None},
            {"key": "version", "occurrences": 2, "kind": "DUPLICATE_KEY_REVIEW",
             "json_path": None},
        ])
        self.assertEqual(by_file["data/duplicate.json"]["status"], "VALID_SYNTAX_REVIEW")
        self.assertEqual(by_file["data/normal.json"]["duplicate_key_candidates"], [])
        self.assertEqual(by_file["data/normal.json"]["status"], "VALID_SYNTAX")
        self.assertEqual(audit["status"], "REVIEW")
        self.assertEqual(audit["syntax_coverage"], "PASS")
        self.assertFalse(audit["semantic_links_verified"])
        self.assertFalse(audit["automatic_deletion_authorized"])
        self.assertEqual(
            (self.root / "data/duplicate.json").read_text(encoding="utf-8"),
            '{"meta":{"version":1,"version":2,"version":3},'
            '"rows":[{"id":1,"name":"a","name":"b"},{"id":2}]}',
        )

    def test_nested_json_id_lists_preserve_container_boundaries(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        self._file(
            "data/nested.json",
            '{"chapters":[{"stages":[{"id":"a"},{"id":"a"}]},'
            '{"stages":[{"id":"a"},{"id":"b"}]}],'
            '"meta":{"a/b":[{"id":1},{"id":1}]}}',
        )
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        entry = audit["files"][0]
        self.assertEqual(entry["id_lists_inspected"], 4)
        self.assertEqual(audit["counts"]["id_lists_inspected"], 4)
        self.assertEqual(entry["duplicate_id_candidates"], [
            {"collection": "$root/chapters/0/stages", "ids": ["a"],
             "kind": "DUPLICATE_ID_REVIEW"},
            {"collection": "$root/meta/a~1b", "ids": ["1"],
             "kind": "DUPLICATE_ID_REVIEW"},
        ])
        # IDs may repeat across separate stage lists without a collision.
        self.assertNotIn("$root/chapters/1/stages", [
            row["collection"] for row in entry["duplicate_id_candidates"]
        ])
        self.assertEqual(entry["status"], "VALID_SYNTAX_REVIEW")
        self.assertFalse(audit["semantic_links_verified"])
        self.assertEqual(report["status"], "REVIEW")

    def test_json_inventory_over_150_files_is_never_truncated(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        for index in range(151):
            self._file(f"data/entry_{index:03}.json", '{"items":[{"id":1}]}')
        self._file("data/entry_151.json", '{"items":[{"id":7},{"id":7}]}')
        sha = self._commit()
        audit = audit_full_scope(self.root, expected_sha=sha, with_json=True)[
            "json_semantic_audit"
        ]
        self.assertEqual(audit["counts"]["tracked"], 152)
        self.assertEqual(audit["counts"]["valid_syntax"], 152)
        self.assertEqual(audit["counts"]["id_lists_inspected"], 152)
        self.assertEqual(audit["counts"]["duplicate_id_review_files"], 1)
        self.assertEqual(len(audit["files"]), 152)
        self.assertEqual(audit["files"][-1]["file"], "data/entry_151.json")
        self.assertFalse(audit["truncated"])
        self.assertEqual(audit["syntax_coverage"], "PASS")
        self.assertFalse(audit["semantic_links_verified"])

    def test_canonical_guide_manifest_chapters_check_tracked_references_only(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        prefix = "data/routes/guide_ultime_manual/"
        self._file(prefix + "present.json", '{"stages":[]}')
        self._file(
            prefix + "manifest_v1.json",
            '{"canonical":{"chapters":['
            '{"id":"ok","file":"present.json"},'
            '{"id":"missing","file":"missing.json"},'
            '{"id":"unsafe","file":"../escape.json"},'
            '{"id":"blank"}'
            ']}}',
        )
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        manifest = next(
            row for row in audit["files"]
            if row["file"] == prefix + "manifest_v1.json"
        )
        self.assertEqual(manifest["manifest_chapter_refs_inspected"], 4)
        self.assertEqual(manifest["manifest_refs_inspected"], 4)
        self.assertEqual(audit["counts"]["manifest_chapter_refs_inspected"], 4)
        self.assertEqual(audit["counts"]["manifest_refs_inspected"], 4)
        self.assertEqual(audit["counts"]["manifest_reference_review_files"], 1)
        self.assertEqual(manifest["manual_manifest_reference_candidates"], [
            {"kind": "MANIFEST_CHAPTER_NOT_TRACKED_REVIEW",
             "chapter_index": 1, "file": "missing.json"},
            {"kind": "MANIFEST_CHAPTER_PATH_UNSAFE_REVIEW",
             "chapter_index": 2, "file": "../escape.json"},
            {"kind": "MANIFEST_CHAPTER_FILE_MISSING_REVIEW", "chapter_index": 3},
        ])
        self.assertEqual(manifest["status"], "VALID_SYNTAX_REVIEW")
        self.assertEqual(audit["syntax_coverage"], "PASS")
        self.assertFalse(audit["semantic_links_verified"])
        self.assertEqual(report["status"], "REVIEW")

    def test_manual_chapter_patch_base_file_dependencies_are_tracked(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        prefix = "data/routes/guide_ultime_manual/"
        self._file(prefix + "base.json", '{"stages":[]}')
        self._file(prefix + "valid.json", '{"base_file":"base.json"}')
        self._file(prefix + "missing.json", '{"base_file":"not-tracked.json"}')
        self._file(prefix + "self.json", '{"base_file":"self.json"}')
        self._file(prefix + "invalid.json", '{"base_file":"../escape.json"}')
        self._file(
            prefix + "manifest_v1.json",
            '{"canonical":{"chapters":[{"file":"valid.json"}]}}',
        )
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        self.assertEqual(audit["counts"]["manual_base_refs_inspected"], 4)
        self.assertEqual(audit["counts"]["manual_base_reference_review_files"], 3)
        entries = {row["file"]: row for row in audit["files"]}
        self.assertEqual(entries[prefix + "valid.json"]["manual_base_reference_candidates"], [])
        self.assertEqual(entries[prefix + "missing.json"]["manual_base_reference_candidates"], [
            {"kind": "MANUAL_BASE_NOT_TRACKED_REVIEW", "file": "not-tracked.json"}
        ])
        self.assertEqual(entries[prefix + "self.json"]["manual_base_reference_candidates"], [
            {"kind": "MANUAL_BASE_SELF_REFERENCE_REVIEW", "file": "self.json"}
        ])
        self.assertEqual(entries[prefix + "invalid.json"]["manual_base_reference_candidates"], [
            {"kind": "MANUAL_BASE_UNSAFE_REVIEW", "file": "../escape.json"}
        ])
        self.assertEqual(audit["syntax_coverage"], "PASS")
        self.assertFalse(audit["semantic_links_verified"])

    def test_manual_patch_cycle_is_review_even_when_all_files_exist(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        prefix = "data/routes/guide_ultime_manual/"
        self._file(prefix + "a.json", '{"base_file":"b.json"}')
        self._file(prefix + "b.json", '{"base_file":"a.json"}')
        self._file(prefix + "c.json", '{"base_file":"a.json"}')
        self._file(
            prefix + "manifest_v1.json",
            '{"canonical":{"chapters":[{"file":"c.json"}]}}',
        )
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        self.assertEqual(audit["counts"]["manual_base_refs_inspected"], 3)
        self.assertEqual(audit["counts"]["manual_base_cycle_files"], 2)
        self.assertEqual(audit["counts"]["manual_base_reference_review_files"], 2)
        entries = {row["file"]: row for row in audit["files"]}
        for filename in ("a.json", "b.json"):
            self.assertEqual(
                entries[prefix + filename]["manual_base_reference_candidates"],
                [{"kind": "MANUAL_BASE_CYCLE_REVIEW"}],
            )
            self.assertEqual(
                entries[prefix + filename]["status"], "VALID_SYNTAX_REVIEW"
            )
        self.assertEqual(entries[prefix + "c.json"]["manual_base_reference_candidates"], [])
        self.assertEqual(audit["syntax_coverage"], "PASS")
        self.assertFalse(audit["semantic_links_verified"])

    def test_canonical_manifest_optional_branches_and_registries_are_scanned(self):
        self._unity()
        self._file("app/ok.py", "pass\n")
        prefix = "data/routes/guide_ultime_manual/"
        self._file(prefix + "present.json", '{"stages":[]}')
        self._file(
            prefix + "manifest_v1.json",
            '{"canonical":{'
            '"chapters":[{"file":"present.json"}],'
            '"conditional_routes":['
            '{"file":"present.json"},'
            '{"file":"../outside.json"},'
            '{"file":"untracked.json"}],'
            '"transversal_routes":[{"file":"present.json"}],'
            '"temporal_registry":"present.json",'
            '"ocre_capture_registry":"untracked.json",'
            '"ocre_final_route":"C:\\\\unsafe.json",'
            '"success_contracts":"present.json"'
            '}}',
        )
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha, with_json=True)
        audit = report["json_semantic_audit"]
        manifest = next(
            row for row in audit["files"]
            if row["file"] == prefix + "manifest_v1.json"
        )
        self.assertEqual(manifest["manifest_chapter_refs_inspected"], 1)
        self.assertEqual(manifest["manifest_refs_inspected"], 9)
        self.assertEqual(audit["counts"]["manifest_refs_inspected"], 9)
        self.assertEqual(manifest["manual_manifest_reference_candidates"], [
            {"kind": "MANIFEST_REFERENCE_UNSAFE_REVIEW",
             "collection": "conditional_routes", "index": 1,
             "file": "../outside.json"},
            {"kind": "MANIFEST_REFERENCE_NOT_TRACKED_REVIEW",
             "collection": "conditional_routes", "index": 2,
             "file": "untracked.json"},
            {"kind": "MANIFEST_REFERENCE_NOT_TRACKED_REVIEW",
             "collection": "ocre_capture_registry",
             "file": "untracked.json"},
            {"kind": "MANIFEST_REFERENCE_UNSAFE_REVIEW",
             "collection": "ocre_final_route",
             "file": "C:\\unsafe.json"},
        ])
        self.assertEqual(audit["syntax_coverage"], "PASS")
        self.assertFalse(audit["semantic_links_verified"])
        self.assertFalse(audit["assets_verified"])
        self.assertEqual(report["status"], "REVIEW")

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
