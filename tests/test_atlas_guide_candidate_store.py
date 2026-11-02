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


def candidate() -> dict:
    source = {
        "schema_version": 1, "rights_verified": True,
        "reference_verified": True, "complete": True,
        "guides": [{
            "guide_id": 99, "title": "Guide exemple",
            "steps": [{
                "source_step_id": "a", "title": "Départ",
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
        changed = copy.deepcopy(self.preview)
        changed["routes"][0]["steps"][0]["manual_title"] = "Nouveau texte"
        with self.assertRaisesRegex(GuideRouteContractError, "stale"):
            publish_candidate(changed, root=self.root)
        self.assertEqual(selected_candidate(self.root), first["candidate_sha256"])

    def test_rollback_previous_generation_with_cas(self) -> None:
        first = publish_candidate(self.preview, root=self.root)
        next_preview = copy.deepcopy(self.preview)
        next_preview["routes"][0]["steps"][0]["manual_title"] = "Modifié"
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
        revised = copy.deepcopy(self.preview)
        revised["routes"][0]["steps"][0]["manual_title"] = "Second version"
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
