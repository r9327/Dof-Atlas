from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.constants import KEY_SESSION_ORDER
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)
from app.network.character_resolver import CharacterSlotResolver
from app.network.current_protocol_profile import dofus_361010_candidate_manifest
from app.network.normalizer import ProtocolEventNormalizer
from app.network.progress_bridge import NetworkProgressBridge
from app.network.transport import CapturedProtocolMessage
from app.quest_catalog import QuestCatalog, QuestRecord


BUILD = "ab" * 32
SNAPSHOT_TYPE = "type.ankama.com/qzx"


def _varint(value: int) -> bytes:
    output = bytearray()
    current = int(value)
    while True:
        byte = current & 0x7F
        current >>= 7
        if current:
            output.append(byte | 0x80)
        else:
            output.append(byte)
            return bytes(output)


def _v(field_number: int, value: int) -> bytes:
    return _varint((field_number << 3) | 0) + _varint(value)


def _b(field_number: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(value)) + value


def _kvi(character_id: int = 9001, name: str = "Alpha") -> CapturedProtocolMessage:
    details = _b(2, name.encode("utf-8"))
    entry = _b(1, details) + _v(2, character_id)
    return CapturedProtocolMessage("s1", "type.ankama.com/kvi", _b(1, entry))


def _kva(character_id: int = 9001) -> CapturedProtocolMessage:
    payload = _b(1, _b(1, _v(2, character_id)))
    return CapturedProtocolMessage("s1", "type.ankama.com/kva", payload)


def _snapshot(
    quest_ids: tuple[int, ...],
    *,
    player_id: int = 9001,
) -> CapturedProtocolMessage:
    payload = b"".join(
        _b(1, _v(1, quest_id) + _v(2, 1))
        for quest_id in quest_ids
    )
    payload += _v(4, player_id)
    return CapturedProtocolMessage("s1", SNAPSHOT_TYPE, payload)


class _AchievementProvider:
    def __init__(self, achievement) -> None:
        self.achievement = achievement

    def load_retained(self):
        return [self.achievement]

    def get_by_id(self, achievement_id: int):
        return self.achievement if int(achievement_id) == int(self.achievement.id) else None


class OfflineQuestReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        profile_path = root / "profiles.json"
        client_index_path = root / "client_index.json"
        profile_path.write_text(
            json.dumps({KEY_SESSION_ORDER: ["Alpha", ""]}),
            encoding="utf-8",
        )
        client_index_path.write_text(
            json.dumps({"clients": [{"index": 1, "name": "Alpha"}]}),
            encoding="utf-8",
        )
        self.quest_progress = QuestProgressService(root / "quest_progress.json")
        self.achievement_progress = AchievementProgressService(root / "achievement_progress.json")
        self.catalog = QuestCatalog(
            [
                QuestRecord(id=10, name="Offline A", category="Test", level_min=1, level_max=200, start_criterion=""),
                QuestRecord(id=20, name="Offline B", category="Test", level_min=1, level_max=200, start_criterion=""),
                QuestRecord(id=30, name="Manual only", category="Test", level_min=1, level_max=200, start_criterion=""),
            ]
        )
        quest_ref = SimpleNamespace(entity_type="quest", entity_id=10)
        achievement_objective = SimpleNamespace(
            id=501,
            objective_type="",
            entity_refs=(quest_ref,),
            criterion="",
            text="",
        )
        achievement = SimpleNamespace(
            id=500,
            category_name="Quêtes",
            objectives=(achievement_objective,),
        )
        self.provider = _AchievementProvider(achievement)
        self.resolver = CharacterSlotResolver(profile_path, client_index_path, slot_count=2)
        self.bridge = NetworkProgressBridge(
            quest_catalog=self.catalog,
            quest_progress_service=self.quest_progress,
            achievement_progress_service=self.achievement_progress,
            achievement_provider=self.provider,
            character_resolver=self.resolver,
            logger=logging.getLogger(f"offline-reconcile-{id(self)}"),
        )
        self.decoder = dofus_361010_candidate_manifest(
            BUILD,
            finished_quests_snapshot_type_url=SNAPSHOT_TYPE,
        ).build_decoder(active_build_sha256_provider=lambda: BUILD)
        self.normalizer = ProtocolEventNormalizer()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _handle(self, message: CapturedProtocolMessage):
        decoded = self.decoder.decode(message)
        if decoded is None:
            return None
        event = self.normalizer.normalize(decoded)
        if event is None:
            return None
        return self.bridge.handle(event)

    def _identify(self) -> None:
        # kvi populates only volatile id -> name correlation.
        self.assertIsNone(self._handle(_kvi()))
        result = self._handle(_kva())
        self.assertIsNotNone(result)
        self.assertTrue(result.accepted)
        self.assertEqual(result.character_key, "character:9001")

    def test_login_snapshot_is_rejected_without_exact_opcode_proof(self) -> None:
        # Simulate local/manual progression that existed before Atlas saw this
        # login. It is intentionally absent from the server snapshot below and
        # must never be unset by reconciliation.
        self.quest_progress.set_quest_completed("character:1", 30, True)
        self._identify()

        result = self._handle(_snapshot((10, 20)))
        self.assertIsNotNone(result)
        self.assertFalse(result.accepted)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason, "finished_quests_snapshot_unverified")
        self.assertEqual(
            self.quest_progress.completed_quest_ids("character:1"),
            {30},
        )
        self.assertFalse(self.achievement_progress.is_achievement_completed("character:1", 500))

    def test_repeated_login_snapshot_remains_non_mutating(self) -> None:
        self._identify()
        first = self._handle(_snapshot((10, 20)))
        second = self._handle(_snapshot((10, 20)))
        self.assertFalse(first.accepted)
        self.assertFalse(first.changed)
        self.assertEqual(first.reason, "finished_quests_snapshot_unverified")
        self.assertIsNotNone(second)
        self.assertFalse(second.accepted)
        self.assertFalse(second.changed)
        self.assertEqual(second.reason, "finished_quests_snapshot_unverified")
        self.assertEqual(self.quest_progress.completed_quest_ids("character:1"), set())

    def test_snapshot_for_different_player_is_rejected_without_writes(self) -> None:
        self._identify()
        result = self._handle(_snapshot((10, 20), player_id=9002))
        self.assertIsNotNone(result)
        self.assertFalse(result.accepted)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason, "character_id_mismatch")
        self.assertEqual(self.quest_progress.completed_quest_ids("character:1"), set())

    def test_snapshot_cannot_apply_before_verified_character_identity(self) -> None:
        result = self._handle(_snapshot((10, 20)))
        self.assertIsNotNone(result)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "character_not_identified")
        self.assertEqual(self.quest_progress.completed_quest_ids("character:1"), set())

    def test_snapshot_decoder_requires_player_id_for_calibrated_rule(self) -> None:
        payload = b"".join(
            _b(1, _v(1, quest_id) + _v(2, 1))
            for quest_id in (10, 20)
        )
        self.assertIsNone(
            self.decoder.decode(CapturedProtocolMessage("s1", SNAPSHOT_TYPE, payload))
        )


if __name__ == "__main__":
    unittest.main()
