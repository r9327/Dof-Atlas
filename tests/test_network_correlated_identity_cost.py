from __future__ import annotations

import unittest

from app.network.correlated_identity_decoder import (
    CorrelatedCharacterIdentityDecoder,
    CorrelatedCharacterIdentityRule,
)
from app.network.normalizer import DecodedClientMessage
from app.network.transport import CapturedProtocolMessage


FINGERPRINT = "ab" * 32


class _Delegate:
    def __init__(self) -> None:
        self.messages: list[CapturedProtocolMessage] = []

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        self.messages.append(message)
        return None


class CorrelatedIdentityCostTests(unittest.TestCase):
    def test_unrelated_packets_do_not_call_active_build_provider(self) -> None:
        calls = 0

        def fingerprint_provider() -> str:
            nonlocal calls
            calls += 1
            return FINGERPRINT

        delegate = _Delegate()
        decoder = CorrelatedCharacterIdentityDecoder(
            delegate,
            CorrelatedCharacterIdentityRule(
                roster_type_url="type.ankama.com/kvi",
                selected_type_url="type.ankama.com/kva",
                roster_entry_field=1,
                roster_character_id_path=(2,),
                roster_character_name_path=(1, 2),
                selected_character_id_path=(1, 1, 2),
            ),
            mapping_version="3.6.10.10",
            mapping_fingerprint=FINGERPRINT,
            active_fingerprint_provider=fingerprint_provider,
        )

        message = CapturedProtocolMessage(
            "session-1",
            "type.ankama.com/unrelated",
            b"\x08\x01",
        )
        self.assertIsNone(decoder.decode(message))
        self.assertEqual(delegate.messages, [message])
        self.assertEqual(calls, 0)

    def test_identity_packet_still_checks_active_build(self) -> None:
        calls = 0

        def fingerprint_provider() -> str:
            nonlocal calls
            calls += 1
            return FINGERPRINT

        decoder = CorrelatedCharacterIdentityDecoder(
            _Delegate(),
            CorrelatedCharacterIdentityRule(
                roster_type_url="type.ankama.com/kvi",
                selected_type_url="type.ankama.com/kva",
                roster_entry_field=1,
                roster_character_id_path=(2,),
                roster_character_name_path=(1, 2),
                selected_character_id_path=(1, 1, 2),
            ),
            mapping_version="3.6.10.10",
            mapping_fingerprint=FINGERPRINT,
            active_fingerprint_provider=fingerprint_provider,
        )

        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    "session-1",
                    "type.ankama.com/kvi",
                    b"",
                )
            )
        )
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
