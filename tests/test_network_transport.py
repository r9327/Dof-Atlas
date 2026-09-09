from __future__ import annotations

import unittest

from app.network.events import QuestCompletedEvent, SessionClosedEvent
from app.network.normalizer import DecodedClientMessage
from app.network.transport import (
    CapturedProtocolMessage,
    DecodedNetworkEventSource,
    TransportSessionClosed,
)


class FakeSource:
    def __init__(self, items) -> None:
        self.items = list(items)
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def read_item(self, timeout: float):
        del timeout
        if not self.items:
            return None
        return self.items.pop(0)


class FakeDecoder:
    def __init__(self, *, fail_types=()) -> None:
        self.fail_types = set(fail_types)
        self.reset_count = 0
        self.closed_sessions: list[str] = []

    def decode(self, message: CapturedProtocolMessage):
        if message.type_url in self.fail_types:
            raise ValueError("synthetic decoder failure")
        if message.type_url != "type.ankama.com/quest_done":
            return None
        return DecodedClientMessage(
            session_id=message.session_id,
            event_type="quest_completed",
            fields={"quest_id": 1234},
            event_id="event-1234",
            verified=True,
        )

    def reset(self) -> None:
        self.reset_count += 1

    def session_closed(self, session_id: str) -> None:
        self.closed_sessions.append(session_id)


class NetworkTransportTests(unittest.TestCase):
    def test_source_start_and_stop_are_delegated_and_decoder_is_reset(self) -> None:
        raw = FakeSource([])
        decoder = FakeDecoder()
        source = DecodedNetworkEventSource(raw, decoder)
        source.start()
        self.assertTrue(raw.started)
        self.assertEqual(decoder.reset_count, 1)
        source.stop()
        self.assertFalse(raw.started)
        self.assertEqual(decoder.reset_count, 2)

    def test_unknown_message_is_skipped_before_verified_event(self) -> None:
        raw = FakeSource(
            [
                CapturedProtocolMessage("session-1", "type.ankama.com/unknown", b"x"),
                CapturedProtocolMessage("session-1", "type.ankama.com/quest_done", b"x"),
            ]
        )
        source = DecodedNetworkEventSource(raw, FakeDecoder())
        event = source.read_event(0.5)
        self.assertIsInstance(event, QuestCompletedEvent)
        self.assertEqual(event.quest_id, 1234)
        self.assertTrue(event.reliable)

    def test_decoder_failure_is_skipped_before_next_event(self) -> None:
        raw = FakeSource(
            [
                CapturedProtocolMessage("session-1", "type.ankama.com/broken", b"x"),
                CapturedProtocolMessage("session-1", "type.ankama.com/quest_done", b"x"),
            ]
        )
        source = DecodedNetworkEventSource(
            raw,
            FakeDecoder(fail_types={"type.ankama.com/broken"}),
        )
        event = source.read_event(0.5)
        self.assertIsInstance(event, QuestCompletedEvent)
        self.assertEqual(event.quest_id, 1234)

    def test_transport_close_becomes_reliable_session_close_and_purges_decoder_session(self) -> None:
        decoder = FakeDecoder()
        source = DecodedNetworkEventSource(
            FakeSource([TransportSessionClosed(session_id="session-9")]),
            decoder,
        )
        event = source.read_event(0.5)
        self.assertIsInstance(event, SessionClosedEvent)
        self.assertEqual(event.session_id, "session-9")
        self.assertTrue(event.reliable)
        self.assertEqual(decoder.closed_sessions, ["session-9"])

    def test_unverified_decoded_message_never_becomes_business_event(self) -> None:
        class UnverifiedDecoder:
            def decode(self, message):
                return DecodedClientMessage(
                    session_id=message.session_id,
                    event_type="quest_completed",
                    fields={"quest_id": 1234},
                    event_id="unverified",
                    verified=False,
                )

        source = DecodedNetworkEventSource(
            FakeSource([CapturedProtocolMessage("session-1", "type.ankama.com/anything", b"x")]),
            UnverifiedDecoder(),
        )
        self.assertIsNone(source.read_event(0.5))

    def test_client_to_server_decode_cannot_reach_any_business_mutation_domain(self) -> None:
        class PermissiveDecoder:
            def __init__(self, event_type: str, fields: dict[str, object]) -> None:
                self.event_type = event_type
                self.fields = fields
                self.decode_count = 0

            def decode(self, message):
                self.decode_count += 1
                return DecodedClientMessage(
                    session_id=message.session_id,
                    event_type=self.event_type,
                    fields=self.fields,
                    event_id=f"accidentally-accepted-outbound:{self.event_type}",
                    verified=True,
                )

        class RejectingBusinessNormalizer:
            def normalize(self, _decoded):
                raise AssertionError("client_to_server packet reached business normalizer")

        cases = (
            ("character_identified", {"character_name": "Injected", "character_id": 9001}),
            ("quest_started", {"quest_id": 1234}),
            ("quest_completed", {"quest_id": 1234}),
            ("achievement_unlocked", {"achievement_id": 4567}),
            ("achievement_progress", {"achievement_id": 4567, "current": 1, "total": 2}),
        )
        for event_type, fields in cases:
            with self.subTest(event_type=event_type):
                decoder = PermissiveDecoder(event_type, fields)
                source = DecodedNetworkEventSource(
                    FakeSource(
                        [
                            CapturedProtocolMessage(
                                "session-1",
                                "type.ankama.com/outbound",
                                b"x",
                                direction="client_to_server",
                            )
                        ]
                    ),
                    decoder,
                    normalizer=RejectingBusinessNormalizer(),
                )

                self.assertIsNone(source.read_event(0.05))
                self.assertEqual(decoder.decode_count, 1)


if __name__ == "__main__":
    unittest.main()
