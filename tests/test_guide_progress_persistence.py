from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.json_store import InvalidPersistentJsonError
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService


class GuideProgressPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "guide_progress.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_two_live_instances_do_not_overwrite_each_other(self) -> None:
        first = GuideProgressService(self.path)
        second = GuideProgressService(self.path)

        first.set_manual_step_completed("character:1", "guide_a", "stage:a", True)
        second.set_manual_step_completed("character:1", "guide_a", "stage:b", True)

        fresh = GuideProgressService(self.path)
        self.assertEqual(
            {"stage:a", "stage:b"},
            fresh.manual_steps("character:1", "guide_a"),
        )

    def test_manual_steps_returns_caller_owned_copy(self) -> None:
        service = GuideProgressService(self.path)
        service.set_manual_step_completed("character:1", "guide_a", "stage:a", True)

        returned = service.manual_steps("character:1", "guide_a")
        returned.remove("stage:a")
        returned.add("stage:synthetic")

        self.assertEqual(
            {"stage:a"}, service.manual_steps("character:1", "guide_a")
        )
        self.assertTrue(
            service.is_manual_step_completed("character:1", "guide_a", "stage:a")
        )
        self.assertFalse(
            service.is_manual_step_completed("character:1", "guide_a", "stage:synthetic")
        )

    def test_batch_expected_states_reject_stale_snapshot_without_partial_write(self) -> None:
        first = GuideProgressService(self.path)
        second = GuideProgressService(self.path)
        second.set_manual_step_completed("character:2", "guide_a", "stage:1", True)

        with self.assertRaisesRegex(RuntimeError, "changed since selection"):
            first.set_manual_steps_for_characters(
                ("character:1", "character:2"),
                "guide_a",
                "stage:1",
                True,
                expected_completed={"character:1": False, "character:2": False},
            )

        fresh = GuideProgressService(self.path)
        self.assertEqual(set(), fresh.manual_steps("character:1", "guide_a"))
        self.assertEqual({"stage:1"}, fresh.manual_steps("character:2", "guide_a"))

        self.assertTrue(
            first.set_manual_steps_for_characters(
                ("character:1", "character:2"),
                "guide_a",
                "stage:1",
                True,
                expected_completed={"character:1": False, "character:2": True},
            )
        )
        final = GuideProgressService(self.path)
        self.assertEqual({"stage:1"}, final.manual_steps("character:1", "guide_a"))
        self.assertEqual({"stage:1"}, final.manual_steps("character:2", "guide_a"))

    def test_batch_rejects_noncanonical_identity_without_writing(self) -> None:
        service = GuideProgressService(self.path)
        with self.assertRaises(ValueError):
            service.set_manual_steps_for_characters(
                ("character:1", "slot:2"), "guide_a", "stage:1", True,
            )
        self.assertFalse(self.path.exists())

    def test_corrupt_json_is_preserved_and_refused(self) -> None:
        original = b'{"version": 1, "characters": '
        self.path.write_bytes(original)

        with self.assertRaises(InvalidPersistentJsonError):
            GuideProgressService(self.path)

        backups = list(self.path.parent.glob("guide_progress.json.corrupt.*.bak"))
        self.assertEqual(1, len(backups))
        self.assertEqual(original, backups[0].read_bytes())
        self.assertEqual(original, self.path.read_bytes())

    def test_live_reader_observes_coordinated_peer_mutation(self) -> None:
        reader = GuideProgressService(self.path)
        writer = GuideProgressService(self.path)

        writer.set_manual_step_completed("character:1", "guide_a", "stage:a", True)

        self.assertIn("stage:a", reader.manual_steps("character:1", "guide_a"))

    def test_reload_observes_external_file_mutation(self) -> None:
        reader = GuideProgressService(self.path)
        payload = {
            "version": 1,
            "characters": {
                "character:1": {
                    "manual_steps": {
                        "guide_a": ["stage:external"],
                    }
                }
            },
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

        reader.reload()

        self.assertIn("stage:external", reader.manual_steps("character:1", "guide_a"))


    def test_preparation_quantities_are_isolated_and_survive_reopen(self) -> None:
        first = GuideProgressService(self.path)
        first.set_preparation_quantity(
            "character:1", "source_guide:test", "item:123", 3, required=8,
        )
        first.set_preparation_quantity(
            "character:2", "source_guide:test", "item:123", 5, required=8,
        )
        self.assertEqual(
            GuideProgressService(self.path).preparation_quantity(
                "character:1", "source_guide:test", "item:123"
            ), 3,
        )
        self.assertEqual(first.preparation_quantity(
            "character:2", "source_guide:test", "item:123"
        ), 5)
        self.assertEqual(first.preparation_quantity(
            "character:1", "source_guide:other", "item:123"
        ), 0)

    def test_preparation_bounds_and_identity_reject_without_writes(self) -> None:
        service = GuideProgressService(self.path)
        for value in (-1, 9, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                service.set_preparation_quantity(
                    "character:1", "guide_a", "item:123", value, required=8,
                )
        for resource in ("item:0", "item:01", "name:unsigned", "monster:123"):
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                service.set_preparation_quantity(
                    "character:1", "guide_a", resource, 1, required=8,
                )
        with self.assertRaises(ValueError):
            service.set_preparation_quantity(
                "slot:1", "guide_a", "item:123", 1, required=8,
            )
        self.assertFalse(self.path.exists())

    def test_preparation_cas_rejects_stale_and_preserves_manual_steps(self) -> None:
        first = GuideProgressService(self.path)
        second = GuideProgressService(self.path)
        first.set_manual_step_completed("character:1", "guide_a", "stage:a", True)
        first.set_preparation_quantity(
            "character:1", "guide_a", "item:123", 2, required=8,
        )
        with self.assertRaisesRegex(RuntimeError, "changed since reading"):
            second.set_preparation_quantity(
                "character:1", "guide_a", "item:123", 7,
                required=8, expected_quantity=0,
            )
        self.assertTrue(second.set_preparation_quantity(
            "character:1", "guide_a", "item:123", 4,
            required=8, expected_quantity=2,
        ))
        fresh = GuideProgressService(self.path)
        self.assertEqual(fresh.preparation_quantity(
            "character:1", "guide_a", "item:123"
        ), 4)
        self.assertEqual(fresh.manual_steps("character:1", "guide_a"), {"stage:a"})
        self.assertTrue(fresh.set_preparation_quantity(
            "character:1", "guide_a", "item:123", 0,
            required=8, expected_quantity=4,
        ))
        self.assertEqual(fresh.preparation_quantity(
            "character:1", "guide_a", "item:123"
        ), 0)

    def test_preparation_legacy_progress_remains_readable_and_corrupt_counts_rejected(self):
        legacy = {
            "version": 1,
            "characters": {"character:1": {"manual_steps": {"guide_a": ["stage:a"]}}},
        }
        self.path.write_text(json.dumps(legacy), encoding="utf-8")
        service = GuideProgressService(self.path)
        self.assertEqual(service.preparation_quantity(
            "character:1", "guide_a", "item:123"
        ), 0)
        legacy["characters"]["character:1"]["preparation_counts"] = {
            "guide_a": {"item:123": True},
        }
        self.path.write_text(json.dumps(legacy), encoding="utf-8")
        with self.assertRaises(InvalidPersistentJsonError):
            GuideProgressService(self.path)

if __name__ == "__main__":
    unittest.main()
