from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.calibrated_mapping_install import install_calibrated_current_profile
from app.network.current_protocol_profile import (
    DOFUS_361010_PROFILE,
    dofus_361010_candidate_mapping_payload,
    dofus_361010_profile_digest,
)
from app.network.protocol_calibration import (
    ProtocolCalibrationCertificate,
    ProtocolCalibrationStatus,
)


BUILD = "ab" * 32


def certificate(**changes) -> ProtocolCalibrationCertificate:
    values = {
        "game_version": DOFUS_361010_PROFILE.game_version,
        "build_sha256": BUILD,
        "evidence_revision": DOFUS_361010_PROFILE.evidence_revision,
        "source_commit": DOFUS_361010_PROFILE.source_commit,
        "profile_digest": dofus_361010_profile_digest(),
        "character_key": "character:9001",
        "character_id": 9001,
        "verified_quest_ids": (101, 202),
        "quest_journal_type_url": DOFUS_361010_PROFILE.quest_journal_type_url,
        "journal_verified_quest_ids": (303,),
        "journal_observation_count": 1,
        "finished_quests_snapshot_type_url": "",
        "snapshot_verified_quest_ids": (),
        "snapshot_observation_count": 0,
    }
    values.update(changes)
    return ProtocolCalibrationCertificate(**values)


def status(
    cert: ProtocolCalibrationCertificate | None = None,
    *,
    ready: bool = True,
    reason: str = "profile_calibrated",
) -> ProtocolCalibrationStatus:
    cert = cert if cert is not None else certificate()
    return ProtocolCalibrationStatus(
        ready=ready,
        reason=reason,
        build_sha256=cert.build_sha256,
        identified_session_count=1,
        max_distinct_completion_count=len(cert.verified_quest_ids),
        quest_journal_observation_count=cert.journal_observation_count,
        quest_journal_verified_count=len(cert.journal_verified_quest_ids),
        snapshot_candidate_count=1 if cert.finished_quests_snapshot_type_url else 0,
        snapshot_candidate_type_url=cert.finished_quests_snapshot_type_url,
        certificate=cert,
    )


def legacy_lqn_payload(*, include_journal: bool = False, completion_message_id: int = 56) -> dict:
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
            "completion_message_id": completion_message_id,
            "parameters_field": 4,
            "quest_id_parameter_index": 0,
        },
        "messages": {},
    }
    if include_journal:
        payload["quest_journal_snapshot"] = current["quest_journal_snapshot"]
    return payload


class CalibratedMappingInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_installs_exact_idz_live_only_profile_after_calibration(self) -> None:
        result = install_calibrated_current_profile(status(), destination_root=self.root)
        self.assertTrue(result.success)
        self.assertTrue(result.installed)
        self.assertEqual(result.reason, "mapping_installed_not_started")
        self.assertIsNotNone(result.destination)
        payload = json.loads(result.destination.read_text(encoding="utf-8"))
        self.assertEqual(payload["game_version"], "3.6.10.10")
        self.assertEqual(payload["build_sha256"], BUILD)
        self.assertEqual(payload["character_identity"]["roster_type_url"], "type.ankama.com/kvi")
        self.assertNotIn("quest_completion_info", payload)
        self.assertEqual(set(payload["messages"]), {"type.ankama.com/idz"})
        idz = payload["messages"]["type.ankama.com/idz"]
        self.assertEqual(idz["event_type"], "quest_completed")
        self.assertEqual(
            [field["output_name"] for field in idz["fields"]],
            ["quest_id", "validated_step_id"],
        )
        self.assertNotIn("quest_journal_snapshot", payload)
        self.assertNotIn("finished_quests_snapshot", payload)

    def test_rejects_missing_or_forged_journal_calibration_evidence(self) -> None:
        cases = (
            certificate(quest_journal_type_url=""),
            certificate(quest_journal_type_url="type.ankama.com/abc"),
            certificate(journal_observation_count=0),
            certificate(journal_verified_quest_ids=(303, 303)),
            certificate(journal_verified_quest_ids=(0,)),
        )
        for cert in cases:
            with self.subTest(cert=cert):
                result = install_calibrated_current_profile(status(cert), destination_root=self.root)
                self.assertFalse(result.success)
                self.assertFalse(result.installed)
                self.assertEqual(result.reason, "calibration_quest_journal_unverified")
                self.assertEqual(list(self.root.glob("*.json")), [])

    def test_empty_but_strictly_observed_journal_can_only_gate_idz_install(self) -> None:
        cert = certificate(journal_verified_quest_ids=(), journal_observation_count=1)
        result = install_calibrated_current_profile(status(cert), destination_root=self.root)
        self.assertTrue(result.success)
        self.assertTrue(result.installed)
        payload = json.loads(result.destination.read_text(encoding="utf-8"))
        self.assertNotIn("quest_journal_snapshot", payload)

    def test_rejects_shape_only_snapshot_evidence(self) -> None:
        cert = certificate(
            finished_quests_snapshot_type_url="type.ankama.com/qzy",
            snapshot_verified_quest_ids=(303, 404, 505),
            snapshot_observation_count=2,
        )
        result = install_calibrated_current_profile(status(cert), destination_root=self.root)
        self.assertFalse(result.success)
        self.assertFalse(result.installed)
        self.assertEqual(result.reason, "calibration_unverified_snapshot_evidence")
        self.assertEqual(list(self.root.glob("*.json")), [])

    def test_identical_reinstall_is_idempotent(self) -> None:
        first = install_calibrated_current_profile(status(), destination_root=self.root)
        second = install_calibrated_current_profile(status(), destination_root=self.root)
        self.assertTrue(first.installed)
        self.assertTrue(second.success)
        self.assertFalse(second.installed)
        self.assertEqual(second.reason, "mapping_already_installed")
        self.assertEqual(second.destination, first.destination)

    def test_existing_exact_idz_live_only_mapping_is_already_ready(self) -> None:
        live_only_path = self.root / "mapping_live_only.json"
        live_only_path.write_text(
            json.dumps(
                dofus_361010_candidate_mapping_payload(BUILD),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        result = install_calibrated_current_profile(status(), destination_root=self.root)

        self.assertTrue(result.success)
        self.assertFalse(result.installed)
        self.assertEqual(result.reason, "mapping_already_installed")
        self.assertEqual(result.destination, live_only_path)
        persisted = json.loads(live_only_path.read_text(encoding="utf-8"))
        self.assertNotIn("quest_journal_snapshot", persisted)
        self.assertEqual(set(persisted["messages"]), {"type.ankama.com/idz"})

    def test_historical_exact_idz_plus_idr_mapping_is_downgraded_in_place(self) -> None:
        old_path = self.root / "mapping_old_idr.json"
        old_path.write_text(
            json.dumps(dofus_361010_candidate_mapping_payload(BUILD, include_quest_journal=True)),
            encoding="utf-8",
        )

        result = install_calibrated_current_profile(status(), destination_root=self.root)

        self.assertTrue(result.success)
        self.assertTrue(result.installed)
        self.assertEqual(result.destination, old_path)
        persisted = json.loads(old_path.read_text(encoding="utf-8"))
        self.assertNotIn("quest_journal_snapshot", persisted)
        self.assertEqual(set(persisted["messages"]), {"type.ankama.com/idz"})

    def test_exact_legacy_lqn_plus_idr_mapping_is_replaced_in_place(self) -> None:
        old_path = self.root / "mapping_old_lqn.json"
        old_path.write_text(json.dumps(legacy_lqn_payload(include_journal=True)), encoding="utf-8")

        result = install_calibrated_current_profile(status(), destination_root=self.root)

        self.assertTrue(result.success)
        self.assertTrue(result.installed)
        self.assertEqual(result.destination, old_path)
        persisted = json.loads(old_path.read_text(encoding="utf-8"))
        self.assertNotIn("quest_completion_info", persisted)
        self.assertNotIn("quest_journal_snapshot", persisted)
        self.assertEqual(set(persisted["messages"]), {"type.ankama.com/idz"})

    def test_noncanonical_lqn_mapping_is_never_overwritten(self) -> None:
        old_path = self.root / "mapping_custom_lqn.json"
        original = legacy_lqn_payload(completion_message_id=57)
        old_path.write_text(json.dumps(original), encoding="utf-8")

        result = install_calibrated_current_profile(status(), destination_root=self.root)

        self.assertFalse(result.success)
        self.assertFalse(result.installed)
        self.assertEqual(result.reason, "different_mapping_already_installed")
        self.assertEqual(json.loads(old_path.read_text(encoding="utf-8")), original)

    def test_rejects_not_ready_status(self) -> None:
        result = install_calibrated_current_profile(
            status(ready=False, reason="awaiting_distinct_quest_completions"),
            destination_root=self.root,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "calibration_not_ready")
        self.assertEqual(list(self.root.glob("*.json")), [])

    def test_rejects_stale_or_forged_profile_digest(self) -> None:
        result = install_calibrated_current_profile(
            status(certificate(profile_digest="cd" * 32)),
            destination_root=self.root,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "calibration_profile_digest_mismatch")

    def test_rejects_insufficient_or_duplicate_quest_evidence(self) -> None:
        one = install_calibrated_current_profile(
            status(certificate(verified_quest_ids=(101,))),
            destination_root=self.root,
        )
        duplicate = install_calibrated_current_profile(
            status(certificate(verified_quest_ids=(101, 101))),
            destination_root=self.root,
        )
        self.assertEqual(one.reason, "calibration_insufficient_distinct_quests")
        self.assertEqual(duplicate.reason, "calibration_insufficient_distinct_quests")
        self.assertEqual(list(self.root.glob("*.json")), [])

    def test_rejects_partial_legacy_snapshot_evidence_too(self) -> None:
        cases = (
            certificate(snapshot_verified_quest_ids=(303,)),
            certificate(snapshot_observation_count=1),
            certificate(finished_quests_snapshot_type_url="type.ankama.com/kvi"),
        )
        for cert in cases:
            with self.subTest(cert=cert):
                result = install_calibrated_current_profile(status(cert), destination_root=self.root)
                self.assertFalse(result.success)
                self.assertEqual(result.reason, "calibration_unverified_snapshot_evidence")
                self.assertEqual(list(self.root.glob("*.json")), [])

    def test_rejects_non_atlas_character_key(self) -> None:
        result = install_calibrated_current_profile(
            status(certificate(character_key="slot:3")),
            destination_root=self.root,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "calibration_invalid_character_key")

    def test_rejects_different_exact_mapping_already_present(self) -> None:
        existing = {
            "schema_version": 1,
            "game_version": "other",
            "build_sha256": BUILD,
            "messages": {
                "ankama.com/c": {
                    "event_type": "character_identified",
                    "fields": [
                        {"output_name": "character_name", "path": [1], "kind": "string", "required": True}
                    ],
                },
                "ankama.com/q": {
                    "event_type": "quest_completed",
                    "fields": [
                        {"output_name": "quest_id", "path": [1], "kind": "positive_int", "required": True}
                    ],
                },
            },
        }
        (self.root / "existing.json").write_text(json.dumps(existing), encoding="utf-8")
        result = install_calibrated_current_profile(status(), destination_root=self.root)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "different_mapping_already_installed")


if __name__ == "__main__":
    unittest.main()
