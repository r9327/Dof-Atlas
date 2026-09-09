from __future__ import annotations

import inspect
import logging
import unittest
from unittest.mock import patch

from app.network.calibration_runtime import ProtocolCalibrationRuntime
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.network.progress_bridge import EventApplicationResult
from app.network.runtime import NetworkEventRuntime
from app.ui.network_bridge import NetworkUiBridge
from tests.test_network_calibration_runtime import _Source, _kvi, _kva, _Resolver, BUILD
from app.network.protocol_calibration import CurrentProtocolCalibration
from app.quest_catalog import QuestCatalog
from app.network.capture_ipc import CaptureIpcDisconnected
from app.network.mapped_decoder import StrictMappedProtocolDecoder, ProtocolMessageRule, ProtocolFieldRule
from app.network.transport import CapturedProtocolMessage


class NetworkAuditRegressionTests(unittest.TestCase):
    def test_new_character_name_cannot_reuse_previous_pid_identity_in_picker(self):
        import json
        import tempfile
        from pathlib import Path
        from app.quest_catalog import load_quest_characters
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'profiles.json').write_text('{}')
            (root/'clients.json').write_text(json.dumps({'clients': [{'character_name': 'Beta', 'pid': 100}]}))
            (root/'bindings.json').write_text(json.dumps({'characters': {'42': {
                'name': 'Alpha', 'pid': 100, 'source': 'verified_network_identity'}}}))
            rows = load_quest_characters(root/'profiles.json', root/'clients.json',
                binding_path=root/'bindings.json', connected_only=True)
            self.assertEqual(rows, [])

    def test_calibration_publishes_identity_without_any_quest_evidence(self):
        calibration = CurrentProtocolCalibration(
            build_sha256=BUILD, active_build_sha256_provider=lambda: BUILD,
            quest_catalog=QuestCatalog([]), character_resolver=_Resolver(),
        )
        runtime = ProtocolCalibrationRuntime(_Source((_kvi(), _kva())), calibration)
        original = runtime._publish

        def publish(status):
            original(status)
            if status.identified_session_count:
                runtime._stop_event.set()

        with patch.object(runtime, "_publish", side_effect=publish):
            runtime._run()
        results = runtime.drain_identity_results()
        self.assertEqual([r.character_key for r in results], ["character:9001"])
        self.assertFalse(runtime.latest_status.ready)
        self.assertEqual(runtime.latest_status.quest_journal_observation_count, 0)
        self.assertEqual(runtime.drain_identity_results(), [])

    def test_older_connection_cannot_replace_reconnected_profile(self):
        state = CharacterRuntimeStateStore()
        for session in ("tcp:100:1", "tcp:200:2"):
            state.identify(session_id=session, character_key="character:42",
                           character_id=42, name="Alpha")
        self.assertTrue(state.update_verified_profile("tcp:200:2", level=200))
        self.assertFalse(state.update_verified_profile("tcp:100:1", level=100))
        self.assertEqual(state.snapshot("character:42").level, 200)
        state.close_session("tcp:200:2")
        self.assertFalse(state.update_verified_profile("tcp:100:1", level=100))

    def test_noop_identity_reaches_ui_and_lossless_results_exceed_old_limits(self):
        result = EventApplicationResult(True, False, "character_identified", "character:42")
        class Source:
            count = 0
            def read_event(self, timeout):
                self.count += 1
                if self.count > 5000:
                    runtime._stop_event.set()
                    return None
                return object()
            def stop(self):
                pass
        class Bridge:
            def handle(self, event):
                return result
            def reset_sessions(self):
                pass
        runtime = NetworkEventRuntime(Source(), Bridge(), logger=logging.getLogger(__name__))
        runtime._run()
        self.assertEqual(len(runtime.drain_results(6000)), 5000)

    def test_ui_poll_uses_explicit_consumers(self):
        self.assertNotIn("allWidgets", inspect.getsource(NetworkUiBridge._poll))

    def test_disconnected_helper_stops_reader_instead_of_spinning(self):
        from unittest.mock import Mock
        source, bridge = Mock(), Mock()
        source.read_event.side_effect = CaptureIpcDisconnected('closed')
        runtime = NetworkEventRuntime(source, bridge, logger=Mock())
        runtime._run()
        self.assertEqual(runtime.start_failure_reason, 'capture_helper_disconnected')
        source.read_event.assert_called_once()
        source.stop.assert_called_once()
        bridge.handle.assert_not_called()
        bridge.reset_sessions.assert_called_once()

    def test_malformed_mapped_payload_logs_once_and_never_emits_event(self):
        from unittest.mock import Mock
        decoder = StrictMappedProtocolDecoder(mapping_version='test',
            active_version_provider=lambda: 'test', rules={'known': ProtocolMessageRule(
                'character_identified', (ProtocolFieldRule('character_id', (1,), 'positive_int'),))})
        message = CapturedProtocolMessage(session_id='s', type_url='known', payload=b'\x80', direction='server_to_client')
        logger = Mock()
        with patch('app.core.logger.get_runtime_logger', return_value=logger):
            for _ in range(10):
                self.assertIsNone(decoder.decode(message))
        logger.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
