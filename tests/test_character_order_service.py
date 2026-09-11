from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from app.constants import KEY_SESSION_ORDER
from app.services.character_order_service import CharacterOrderService
import app.services.profile_settings_service as profile_settings_module


@dataclass(frozen=True)
class Row:
    label: str


class CharacterOrderServiceTests(unittest.TestCase):
    def test_save_preserves_other_profile_values_and_new_instance_keeps_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text(
                json.dumps({"other_setting": 42, KEY_SESSION_ORDER: ["alpha", "beta"]}),
                encoding="utf-8",
            )

            service = CharacterOrderService(profile)
            self.assertTrue(service.save_labels(["Beta", "Alpha"]))

            payload = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(payload["other_setting"], 42)
            self.assertEqual(payload[KEY_SESSION_ORDER], ["beta", "alpha"])
            self.assertEqual(
                CharacterOrderService(profile).load_order(),
                ("beta", "alpha"),
            )

    def test_two_instances_reload_current_profile_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text(json.dumps({"keep": "yes"}), encoding="utf-8")
            first = CharacterOrderService(profile)
            second = CharacterOrderService(profile)

            self.assertTrue(first.save_labels(["Alpha", "Beta"]))
            payload = json.loads(profile.read_text(encoding="utf-8"))
            payload["written_between_instances"] = True
            profile.write_text(json.dumps(payload), encoding="utf-8")

            self.assertTrue(second.save_labels(["Beta", "Alpha"]))
            final_payload = json.loads(profile.read_text(encoding="utf-8"))
            self.assertTrue(final_payload["written_between_instances"])
            self.assertEqual(final_payload[KEY_SESSION_ORDER], ["beta", "alpha"])

    def test_sort_rows_uses_saved_order_and_keeps_unknown_rows_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["beta", "alpha"]}),
                encoding="utf-8",
            )
            service = CharacterOrderService(profile)
            rows = [Row("Alpha"), Row("Gamma"), Row("Beta"), Row("Delta")]

            ordered = service.sort_rows(rows, label_getter=lambda row: row.label)

            self.assertEqual(
                [row.label for row in ordered],
                ["Beta", "Alpha", "Gamma", "Delta"],
            )

    def test_duplicate_empty_and_mixed_case_labels_are_normalized(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text("{}", encoding="utf-8")
            service = CharacterOrderService(profile)

            self.assertTrue(
                service.save_labels([" Alpha ", "", "alpha", "BETA", "Beta"])
            )

            payload = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(payload[KEY_SESSION_ORDER], ["alpha", "beta"])

    def test_legacy_sparse_order_reads_compact_and_migrates_on_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            legacy = ["alpha", "", "beta", "", "gamma", "", "", ""]
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: legacy}),
                encoding="utf-8",
            )
            service = CharacterOrderService(profile)

            self.assertEqual(service.load_order(), ("alpha", "beta", "gamma"))
            self.assertEqual(
                json.loads(profile.read_text(encoding="utf-8"))[KEY_SESSION_ORDER],
                legacy,
            )

            self.assertTrue(service.save_labels(["Beta", "Alpha", "Gamma"]))
            payload = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(
                payload[KEY_SESSION_ORDER],
                ["beta", "alpha", "gamma"],
            )

    def test_unknown_legacy_tokens_are_preserved_without_sparse_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text(
                json.dumps(
                    {
                        KEY_SESSION_ORDER: [
                            "alpha",
                            "legacy_unverified",
                            "",
                            "",
                        ]
                    }
                ),
                encoding="utf-8",
            )
            service = CharacterOrderService(profile)

            self.assertTrue(service.save_labels(["Beta", "Alpha"]))

            payload = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(
                payload[KEY_SESSION_ORDER],
                ["beta", "legacy_unverified", "alpha"],
            )
            self.assertEqual(
                service.load_order(),
                ("beta", "legacy_unverified", "alpha"),
            )

    def test_partial_reorder_preserves_offline_character_anchor(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["alpha", "beta", "gamma"]}),
                encoding="utf-8",
            )
            service = CharacterOrderService(profile)

            self.assertTrue(service.save_labels(["Gamma", "Alpha"]))

            payload = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(
                payload[KEY_SESSION_ORDER],
                ["gamma", "beta", "alpha"],
            )

    def test_logical_order_is_not_limited_to_eight_organizer_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text("{}", encoding="utf-8")
            labels = [f"Character {index}" for index in range(1, 11)]
            service = CharacterOrderService(profile)

            self.assertTrue(service.save_labels(labels))

            expected = tuple(f"character_{index}" for index in range(1, 11))
            self.assertEqual(CharacterOrderService(profile).load_order(), expected)
            payload = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(len(payload[KEY_SESSION_ORDER]), 10)

    def test_remove_label_is_explicit_and_preserves_remaining_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text(
                json.dumps(
                    {
                        "other": 7,
                        KEY_SESSION_ORDER: ["alpha", "", "beta", "offline", ""],
                    }
                ),
                encoding="utf-8",
            )
            service = CharacterOrderService(profile)

            self.assertTrue(service.remove_label(" Beta "))

            payload = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(payload[KEY_SESSION_ORDER], ["alpha", "offline"])
            self.assertEqual(payload["other"], 7)
            self.assertFalse(service.remove_label("Beta"))
            self.assertFalse(service.remove_label(""))

    def test_save_uses_atomic_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profiles.json"
            profile.write_text("{}", encoding="utf-8")
            service = CharacterOrderService(profile)
            original_writer = profile_settings_module._write_json_atomic_unchecked
            calls: list[Path] = []

            def tracked_writer(path, payload):
                calls.append(Path(path))
                return original_writer(path, payload)

            with patch.object(
                profile_settings_module,
                "_write_json_atomic_unchecked",
                side_effect=tracked_writer,
            ):
                self.assertTrue(service.save_labels(["Alpha", "Beta"]))

            self.assertEqual(calls, [profile])
            self.assertEqual(
                json.loads(profile.read_text(encoding="utf-8"))[KEY_SESSION_ORDER],
                ["alpha", "beta"],
            )


if __name__ == "__main__":
    unittest.main()
