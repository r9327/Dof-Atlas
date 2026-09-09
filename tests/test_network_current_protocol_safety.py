from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.network.calibration_bootstrap import ProtocolCalibrationBootstrapResult
from app.network.calibration_controller import ProtocolCalibrationController
from app.network.discovery_evidence import (
    ProtocolDiscoveryEvidenceError,
    build_discovery_consensus,
    parse_discovery_consensus,
)
from app.network.mapping_install import ProtocolMappingInstallResult
from app.network.protocol_calibration import ProtocolCalibrationStatus
from app.quest_catalog import QuestCatalog


BUILD = "ab" * 32
PRIVACY = "no_payload_no_scalar_value_no_session_no_address_storage"


def _report(capture_id: str, type_url: str) -> dict:
    return {
        "schema_version": 1,
        "purpose": "protocol_mapping_discovery_evidence_only",
        "authoritative_mapping": False,
        "privacy": PRIVACY,
        "direction": "server_to_client",
        "capture_id": capture_id,
        "build_sha256": BUILD,
        "event_type": "quest_completed",
        "observed_message_count": 1,
        "malformed_message_count": 0,
        "dropped_candidate_count": 0,
        "candidate_count": 1,
        "candidates": [
            {
                "type_url": type_url,
                "path": [4],
                "kind": "positive_int",
                "matching_message_count": 1,
            }
        ],
    }


class _FakeCalibrationRuntime:
    def drain_identity_results(self):
        return []

    def __init__(self, latest: ProtocolCalibrationStatus, *, stop_result: bool = True) -> None:
        self.latest_status = latest
        self.stop_result = bool(stop_result)
        self.is_running = False
        self.start_count = 0
        self.stop_count = 0
        self.statuses: list[ProtocolCalibrationStatus] = []

    def start(self) -> bool:
        self.start_count += 1
        self.is_running = True
        return True

    def stop(self) -> bool:
        self.stop_count += 1
        if self.stop_result:
            self.is_running = False
        return self.stop_result

    def drain_statuses(self, _limit: int) -> list[ProtocolCalibrationStatus]:
        rows = list(self.statuses)
        self.statuses.clear()
        return rows


def _ready_status() -> ProtocolCalibrationStatus:
    return ProtocolCalibrationStatus(
        ready=True,
        reason="profile_calibrated",
        build_sha256=BUILD,
        identified_session_count=1,
        max_distinct_completion_count=2,
        certificate=None,
    )


class CurrentProtocolSafetyTests(unittest.TestCase):
    def test_discovery_evidence_accepts_current_type_ankama_prefix(self) -> None:
        consensus = build_discovery_consensus(
            (
                _report("1" * 32, "type.ankama.com/lqn"),
                _report("2" * 32, "type.ankama.com/lqn"),
            )
        )
        self.assertTrue(consensus.unambiguous)
        self.assertEqual(consensus.candidates[0].type_url, "type.ankama.com/lqn")
        self.assertEqual(parse_discovery_consensus(consensus.to_dict()), consensus)

    def test_discovery_evidence_still_rejects_foreign_type_url(self) -> None:
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            build_discovery_consensus(
                (
                    _report("3" * 32, "example.com/lqn"),
                    _report("4" * 32, "example.com/lqn"),
                )
            )

    def test_controller_requires_context_before_composing_capture(self) -> None:
        controller = ProtocolCalibrationController(lambda: ())
        with patch("app.network.calibration_bootstrap.build_windows_protocol_calibration") as build:
            status = controller.start()
        self.assertEqual(status.reason, "waiting_context")
        build.assert_not_called()

    def test_controller_does_not_start_when_mapping_is_already_ready(self) -> None:
        controller = ProtocolCalibrationController(lambda: (1,))
        controller.configure_context(quest_catalog=QuestCatalog([]))
        bootstrap = ProtocolCalibrationBootstrapResult(
            None,
            "mapping_already_ready",
            build_sha256=BUILD,
            existing_mapping_path=Path("mapping.json"),
        )
        with patch(
            "app.network.calibration_bootstrap.build_windows_protocol_calibration",
            return_value=bootstrap,
        ):
            status = controller.start()
        self.assertFalse(status.running)
        self.assertEqual(status.reason, "mapping_already_ready")
        self.assertEqual(status.mapping_path, Path("mapping.json"))

    def test_ready_certificate_never_installs_until_reader_is_stopped(self) -> None:
        runtime = _FakeCalibrationRuntime(_ready_status(), stop_result=False)
        controller = ProtocolCalibrationController(lambda: (1,))
        controller.configure_context(quest_catalog=QuestCatalog([]))
        bootstrap = ProtocolCalibrationBootstrapResult(runtime, "ready_to_calibrate", BUILD)
        with patch(
            "app.network.calibration_bootstrap.build_windows_protocol_calibration",
            return_value=bootstrap,
        ):
            self.assertTrue(controller.start().running)
        runtime.statuses.append(_ready_status())
        with patch("app.network.calibrated_mapping_install.install_calibrated_current_profile") as install:
            status = controller.poll()
        install.assert_not_called()
        self.assertEqual(status.reason, "calibration_stop_failed_before_install")
        self.assertTrue(status.running)

    def test_install_exception_is_contained_and_reader_reference_is_cleared(self) -> None:
        runtime = _FakeCalibrationRuntime(_ready_status())
        controller = ProtocolCalibrationController(lambda: (1,))
        controller.configure_context(quest_catalog=QuestCatalog([]))
        bootstrap = ProtocolCalibrationBootstrapResult(runtime, "ready_to_calibrate", BUILD)
        with patch(
            "app.network.calibration_bootstrap.build_windows_protocol_calibration",
            return_value=bootstrap,
        ):
            controller.start()
        runtime.statuses.append(_ready_status())
        with patch(
            "app.network.calibrated_mapping_install.install_calibrated_current_profile",
            side_effect=RuntimeError("boom"),
        ):
            status = controller.poll()
        self.assertFalse(status.running)
        self.assertFalse(status.installed)
        self.assertEqual(status.reason, "calibration_install_error")

    def test_successful_install_is_reported_without_starting_progression(self) -> None:
        runtime = _FakeCalibrationRuntime(_ready_status())
        controller = ProtocolCalibrationController(lambda: (1,))
        controller.configure_context(quest_catalog=QuestCatalog([]))
        bootstrap = ProtocolCalibrationBootstrapResult(runtime, "ready_to_calibrate", BUILD)
        install_result = ProtocolMappingInstallResult(
            True,
            True,
            "mapping_installed_not_started",
            build_sha256=BUILD,
            destination=Path("mapping.json"),
        )
        with patch(
            "app.network.calibration_bootstrap.build_windows_protocol_calibration",
            return_value=bootstrap,
        ):
            controller.start()
        runtime.statuses.append(_ready_status())
        with patch(
            "app.network.calibrated_mapping_install.install_calibrated_current_profile",
            return_value=install_result,
        ) as install:
            status = controller.poll()
        install.assert_called_once()
        self.assertFalse(status.running)
        self.assertTrue(status.installed)
        self.assertEqual(status.reason, "mapping_installed_not_started")
        self.assertEqual(status.mapping_path, Path("mapping.json"))


if __name__ == "__main__":
    unittest.main()
