from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_guide_ultime_canonical_dependencies import (
    BONTA_DEPENDENT_CHAPTERS,
    CANONICAL_BONTA_FILE,
    audit as audit_dependencies,
)
from tools.audit_guide_ultime_canonical_lock import (
    BASE,
    LOCK,
    MANIFEST,
    EXPECTED_ACTIVE_SOURCE_BASELINE_COMMIT,
    EXPECTED_LOCK_ID,
    EXPECTED_LOCK_SCHEMA_VERSION,
    _composition_source_files,
    _effective_dependency_files,
    _route_level_hook_files,
    _validate_manifest_support_lock,
    audit,
)


class GuideUltimeCanonicalLockTests(unittest.TestCase):
    def test_all_canonical_chapters_match_final_data_lock(self) -> None:
        report = audit()
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["chapter_count"], 13)
        self.assertEqual(report["supporting_route_count"], 12)
        self.assertEqual(report["manifest_support_count"], 11)
        self.assertEqual(report["locked_stage_count"], 267)
        self.assertEqual(report["resolved_stage_count"], 267)
        self.assertEqual(report["errors"], [])
        self.assertTrue(all(row["locked"] for row in report["chapters"]))
        self.assertTrue(all(row["locked"] for row in report["supporting_routes"]))
        self.assertEqual(report["active_source_count"], len(report["active_sources"]))
        self.assertTrue(report["active_sources"])
        self.assertTrue(all(row["locked"] for row in report["active_sources"]), report["errors"])
        self.assertEqual(report["active_source_drift"], [])

    def test_lock_identity_and_baseline_are_pinned_outside_json(self) -> None:
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        report = audit()
        self.assertEqual(int(lock["schema_version"]), EXPECTED_LOCK_SCHEMA_VERSION)
        self.assertEqual(lock["lock_id"], EXPECTED_LOCK_ID)
        self.assertEqual(lock["active_source_baseline_commit"], EXPECTED_ACTIVE_SOURCE_BASELINE_COMMIT)
        self.assertEqual(report["active_source_declared_baseline_commit"], EXPECTED_ACTIVE_SOURCE_BASELINE_COMMIT)
        self.assertEqual(report["active_source_baseline_commit"], EXPECTED_ACTIVE_SOURCE_BASELINE_COMMIT)

    def test_lock_matches_manifest_order_and_declared_counts(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        manifest_rows = sorted(manifest["canonical"]["chapters"], key=lambda row: int(row["order"]))
        lock_rows = sorted(lock["chapters"], key=lambda row: int(row["order"]))
        self.assertEqual(
            [(row["id"], row["file"], int(row["stage_count"])) for row in manifest_rows],
            [(row["id"], row["file"], int(row["stage_count"])) for row in lock_rows],
        )
        self.assertEqual(sum(int(row["stage_count"]) for row in lock_rows), 267)

    def test_each_locked_file_has_a_real_git_blob_fingerprint(self) -> None:
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        for row in [*lock["chapters"], *lock["supporting_routes"]]:
            path = BASE / str(row["file"])
            self.assertTrue(path.is_file(), row)
            sha = str(row.get("git_blob_sha") or "")
            self.assertEqual(len(sha), 40, row)
            self.assertTrue(all(char in "0123456789abcdef" for char in sha), row)

    def test_every_active_composition_source_has_a_baseline_blob_fingerprint(self) -> None:
        report = audit()
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["active_source_count"], len(report["active_sources"]))
        for row in report["active_sources"]:
            expected = str(row.get("expected_git_blob_sha") or "")
            actual = str(row.get("actual_git_blob_sha") or "")
            self.assertEqual(len(expected), 40, row)
            self.assertEqual(len(actual), 40, row)
            self.assertTrue(all(char in "0123456789abcdef" for char in expected), row)
            self.assertTrue(all(char in "0123456789abcdef" for char in actual), row)
            self.assertEqual(expected, actual, row)
            self.assertTrue(row["locked"], row)

    def test_active_source_lock_covers_real_chains_and_excludes_dead_history(self) -> None:
        report = audit()
        self.assertEqual(report["status"], "PASS", report["errors"])
        active = set(report["active_source_files"])
        self.assertIn("manifest_v1.json", active)
        for row in report["chapters"]:
            self.assertTrue(set(row["resolved_from"]).issubset(active), row)

        for filename in ("astrub_v2.json", "astrub_v3.json", "astrub_v4.json", "astrub_v5.json"):
            self.assertIn(filename, active)
        self.assertNotIn("astrub_v1.json", active)
        self.assertNotIn("astrub_v6.json", active)

        for filename in (
            "bonta_1_20_v1.json",
            "bonta_1_22_v2.json",
            "bonta_1_40_v3.json",
            "bonta_1_50_v4.json",
            "bonta_1_60_v5.json",
            "bonta_1_70_v6.json",
            "bonta_1_70_v7.json",
            "bonta_1_80_v8.json",
            "bonta_1_80_v9.json",
            "bonta_1_90_v10.json",
            "bonta_1_100_v11.json",
            "bonta_1_100_v12.json",
            "bonta_1_100_v13.json",
            "bonta_1_100_v14.json",
            "bonta_1_100_v15.json",
            "bonta_1_100_v16.json",
            "bonta_1_100_v17.json",
        ):
            self.assertIn(filename, active)
        self.assertNotIn("bonta_1_80_v7.json", active)

        for filename in (
            "temporal_registry_v11.json",
            "temporal_registry_v12.json",
            "temporal_registry_v13.json",
            "temporal_registry_v14.json",
            "temporal_registry_v15.json",
        ):
            self.assertIn(filename, active)

        for filename in (
            "ocre_final_route_v2.json",
            "ocre_final_route_v1.json",
            "ocre_completion_route_v2.json",
            "ocre_completion_route_v1.json",
            "ocre_capture_registry_v1.json",
        ):
            self.assertIn(filename, active)

    def test_effective_dependencies_combine_depends_on_and_transversal_routes(self) -> None:
        dependencies = _effective_dependency_files({
            "depends_on": ["bonta_1_100_v17.json"],
            "transversal_routes": ["temporal_registry_v15.json"],
        })
        self.assertEqual(dependencies, {"bonta_1_100_v17.json", "temporal_registry_v15.json"})

    def test_route_level_files_only_follow_explicit_route_hooks(self) -> None:
        files = _route_level_hook_files({
            "stages": [{
                "route_hooks": ["ocre_final_route_v2", "BNT-36"],
                "transversal": "ocre_completion_route_v2 puis BNT-40",
            }]
        })
        self.assertEqual(files, {"ocre_final_route_v2.json"})

    def test_raw_base_stage_import_is_part_of_active_composition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "import.json").write_text(json.dumps({"stages": [{"id": "IMPORTED"}]}), encoding="utf-8")
            (root / "base.json").write_text(json.dumps({
                "stages": [{"id": "BASE"}],
                "stage_imports": [{"file": "import.json", "stage_id": "IMPORTED", "after": "BASE"}],
            }), encoding="utf-8")
            wrapper = root / "wrapper.json"
            wrapper.write_text(json.dumps({"base_file": "base.json", "stage_patches": {}}), encoding="utf-8")
            errors: list[dict] = []
            sources, import_roots = _composition_source_files(wrapper, errors)
            self.assertEqual(errors, [])
            self.assertEqual(sources, {"wrapper.json", "base.json", "import.json"})
            self.assertEqual(import_roots, {"import.json"})

    def test_manifest_support_missing_from_lock_fails_standalone_contract(self) -> None:
        canonical = {
            "conditional_routes": [{"id": "class_branch", "file": "branch_v1.json"}],
            "transversal_routes": [],
            "temporal_registry": "temporal_v1.json",
            "ocre_capture_registry": "capture_v1.json",
            "ocre_final_route": "ocre_v1.json",
            "success_contracts": "success_v1.json",
        }
        support_rows = [
            {"id": "temporal_registry", "file": "temporal_v1.json", "manifest_key": "temporal_registry"},
            {"id": "ocre_capture_registry", "file": "capture_v1.json", "manifest_key": "ocre_capture_registry"},
            {"id": "ocre_final_route", "file": "ocre_v1.json", "manifest_key": "ocre_final_route"},
            {"id": "success_contracts", "file": "success_v1.json", "manifest_key": "success_contracts"},
        ]
        errors: list[dict] = []
        _validate_manifest_support_lock(canonical, support_rows, errors)
        self.assertIn("support_lock_missing_for_manifest_route", {row["code"] for row in errors})

    def test_supporting_routes_cover_all_manifest_behavior_switches(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        canonical = manifest["canonical"]
        support = {str(row.get("id") or ""): row for row in lock["supporting_routes"]}
        conditional_ids = {str(row.get("id") or "") for row in canonical.get("conditional_routes", [])}
        transversal_ids = {str(row.get("id") or "") for row in canonical.get("transversal_routes", [])}
        self.assertTrue(conditional_ids.issubset(support))
        self.assertTrue(transversal_ids.issubset(support))
        for key in ("temporal_registry", "ocre_capture_registry", "ocre_final_route", "success_contracts"):
            self.assertIn(key, support)
            self.assertEqual(support[key]["file"], canonical[key])
        self.assertIn("ocre_completion_route", support)
        self.assertEqual(support["ocre_completion_route"]["file"], "ocre_completion_route_v2.json")

    def test_canonical_hook_dependencies_never_use_legacy_bonta_snapshots(self) -> None:
        report = audit_dependencies()
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["errors"], [])
        by_id = {row["id"]: row for row in report["chapters"]}
        for chapter_id in BONTA_DEPENDENT_CHAPTERS:
            self.assertIn(chapter_id, by_id)
            self.assertEqual(by_id[chapter_id]["bonta_dependencies"], [CANONICAL_BONTA_FILE], chapter_id)

    def test_noncanonical_overlays_are_explicitly_excluded_from_lock(self) -> None:
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        overlays = {str(row.get("file") or ""): row for row in lock.get("noncanonical_overlays", [])}
        self.assertIn("astrub_v6.json", overlays)
        self.assertEqual(overlays["astrub_v6.json"]["state"], "CANDIDATE_NOT_LOCKED")
        self.assertTrue((Path(BASE) / "astrub_v6.json").is_file())


if __name__ == "__main__":
    unittest.main()
