from __future__ import annotations

import base64
import logging
import unittest
from unittest.mock import patch

from app.network.elevated_capture import (
    ElevatedWindowsProtocolSource,
    NetworkCaptureStartError,
)


class _FakeConnection:
    def __init__(self, frames: list[dict[str, object]]) -> None:
        self.frames = list(frames)
        self.sent: list[dict[str, object]] = []
        self.closed = False

    def send(self, frame: dict[str, object]) -> None:
        self.sent.append(dict(frame))

    def receive(self, _timeout: float) -> dict[str, object] | None:
        if not self.frames:
            return None
        return self.frames.pop(0)

    def close(self) -> None:
        self.closed = True


def _message(type_url: str, payload: bytes, *, session_id: str = "tcp:4242:1") -> dict[str, object]:
    return {
        "kind": "message",
        "session_id": session_id,
        "type_url": type_url,
        "payload": base64.b64encode(payload).decode("ascii"),
    }


def _connected_source(connection: _FakeConnection) -> ElevatedWindowsProtocolSource:
    source = ElevatedWindowsProtocolSource(
        lambda: (),
        logger=logging.getLogger("test.network.capture.control"),
        keep_helper_alive=True,
    )
    source._connection = connection
    source._connected = True
    source._started = True
    return source


class ElevatedCaptureControlBufferTests(unittest.TestCase):
    def test_stop_resume_discards_control_race_messages_instead_of_replaying_them(self) -> None:
        connection = _FakeConnection(
            [
                _message("type.ankama.com/kvi", b"\x08\x01"),
                _message("type.ankama.com/kva", b"\x08\x02"),
                _message("type.ankama.com/idr", b"\x08\x03"),
                {"kind": "paused"},
                {"kind": "resumed"},
            ]
        )
        source = _connected_source(connection)

        source.stop()
        self.assertFalse(source.is_started)
        self.assertEqual(source._pending_frames, [])
        self.assertIsNone(source.read_item(0.0))

        source.start()
        self.assertTrue(source.is_started)
        self.assertIsNone(source.read_item(0.0))
        self.assertEqual(source._pending_frames, [])
        self.assertEqual(
            [str(frame.get("kind") or "") for frame in connection.sent],
            ["pause", "handles", "resume"],
        )

    def test_session_closed_frame_is_discarded_at_pause_handoff(self) -> None:
        connection = _FakeConnection(
            [
                {"kind": "closed", "session_id": "tcp:4242:9"},
                {"kind": "paused"},
                {"kind": "resumed"},
            ]
        )
        source = _connected_source(connection)

        source.stop()
        self.assertEqual(source._pending_frames, [])

        source.start()
        self.assertIsNone(source.read_item(0.0))

    def test_close_after_pause_has_no_stale_control_race_frames(self) -> None:
        connection = _FakeConnection(
            [
                _message("type.ankama.com/idr", b"\x08\x2a"),
                {"kind": "paused"},
            ]
        )
        source = _connected_source(connection)

        source.stop()
        self.assertEqual(source._pending_frames, [])

        source.close()

        self.assertEqual(source._pending_frames, [])
        self.assertTrue(connection.closed)
        self.assertEqual(str(connection.sent[-1].get("kind") or ""), "stop")

    def test_control_buffer_overflow_fails_closed_instead_of_evicting_old_frames(self) -> None:
        connection = _FakeConnection(
            [
                _message("type.ankama.com/kvi", b"\x01"),
                _message("type.ankama.com/kva", b"\x02"),
                _message("type.ankama.com/idr", b"\x03"),
                {"kind": "paused"},
            ]
        )
        source = _connected_source(connection)

        with patch("app.network.elevated_capture._MAX_CONTROL_RACE_FRAMES", 2):
            with self.assertRaises(NetworkCaptureStartError) as raised:
                source._wait_for_control_frame(
                    connection,
                    expected_kind="paused",
                    timeout=1.0,
                )

        self.assertEqual(raised.exception.reason, "capture_helper_control_buffer_overflow")
        self.assertEqual(
            [str(frame.get("type_url") or "") for frame in source._pending_frames],
            ["type.ankama.com/kvi", "type.ankama.com/kva"],
        )


if __name__ == "__main__":
    unittest.main()
