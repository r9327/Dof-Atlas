"""The state factories and cache stamps must stay cross-module compatible."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.file_stamp import (
    mtime_ctime_size_stamp, mtime_ctime_size_stamp_or_zero, mtime_size_stamp, resolved_mtime_size_stamp,
)
from app.core.progress_coordinator import empty_progress_payload


class CoreSharedStateTests(unittest.TestCase):
    def test_quest_progress_int_adapter_keeps_legacy_coercion(self) -> None:
        from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
        for value, expected in (("12", 12), (True, 1), (-2, -2), (None, None), ("bad", None)):
            with self.subTest(value=value):
                self.assertEqual(QuestProgressService._safe_int(value), expected)

    def test_progress_payload_is_fresh_and_versioned(self) -> None:
        first = empty_progress_payload()
        self.assertEqual(first, {"version": 1, "characters": {}})
        first["characters"]["character:1"] = {"done": {"123": True}}
        second = empty_progress_payload()
        self.assertEqual(second, {"version": 1, "characters": {}})
        self.assertIsNot(first["characters"], second["characters"])

    def test_progress_root_defaults_reuse_same_payload_and_preserve_data(self) -> None:
        from app.core.progress_coordinator import complete_progress_root

        for payload, expected in (
            ({}, {"version": 1, "characters": {}}),
            ({"characters": {"character:7": {"done": {}}}},
             {"version": 1, "characters": {"character:7": {"done": {}}}}),
            ({"version": 1, "characters": {}, "custom": [1, 2]},
             {"version": 1, "characters": {}, "custom": [1, 2]}),
        ):
            with self.subTest(payload=payload):
                self.assertIs(complete_progress_root(payload), payload)
                self.assertEqual(payload, expected)

    def test_three_progress_schemas_share_envelope_without_losing_domain_rules(self) -> None:
        from app.core.progress_coordinator import progress_characters_for_validation
        from app.modules.encyclopedia.services.guide_progress_service import _guide_progress_schema_error
        from app.modules.encyclopedia.services.quest_progress_service import _quest_progress_schema_error
        from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
            _achievement_progress_schema_error,
        )

        validators = (
            _guide_progress_schema_error,
            _quest_progress_schema_error,
            _achievement_progress_schema_error,
        )
        invalid_roots = (
            (None, "la racine doit être un objet"),
            ({"version": 2}, "version inconnue: 2"),
            ({"characters": []}, "characters doit être un objet"),
            ({"characters": {"character:1": []}},
             "characters['character:1'] doit être un objet"),
        )
        for payload, message in invalid_roots:
            with self.subTest(payload=payload):
                self.assertEqual(progress_characters_for_validation(payload), ({}, message))
                for validator in validators:
                    self.assertEqual(validator(payload), message)
        valid = {"characters": {"character:1": {}}}
        self.assertIs(progress_characters_for_validation(valid)[0], valid["characters"])
        for validator in validators:
            self.assertIsNone(validator(valid))
        self.assertEqual(
            _quest_progress_schema_error({"characters": {"character:1": {"done": []}}}),
            "characters['character:1'].done doit être un objet",
        )
        self.assertEqual(
            _quest_progress_schema_error({"characters": {
                "character:1": {"done": {}}, "character:2": {"quest_items": {"9": []}},
            }}),
            "quest_items['9'] doit être un objet",
        )
        self.assertEqual(
            _guide_progress_schema_error({"characters": {"character:1": {"manual_steps": []}}}),
            "characters['character:1'].manual_steps doit être un objet",
        )
        self.assertEqual(
            _achievement_progress_schema_error(
                {"characters": {"character:1": {"completed_achievements": {}}}}
            ),
            "characters['character:1'].completed_achievements doit être une liste",
        )

    def test_file_stamps_match_existing_cache_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            self.assertEqual(mtime_size_stamp(None), (0, 0))
            self.assertEqual(mtime_size_stamp(path), (0, 0))
            self.assertEqual(resolved_mtime_size_stamp(path), (str(path.resolve()), 0, 0))
            path.write_bytes(b"Atlas cache")
            stat = path.stat()
            stamp = (int(stat.st_mtime_ns), int(stat.st_size))
            self.assertEqual(mtime_size_stamp(path), stamp)
            self.assertEqual(
                resolved_mtime_size_stamp(path), (str(path.resolve()), *stamp)
            )
            self.assertEqual(
                mtime_ctime_size_stamp(path),
                (int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size)),
            )
            self.assertEqual(mtime_ctime_size_stamp_or_zero(path), mtime_ctime_size_stamp(path))
            path.unlink()
            self.assertEqual(mtime_size_stamp(path), (0, 0))
            self.assertIsNone(mtime_ctime_size_stamp(path))
            self.assertEqual(mtime_ctime_size_stamp_or_zero(path), (0, 0, 0))


    def test_write_validation_is_shared_by_three_progress_services(self) -> None:
        from app.core.progress_coordinator import validate_progress_character_keys

        validate_progress_character_keys({"characters": {"character:1": {}}})
        validate_progress_character_keys({})
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            validate_progress_character_keys({"characters": []})
        for invalid in ("slot:1", "character:0", "character:01"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_progress_character_keys({"characters": {invalid: {}}})


if __name__ == "__main__":
    unittest.main()
