"""Crash, concurrency and rollback checks for the non-active Guide candidate store."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.services.guide_shared_route_contract import (
    GuideRouteContractError,
)
from tools.atlas_guide_candidate_store import (
    publish_candidate, rollback_candidate, selected_candidate,
)
from tools.atlas_guide_importer import prepare_preview


def candidate(*, step_title: str = "Départ") -> dict:
    source = {
        "schema_version": 1, "rights_verified": True,
        "reference_verified": True, "complete": True,
        "guides": [{
            "guide_id": 99, "title": "Guide exemple",
            "steps": [{
                "source_step_id": "a", "title": step_title,
                "actions": [{
                    "action_id": "talk", "kind": "talk", "text": "Parler au PNJ",
                }],
            }],
        }],
    }
    return prepare_preview(source, expected_guides=1, expected_steps=1)


class CandidateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "candidates"
        self.preview = candidate()

    def test_publish_is_atomic_and_not_a_runtime_install(self) -> None:
        before = copy.deepcopy(self.preview)
        result = publish_candidate(self.preview, root=self.root)
        self.assertEqual(before, self.preview)
        self.assertFalse(result["certified"])
        self.assertFalse(result["runtime_activation"])
        self.assertEqual(result["status"], "CANDIDATE_STORED_NOT_ACTIVE")
        sha = result["candidate_sha256"]
        self.assertEqual(selected_candidate(self.root), sha)
        path = self.root / "generations" / (sha + ".json")
        self.assertEqual(json.loads(path.read_text()), self.preview)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         [".atlas-guide-candidates-v1.json", "generations", "selected.json"])
        self.assertFalse((self.root / "data").exists())

    def test_idempotent_same_selection(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        second = publish_candidate(
            self.preview, root=self.root, expected_selected=first["candidate_sha256"]
        )
        self.assertEqual(first["candidate_sha256"], second["candidate_sha256"])
        self.assertEqual(len(list((self.root / "generations").iterdir())), 1)

    def test_stale_cas_does_not_override_candidate(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        changed = candidate(step_title="Nouveau texte")
        with self.assertRaisesRegex(GuideRouteContractError, "stale"):
            publish_candidate(changed, root=self.root)
        self.assertEqual(selected_candidate(self.root), first["candidate_sha256"])

    def test_rollback_previous_generation_with_cas(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        next_preview = candidate(step_title="Modifié")
        second = publish_candidate(
            next_preview, root=self.root, expected_selected=first["candidate_sha256"]
        )
        rollback = rollback_candidate(
            root=self.root, expected_selected=second["candidate_sha256"],
            restore_sha256=first["candidate_sha256"],
        )
        self.assertFalse(rollback["certified"])
        self.assertEqual(selected_candidate(self.root), first["candidate_sha256"])
        self.assertEqual(len(list((self.root / "generations").iterdir())), 2)
        with self.assertRaisesRegex(GuideRouteContractError, "stale"):
            rollback_candidate(
                root=self.root, expected_selected=second["candidate_sha256"]
            )

    def test_rollback_to_no_selection_is_not_an_install(self) -> None:
        existing = publish_candidate(self.preview, root=self.root)
        result = rollback_candidate(
            root=self.root, expected_selected=existing["candidate_sha256"]
        )
        self.assertEqual(result["candidate_sha256"], "NONE")
        self.assertEqual(selected_candidate(self.root), "NONE")

    def test_concurrent_lock_blocks_without_mutation(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        lock = self.root / ".writer.lock"
        lock.mkdir()
        try:
            with self.assertRaisesRegex(GuideRouteContractError, "concurrent"):
                publish_candidate(
                    self.preview, root=self.root, expected_selected=first["candidate_sha256"]
                )
            self.assertEqual(selected_candidate(self.root), first["candidate_sha256"])
        finally:
            lock.rmdir()

    def test_crash_on_pointer_replace_preserves_previous_selection(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        revised = candidate(step_title="Second version")
        with patch("tools.atlas_guide_candidate_store.os.replace", side_effect=OSError("disk fault")):
            with self.assertRaisesRegex(OSError, "disk fault"):
                publish_candidate(
                    revised, root=self.root, expected_selected=first["candidate_sha256"]
                )
        self.assertEqual(selected_candidate(self.root), first["candidate_sha256"])
        self.assertFalse((self.root / ".writer.lock").exists())
        result = publish_candidate(
            revised, root=self.root, expected_selected=first["candidate_sha256"]
        )
        self.assertNotEqual(result["candidate_sha256"], first["candidate_sha256"])

    def test_tampered_immutable_generation_is_rejected(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        path = self.root / "generations" / (first["candidate_sha256"] + ".json")
        path.write_text("{}")
        with self.assertRaisesRegex(GuideRouteContractError, "SHA mismatch"):
            selected_candidate(self.root)
        with self.assertRaises(GuideRouteContractError):
            rollback_candidate(root=self.root, expected_selected=first["candidate_sha256"])

    def test_incomplete_or_fake_certificate_is_rejected(self) -> None:
        for field, value in (("certified", True), ("mode", "APPLY"),
                             ("guide_count", 123), ("status", "CERTIFIED")):
            malformed = copy.deepcopy(self.preview)
            malformed[field] = value
            with self.subTest(field=field), self.assertRaises(GuideRouteContractError):
                publish_candidate(malformed, root=self.root)
        self.assertFalse(self.root.exists())

    def test_action_count_and_false_numeric_metadata_never_published(self) -> None:
        for field, value in (
            ("action_count", 999),
            ("action_count", True),
            ("step_count", True),
            ("guide_count", True),
            ("expected_guide_count", 0),
            ("expected_step_count", "1"),
            ("is_partial", "false"),
        ):
            malformed = copy.deepcopy(self.preview)
            malformed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                GuideRouteContractError
            ):
                publish_candidate(malformed, root=self.root)
        self.assertFalse(self.root.exists())

    def test_failed_atomic_generation_write_leaves_no_partial_named_file(self) -> None:
        with patch("tools.atlas_guide_candidate_store.os.replace",
                   side_effect=OSError("injected IO failure")):
            with self.assertRaisesRegex(OSError, "injected IO failure"):
                publish_candidate(self.preview, root=self.root)
        self.assertEqual(list((self.root / "generations").glob("*.json")), [])
        self.assertEqual(
            list((self.root / "generations").glob(".atlas-stage-*")), []
        )
        self.assertEqual(selected_candidate(self.root), "NONE")
        result = publish_candidate(self.preview, root=self.root)
        self.assertEqual(selected_candidate(self.root), result["candidate_sha256"])

    def test_selected_metadata_symlink_cannot_escape_store(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        selected = self.root / "selected.json"
        saved_content = selected.read_text(encoding="utf-8")
        outside = Path(self.temp.name) / "outside-sensitive.json"
        outside.write_text(saved_content, encoding="utf-8")
        selected.unlink()
        try:
            selected.symlink_to(outside)
        except OSError:
            self.skipTest("Windows symlinks unavailable to this test user")
        with self.assertRaisesRegex(GuideRouteContractError, "symlink"):
            publish_candidate(
                self.preview, root=self.root,
                expected_selected=first["candidate_sha256"],
            )
        self.assertEqual(outside.read_text(encoding="utf-8"), saved_content)

    def test_generation_directory_symlink_cannot_write_outside(self) -> None:
        self.root.mkdir()
        marker = self.root / ".atlas-guide-candidates-v1.json"
        marker.write_text(
            json.dumps({"format": "atlas-guide-candidate-store/v1",
                        "runtime_activation": False}),
            encoding="utf-8",
        )
        outside = Path(self.temp.name) / "unrelated-user-folder"
        outside.mkdir()
        try:
            (self.root / "generations").symlink_to(
                outside, target_is_directory=True
            )
        except OSError:
            self.skipTest("Windows directory symlinks unavailable to test user")
        with self.assertRaisesRegex(GuideRouteContractError, "symlink"):
            publish_candidate(self.preview, root=self.root)
        self.assertEqual(list(outside.iterdir()), [])

    def test_manual_title_cannot_diverge_from_source_title(self) -> None:
        altered = copy.deepcopy(self.preview)
        altered["routes"][0]["steps"][0]["manual_title"] = "Falsified UI title"
        with self.assertRaisesRegex(GuideRouteContractError, "stage title"):
            publish_candidate(altered, root=self.root)
        self.assertFalse(self.root.exists())

    def test_canonical_route_rebuild_blocks_forged_header_index_and_flags(self) -> None:
        for mutation in ("page_index", "guide_label", "manual_manifest",
                         "stage_source", "route_model", "extra_route_flag"):
            bad = copy.deepcopy(self.preview)
            route = bad["routes"][0]
            card = route["steps"][0]
            if mutation == "page_index":
                card["index"] = 800
            elif mutation == "guide_label":
                card["manual_chapter_label"] = "Fake alternate header"
            elif mutation == "manual_manifest":
                route["manual_manifest"] = True
            elif mutation == "stage_source":
                card["manual_source"] = False
            elif mutation == "route_model":
                route["route_model"] = "other_renderer"
            else:
                route["certified"] = True
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                GuideRouteContractError, "canonical source-to-UI projection"
            ):
                publish_candidate(bad, root=self.root)
        self.assertFalse(self.root.exists())

    def test_original_guide_metadata_must_remain_consistent(self) -> None:
        bad = copy.deepcopy(self.preview)
        bad["routes"][0]["source_guide_metadata"]["title"] = "Other title"
        with self.assertRaises(GuideRouteContractError):
            publish_candidate(bad, root=self.root)
        bad = copy.deepcopy(self.preview)
        bad["routes"][0]["source_guide_metadata"]["guide_id"] = 123
        with self.assertRaises(GuideRouteContractError):
            publish_candidate(bad, root=self.root)
        self.assertFalse(self.root.exists())

    def test_candidate_stage_identity_must_match_original_source(self) -> None:
        for change in ("stage", "chapter", "source_step", "missing_actions"):
            malformed = copy.deepcopy(self.preview)
            stage = malformed["routes"][0]["steps"][0]
            if change == "stage":
                stage["manual_stage_id"] = "source:99:wrong"
            elif change == "chapter":
                stage["manual_chapter_id"] = "different-route"
            elif change == "source_step":
                stage["manual_runtime_metadata"]["source_step"]["source_step_id"] = "wrong"
            else:
                stage["manual_runtime_metadata"]["source_step"]["actions"] = None
            with self.subTest(change=change), self.assertRaises(
                GuideRouteContractError
            ):
                publish_candidate(malformed, root=self.root)
        self.assertFalse(self.root.exists())

    def test_ui_projection_cannot_drop_rewrite_or_hide_source_action(self) -> None:
        for change in ("missing_row", "missing_line", "wrong_text",
                       "wrong_action_id", "wrong_source_action"):
            malformed = copy.deepcopy(self.preview)
            stage = malformed["routes"][0]["steps"][0]
            rows = stage["manual_sections"]["now"]
            if change == "missing_row":
                rows.clear()
            elif change == "missing_line":
                stage["manual_lines"].clear()
            elif change == "wrong_text":
                rows[0]["text"] = "Not in source"
                stage["manual_lines"][0]["text"] = "Not in source"
            elif change == "wrong_action_id":
                rows[0]["source_action_id"] = "rogue"
                stage["manual_lines"][0]["source_action_id"] = "rogue"
            else:
                rows[0]["source_action"]["text"] = "falsified"
                stage["manual_lines"][0]["source_action"]["text"] = "falsified"
            with self.subTest(change=change), self.assertRaises(
                GuideRouteContractError
            ):
                publish_candidate(malformed, root=self.root)
        self.assertFalse(self.root.exists())

    def test_preparation_resources_and_travel_cannot_be_lost_in_projection(self) -> None:
        source = {
            "schema_version": 1, "rights_verified": True,
            "reference_verified": True, "complete": True,
            "guides": [{"guide_id": 99, "title": "SYNTHETIC",
                        "steps": [{
                            "source_step_id": "s", "title": "Fake scene",
                            "coordinates": [-1, 2],
                            "actions": [
                                {"action_id": "prep", "kind": "prepare",
                                 "text": "Prepare synthetic item",
                                 "items": [{"name": "Fake item", "quantity": 2}]},
                                {"action_id": "go", "kind": "travel",
                                 "text": "Travel [-1,2]", "coordinates": [-1, 2]},
                                {"action_id": "battle", "kind": "combat",
                                 "text": "Fight synthetic monster",
                                 "monsters": [{"name": "Fake monster", "quantity": 1}]},
                            ],
                        }]}],
        }
        source_preview = prepare_preview(source, expected_guides=1, expected_steps=1)
        accepted = publish_candidate(source_preview, root=self.root)
        self.assertEqual(accepted["status"], "CANDIDATE_STORED_NOT_ACTIVE")
        # Each alteration must fail without modifying a previous generation.
        for alteration in ("resource_names", "preparation", "travel_position",
                           "wrong_section", "wrong_kind", "step_position"):
            with tempfile.TemporaryDirectory() as scratch:
                root = Path(scratch) / "candidates"
                bad = copy.deepcopy(source_preview)
                card = bad["routes"][0]["steps"][0]
                if alteration == "resource_names":
                    card["manual_resource_names"] = []
                elif alteration == "preparation":
                    card["a_preparer"] = []
                elif alteration == "travel_position":
                    card["manual_sections"]["now"][0]["position"] = "[9,9]"
                elif alteration == "wrong_section":
                    card["manual_sections"]["opportunity"].append(
                        card["manual_sections"]["now"].pop(0)
                    )
                    card["manual_lines"] = [
                        row for section in ("now", "opportunity", "keep", "boss", "before_leave")
                        for row in card["manual_sections"][section]
                    ]
                elif alteration == "wrong_kind":
                    card["manual_sections"]["now"][1]["kind"] = "action"
                else:
                    card["manual_route_position"] = "9,9"
                with self.subTest(alteration=alteration), self.assertRaises(
                    GuideRouteContractError
                ):
                    publish_candidate(bad, root=root)
                self.assertFalse(root.exists())
        self.assertEqual(
            selected_candidate(self.root), accepted["candidate_sha256"]
        )

    def test_foreign_existing_folder_is_not_adopted(self) -> None:
        self.root.mkdir()
        (self.root / "sensitive-user-data.json").write_text("{}")
        with self.assertRaisesRegex(GuideRouteContractError, "unmanaged"):
            publish_candidate(self.preview, root=self.root)
        self.assertTrue((self.root / "sensitive-user-data.json").exists())

    def test_missing_rollback_generation_fails_closed(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        with self.assertRaisesRegex(GuideRouteContractError, "missing"):
            rollback_candidate(root=self.root, expected_selected=first["candidate_sha256"],
                               restore_sha256="b" * 64)
        self.assertEqual(selected_candidate(self.root), first["candidate_sha256"])


if __name__ == "__main__":
    unittest.main()
