from __future__ import annotations

import threading
import time
import unittest

from app.network.calibration_runtime import ProtocolCalibrationRuntime
from app.network.character_resolver import CharacterResolution
from app.network.protocol_calibration import CurrentProtocolCalibration
from app.network.transport import CapturedProtocolMessage
from app.quest_catalog import QuestCatalog, QuestRecord, QuestStep


BUILD = "ab" * 32


def _varint(value: int) -> bytes:
    output = bytearray()
    current = int(value)
    while True:
        byte = current & 0x7F
        current >>= 7
        if current:
            output.append(byte | 0x80)
        else:
            output.append(byte)
            return bytes(output)


def _v(field_number: int, value: int) -> bytes:
    return _varint((field_number << 3) | 0) + _varint(value)


def _b(field_number: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(value)) + value


def _kvi() -> CapturedProtocolMessage:
    details = _b(2, b"Atlas-Test")
    entry = _b(1, details) + _v(2, 9001)
    return CapturedProtocolMessage("s1", "type.ankama.com/kvi", _b(1, entry))


def _kva() -> CapturedProtocolMessage:
    return CapturedProtocolMessage("s1", "type.ankama.com/kva", _b(1, _b(1, _v(2, 9001))))


def _journal() -> CapturedProtocolMessage:
    payload = _b(3, _v(1, 1) + _v(2, 101))
    payload += _b(3, _v(1, 1) + _v(2, 202))
    return CapturedProtocolMessage("s1", "type.ankama.com/idr", payload)


def _idz(quest_id: int, step_id: int) -> CapturedProtocolMessage:
    return CapturedProtocolMessage(
        "s1",
        "type.ankama.com/idz",
        _v(1, quest_id) + _v(2, step_id),
    )


def _quest(quest_id: int, final_step_id: int) -> QuestRecord:
    return QuestRecord(
        id=quest_id,
        name=f"Q{quest_id}",
        category="Test",
        level_min=1,
        level_max=200,
        start_criterion="",
        steps=[QuestStep(id=final_step_id, name=f"S{final_step_id}", description="")],
    )


class _Resolver:
    def resolve(self, name: str):
        if name == "Atlas-Test":
            return CharacterResolution("slot:1", "Atlas-Test", 1)
        return None


class _Source:
    def __init__(self, items=(), *, fail_start: bool = False) -> None:
        self.items = list(items)
        self.fail_start = fail_start
        self.started = False
        self.stop_count = 0

    def start(self) -> None:
        if self.fail_start:
            raise RuntimeError("boom")
        self.started = True

    def stop(self) -> None:
        self.started = False
        self.stop_count += 1

    def read_item(self, timeout: float):
        del timeout
        if self.items:
            return self.items.pop(0)
        time.sleep(0.001)
        return None


class _LateItemSource(_Source):
    def __init__(self) -> None:
        super().__init__()
        self.read_started = threading.Event()
        self.release = threading.Event()

    def stop(self) -> None:
        super().stop()
        self.release.set()

    def read_item(self, timeout: float):
        del timeout
        self.read_started.set()
        self.release.wait(1.0)
        return _journal()


class CalibrationRuntimeTests(unittest.TestCase):
    def calibration(self) -> CurrentProtocolCalibration:
        catalog = QuestCatalog([_quest(101, 1001), _quest(202, 2001)])
        return CurrentProtocolCalibration(
            build_sha256=BUILD,
            active_build_sha256_provider=lambda: BUILD,
            quest_catalog=catalog,
            character_resolver=_Resolver(),
        )

    def wait_until_stopped(self, runtime: ProtocolCalibrationRuntime) -> None:
        deadline = time.monotonic() + 1.0
        while runtime.is_running and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(runtime.is_running)

    def test_runtime_auto_stops_on_ready_certificate(self) -> None:
        source = _Source((_journal(), _kvi(), _kva(), _idz(101, 1001), _idz(202, 2001)))
        runtime = ProtocolCalibrationRuntime(source, self.calibration(), read_timeout=0.01)
        self.assertTrue(runtime.start())
        self.wait_until_stopped(runtime)

        self.assertTrue(runtime.latest_status.ready)
        self.assertEqual(runtime.latest_status.reason, "profile_calibrated")
        self.assertGreaterEqual(source.stop_count, 1)
        statuses = runtime.drain_statuses()
        self.assertEqual(statuses[0].reason, "awaiting_character_identity")
        self.assertEqual(statuses[-1].reason, "profile_calibrated")

    def test_unchanged_packets_do_not_spam_status_queue(self) -> None:
        unrelated = CapturedProtocolMessage("s1", "type.ankama.com/zzz", b"")
        source = _Source(
            (
                _journal(),
                unrelated,
                unrelated,
                _kvi(),
                unrelated,
                _kva(),
                unrelated,
                _idz(101, 1001),
                unrelated,
                _idz(202, 2001),
            )
        )
        runtime = ProtocolCalibrationRuntime(source, self.calibration(), read_timeout=0.01)
        self.assertTrue(runtime.start())
        self.wait_until_stopped(runtime)
        statuses = runtime.drain_statuses()
        self.assertEqual(
            [row.reason for row in statuses],
            [
                "awaiting_character_identity",
                "awaiting_distinct_quest_completions",
                "awaiting_distinct_quest_completions",
                "profile_calibrated",
            ],
        )
        self.assertEqual(
            [row.max_distinct_completion_count for row in statuses],
            [0, 0, 1, 2],
        )
        self.assertEqual(statuses[-1].quest_journal_observation_count, 1)
        self.assertEqual(statuses[-1].quest_journal_verified_count, 2)

    def test_start_failure_does_not_leave_reader_running(self) -> None:
        source = _Source(fail_start=True)
        source.start_failure_reason = "capture_elevation_cancelled"
        runtime = ProtocolCalibrationRuntime(source, self.calibration(), read_timeout=0.01)
        self.assertFalse(runtime.start())
        self.assertFalse(runtime.is_running)
        self.assertEqual(runtime.start_failure_reason, "capture_elevation_cancelled")
        self.assertEqual(runtime.drain_statuses(), [])

    def test_explicit_stop_is_idempotent(self) -> None:
        source = _Source()
        runtime = ProtocolCalibrationRuntime(source, self.calibration(), read_timeout=0.01)
        self.assertTrue(runtime.start())
        self.assertTrue(runtime.stop())
        self.assertTrue(runtime.stop())
        self.assertFalse(runtime.is_running)

    def test_item_returned_during_stop_is_not_observed(self) -> None:
        source = _LateItemSource()
        runtime = ProtocolCalibrationRuntime(source, self.calibration(), read_timeout=0.01)

        self.assertTrue(runtime.start())
        self.assertTrue(source.read_started.wait(1.0))
        self.assertTrue(runtime.stop())

        statuses = runtime.drain_statuses()
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].reason, "awaiting_character_identity")


if __name__ == "__main__":
    unittest.main()
