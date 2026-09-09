from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.calibration_bootstrap import build_windows_protocol_calibration
from app.network.current_protocol_profile import (
    DOFUS_361010_PROFILE,
    dofus_361010_candidate_mapping_payload,
)
from app.quest_catalog import QuestCatalog, QuestRecord


BUILD = "ab" * 32
SNAPSHOT_TYPE = "type.ankama.com/qzx"


def legacy_lqn_payload(*, include_journal: bool = False) -> dict:
    current = dofus_361010_candidate_mapping_payload(BUILD, include_quest_journal=include_journal)
    payload = {
        "schema_version": 1,
        "game_version": DOFUS_361010_PROFILE.game_version,
        "build_sha256": BUILD,
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


class CalibrationBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.catalog = QuestCatalog(
            [
                QuestRecord(id=101, name="Q1", category="Test", level_min=1, level_max=200, start_criterion=""),
                QuestRecord(id=202, name="Q2", category="Test", level_min=1, level_max=200, start_criterion=""),
            ]
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def build(self, fingerprint: str = BUILD):
        return build_windows_protocol_calibration(
            window_handles_provider=lambda: (123,),
            quest_catalog=self.catalog,
            mapping_roots=(self.root,),
            build_sha256_provider=lambda: fingerprint,
        )

    def test_composes_without_starting_capture_when_mapping_missing(self) -> None:
        result = self.build()
        self.assertTrue(result.ready)
        self.assertEqual(result.reason, "ready_to_calibrate")
        self.assertEqual(result.build_sha256, BUILD)
        self.assertIsNotNone(result.runtime)
        self.assertEqual(
            type(result.runtime.source).__name__,
            "DiagnosticProtocolMessageSource",
        )
        self.assertEqual(
            type(result.runtime.source.delegate).__name__,
            "ElevatedWindowsProtocolSource",
        )
        self.assertFalse(result.runtime.is_running)

    def test_existing_idz_live_only_mapping_skips_calibration(self) -> None:
        path = self.root / "mapping.json"
        path.write_text(
            json.dumps(dofus_361010_candidate_mapping_payload(BUILD)),
            encoding="utf-8",
        )
        result = self.build()
        self.assertFalse(result.ready)
        self.assertEqual(result.reason, "mapping_already_ready")
        self.assertEqual(result.existing_mapping_path, path)
        self.assertIsNone(result.runtime)

    def test_legacy_lqn_plus_idr_mapping_does_not_skip_new_calibration(self) -> None:
        path = self.root / "mapping.json"
        path.write_text(json.dumps(legacy_lqn_payload(include_journal=True)), encoding="utf-8")

        result = self.build()

        self.assertTrue(result.ready)
        self.assertEqual(result.reason, "ready_to_calibrate")
        self.assertIsNotNone(result.runtime)
        self.assertIsNone(result.existing_mapping_path)

    def test_custom_same_capabilities_mapping_does_not_inherit_canonical_trust(self) -> None:
        payload = dofus_361010_candidate_mapping_payload(BUILD, include_quest_journal=True)
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
        (self.root / "mapping.json").write_text(json.dumps(payload), encoding="utf-8")

        result = self.build()

        self.assertTrue(result.ready)
        self.assertEqual(result.reason, "ready_to_calibrate")
        self.assertIsNotNone(result.runtime)
        self.assertIsNone(result.existing_mapping_path)

    def test_legacy_snapshot_does_not_substitute_for_live_idz_mapping(self) -> None:
        path = self.root / "mapping.json"
        path.write_text(
            json.dumps(
                dofus_361010_candidate_mapping_payload(
                    BUILD,
                    finished_quests_snapshot_type_url=SNAPSHOT_TYPE,
                )
            ),
            encoding="utf-8",
        )
        result = self.build()
        self.assertTrue(result.ready)
        self.assertEqual(result.reason, "ready_to_calibrate")
        self.assertIsNotNone(result.runtime)

    def test_existing_idz_plus_historical_idr_mapping_does_not_make_idr_authoritative(self) -> None:
        path = self.root / "mapping.json"
        path.write_text(
            json.dumps(
                dofus_361010_candidate_mapping_payload(
                    BUILD,
                    include_quest_journal=True,
                )
            ),
            encoding="utf-8",
        )
        result = self.build()
        self.assertTrue(result.ready)
        self.assertEqual(result.reason, "ready_to_calibrate")
        self.assertIsNone(result.existing_mapping_path)
        self.assertIsNotNone(result.runtime)

    def test_ambiguous_existing_mapping_fails_closed(self) -> None:
        payload = dofus_361010_candidate_mapping_payload(BUILD)
        (self.root / "a.json").write_text(json.dumps(payload), encoding="utf-8")
        (self.root / "b.json").write_text(json.dumps(payload), encoding="utf-8")
        result = self.build()
        self.assertFalse(result.ready)
        self.assertEqual(result.reason, "existing_mapping_ambiguous")
        self.assertIsNone(result.runtime)

    def test_unavailable_fingerprint_does_not_compose_capture(self) -> None:
        result = self.build("")
        self.assertFalse(result.ready)
        self.assertEqual(result.reason, "build_fingerprint_unavailable")
        self.assertIsNone(result.runtime)


if __name__ == "__main__":
    unittest.main()
