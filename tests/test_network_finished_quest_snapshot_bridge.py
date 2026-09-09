from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.network.character_resolver import CharacterResolution
from app.network.events import (
    CharacterIdentifiedEvent,
    FinishedQuestsSnapshotEvent,
    QuestCompletedEvent,
    SessionClosedEvent,
)
from app.network.progress_bridge import NetworkProgressBridge


class _Resolver:
    def resolve(self, name: str):
        if name == "Alice":
            return CharacterResolution(character_key="character:55", label="Alice", slot=1)
        if name == "Bob":
            return CharacterResolution(character_key="character:66", label="Bob", slot=2)
        return None


class _AchievementProgress:
    def __init__(self) -> None:
        self.sync_calls: list[str] = []

    def sync_from_quest_progress(self, character_key, *_args):
        self.sync_calls.append(character_key)
        return False


class FinishedQuestSnapshotBridgeTests(unittest.TestCase):
    def _bridge(self, path: Path):
        achievement_progress = _AchievementProgress()
        bridge = NetworkProgressBridge(
            quest_catalog=SimpleNamespace(by_id={101: object(), 202: object(), 303: object()}),
            quest_progress_service=QuestProgressService(path),
            achievement_progress_service=achievement_progress,
            achievement_provider=object(),
            guide_provider=None,
            character_resolver=_Resolver(),
        )
        return bridge, achievement_progress

    def test_snapshot_like_full_catalog_never_mutates_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "quests.json"
            bridge, achievement_progress = self._bridge(path)

            identified = bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Alice",
                    character_id=55,
                )
            )
            self.assertTrue(identified.accepted)

            applied = bridge.handle(
                FinishedQuestsSnapshotEvent(
                    session_id="s1",
                    event_id="snapshot:1",
                    reliable=True,
                    quest_ids=(101, 202, 303),
                    player_id=55,
                )
            )
            self.assertFalse(applied.accepted)
            self.assertFalse(applied.changed)
            self.assertEqual(applied.reason, "finished_quests_snapshot_unverified")
            self.assertEqual(applied.character_key, "character:55")
            self.assertEqual(
                bridge.quest_progress_service.completed_quest_ids("character:55"),
                set(),
            )
            self.assertEqual(achievement_progress.sync_calls, [])

    def test_character_switch_clears_session_dedupe_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Alice",
                    character_id=55,
                )
            )
            first = bridge.handle(
                QuestCompletedEvent(
                    session_id="s1",
                    event_id="quest:101",
                    reliable=True,
                    quest_id=101,
                )
            )
            self.assertTrue(first.changed)
            self.assertEqual(first.character_key, "character:55")

            switched = bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Bob",
                    character_id=66,
                )
            )
            self.assertTrue(switched.changed)
            self.assertEqual(switched.character_key, "character:66")

            same_wire_event_for_bob = bridge.handle(
                QuestCompletedEvent(
                    session_id="s1",
                    event_id="quest:101",
                    reliable=True,
                    quest_id=101,
                )
            )
            self.assertTrue(same_wire_event_for_bob.accepted)
            self.assertTrue(same_wire_event_for_bob.changed)
            self.assertEqual(same_wire_event_for_bob.reason, "quest_completed")
            self.assertEqual(same_wire_event_for_bob.character_key, "character:66")
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), {101})
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:66"), {101})
            self.assertEqual(achievement_progress.sync_calls, ["character:55", "character:66"])

    def test_session_close_clears_session_dedupe_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Alice",
                    character_id=55,
                )
            )
            first = bridge.handle(
                QuestCompletedEvent(
                    session_id="s1",
                    event_id="quest:101",
                    reliable=True,
                    quest_id=101,
                )
            )
            self.assertTrue(first.changed)

            closed = bridge.handle(
                SessionClosedEvent(
                    session_id="s1",
                    reliable=True,
                )
            )
            self.assertTrue(closed.accepted)
            self.assertEqual(closed.reason, "session_closed")

            bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Alice",
                    character_id=55,
                )
            )
            replay_after_reconnect = bridge.handle(
                QuestCompletedEvent(
                    session_id="s1",
                    event_id="quest:101",
                    reliable=True,
                    quest_id=101,
                )
            )
            self.assertTrue(replay_after_reconnect.accepted)
            self.assertFalse(replay_after_reconnect.changed)
            self.assertEqual(replay_after_reconnect.reason, "quest_already_completed")
            self.assertEqual(achievement_progress.sync_calls, ["character:55", "character:55"])

    def test_snapshot_rejects_player_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Alice",
                    character_id=55,
                )
            )
            result = bridge.handle(
                FinishedQuestsSnapshotEvent(
                    session_id="s1",
                    reliable=True,
                    quest_ids=(303,),
                    player_id=99,
                )
            )
            self.assertFalse(result.accepted)
            self.assertEqual(result.reason, "character_id_mismatch")
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, [])

    def test_snapshot_rejects_missing_snapshot_player_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Alice",
                    character_id=55,
                )
            )
            result = bridge.handle(
                FinishedQuestsSnapshotEvent(
                    session_id="s1",
                    reliable=True,
                    quest_ids=(303,),
                    player_id=None,
                )
            )
            self.assertFalse(result.accepted)
            self.assertEqual(result.reason, "snapshot_player_id_missing")
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, [])

    def test_snapshot_rejects_session_without_verified_character_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            identified = bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Alice",
                    character_id=None,
                )
            )
            self.assertTrue(identified.accepted)
            result = bridge.handle(
                FinishedQuestsSnapshotEvent(
                    session_id="s1",
                    reliable=True,
                    quest_ids=(303,),
                    player_id=55,
                )
            )
            self.assertFalse(result.accepted)
            self.assertEqual(result.reason, "character_id_missing")
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, [])

    def test_snapshot_requires_character_route_and_rejects_wholly_unknown_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            no_character = bridge.handle(
                FinishedQuestsSnapshotEvent(
                    session_id="s1",
                    reliable=True,
                    quest_ids=(101,),
                    player_id=55,
                )
            )
            self.assertFalse(no_character.accepted)
            self.assertEqual(no_character.reason, "character_not_identified")

            bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="s1",
                    reliable=True,
                    character_name="Alice",
                    character_id=55,
                )
            )
            unknown = bridge.handle(
                FinishedQuestsSnapshotEvent(
                    session_id="s1",
                    reliable=True,
                    quest_ids=(999, 1000),
                    player_id=55,
                )
            )
            self.assertFalse(unknown.accepted)
            self.assertEqual(unknown.reason, "finished_quests_snapshot_unverified")
            self.assertEqual(achievement_progress.sync_calls, [])


if __name__ == "__main__":
    unittest.main()
