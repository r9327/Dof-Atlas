from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)
from app.network.bootstrap import build_windows_network_runtime
from app.network.current_protocol_profile import (
    DOFUS_361010_PROFILE,
    dofus_361010_candidate_mapping_payload,
)
from app.network.transport import CapturedProtocolMessage
from app.quest_catalog import QuestCatalog, QuestRecord


class EmptyAchievementProvider:
    def load_retained(self):
        return []

    def get_by_id(self, achievement_id: int):
        del achievement_id
        return None


def mapping_payload(build_sha256: str, *, include_identity: bool = True) -> dict:
    messages = {
        "ankama.com/quest_done": {
            "event_type": "quest_completed",
            "fields": [
                {
                    "output_name": "quest_id",
                    "path": [1],
                    "kind": "positive_int",
                    "required": True,
                }
            ],
        }
    }
    if include_identity:
        messages["ankama.com/character"] = {
            "event_type": "character_identified",
            "fields": [
                {
                    "output_name": "character_name",
                    "path": [1],
                    "kind": "string",
                    "required": True,
                }
            ],
        }
    return {
        "schema_version": 1,
        "game_version": "3.6.test",
        "build_sha256": build_sha256,
        "messages": messages,
    }


def legacy_lqn_payload(build_sha256: str, *, include_journal: bool = True) -> dict:
    current = dofus_361010_candidate_mapping_payload(
        build_sha256,
        include_quest_journal=include_journal,
    )
    payload = {
        "schema_version": 1,
        "game_version": DOFUS_361010_PROFILE.game_version,
        "build_sha256": build_sha256,
        "character_identity": current["character_identity"],
        "quest_completion_info": {
            "type_url": "type.ankama.com/lqn",
            "message_type_field": 1,
            "completion_message_type": 0,
            "message_id_field": 2,
            "completion_message_id": 56,
            "parameters_field": 4,
            "quest_id_parameter_index": 0,
        },
        "messages": {},
    }
    if include_journal:
        payload["quest_journal_snapshot"] = current["quest_journal_snapshot"]
    return payload


class NetworkBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mapping_root = self.root / "mappings"
        self.mapping_root.mkdir()
        self.quest_progress = QuestProgressService(self.root / "quest_progress.json")
        self.achievement_progress = AchievementProgressService(self.root / "achievement_progress.json")
        self.catalog = QuestCatalog(
            [
                QuestRecord(
                    id=10,
                    name="Quest A",
                    category="Test",
                    level_min=1,
                    level_max=200,
                    start_criterion="",
                )
            ]
        )
        self.logger = logging.getLogger(f"network-bootstrap-{id(self)}")
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_mapping(self, build_sha256: str, *, include_identity: bool = True) -> Path:
        path = self.mapping_root / "mapping.json"
        path.write_text(
            json.dumps(mapping_payload(build_sha256, include_identity=include_identity)),
            encoding="utf-8",
        )
        return path

    def build(self, fingerprint: str):
        return build_windows_network_runtime(
            window_handles_provider=lambda: (123,),
            quest_catalog=self.catalog,
            achievement_provider=EmptyAchievementProvider(),
            mapping_roots=(self.mapping_root,),
            quest_progress_service=self.quest_progress,
            achievement_progress_service=self.achievement_progress,
            build_sha256_provider=lambda: fingerprint,
            logger=self.logger,
        )

    def test_exact_noncurrent_mapping_composes_runtime_without_starting_capture(self) -> None:
        mapping_path = self.write_mapping("a" * 64)
        result = self.build("a" * 64)

        self.assertTrue(result.ready)
        self.assertIsNotNone(result.runtime)
        self.assertFalse(result.runtime.is_running)
        self.assertEqual(result.build_sha256, "a" * 64)
        self.assertEqual(result.mapping_path, mapping_path)
        self.assertEqual(result.missing_required_events, ())
        self.assertFalse(result.catchup_ready)

    def test_mapping_without_character_identity_is_not_production_ready(self) -> None:
        mapping_path = self.write_mapping("a" * 64, include_identity=False)
        result = self.build("a" * 64)

        self.assertFalse(result.ready)
        self.assertIsNone(result.runtime)
        self.assertEqual(result.reason, "mapping_missing_required_events")
        self.assertEqual(result.mapping_path, mapping_path)
        self.assertEqual(result.missing_required_events, ("character_identified",))

    def test_missing_exact_mapping_keeps_network_disabled(self) -> None:
        self.write_mapping("b" * 64)
        result = self.build("a" * 64)

        self.assertFalse(result.ready)
        self.assertIsNone(result.runtime)
        self.assertEqual(result.reason, "mapping_no_exact_match")

    def test_unavailable_fingerprint_keeps_network_disabled_before_mapping_lookup(self) -> None:
        self.write_mapping("a" * 64)
        result = self.build("")

        self.assertFalse(result.ready)
        self.assertIsNone(result.runtime)
        self.assertEqual(result.reason, "build_fingerprint_unavailable")

    def test_ambiguous_exact_mapping_keeps_network_disabled(self) -> None:
        self.write_mapping("a" * 64)
        second = self.mapping_root / "mapping-2.json"
        second.write_text(json.dumps(mapping_payload("a" * 64)), encoding="utf-8")

        result = self.build("a" * 64)

        self.assertFalse(result.ready)
        self.assertIsNone(result.runtime)
        self.assertEqual(result.reason, "mapping_ambiguous_exact_match")

    def test_historical_idr_mapping_is_stripped_before_runtime_decoder(self) -> None:
        build = "a" * 64
        path = self.mapping_root / "mapping.json"
        path.write_text(
            json.dumps(
                dofus_361010_candidate_mapping_payload(
                    build,
                    include_quest_journal=True,
                )
            ),
            encoding="utf-8",
        )

        result = self.build(build)

        self.assertTrue(result.ready)
        self.assertFalse(result.catchup_ready)
        self.assertIsNotNone(result.runtime)
        decoded = result.runtime.source.decoder.decode(
            CapturedProtocolMessage(
                "s1",
                DOFUS_361010_PROFILE.quest_journal_type_url,
                b"\x18\x01",
            )
        )
        self.assertIsNone(decoded)

    def test_historical_idr_alias_is_fail_closed_even_on_noncurrent_mapping(self) -> None:
        build = "a" * 64
        payload = mapping_payload(build)
        reviewed = dofus_361010_candidate_mapping_payload(build, include_quest_journal=True)
        payload["quest_journal_snapshot"] = reviewed["quest_journal_snapshot"]
        path = self.mapping_root / "mapping.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        result = self.build(build)

        self.assertTrue(result.ready)
        self.assertFalse(result.catchup_ready)
        self.assertIsNotNone(result.runtime)
        decoded = result.runtime.source.decoder.decode(
            CapturedProtocolMessage(
                "s1",
                DOFUS_361010_PROFILE.quest_journal_type_url,
                b"\x18\x01",
            )
        )
        self.assertIsNone(decoded)

    def test_generic_historical_idr_rule_is_fail_closed_even_on_noncurrent_mapping(self) -> None:
        build = "a" * 64
        payload = mapping_payload(build)
        payload["messages"][DOFUS_361010_PROFILE.quest_journal_type_url] = {
            "event_type": "quest_completed",
            "fields": [
                {
                    "output_name": "quest_id",
                    "path": [1],
                    "kind": "positive_int",
                    "required": True,
                }
            ],
        }
        path = self.mapping_root / "mapping.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        result = self.build(build)

        self.assertTrue(result.ready)
        self.assertFalse(result.catchup_ready)
        self.assertIsNotNone(result.runtime)
        decoded = result.runtime.source.decoder.decode(
            CapturedProtocolMessage(
                "s1",
                DOFUS_361010_PROFILE.quest_journal_type_url,
                b"\x08\x0a",
            )
        )
        self.assertIsNone(decoded)

    def test_legacy_shape_only_snapshot_mapping_is_stripped_at_runtime(self) -> None:
        build = "a" * 64
        path = self.mapping_root / "mapping.json"
        path.write_text(
            json.dumps(
                dofus_361010_candidate_mapping_payload(
                    build,
                    finished_quests_snapshot_type_url="type.ankama.com/qzx",
                )
            ),
            encoding="utf-8",
        )

        result = self.build(build)

        self.assertTrue(result.ready)
        self.assertFalse(result.catchup_ready)
        self.assertIsNotNone(result.runtime)
        self.assertEqual(
            type(result.runtime.source.source).__name__,
            "DiagnosticProtocolMessageSource",
        )
        self.assertEqual(
            type(result.runtime.source.source.delegate).__name__,
            "ElevatedWindowsProtocolSource",
        )
        self.assertNotEqual(
            type(result.runtime.source.decoder).__name__,
            "FinishedQuestsSnapshotDecoder",
        )

    def test_disproved_lqn_completion_is_stripped_before_runtime_capability_check(self) -> None:
        build = "a" * 64
        path = self.mapping_root / "mapping.json"
        path.write_text(json.dumps(legacy_lqn_payload(build)), encoding="utf-8")

        result = self.build(build)

        self.assertFalse(result.ready)
        self.assertIsNone(result.runtime)
        self.assertEqual(result.reason, "mapping_missing_required_events")
        self.assertEqual(result.missing_required_events, ("quest_completion",))
        self.assertFalse(result.catchup_ready)

    def test_custom_current_mapping_with_same_capabilities_is_rejected(self) -> None:
        build = "a" * 64
        payload = dofus_361010_candidate_mapping_payload(build, include_quest_journal=True)
        payload["messages"] = {
            "type.ankama.com/abc": {
                "event_type": "quest_completed",
                "fields": [
                    {
                        "output_name": "quest_id",
                        "path": [1],
                        "kind": "positive_int",
                        "required": True,
                    }
                ],
            }
        }
        path = self.mapping_root / "mapping.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        result = self.build(build)

        self.assertFalse(result.ready)
        self.assertIsNone(result.runtime)
        self.assertEqual(result.reason, "mapping_current_profile_noncanonical")
        self.assertEqual(result.mapping_path, path)
        self.assertFalse(result.catchup_ready)


if __name__ == "__main__":
    unittest.main()
