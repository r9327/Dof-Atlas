from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

from app.network.diagnostics import DEBUG_GATE
from app.network.request_response_diagnostics import (
    PassiveRequestResponseDiagnostics,
    client_request_metadata,
)
from app.network.transport import CapturedProtocolMessage


class PassiveRequestResponseDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        DEBUG_GATE.clear()
        self.logger = logging.getLogger(f"request-response-diagnostics-{id(self)}")
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self) -> None:
        DEBUG_GATE.clear()

    def test_empty_client_payload_is_unclassified_and_never_quests_request(self) -> None:
        metadata = client_request_metadata(
            CapturedProtocolMessage(
                "session-1",
                "type.ankama.com/abc",
                b"",
                direction="client_to_server",
            )
        )

        self.assertTrue(metadata.payload_empty)
        self.assertEqual(metadata.payload_size, 0)
        self.assertEqual(metadata.payload_fields, ())
        self.assertEqual(metadata.classification, "unclassified_empty_request")
        self.assertFalse(metadata.quest_request_verified)

    def test_temporal_correlation_remains_metadata_only_and_unverified(self) -> None:
        diagnostics = PassiveRequestResponseDiagnostics(logger=self.logger, phase="test")
        outbound = CapturedProtocolMessage(
            "session-1",
            "type.ankama.com/abc",
            b"",
            direction="client_to_server",
        )
        inbound = CapturedProtocolMessage(
            "session-1",
            "type.ankama.com/idz",
            b"\x08\x65\x10\x66",
            direction="server_to_client",
        )

        with (
            patch(
                "app.network.request_response_diagnostics.network_debug_enabled",
                return_value=True,
            ),
            patch("app.network.request_response_diagnostics.network_debug_log") as debug_log,
        ):
            diagnostics.observe(outbound)
            diagnostics.observe(inbound)

        correlations = [
            call
            for call in debug_log.call_args_list
            if len(call.args) >= 2 and call.args[1] == "[NETWORK][REQUEST_RESPONSE_CORRELATION]"
        ]
        self.assertEqual(len(correlations), 1)
        fields = correlations[0].kwargs
        self.assertEqual(fields["classification"], "temporal_only_unverified")
        self.assertFalse(fields["quest_request_verified"])
        self.assertFalse(fields["quest_event_verified"])
        self.assertEqual(fields["request_type"], "type.ankama.com/abc")
        self.assertEqual(fields["response_type"], "type.ankama.com/idz")

        recent = diagnostics._recent["session-1"][-1]
        self.assertFalse(hasattr(recent, "payload"))
        self.assertFalse(hasattr(recent.metadata, "payload"))
        self.assertEqual(recent.metadata.payload_size, 0)

    def test_deep_request_history_is_bounded_and_session_scoped(self) -> None:
        diagnostics = PassiveRequestResponseDiagnostics(logger=self.logger, phase="test")
        with patch(
            "app.network.request_response_diagnostics.network_debug_enabled",
            return_value=True,
        ), patch("app.network.request_response_diagnostics.network_debug_log"):
            for index in range(20):
                diagnostics.observe(
                    CapturedProtocolMessage(
                        "session-1",
                        f"type.ankama.com/a{index:02d}",
                        bytes((index,)),
                        direction="client_to_server",
                    )
                )

        self.assertEqual(len(diagnostics._recent["session-1"]), 8)
        diagnostics.session_closed("session-1")
        self.assertNotIn("session-1", diagnostics._recent)


if __name__ == "__main__":
    unittest.main()
