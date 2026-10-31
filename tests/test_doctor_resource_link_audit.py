"""Focused contract for Doctor's advisory resource-consumer inventory."""
import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.resource_link_audit import inspect_resource_links


class DoctorResourceLinkTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def file(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")

    def audit(self, tracked):
        return inspect_resource_links(self.root, tracked,
                                      [p for p in tracked if p.endswith(".py")],
                                      [p for p in tracked if p.endswith(".json")])

    def test_resolved_and_missing_and_dynamic_never_authorize_deletion(self):
        self.file("app/view.py", 'ICON = "data/icons/a.png"\nUNKNOWN = "data/icons/lost.png"\n')
        self.file("data/manifest.json", json.dumps({"file": "data/icons/b.png"}))
        tracked = ["app/view.py", "data/manifest.json", "data/icons/a.png", "data/icons/b.png", "data/icons/c.png"]
        report = self.audit(tracked)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["counts"]["static_resolved_resources"], 2)
        self.assertEqual(report["counts"]["no_static_consumer_candidates"], 2)
        self.assertEqual(report["counts"]["unresolved_literals"], 1)
        self.assertFalse(report["automatic_deletion_authorized"])
        self.assertFalse(report["runtime_consumers_verified"])

    def test_basename_only_is_weak_evidence_and_sample_count_is_exact(self):
        self.file("app/view.py", 'IMG = "flag.png"\n')
        tracked = ["app/view.py", "data/icons/flag.png", "data/old/flag.png"]
        result = self.audit(tracked)
        self.assertEqual(result["counts"]["static_resolved_resources"], 0)
        self.assertEqual(result["counts"]["basename_possible_resources"], 2)
        self.assertEqual(result["counts"]["no_static_consumer_candidates"], 0)
        self.assertEqual(result["ambiguous_literal_examples"][0]["candidate_count"], 2)

    def test_collector_reuses_parsed_ast_and_json_without_duplicate_reads(self):
        import ast
        from tools.atlas_doctor_lib.resource_link_audit import ResourceLinkCollector
        tracked = ["app/view.py", "data/meta.json", "data/icons/a.png"]
        collector = ResourceLinkCollector(tracked)
        collector.inspect_python_tree("app/view.py", ast.parse('ICON = "data/icons/a.png"'))
        collector.observe_json("data/meta.json", {"icon": "data/icons/a.png"})
        result = collector.finish()
        self.assertEqual(result["counts"]["python_files_scanned"], 1)
        self.assertEqual(result["counts"]["json_files_scanned"], 1)
        self.assertEqual(result["counts"]["static_resolved_resources"], 1)
        self.assertFalse(result["automatic_deletion_authorized"])

    def test_missing_source_fails_closed(self):
        result = self.audit(["app/missing.py", "data/missing.json"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(len(result["scan_errors"]), 2)
        self.assertFalse(result["automatic_deletion_authorized"])

    def test_page_all_candidates_without_false_cleanup(self):
        self.file("app/view.py", "pass\n")
        tracked = ["app/view.py"] + [f"data/icons/unused_{i:03d}.png" for i in range(125)]
        pages = [inspect_resource_links(self.root, tracked, ["app/view.py"], [], offset=i)
                 for i in (0, 40, 80, 120)]
        names = [name for page in pages for name in page["no_static_consumer_examples"]]
        self.assertEqual(len(names), 125)
        self.assertEqual(len(set(names)), 125)
        self.assertTrue(all(page["no_static_consumer_total"] == 125 for page in pages))
        self.assertEqual(pages[0]["no_static_consumer_next_offset"], 40)
        self.assertIsNone(pages[-1]["no_static_consumer_next_offset"])
        self.assertTrue(all(not page["automatic_deletion_authorized"] for page in pages))

    def test_single_pass_exhaustive_export_lists_every_candidate(self):
        from tools.atlas_doctor_lib.resource_link_audit import ResourceLinkCollector
        tracked = [f"data/unlinked_{i:03d}.json" for i in range(105)]
        collector = ResourceLinkCollector(tracked)
        short = collector.finish()
        self.assertNotIn("no_static_consumer_all_candidates", short)
        full = collector.finish(include_all=True)
        self.assertEqual(len(full["no_static_consumer_all_candidates"]), 105)
        self.assertEqual(full["no_static_consumer_total"], 105)
        self.assertTrue(full["all_candidates_exported"])
        self.assertFalse(full["automatic_deletion_authorized"])

    def test_untrusted_parent_path_never_resolves(self):
        self.file("app/view.py", 'DATA = "../escape.json"\n')
        result = self.audit(["app/view.py"])
        self.assertEqual(result["counts"]["unsafe_literals"], 1)
        self.assertFalse(result["automatic_deletion_authorized"])

    def test_all_reference_occurrences_exported_not_just_first_40(self):
        from tools.atlas_doctor_lib.resource_link_audit import ResourceLinkCollector
        tracked = ["app/view.py"] + [
            f"data/variant_{i:02}/flag.png" for i in range(7)
        ]
        collector = ResourceLinkCollector(tracked)
        for index in range(65):
            collector.inspect_literal("app/view.py", f"data/not_found_{index:03}.png", index + 1)
        for index in range(45):
            collector.inspect_literal("app/view.py", f"../escape_{index:03}.png", 100 + index)
        for index in range(60):
            collector.inspect_literal("app/view.py", "flag.png", 200 + index)
        result = collector.finish(include_all=True)
        self.assertEqual(len(result["unresolved_literal_examples"]), 40)
        self.assertEqual(len(result["unresolved_literal_all_candidates"]), 110)
        self.assertEqual(len(result["ambiguous_literal_examples"]), 40)
        self.assertEqual(len(result["ambiguous_literal_all_candidates"]), 60)
        self.assertEqual(result["ambiguous_literal_all_candidates"][0]["candidate_count"], 7)
        self.assertEqual(len(result["ambiguous_literal_all_candidates"][0]["candidates"]), 7)
        self.assertTrue(result["all_link_candidates_exported"])
        self.assertFalse(result["automatic_deletion_authorized"])

    def test_json_key_values_and_pointer_preserve_provenance(self):
        from tools.atlas_doctor_lib.resource_link_audit import ResourceLinkCollector
        tracked = ["data/manifest.json", "data/icons/present.png"]
        collector = ResourceLinkCollector(tracked)
        collector.observe_json("data/manifest.json", {
            "images": [{"data/icons/missing.png": "data/icons/present.png"}],
            "path/with~escape": {"key_missing.png": "ignored"},
        })
        result = collector.finish(include_all=True)
        self.assertEqual(result["counts"]["static_resolved_resources"], 1)
        self.assertEqual(result["counts"]["unresolved_literals"], 2)
        findings = {x["literal"]: x for x in result["unresolved_literal_all_candidates"]}
        self.assertEqual(findings["data/icons/missing.png"]["json_pointer"],
                         "/images/0/data~1icons~1missing.png")
        self.assertEqual(findings["data/icons/missing.png"]["json_role"], "key")
        self.assertEqual(findings["key_missing.png"]["json_pointer"],
                         "/path~1with~0escape/key_missing.png")
        self.assertTrue(result["all_link_candidates_exported"])

    def test_scripts_windows_and_tools_are_audited_as_possible_consumers(self):
        self.file("scripts/windows/build.py", 'IMAGE = "data/icons/used.png"\n')
        self.file("tools/packager.py", 'OTHER = "data/icons/also.png"\n')
        tracked = ["scripts/windows/build.py", "tools/packager.py",
                   "data/icons/used.png", "data/icons/also.png"]
        report = self.audit(tracked)
        self.assertEqual(report["counts"]["static_resolved_resources"], 2)
        self.assertEqual(report["counts"]["python_files_scanned"], 2)



if __name__ == "__main__":
    unittest.main()
