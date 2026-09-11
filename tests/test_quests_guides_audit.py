from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.tools import audit_quests_guides as audit_module


_REAL_IMAGE_CHECK = audit_module.is_exploitable_image
_LFS_POINTER_RE = re.compile(
    rb"\Aversion https://git-lfs\.github\.com/spec/v1\r?\n"
    rb"oid sha256:[0-9a-f]{64}\r?\n"
    rb"size [1-9][0-9]*\r?\n?\Z"
)


def _ci_image_source_is_valid(path: Path) -> bool:
    try:
        payload = Path(path).read_bytes()
    except OSError:
        return False
    if len(payload) <= 512 and _LFS_POINTER_RE.fullmatch(payload):
        return True
    return _REAL_IMAGE_CHECK(Path(path))


class QuestsGuidesAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # GitHub-hosted validation intentionally checks out without the bulk image
        # LFS payload. A strict, well-formed LFS pointer proves that the image is
        # versioned source data; malformed pointers and real corrupt images still
        # fail the same audit contract.
        with patch.object(
            audit_module,
            "is_exploitable_image",
            side_effect=_ci_image_source_is_valid,
        ):
            cls.audit = audit_module.build_audit()
        cls.inventory = cls.audit["summary"]["inventory"]
        cls.severities = cls.audit["summary"]["issues_by_severity"]

    def test_valid_lfs_pointer_is_accepted_but_malformed_pointer_is_not(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            valid = Path(tmp) / "valid.png"
            invalid = Path(tmp) / "invalid.png"
            valid.write_bytes(
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha256:" + b"a" * 64 + b"\nsize 123\n"
            )
            invalid.write_bytes(
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha256:not-a-digest\nsize 123\n"
            )
            self.assertTrue(_ci_image_source_is_valid(valid))
            self.assertFalse(_ci_image_source_is_valid(invalid))

    def test_active_quest_catalog_identity_is_consistent(self):
        self.assertEqual(self.inventory["active_quests"], self.inventory["raw_quest_rows"])
        self.assertEqual(self.inventory["active_quests"], self.inventory["active_quest_ids_unique"])
        self.assertEqual(self.inventory["raw_quests_without_id"], 0)
        self.assertEqual(self.inventory["active_duplicate_quest_ids"], 0)
        self.assertEqual(self.inventory["raw_duplicate_quest_ids"], 0)

    def test_guides_resolve_to_active_quest_catalog(self):
        self.assertGreater(self.inventory["active_guides"], 0)
        self.assertGreater(self.inventory["guide_quest_references_total"], 0)
        self.assertEqual(self.inventory["dead_guide_quest_references"], 0)
        self.assertEqual(self.inventory["guides_without_chapters"], 0)
        self.assertEqual(self.inventory["guides_without_quests"], 0)

    def test_prerequisites_images_and_progress_have_no_blocking_breakage(self):
        self.assertEqual(self.inventory["graph_missing_edges"], 0)
        self.assertEqual(self.inventory["graph_self_edges"], 0)
        self.assertEqual(self.inventory["missing_referenced_images"], 0)
        self.assertEqual(self.inventory["bad_format_referenced_images"], 0)
        self.assertEqual(self.inventory["guide_progress_inconsistencies"], 0)
        self.assertEqual(self.inventory["user_progress_invalid_quest_refs"], 0)
        self.assertEqual(self.inventory["user_progress_invalid_objective_refs"], 0)

    def test_no_critical_or_automatic_fixable_issue_remains(self):
        self.assertEqual(self.severities.get("critical", 0), 0)
        self.assertEqual(self.severities.get("fixable", 0), 0)

    def test_manual_review_entries_are_actionable(self):
        for row in self.audit["manual_review"]:
            self.assertTrue(row["subject_id"])
            self.assertTrue(row["title"])
            self.assertTrue(row["field"])
            self.assertTrue(row["reason"])


if __name__ == "__main__":
    unittest.main()
