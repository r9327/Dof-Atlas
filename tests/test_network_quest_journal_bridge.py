from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.network.character_resolver import CharacterResolution
from app.network.events import CharacterIdentifiedEvent, QuestJournalSnapshotEvent, SessionClosedEvent
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


class QuestJournalBridgeTests(unittest.TestCase):
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

    @staticmethod
    def _identify(bridge: NetworkProgressBridge, name: str = "Alice", character_id: int | None = 55):
        return bridge.handle(
            CharacterIdentifiedEvent(
                session_id="s1",
                reliable=True,
                character_name=name,
                character_id=character_id,
            )
        )

    @staticmethod
    def _journal(
        *,
        event_id: str = "journal:1",
        finished: tuple[int, ...] = (101,),
        active: tuple[int, ...] = (),
        session_id: str = "s1",
    ) -> QuestJournalSnapshotEvent:
        return QuestJournalSnapshotEvent(
            session_id=session_id,
            event_id=event_id,
            reliable=True,
            finished_quest_ids=finished,
            active_quest_ids=active,
        )

    def test_journal_before_identity_is_retained_without_mutation_then_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")

            pending = bridge.handle(self._journal(finished=(101, 202), active=(303,)))

            self.assertTrue(pending.accepted)
            self.assertFalse(pending.changed)
            self.assertEqual(pending.reason, "quest_journal_pending_identity")
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, [])

            identified = self._identify(bridge)

            self.assertTrue(identified.accepted)
            self.assertTrue(identified.changed)
            self.assertEqual(identified.reason, "character_identified_with_quest_journal")
            self.assertEqual(
                bridge.quest_progress_service.completed_quest_ids("character:55"),
                {101, 202},
            )
            self.assertFalse(bridge.quest_progress_service.is_quest_completed("character:55", 303))
            self.assertEqual(achievement_progress.sync_calls, ["character:55"])

    def test_latest_pre_identity_journal_replaces_older_whole_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, _achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            bridge.handle(self._journal(event_id="journal:old", finished=(101,)))
            bridge.handle(self._journal(event_id="journal:new", finished=(202,)))

            self._identify(bridge)

            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), {202})

    def test_unresolved_identity_discards_pending_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            bridge.handle(self._journal(finished=(101,)))

            unresolved = self._identify(bridge, name="Unknown", character_id=55)
            later = self._identify(bridge, name="Alice", character_id=55)

            self.assertFalse(unresolved.accepted)
            self.assertTrue(later.accepted)
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, [])

    def test_session_close_discards_pending_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            bridge.handle(self._journal(finished=(101,)))
            bridge.handle(SessionClosedEvent(session_id="s1", reliable=True))

            self._identify(bridge)

            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, [])

    def test_journal_requires_verified_character_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            self._identify(bridge, character_id=None)
            result = bridge.handle(self._journal())
            self.assertFalse(result.accepted)
            self.assertEqual(result.reason, "character_id_missing")
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, [])

    def test_pending_journal_is_not_applied_without_concrete_character_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            bridge.handle(self._journal(finished=(101,)))

            first_identity = self._identify(bridge, character_id=None)
            second_identity = self._identify(bridge, character_id=55)

            self.assertTrue(first_identity.accepted)
            self.assertTrue(second_identity.accepted)
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, [])

    def test_journal_marks_only_finished_quests_in_one_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            self._identify(bridge)
            result = bridge.handle(self._journal(finished=(101, 202), active=(303,)))
            self.assertTrue(result.accepted)
            self.assertTrue(result.changed)
            self.assertEqual(result.reason, "quest_journal_reconciled")
            self.assertEqual(result.character_key, "character:55")
            self.assertEqual(
                bridge.quest_progress_service.completed_quest_ids("character:55"),
                {101, 202},
            )
            self.assertFalse(bridge.quest_progress_service.is_quest_completed("character:55", 303))
            self.assertEqual(achievement_progress.sync_calls, ["character:55"])

    def test_unknown_finished_ids_are_ignored_without_blocking_known_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            self._identify(bridge)
            result = bridge.handle(self._journal(finished=(101, 999999)))
            self.assertTrue(result.accepted)
            self.assertTrue(result.changed)
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), {101})
            self.assertEqual(achievement_progress.sync_calls, ["character:55"])

    def test_empty_or_wholly_unknown_finished_set_never_marks_active_quests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            self._identify(bridge)
            result = bridge.handle(
                self._journal(
                    finished=(999999,),
                    active=(101, 202, 303),
                )
            )
            self.assertTrue(result.accepted)
            self.assertFalse(result.changed)
            self.assertEqual(result.reason, "quest_journal_no_known_finished_quests")
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), set())
            self.assertEqual(achievement_progress.sync_calls, ["character:55"])

    def test_same_journal_is_idempotent_and_scoped_to_selected_character(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, achievement_progress = self._bridge(Path(temp_dir) / "quests.json")
            self._identify(bridge)
            event = self._journal(event_id="journal:alice", finished=(101,))
            first = bridge.handle(event)
            duplicate = bridge.handle(event)
            self.assertTrue(first.changed)
            self.assertEqual(duplicate.reason, "duplicate_event")

            switched = self._identify(bridge, name="Bob", character_id=66)
            self.assertTrue(switched.accepted)
            bob = bridge.handle(
                self._journal(
                    event_id="journal:alice",
                    finished=(202,),
                )
            )
            self.assertTrue(bob.accepted)
            self.assertTrue(bob.changed)
            self.assertEqual(bob.character_key, "character:66")
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:55"), {101})
            self.assertEqual(bridge.quest_progress_service.completed_quest_ids("character:66"), {202})
            self.assertEqual(achievement_progress.sync_calls, ["character:55", "character:66"])


if __name__ == "__main__":
    unittest.main()
