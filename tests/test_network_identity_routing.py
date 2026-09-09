from __future__ import annotations

import logging
import unittest

from app.network.character_resolver import CharacterResolution
from app.network.events import CharacterIdentifiedEvent, SessionClosedEvent
from app.network.progress_bridge import NetworkProgressBridge
from app.quest_catalog import QuestCatalog


class StaticResolver:
    def resolve(self, character_name: str):
        rows = {
            "Alpha": CharacterResolution("slot:1", "Alpha", 1),
            "Beta": CharacterResolution("slot:2", "Beta", 2),
        }
        return rows.get(character_name)


class UnusedProgressService:
    pass


class UnusedAchievementProvider:
    def get_by_id(self, achievement_id):
        del achievement_id
        return None


class NetworkIdentityRoutingTests(unittest.TestCase):
    def build_bridge(self) -> NetworkProgressBridge:
        logger = logging.getLogger(f"network-identity-routing-{id(self)}")
        logger.addHandler(logging.NullHandler())
        return NetworkProgressBridge(
            quest_catalog=QuestCatalog([]),
            quest_progress_service=UnusedProgressService(),
            achievement_progress_service=UnusedProgressService(),
            achievement_provider=UnusedAchievementProvider(),
            character_resolver=StaticResolver(),
            logger=logger,
        )

    def test_same_identity_event_id_may_reroute_after_character_switch(self) -> None:
        bridge = self.build_bridge()
        alpha = CharacterIdentifiedEvent(
            session_id="connection-1",
            event_id="identity-alpha",
            reliable=True,
            character_name="Alpha",
        )
        beta = CharacterIdentifiedEvent(
            session_id="connection-1",
            event_id="identity-beta",
            reliable=True,
            character_name="Beta",
        )

        self.assertTrue(bridge.handle(alpha).accepted)
        self.assertEqual(bridge.session_character_key("connection-1"), "slot:1")
        self.assertTrue(bridge.handle(beta).accepted)
        self.assertEqual(bridge.session_character_key("connection-1"), "slot:2")

        repeated_alpha = bridge.handle(alpha)
        self.assertTrue(repeated_alpha.accepted)
        self.assertEqual(repeated_alpha.reason, "character_identified")
        self.assertEqual(bridge.session_character_key("connection-1"), "slot:1")

    def test_repeated_session_close_is_safe_and_not_deduped(self) -> None:
        bridge = self.build_bridge()
        bridge.handle(
            CharacterIdentifiedEvent(
                session_id="connection-1",
                event_id="identity-alpha",
                reliable=True,
                character_name="Alpha",
            )
        )
        close = SessionClosedEvent(
            session_id="connection-1",
            event_id="close-event",
            reliable=True,
        )
        first = bridge.handle(close)
        second = bridge.handle(close)
        self.assertTrue(first.accepted)
        self.assertTrue(first.changed)
        self.assertEqual(first.reason, "session_closed")
        self.assertTrue(second.accepted)
        self.assertFalse(second.changed)
        self.assertEqual(second.reason, "session_closed")
        self.assertEqual(bridge.session_character_key("connection-1"), "")


if __name__ == "__main__":
    unittest.main()
