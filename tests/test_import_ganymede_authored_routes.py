"""Bulk import refuses incomplete/untrusted routes and never writes on dry run."""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock
import unittest
from pathlib import Path

from tools.import_ganymede_authored_routes import import_authored_routes


class GanymedeAuthoredImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.inbox = root / "incoming"
        self.outbox = root / "published"
        self.inbox.mkdir()
        self.index = root / "ganymede_main_index.json"
        self.index.write_text(json.dumps({"guides": [
            {
                "ganymede_guide_id": source_id,
                "title": f"Guide {source_id}",
                "source_url": f"https://ganymede-app.com/guides/{source_id}",
                "listed_step_count": count,
            }
            for source_id, count in ((2203, 2), (2205, 1))
        ]}), encoding="utf-8")

    def write(self, source_id, count, *, kind="talk", folder=None):
        folder = folder or self.inbox
        target = folder / f"ganymede_{source_id}_instructions.json"
        doc = {
            "schema_version": 1, "source_guide_id": source_id,
            "source_url": f"https://ganymede-app.com/guides/{source_id}",
            "expected_source_step_count": count,
            "rights_basis": "atlas_original",
            "steps": [
                {
                    "source_step_number": num,
                    "title": f"Étape {num}",
                    "instructions": f"Réaliser l'action originale {num}",
                    "actions": [{"kind": kind, "text": f"Parler au PNJ {num}"}],
                } for num in range(1, count + 1)
            ],
        }
        target.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return target

    def run_import(self, **kwargs):
        return import_authored_routes(
            self.inbox, index_path=self.index, target_dir=self.outbox,
            expected_routes=2, **kwargs,
        )

    def test_empty_import_is_not_a_success(self):
        with self.assertRaisesRegex(ValueError, "No authored route"):
            self.run_import(strict=False, apply=True)
        self.assertFalse(self.outbox.exists())

    def test_strict_refuses_missing_before_any_writes(self):
        self.write(2203, 2)
        with self.assertRaisesRegex(ValueError, "Missing 1"):
            self.run_import(apply=True)
        self.assertFalse(self.outbox.exists())

    def test_dry_run_verifies_but_writes_nothing(self):
        self.write(2203, 2)
        self.write(2205, 1)
        report = self.run_import()
        self.assertEqual(report["status"], "DRY_RUN")
        self.assertEqual(report["supplied_routes"], 2)
        self.assertEqual(report["verified_steps"], 3)
        self.assertFalse(self.outbox.exists())

    def test_import_idempotent_and_no_implicit_overwrite(self):
        original = self.write(2203, 2)
        self.write(2205, 1)
        report = self.run_import(apply=True)
        self.assertEqual(report["created"], 2)
        self.assertEqual((self.outbox / original.name).read_bytes(), original.read_bytes())
        self.assertEqual(self.run_import(apply=True)["unchanged"], 2)
        previous = (self.outbox / original.name).read_bytes()
        edited = original.read_text(encoding="utf-8").replace(
            "Réaliser l'action originale 1", "Réaliser une action différente",
        )
        original.write_text(edited, encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.run_import(apply=True)
        self.assertEqual((self.outbox / original.name).read_bytes(), previous)
        report = self.run_import(apply=True, allow_overwrite=True)
        self.assertEqual(report["updated"], 1)
        self.assertEqual((self.outbox / original.name).read_bytes(), original.read_bytes())

    def test_invalid_second_route_does_not_write_first(self):
        self.write(2203, 2)
        self.write(2205, 1, kind="unverified_quest_id")
        with self.assertRaisesRegex(ValueError, "Unverified"):
            self.run_import(apply=True)
        self.assertFalse(self.outbox.exists())

    def test_unknown_id_cannot_enter_runtime(self):
        self.write(2203, 2)
        self.write(2205, 1)
        self.write(9999, 1)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.run_import(apply=True)
        self.assertFalse(self.outbox.exists())

    def test_partial_batch_only_with_explicit_opt_in(self):
        self.write(2205, 1)
        report = self.run_import(strict=False, apply=True)
        self.assertEqual(report["created"], 1)
        self.assertEqual(report["missing_routes"], [2203])
        self.assertTrue((self.outbox / "ganymede_2205_instructions.json").exists())

    def test_partial_publication_failure_restores_previous_files(self):
        first = self.write(2203, 2)
        second = self.write(2205, 1)
        self.run_import(apply=True)
        old_first = (self.outbox / first.name).read_bytes()
        old_second = (self.outbox / second.name).read_bytes()
        first.write_text(first.read_text(encoding="utf-8").replace(
            "Réaliser l'action originale 1", "Réaliser la nouvelle action 1",
        ), encoding="utf-8")
        second.write_text(second.read_text(encoding="utf-8").replace(
            "Réaliser l'action originale 1", "Réaliser la nouvelle action 1",
        ), encoding="utf-8")

        replace = os.replace
        failures = 0

        def fail_second_publish(src, dst):
            nonlocal failures
            if Path(dst).name == second.name and failures == 0:
                failures += 1
                raise OSError("simulated second-file write failure")
            return replace(src, dst)

        with mock.patch(
            "tools.import_ganymede_authored_routes.os.replace",
            side_effect=fail_second_publish,
        ):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.run_import(apply=True, allow_overwrite=True)
        self.assertEqual(failures, 1)
        self.assertEqual((self.outbox / first.name).read_bytes(), old_first)
        self.assertEqual((self.outbox / second.name).read_bytes(), old_second)
        self.assertFalse(list(self.outbox.glob(".ganymede-stage-*")))

    def test_failed_new_batch_leaves_no_half_published_routes(self):
        self.write(2203, 2)
        self.write(2205, 1)
        replace = os.replace

        def fail_second_publish(src, dst):
            if Path(dst).name == "ganymede_2205_instructions.json":
                raise OSError("simulated publication failure")
            return replace(src, dst)

        with mock.patch(
            "tools.import_ganymede_authored_routes.os.replace",
            side_effect=fail_second_publish,
        ):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.run_import(apply=True)
        self.assertFalse(list(self.outbox.glob("ganymede_*_instructions.json")))



if __name__ == "__main__":
    unittest.main()
