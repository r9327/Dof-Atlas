from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from app.constants import KEY_SESSION_ORDER
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)
from app.network.character_resolver import CharacterSlotResolver
from app.network.events import CharacterIdentifiedEvent, QuestCompletedEvent, SessionClosedEvent
from app.network.progress_bridge import NetworkProgressBridge
from app.quest_catalog import QuestCatalog, QuestRecord


class EmptyAchievementProvider:
    def load_retained(self):
        return []

    def get_by_id(self, achievement_id: int):
        return None


class NetworkSessionSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.profile_path = self.root / "profiles.json"
        self.client_index_path = self.root / "client_index.json"
        self.profile_path.write_text(
            json.dumps({KEY_SESSION_ORDER: ["Alpha", "Beta"]}),
            encoding="utf-8",
        )
        self.client_index_path.write_text(
            json.dumps({"clients": [{"index": 1, "name": "Alpha"}, {"index": 2, "name": "Beta"}]}),
            encoding="utf-8",
        )
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
        logger = logging.getLogger(f"network-session-safety-{id(self)}")
        logger.addHandler(logging.NullHandler())
        self.bridge = NetworkProgressBridge(
            quest_catalog=self.catalog,
            quest_progress_service=self.quest_progress,
            achievement_progress_service=self.achievement_progress,
            achievement_provider=EmptyAchievementProvider(),
            character_resolver=CharacterSlotResolver(
                self.profile_path,
                self.client_index_path,
                slot_count=2,
            ),
            logger=logger,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unresolved_character_change_clears_previous_route(self) -> None:
        identified = self.bridge.handle(
            CharacterIdentifiedEvent(
                session_id="connection-1",
                event_id="identify-alpha",
                reliable=True,
                character_name="Alpha",
                character_id=1001,
            )
        )
        self.assertTrue(identified.accepted)
        self.assertEqual(self.bridge.session_character_key("connection-1"), "character:1001")

        unresolved = self.bridge.handle(
            CharacterIdentifiedEvent(
                session_id="connection-1",
                event_id="identify-unknown",
                reliable=True,
                character_name="UnknownCharacter",
                character_id=None,
            )
        )
        self.assertFalse(unresolved.accepted)
        self.assertEqual(unresolved.reason, "character_unresolved")
        self.assertEqual(self.bridge.session_character_key("connection-1"), "")

        quest = self.bridge.handle(
            QuestCompletedEvent(
                session_id="connection-1",
                event_id="quest-after-unresolved-character",
                reliable=True,
                quest_id=10,
            )
        )
        self.assertFalse(quest.accepted)
        self.assertEqual(quest.reason, "character_not_identified")
        self.assertFalse(self.quest_progress.is_quest_completed("character:1001", 10))

    def test_session_closed_event_removes_character_route(self) -> None:
        self.bridge.handle(
            CharacterIdentifiedEvent(
                session_id="connection-1",
                reliable=True,
                character_name="Alpha",
                character_id=1001,
            )
        )
        closed = self.bridge.handle(
            SessionClosedEvent(
                session_id="connection-1",
                event_id="disconnect-1",
                reliable=True,
            )
        )
        self.assertTrue(closed.accepted)
        self.assertTrue(closed.changed)
        self.assertEqual(closed.character_key, "character:1001")
        self.assertEqual(self.bridge.session_character_key("connection-1"), "")

        stale = self.bridge.handle(
            QuestCompletedEvent(
                session_id="connection-1",
                event_id="stale-after-close",
                reliable=True,
                quest_id=10,
            )
        )
        self.assertFalse(stale.accepted)
        self.assertFalse(self.quest_progress.is_quest_completed("character:1001", 10))

    def test_runtime_reset_clears_dedupe_with_character_routes(self) -> None:
        event = CharacterIdentifiedEvent(
            session_id="connection-1",
            event_id="same-identification-envelope",
            reliable=True,
            character_name="Alpha",
            character_id=1001,
        )
        first = self.bridge.handle(event)
        self.assertTrue(first.accepted)
        self.assertEqual(self.bridge.session_character_key("connection-1"), "character:1001")

        self.bridge.reset_sessions()
        self.assertEqual(self.bridge.session_character_key("connection-1"), "")

        replayed_after_restart = self.bridge.handle(event)
        self.assertTrue(replayed_after_restart.accepted)
        self.assertNotEqual(replayed_after_restart.reason, "duplicate_event")
        self.assertEqual(self.bridge.session_character_key("connection-1"), "character:1001")

    def test_ambiguous_unconnected_character_name_fails_closed(self) -> None:
        duplicate_profile = self.root / "duplicate_profiles.json"
        empty_clients = self.root / "empty_clients.json"
        duplicate_profile.write_text(
            json.dumps({KEY_SESSION_ORDER: ["SameName", "SameName"]}),
            encoding="utf-8",
        )
        empty_clients.write_text(json.dumps({"clients": []}), encoding="utf-8")
        resolver = CharacterSlotResolver(duplicate_profile, empty_clients, slot_count=2)
        self.assertIsNone(resolver.resolve("SameName"))


if __name__ == "__main__":
    unittest.main()
