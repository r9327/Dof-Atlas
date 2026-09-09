from __future__ import annotations

import json
import select
import socket
import threading
from time import monotonic
from typing import Any


CAPTURE_IPC_VERSION = 1
MAX_CAPTURE_FRAME_BYTES = 16 * 1024 * 1024


class CaptureIpcError(RuntimeError):
    pass


class CaptureIpcDisconnected(CaptureIpcError):
    pass


class FramedJsonConnection:
    """Bounded JSON framing over one already-connected local TCP socket."""

    def __init__(self, sock: socket.socket) -> None:
        self.socket = sock
        self._buffer = bytearray()
        self._send_lock = threading.Lock()
        self._receive_lock = threading.Lock()

    def send(self, payload: dict[str, Any]) -> None:
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CaptureIpcError("capture_ipc_invalid_payload") from exc
        if not encoded or len(encoded) > MAX_CAPTURE_FRAME_BYTES:
            raise CaptureIpcError("capture_ipc_frame_too_large")
        frame = len(encoded).to_bytes(4, "big") + encoded
        with self._send_lock:
            try:
                self.socket.sendall(frame)
            except OSError as exc:
                raise CaptureIpcDisconnected("capture_ipc_disconnected") from exc

    def receive(self, timeout: float) -> dict[str, Any] | None:
        with self._receive_lock:
            deadline = monotonic() + max(0.0, float(timeout))
            while True:
                decoded = self._take_frame()
                if decoded is not None:
                    return decoded
                remaining = max(0.0, deadline - monotonic())
                if remaining <= 0.0:
                    return None
                try:
                    readable, _, _ = select.select((self.socket,), (), (), remaining)
                except (OSError, ValueError) as exc:
                    raise CaptureIpcDisconnected("capture_ipc_disconnected") from exc
                if not readable:
                    return None
                try:
                    chunk = self.socket.recv(65536)
                except OSError as exc:
                    raise CaptureIpcDisconnected("capture_ipc_disconnected") from exc
                if not chunk:
                    raise CaptureIpcDisconnected("capture_ipc_disconnected")
                self._buffer.extend(chunk)
                if len(self._buffer) > MAX_CAPTURE_FRAME_BYTES + 4:
                    raise CaptureIpcError("capture_ipc_frame_too_large")

    def close(self) -> None:
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.socket.close()
        except OSError:
            pass

    def _take_frame(self) -> dict[str, Any] | None:
        if len(self._buffer) < 4:
            return None
        length = int.from_bytes(self._buffer[:4], "big")
        if length <= 0 or length > MAX_CAPTURE_FRAME_BYTES:
            raise CaptureIpcError("capture_ipc_frame_too_large")
        frame_end = 4 + length
        if len(self._buffer) < frame_end:
            return None
        encoded = bytes(self._buffer[4:frame_end])
        del self._buffer[:frame_end]
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CaptureIpcError("capture_ipc_invalid_json") from exc
        if not isinstance(payload, dict):
            raise CaptureIpcError("capture_ipc_invalid_payload")
        return payload


__all__ = [
    "CAPTURE_IPC_VERSION",
    "CaptureIpcDisconnected",
    "CaptureIpcError",
    "FramedJsonConnection",
    "MAX_CAPTURE_FRAME_BYTES",
]
