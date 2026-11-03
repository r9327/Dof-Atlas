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
    read_selected_preview, read_selected_route,
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

    def test_nonfinite_candidate_metadata_cannot_create_store(self) -> None:
        altered = copy.deepcopy(self.preview)
        altered["routes"][0]["source_guide_metadata"]["priority"] = float("inf")
        with self.assertRaisesRegex(GuideRouteContractError, "non-JSON-compatible"):
            publish_candidate(altered, root=self.root)
        self.assertFalse(self.root.exists())

    def test_pinned_candidate_preview_is_read_only_and_exact(self) -> None:
        published = publish_candidate(self.preview, root=self.root)
        digest = published["candidate_sha256"]
        before = sorted(str(path.relative_to(self.root))
                        for path in self.root.rglob("*"))
        preview = read_selected_preview(root=self.root, expected_selected=digest)
        self.assertEqual(preview, self.preview)
        self.assertFalse(preview["certified"])
        self.assertEqual(preview["mode"], "DRY_RUN_ONLY")
        self.assertEqual(
            before, sorted(str(path.relative_to(self.root))
                           for path in self.root.rglob("*"))
        )
        self.assertFalse((self.root / ".writer.lock").exists())
        self.assertFalse((self.root / "data").exists())

    def test_pinned_route_isolated_from_mutation_and_never_activates(self) -> None:
        receipt = publish_candidate(self.preview, root=self.root)
        digest = receipt["candidate_sha256"]
        source_route = self.preview["routes"][0]
        route = read_selected_route(
            root=self.root, expected_selected=digest, route_id="source_guide:99",
        )
        self.assertEqual(route, source_route)
        self.assertEqual(route["source_compliance"], "NOT_CERTIFIED")
        self.assertFalse(route["manual_preview"])
        route["steps"][0]["manual_title"] = "MUTATED BY CALLER"
        route["steps"][0]["manual_sections"]["now"][0]["text"] = "MUTATED"
        reread = read_selected_route(
            root=self.root, expected_selected=digest, route_id="source_guide:99",
        )
        self.assertEqual(reread, source_route)
        self.assertNotIn("MUTATED", str(reread))
        self.assertEqual(selected_candidate(self.root), digest)

    def test_missing_or_mismatched_preview_identity_never_falls_back(self) -> None:
        self.assertFalse(self.root.exists())
        with self.assertRaises(GuideRouteContractError):
            read_selected_preview(root=self.root, expected_selected="1" * 64)
        self.assertFalse(self.root.exists())
        receipt = publish_candidate(self.preview, root=self.root)
        digest = receipt["candidate_sha256"]
        for expected in ("NONE", "0" * 64, "2" * 64, "", 5):
            with self.subTest(expected=expected):
                with self.assertRaises(GuideRouteContractError):
                    read_selected_preview(
                        root=self.root, expected_selected=expected
                    )
        for route_id in ("", "99", "source_guide:404", None, 99):
            with self.subTest(route_id=route_id):
                with self.assertRaises(GuideRouteContractError):
                    read_selected_route(
                        root=self.root, expected_selected=digest,
                        route_id=route_id,
                    )
        self.assertEqual(selected_candidate(self.root), digest)

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

    def test_preview_rejects_stale_selection_after_publish_or_rollback(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        old_digest = first["candidate_sha256"]
        second = publish_candidate(
            candidate(step_title="Nouvelle version"),
            root=self.root, expected_selected=old_digest,
        )
        new_digest = second["candidate_sha256"]
        with self.assertRaisesRegex(GuideRouteContractError, "stale"):
            read_selected_preview(root=self.root, expected_selected=old_digest)
        self.assertEqual(
            read_selected_route(root=self.root, expected_selected=new_digest,
                                route_id="source_guide:99")["steps"][0]["manual_title"],
            "Nouvelle version",
        )
        rollback_candidate(root=self.root, expected_selected=new_digest,
                           restore_sha256=old_digest)
        with self.assertRaisesRegex(GuideRouteContractError, "stale"):
            read_selected_route(root=self.root, expected_selected=new_digest,
                                route_id="source_guide:99")
        self.assertEqual(
            read_selected_route(root=self.root, expected_selected=old_digest,
                                route_id="source_guide:99")["steps"][0]["manual_title"],
            "Départ",
        )

    def test_preview_checks_hash_and_rejects_tampering(self) -> None:
        result = publish_candidate(self.preview, root=self.root)
        digest = result["candidate_sha256"]
        generation = self.root / "generations" / (digest + ".json")
        generation.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(GuideRouteContractError, "SHA mismatch"):
            read_selected_preview(root=self.root, expected_selected=digest)
        with self.assertRaisesRegex(GuideRouteContractError, "SHA mismatch"):
            read_selected_route(
                root=self.root, expected_selected=digest,
                route_id="source_guide:99",
            )

    def test_preview_reuses_hash_verified_bytes_without_reopen(self) -> None:
        result = publish_candidate(self.preview, root=self.root)
        digest = result["candidate_sha256"]
        generation = self.root / "generations" / (digest + ".json")
        original_read_text = Path.read_text

        def reject_generation_text_read(path, *args, **kwargs):
            if path == generation:
                self.fail("selected preview reopened the candidate after hashing")
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", reject_generation_text_read):
            self.assertEqual(
                read_selected_preview(root=self.root, expected_selected=digest),
                self.preview,
            )
            self.assertEqual(
                read_selected_route(
                    root=self.root, expected_selected=digest,
                    route_id="source_guide:99",
                )["steps"][0]["manual_title"],
                "Départ",
            )

    def test_preview_detects_pointer_change_during_generation_read(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        old_digest = first["candidate_sha256"]
        second = publish_candidate(
            candidate(step_title="Autre génération"),
            root=self.root, expected_selected=old_digest,
        )
        new_digest = second["candidate_sha256"]
        rollback_candidate(root=self.root, expected_selected=new_digest,
                           restore_sha256=old_digest)
        from tools import atlas_guide_candidate_store as store

        original = store._verify_generation
        def switch_during_read(root, digest):
            parsed = original(root, digest)
            (self.root / "selected.json").write_text(json.dumps({
                "format": "atlas-guide-candidate-store/v1",
                "candidate_sha256": new_digest,
                "runtime_activation": False,
            }), encoding="utf-8")
            return parsed

        with patch.object(store, "_verify_generation", side_effect=switch_during_read):
            with self.assertRaisesRegex(GuideRouteContractError, "changed during preview"):
                read_selected_preview(root=self.root, expected_selected=old_digest)
        self.assertEqual(selected_candidate(self.root), new_digest)

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

    def test_generation_validation_parses_the_exact_hashed_bytes(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        digest = first["candidate_sha256"]
        generation = self.root / "generations" / (digest + ".json")
        original_read_text = Path.read_text

        def forbid_reopening_generation(path, *args, **kwargs):
            if path == generation:
                self.fail("generation re-opened after SHA-256 validation")
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", forbid_reopening_generation):
            self.assertEqual(selected_candidate(self.root), digest)
            self.assertEqual(
                publish_candidate(
                    self.preview, root=self.root, expected_selected=digest
                )["candidate_sha256"], digest
            )
            self.assertEqual(
                rollback_candidate(
                    root=self.root, expected_selected=digest,
                    restore_sha256=digest,
                )["candidate_sha256"], digest
            )

    def test_tampered_immutable_generation_is_rejected(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        path = self.root / "generations" / (first["candidate_sha256"] + ".json")
        path.write_text("{}")
        with self.assertRaisesRegex(GuideRouteContractError, "SHA mismatch"):
            selected_candidate(self.root)
        with self.assertRaises(GuideRouteContractError):
            rollback_candidate(root=self.root, expected_selected=first["candidate_sha256"])

    def test_selected_pointer_rejects_duplicate_keys_and_nonfinite_values(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        selected = self.root / "selected.json"
        original = selected.read_text(encoding="utf-8")
        for entry in (
            f'"candidate_sha256": "{first["candidate_sha256"]}"',
            '"extra": NaN',
            '"extra": Infinity',
            '"extra": -Infinity',
            '"extra": 1e9999',
        ):
            with self.subTest(entry=entry):
                malformed = original.rstrip()[:-1] + ", " + entry + "}\n"
                selected.write_text(malformed, encoding="utf-8")
                with self.assertRaisesRegex(
                    GuideRouteContractError, "invalid store file"
                ):
                    selected_candidate(self.root)
                selected.write_text(original, encoding="utf-8")
                self.assertEqual(
                    selected_candidate(self.root), first["candidate_sha256"]
                )

    def test_content_addressed_generation_rejects_ambiguous_json(self) -> None:
        import hashlib

        first = publish_candidate(self.preview, root=self.root)
        generation = self.root / "generations" / (first["candidate_sha256"] + ".json")
        original = generation.read_text(encoding="utf-8")
        pointer = self.root / "selected.json"
        for entry in (
            '"guide_count": 1',
            '"extra": NaN',
            '"extra": 1e9999',
        ):
            with self.subTest(entry=entry):
                # Even an attacker who recomputes the filename digest must
                # not get a valid candidate from ambiguous JSON content.
                malformed = original.rstrip()[:-1] + ", " + entry + "}\n"
                digest = hashlib.sha256(malformed.encode("utf-8")).hexdigest()
                (self.root / "generations" / (digest + ".json")).write_text(
                    malformed, encoding="utf-8"
                )
                pointer.write_text(json.dumps({
                    "format": "atlas-guide-candidate-store/v1",
                    "candidate_sha256": digest,
                    "runtime_activation": False,
                }), encoding="utf-8")
                with self.assertRaisesRegex(
                    GuideRouteContractError, "invalid store file"
                ):
                    selected_candidate(self.root)

    def test_partial_candidate_must_obey_both_declared_limits(self) -> None:
        # An API caller can mutate preview metadata without using importer CLI.
        source = {
            "schema_version": 1, "rights_verified": True,
            "reference_verified": True, "complete": False,
            "guides": [
                {"guide_id": str(i), "title": f"Fictional guide {i}",
                 "steps": [{
                     "source_step_id": "one", "title": "Fictional stage",
                     "actions": [{"action_id": "talk", "kind": "talk",
                                  "text": "Synthetic action"}],
                 }]}
                for i in (1, 2)
            ],
        }
        partial = prepare_preview(
            source, expected_guides=3, expected_steps=3, partial=True
        )
        for field in ("expected_guide_count", "expected_step_count"):
            forged = copy.deepcopy(partial)
            forged[field] = 1
            with self.subTest(field=field), self.assertRaisesRegex(
                GuideRouteContractError, "partial candidate exceeds"
            ):
                publish_candidate(forged, root=self.root)
            self.assertFalse(self.root.exists())
        accepted = publish_candidate(partial, root=self.root)
        self.assertEqual(selected_candidate(self.root), accepted["candidate_sha256"])
        self.assertFalse(accepted["certified"])

    def test_all_zero_digests_never_count_as_source_or_selection(self) -> None:
        forged = copy.deepcopy(self.preview)
        forged["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(GuideRouteContractError, "source SHA-256"):
            publish_candidate(forged, root=self.root)
        self.assertFalse(self.root.exists())

        original = publish_candidate(self.preview, root=self.root)
        digest = original["candidate_sha256"]
        with self.assertRaisesRegex(GuideRouteContractError, "restore_sha256"):
            rollback_candidate(
                root=self.root, expected_selected=digest,
                restore_sha256="0" * 64,
            )
        self.assertEqual(selected_candidate(self.root), digest)

        selection = self.root / "selected.json"
        prior = selection.read_text(encoding="utf-8")
        selection.write_text(json.dumps({
            "format": "atlas-guide-candidate-store/v1",
            "candidate_sha256": "0" * 64,
            "runtime_activation": False,
        }), encoding="utf-8")
        with self.assertRaisesRegex(GuideRouteContractError, "selection"):
            selected_candidate(self.root)
        selection.write_text(prior, encoding="utf-8")
        self.assertEqual(selected_candidate(self.root), digest)

    def test_staging_rejects_undeclared_preview_metadata(self) -> None:
        # A forged flag must never travel inside a v1 immutable candidate.
        for field, value in (
            ("runtime_activation", True),
            ("certification_status", "CERTIFIED"),
            ("trusted_source", True),
        ):
            bad = copy.deepcopy(self.preview)
            bad[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                GuideRouteContractError, "unexpected/missing candidate preview fields"
            ):
                publish_candidate(bad, root=self.root)
            self.assertFalse(self.root.exists())

    def test_selected_metadata_cannot_claim_extra_status(self) -> None:
        record = publish_candidate(self.preview, root=self.root)
        selected = self.root / "selected.json"
        original = json.loads(selected.read_text(encoding="utf-8"))
        for field, value in (
            ("certified", True),
            ("runtime_activation_claim", True),
            ("source_rights_verified", True),
        ):
            forged = dict(original)
            forged[field] = value
            selected.write_text(json.dumps(forged), encoding="utf-8")
            with self.subTest(field=field), self.assertRaisesRegex(
                GuideRouteContractError, "invalid selection marker"
            ):
                selected_candidate(self.root)
        selected.write_text(json.dumps(original), encoding="utf-8")
        self.assertEqual(selected_candidate(self.root), record["candidate_sha256"])

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

    def test_stale_publish_to_uninitialized_root_never_creates_store(self) -> None:
        for expected in ("a" * 64, "b" * 64):
            with self.subTest(expected=expected), self.assertRaisesRegex(
                GuideRouteContractError, "stale candidate selection"
            ):
                publish_candidate(self.preview, root=self.root, expected_selected=expected)
            self.assertFalse(self.root.exists())

    def test_rollback_to_uninitialized_root_does_not_create_managed_store(self) -> None:
        with self.assertRaisesRegex(GuideRouteContractError, "missing managed"):
            rollback_candidate(root=self.root, expected_selected="NONE")
        self.assertFalse(self.root.exists())
        self.root.mkdir()
        sentinel = self.root / "foreign-user.json"
        sentinel.write_text('{"untouched": true}', encoding="utf-8")
        with self.assertRaisesRegex(GuideRouteContractError, "missing managed"):
            rollback_candidate(root=self.root, expected_selected="NONE")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), '{"untouched": true}')
        self.assertEqual([path.name for path in self.root.iterdir()], ["foreign-user.json"])

    def test_invalid_publish_cas_pointer_is_rejected_before_store_creation(self) -> None:
        for token in (None, True, "", "../outside", "ABC" * 21 + "A", "a" * 63):
            with self.subTest(pointer=token), self.assertRaisesRegex(
                GuideRouteContractError, "expected_selected"
            ):
                publish_candidate(self.preview, root=self.root, expected_selected=token)
            self.assertFalse(self.root.exists())

    def test_invalid_rollback_pointers_never_change_selection(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        for token in (None, True, "", "../outside", "A" * 64, "a" * 63):
            with self.subTest(pointer=token):
                with self.assertRaisesRegex(GuideRouteContractError, "restore_sha256"):
                    rollback_candidate(root=self.root,
                                       expected_selected=first["candidate_sha256"],
                                       restore_sha256=token)
                with self.assertRaisesRegex(GuideRouteContractError, "expected_selected"):
                    rollback_candidate(root=self.root, expected_selected=token)
                self.assertEqual(selected_candidate(self.root), first["candidate_sha256"])

    def test_dangling_selection_symlink_cannot_be_taken_as_none(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        selected = self.root / "selected.json"
        selected.unlink()
        try:
            selected.symlink_to(self.root / "nonexistent-outside-pointer.json")
        except OSError:
            self.skipTest("Windows symlinks unavailable to this test user")
        with self.assertRaisesRegex(GuideRouteContractError, "symlink"):
            selected_candidate(self.root)
        with self.assertRaisesRegex(GuideRouteContractError, "symlink"):
            publish_candidate(self.preview, root=self.root,
                              expected_selected=first["candidate_sha256"])
        with self.assertRaisesRegex(GuideRouteContractError, "symlink"):
            rollback_candidate(root=self.root,
                               expected_selected=first["candidate_sha256"])
        self.assertTrue(selected.is_symlink())

    def test_boolean_schema_version_does_not_enter_candidate_store(self) -> None:
        malformed = copy.deepcopy(self.preview)
        malformed["schema_version"] = True
        with self.assertRaisesRegex(GuideRouteContractError, "dry-run importer"):
            publish_candidate(malformed, root=self.root)
        self.assertFalse(self.root.exists())

    def test_candidate_store_rejects_source_tree_roots_before_any_write(self) -> None:
        checkout = Path(__file__).resolve().parents[1]
        for folder in ("app", "tools", "tests", "docs", "scripts",
                       ".github", "local_dofus_data", "APP"):
            candidate_root = checkout / folder / "__synthetic_stage_must_not_exist__"
            with self.subTest(folder=folder), self.assertRaisesRegex(
                GuideRouteContractError, "outside repository sources"
            ):
                publish_candidate(self.preview, root=candidate_root)
            self.assertFalse(candidate_root.exists())

    def test_candidate_store_rejects_parent_traversal_before_write(self) -> None:
        checkout = Path(__file__).resolve().parents[1]
        destinations = (
            checkout / "artifacts" / ".." / "app" / "__synthetic_stage_no_write__",
            Path(self.temp.name) / "safe" / ".." / "other",
        )
        for destination in destinations:
            with self.subTest(destination=str(destination)), self.assertRaisesRegex(
                GuideRouteContractError, "parent traversal"
            ):
                publish_candidate(self.preview, root=destination)
        self.assertFalse((checkout / "app" / "__synthetic_stage_no_write__").exists())
        self.assertFalse((Path(self.temp.name) / "other").exists())

    def test_repo_artifacts_candidate_root_is_accepted_without_creating_it(self) -> None:
        from tools.atlas_guide_candidate_store import _safe_root
        checkout = Path(__file__).resolve().parents[1]
        permitted = checkout / "artifacts" / "__synthetic_stage_not_written__"
        self.assertEqual(_safe_root(permitted), permitted.absolute())
        self.assertFalse(permitted.exists())

    def test_artifacts_root_itself_is_not_a_candidate_store(self) -> None:
        checkout = Path(__file__).resolve().parents[1]
        root = checkout / "artifacts"
        from tools.atlas_guide_candidate_store import _safe_root
        with self.assertRaisesRegex(
            GuideRouteContractError, "outside repository sources"
        ):
            _safe_root(root)
        # A managed root is allowed only below artifacts/<dedicated-dir>.
        dedicated = root / "__synthetic_stage_no_write__"
        self.assertEqual(_safe_root(dedicated), dedicated.absolute())
        self.assertFalse(dedicated.exists())

    def test_case_variant_protected_store_root_does_not_write(self) -> None:
        forbidden = Path(self.temp.name) / "DATA" / "candidates"
        with self.assertRaisesRegex(GuideRouteContractError, "data/save/cache"):
            publish_candidate(self.preview, root=forbidden)
        self.assertFalse(forbidden.parent.exists())


if __name__ == "__main__":
    unittest.main()
