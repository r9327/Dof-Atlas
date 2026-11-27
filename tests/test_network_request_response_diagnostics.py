from __future__ import annotations

import json
import logging
import unittest
from unittest.mock import Mock, patch

from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.network.diagnostics import DEBUG_GATE
from app.network.request_response_diagnostics import (
    DiagnosticProtocolMessageSource,
    PassiveRequestResponseDiagnostics,
    client_request_metadata,
)
from app.network.transport import CapturedProtocolMessage, TransportSessionClosed


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

    def test_zaap_diagnostic_samples_both_wire_layouts_without_raw_data(self) -> None:
        build = "a" * 64
        diagnostics = PassiveRequestResponseDiagnostics(
            logger=self.logger, build_sha256=build, active_build_provider=lambda: build,
        )
        # The archive's wire notes put embedded destinations in tag 3. The
        # extracted schema instead puts a bool there and destinations in tag 4.
        with patch.dict("os.environ", {"ATLAS_ZAAP_DIAGNOSTICS": "1"}, clear=True):
            with self.assertLogs(self.logger, level="INFO") as capture:
                diagnostics.observe(CapturedProtocolMessage(
                    "private-session", "type.ankama.com/hjj",
                    b"\x10\x09\x1a\x02\x28\x0b\x20\x01\x0a\x0cprivate-data",
                ))
                diagnostics.observe(CapturedProtocolMessage(
                    "private-session", "type.ankama.com/hjj",
                    b"\x10\x08\x18\x01\x22\x02\x28\x0c",
                ))
        archive, schema = self._zaap_rows(capture.output)
        self.assertEqual(archive["open_map_candidate"], 9)
        self.assertEqual(archive["destination_tag_3"]["map_id_candidates"], [11])
        self.assertEqual(archive["destination_tag_4"]["varint_count"], 1)
        self.assertEqual(schema["destination_tag_3"]["varint_count"], 1)
        self.assertEqual(schema["destination_tag_4"]["map_id_candidates"], [12])
        self.assertEqual(archive["build_sha256"], build)
        self.assertEqual(archive["classification"], "wire_sample_unverified")
        self.assertNotIn("private-", "\n".join(capture.output))

    def test_zaap_diagnostic_checks_opt_in_message_direction_and_active_build(self) -> None:
        build = "a" * 64
        provider = Mock(return_value="b" * 64)
        diagnostics = PassiveRequestResponseDiagnostics(
            logger=self.logger, build_sha256=build, active_build_provider=provider,
        )
        inbound = CapturedProtocolMessage("s", "type.ankama.com/jru", b"\x10\x2a")
        with patch.dict("os.environ", {}, clear=True), self.assertNoLogs(self.logger, level="INFO"):
            diagnostics.observe(inbound)
        provider.assert_not_called()

        with patch.dict("os.environ", {"ATLAS_ZAAP_DIAGNOSTICS": "1"}, clear=True):
            with self.assertNoLogs(self.logger, level="INFO"):
                diagnostics.observe(CapturedProtocolMessage(
                    "s", "type.ankama.com/jru", inbound.payload, direction="client_to_server",
                ))
                diagnostics.observe(CapturedProtocolMessage("s", "type.ankama.com/unknown", b""))
                diagnostics.observe(inbound)
            provider.assert_called_once_with()

    def test_zaap_diagnostic_uses_capture_lifecycle_and_passes_transport_items_through(self) -> None:
        build = "a" * 64
        state = CharacterRuntimeStateStore()
        state.identify(session_id="source-session", character_key="character:17",
                       character_id=17, name="Private character")
        move = CapturedProtocolMessage(
            "source-session", "type.ankama.com/hjc", b"\x10\x01\x18\x2a",
            direction="client_to_server",
        )
        arrival = CapturedProtocolMessage("source-session", "type.ankama.com/jru", b"\x10\x2a")
        close = TransportSessionClosed("source-session")
        delegate = Mock()
        delegate.read_item.side_effect = [move, arrival, close, arrival, arrival]
        source = DiagnosticProtocolMessageSource(
            delegate, logger=self.logger, phase="calibration",
            build_sha256=build, active_build_provider=lambda: build,
        )
        with (
            patch.dict("os.environ", {"ATLAS_ZAAP_DIAGNOSTICS": "1"}, clear=True),
            patch("app.network.request_response_diagnostics.character_runtime_state", return_value=state),
            self.assertLogs(self.logger, level="INFO") as capture,
        ):
            source.start()
            for item in (move, arrival, close, arrival):
                self.assertIs(source.read_item(0.1), item)
            source.stop()
            source.start()
            self.assertIs(source.read_item(0.1), arrival)
        sent, loaded, closed, reopened, restarted = self._zaap_rows(capture.output)
        self.assertEqual(sent["selection_id_candidate"], loaded["loaded_map_candidate"])
        self.assertEqual(sent["session_alias"], loaded["session_alias"])
        self.assertIsNotNone(loaded["last_verified_character_alias"])
        self.assertEqual(closed["session_alias"], loaded["session_alias"])
        self.assertEqual(closed["classification"], "transport_session_closed")
        self.assertNotEqual(loaded["session_alias"], reopened["session_alias"])
        self.assertEqual(reopened["sequence"], 4)
        self.assertEqual(restarted["sequence"], 1)
        self.assertNotEqual(reopened["last_verified_character_alias"], restarted["last_verified_character_alias"])
        self.assertNotIn("source-session", "\n".join(capture.output))
        self.assertNotIn("Private character", "\n".join(capture.output))
        self.assertTrue(state.snapshot("character:17").connected)

    def test_zaap_diagnostic_keeps_dialog_and_loading_markers_unverified(self) -> None:
        build = "a" * 64
        diagnostics = PassiveRequestResponseDiagnostics(
            logger=self.logger, build_sha256=build, active_build_provider=lambda: build,
        )
        with (
            patch.dict("os.environ", {"ATLAS_ZAAP_DIAGNOSTICS": "1"}, clear=True),
            self.assertLogs(self.logger, level="INFO") as capture,
        ):
            diagnostics.observe(CapturedProtocolMessage("s", "type.ankama.com/kld", b"\x08\x0a"))
            diagnostics.observe(CapturedProtocolMessage("s", "type.ankama.com/lva", b""))
        dialog, loading = self._zaap_rows(capture.output)
        self.assertFalse(dialog["payload_empty"])
        self.assertTrue(loading["payload_empty"])
        self.assertEqual(dialog["session_alias"], loading["session_alias"])
        for row in (dialog, loading):
            self.assertEqual(row["classification"], "wire_sample_unverified")
            self.assertNotIn("loaded_map_candidate", row)

    def test_zaap_diagnostic_reports_truncation_and_malformed_messages_within_budget(self) -> None:
        build = "a" * 64
        diagnostics = PassiveRequestResponseDiagnostics(
            logger=self.logger, build_sha256=build, active_build_provider=lambda: build,
        )
        with (
            patch.dict("os.environ", {"ATLAS_ZAAP_DIAGNOSTICS": "1"}, clear=True),
            patch("app.network.request_response_diagnostics._MAX_ZAAP_DESTINATIONS", 2),
            patch("app.network.request_response_diagnostics._MAX_ZAAP_OBSERVATIONS", 2),
            self.assertLogs(self.logger, level="INFO") as capture,
        ):
            diagnostics.observe(CapturedProtocolMessage(
                "s", "type.ankama.com/hjj", b"\x1a\x02\x28\x01" * 3,
            ))
            diagnostics.observe(CapturedProtocolMessage("s", "type.ankama.com/jss", b"\x10"))
            diagnostics.observe(CapturedProtocolMessage("s", "type.ankama.com/jru", b"\x10\x2a"))
        large, malformed = self._zaap_rows(capture.output)
        self.assertEqual(large["destination_tag_3"]["embedded_count"], 3)
        self.assertEqual(large["destination_tag_3"]["map_id_candidates"], [1, 1])
        self.assertTrue(large["destination_tag_3"]["sample_truncated"])
        self.assertTrue(malformed["malformed"])
        self.assertNotIn("loaded_map_candidate", malformed)

    @staticmethod
    def _zaap_rows(lines: list[str]) -> list[dict]:
        return [json.loads(line.split("[NETWORK][ZAAP][OBSERVED] ", 1)[1]) for line in lines]


if __name__ == "__main__":
    unittest.main()
