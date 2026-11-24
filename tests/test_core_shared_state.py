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

    def test_external_quest_save_cannot_overwrite_newer_disk_snapshot(self) -> None:
        import json
        from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quests.json"
            service = QuestProgressService(path)
            service.set_quest_completed("character:1", 42, True)
            external = {"version": 1, "characters": {"character:1": {"done": {"42": True, "123": True}}}}
            path.write_text(json.dumps(external), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "snapshot is stale"):
                service.save()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), external)
            self.assertTrue(service.is_quest_completed("character:1", 123))

    def test_scalar_and_batch_guide_progress_share_same_persistence(self) -> None:
        from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide.json"
            first, second = GuideProgressService(path), GuideProgressService(path)
            self.assertTrue(first.set_manual_step_completed("character:1", "guide", "step", True))
            self.assertFalse(second.set_manual_steps_for_characters(("character:1",), "guide", "step", True))
            self.assertTrue(second.set_manual_steps_for_characters(("character:1", "character:2"), "guide", "step", True))
            self.assertTrue(first.is_manual_step_completed("character:2", "guide", "step"))
            self.assertTrue(first.set_manual_step_completed("character:1", "guide", "step", False))
            self.assertFalse(second.is_manual_step_completed("character:1", "guide", "step"))
            self.assertTrue(second.is_manual_step_completed("character:2", "guide", "step"))

    def test_guide_quest_count_uses_same_unique_completion_logic(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock
        from app.modules.encyclopedia.services.guide_progress_calculator import GuideProgressCalculator, ProgressCount

        progress = Mock()
        progress.completed_quest_ids.return_value = {17}
        calculator = GuideProgressCalculator(progress, Mock(), Mock(), {})
        steps = (
            SimpleNamespace(step_type="quest", entity_id=17, counts_for_completion=True),
            SimpleNamespace(step_type="quest", entity_id=17, counts_for_completion=True),
            SimpleNamespace(step_type="quest", entity_id=18, counts_for_completion=True),
            SimpleNamespace(step_type="quest", entity_id=19, counts_for_completion=False),
            SimpleNamespace(step_type="info", entity_id=None, counts_for_completion=True),
        )
        self.assertEqual(calculator.quest_steps_progress(SimpleNamespace(id="test"), steps, "character:1"), ProgressCount(1, 2))
        self.assertEqual(calculator.quest_ids_progress("test", (17, 17, 18), "character:1"), ProgressCount(1, 2))

    def test_achievement_objective_cache_signature_skips_invalid_numeric_values(self) -> None:
        from app.modules.encyclopedia.services.progress_service import AchievementProgressService

        self.assertEqual(
            AchievementProgressService._manual_objectives_signature({
                "completed_objectives": {"17": [4, "4", 8, float("inf"), None], "bad": [3]}
            }),
            ((17, (4, 8)),),
        )

    def test_map_manifest_recovers_from_wrong_root_and_preserves_atomic_writes(self) -> None:
        from unittest.mock import patch
        from app.services.maps import map_manifest

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            with patch.object(map_manifest, "MAP_MANIFEST_PATH", path):
                path.write_text("[]", encoding="utf-8")
                self.assertEqual(map_manifest.load_map_entries(), [])
                path.write_text("{", encoding="utf-8")
                self.assertEqual(map_manifest.load_map_entries(), [])
                map_manifest.write_json(path, {"maps": [], "name": "Éliotrope"})
                self.assertEqual(map_manifest.load_manifest()["name"], "Éliotrope")

    def test_organizer_settings_and_zaap_readers_share_existing_numeric_contracts(self) -> None:
        from app.core.settings import int_value
        from app.core.profile_settings import read_zaap_button_ratios as profile_reader
        from app.core.zaap_shortcuts import read_zaap_button_ratios, update_zaap_shortcuts_field
        from app.core.progress_coordinator import coordinator_for

        self.assertEqual(int_value("42", 7), 42)
        self.assertEqual(int_value(float("inf"), 7), 7)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zaap.json"
            value = {"x_ratio": 0.25, "y_ratio": 0.75}
            update_zaap_shortcuts_field(path, "zaap_button", value)
            self.assertEqual(profile_reader(path=path), (0.25, 0.75))
            self.assertEqual(read_zaap_button_ratios(path=path), (0.25, 0.75))
            generation = coordinator_for(path).generation
            update_zaap_shortcuts_field(path, "zaap_button", value)
            self.assertEqual(coordinator_for(path).generation, generation)

    def test_quest_offset_cache_is_rebuilt_if_gzip_is_truncated(self) -> None:
        from app.quest_source_index import JsonSourceMapping

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "source.json"
            path.write_text('{"entries": {"a": {"name": "test"}}}', encoding="utf-8")
            cache_root = root / "cache"
            first = JsonSourceMapping(path, cache_root, "entries")
            try:
                self.assertEqual(first["a"], {"name": "test"})
            finally:
                first.close()
            cache, = cache_root.glob("source_*.json.gz")
            cache.write_bytes(cache.read_bytes()[:-8])
            second = JsonSourceMapping(path, cache_root, "entries")
            try:
                self.assertEqual(second["a"], {"name": "test"})
            finally:
                second.close()

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

    def test_progress_character_writer_repairs_only_selected_row(self) -> None:
        from app.core.progress_coordinator import mutable_progress_character

        payload = {"characters": {"character:1": "invalid", "character:2": {"ok": True}}}
        row = mutable_progress_character(
            payload, "character:1", defaults={"done": {}},
        )
        row["done"]["42"] = True
        self.assertEqual(payload["characters"]["character:1"], {"done": {"42": True}})
        self.assertEqual(payload["characters"]["character:2"], {"ok": True})
        self.assertIs(mutable_progress_character(payload, "character:1"), row)
        broken_root = {"characters": "bad"}
        self.assertEqual(
            mutable_progress_character(broken_root, "character:3"), {},
        )
        self.assertEqual(broken_root, {"characters": {"character:3": {}}})

    def test_progress_character_reader_never_mutates_root_or_corrupt_rows(self) -> None:
        from app.core.progress_coordinator import read_progress_character

        row = {"done": {"8": True}}
        payload = {"characters": {"character:1": row, "character:2": "bad"}}
        self.assertIs(read_progress_character(payload, " character:1 "), row)
        self.assertEqual(read_progress_character(payload, "character:2"), {})
        self.assertEqual(read_progress_character(payload, ""), {})
        self.assertEqual(read_progress_character({"characters": None}, "character:1"), {})
        self.assertEqual(payload["characters"]["character:2"], "bad")

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

    def test_compatibility_save_refuses_stale_peer_for_all_progress_domains(self) -> None:
        from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
        from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
        from app.modules.encyclopedia.services.serialized_achievement_progress_service import AchievementProgressService

        with tempfile.TemporaryDirectory() as tmp:
            for service_type, domain in (
                (GuideProgressService, "Guide"),
                (QuestProgressService, "Quest"),
                (AchievementProgressService, "Achievement"),
            ):
                with self.subTest(domain=domain):
                    path = Path(tmp) / f"{domain}.json"
                    first, second = service_type(path), service_type(path)
                    first.save()
                    with self.assertRaisesRegex(RuntimeError, f"{domain} progress snapshot is stale"):
                        second.save()
                    second.save()

    def test_nested_progress_map_validation_preserves_first_error(self) -> None:
        from app.core.progress_coordinator import progress_mapping_values_error

        self.assertIsNone(progress_mapping_values_error("manual_steps", {"g": []}, value_type=list))
        self.assertEqual(
            progress_mapping_values_error("completed_objectives", {"1": [], "2": {}, "3": None}, value_type=list),
            "completed_objectives['2'] doit être une liste",
        )
        self.assertEqual(
            progress_mapping_values_error("quest_items", {"1": []}, value_type=dict),
            "quest_items['1'] doit être un objet",
        )

    def test_character_cache_uses_one_order_snapshot_and_returns_detached_rows(self) -> None:
        from unittest.mock import patch
        from app.pages import quest_character_cache as cache
        from app.quest_catalog import QuestCharacter

        rows = [QuestCharacter("character:1", "Alpha", 1), QuestCharacter("character:2", "Beta", 2)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            cache.clear_quest_character_cache()
            try:
                with patch.object(cache, "_semantic_session_order", return_value=("beta", "alpha")) as order:
                    with patch.object(cache, "_ORIGINAL_LOAD_QUEST_CHARACTERS", return_value=rows) as load:
                        first = cache.cached_load_quest_characters(path / "profile", path / "clients")
                        self.assertEqual([row.label for row in first], ["Beta", "Alpha"])
                        self.assertEqual(order.call_count, 1)
                        first[0].label = "Changed"
                        second = cache.cached_load_quest_characters(path / "profile", path / "clients")
                        self.assertEqual([row.label for row in second], ["Beta", "Alpha"])
                        self.assertEqual(load.call_count, 1)
            finally:
                cache.clear_quest_character_cache()

    def test_optional_file_stamp_keeps_missing_and_strict_contracts(self) -> None:
        from app.core.file_stamp import mtime_size_stamp_optional
        from app.quest_catalog import _path_signature

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            self.assertIsNone(mtime_size_stamp_optional(path))
            self.assertEqual(_path_signature("source", path), ("source", str(path), None, None))
            with self.assertRaises(FileNotFoundError):
                mtime_size_stamp_optional(path, strict=True)
            path.write_bytes(b"data")
            stamp = mtime_size_stamp_optional(path)
            self.assertEqual(stamp[1], 4)
            self.assertEqual(_path_signature("source", path), ("source", str(path), *stamp))

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
