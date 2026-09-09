from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import hmac
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
from time import monotonic
from typing import Any, Callable, Iterable, Protocol

from app.core.logger import get_runtime_logger
from app.network.capture_ipc import (
    CAPTURE_IPC_VERSION,
    CaptureIpcDisconnected,
    CaptureIpcError,
    FramedJsonConnection,
)
from app.network.diagnostics import network_debug_enabled, network_debug_log
from app.network.transport import (
    CapturedProtocolMessage,
    ProtocolTransportItem,
    TransportSessionClosed,
)


_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_HIDE = 0
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_ERROR_CANCELLED = 1223
_MAX_CAPTURE_HANDLES = 32
_MAX_CONTROL_RACE_FRAMES = 4096


class NetworkCaptureStartError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "capture_helper_start_failed")
        super().__init__(self.reason)


class ElevatedHelperProcess(Protocol):
    def wait(self, timeout: float) -> bool:
        ...

    def terminate(self) -> None:
        ...

    def close(self) -> None:
        ...


class _ShellExecuteInfoW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("fMask", ctypes.wintypes.ULONG),
        ("hwnd", ctypes.wintypes.HWND),
        ("lpVerb", ctypes.wintypes.LPCWSTR),
        ("lpFile", ctypes.wintypes.LPCWSTR),
        ("lpParameters", ctypes.wintypes.LPCWSTR),
        ("lpDirectory", ctypes.wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.wintypes.LPCWSTR),
        ("hkeyClass", ctypes.wintypes.HKEY),
        ("dwHotKey", ctypes.wintypes.DWORD),
        ("hIcon", ctypes.wintypes.HANDLE),
        ("hProcess", ctypes.wintypes.HANDLE),
    ]


class WindowsElevatedHelperProcess:
    def __init__(self, process_handle: int) -> None:
        self._handle = int(process_handle)
        self._lock = threading.Lock()

    def wait(self, timeout: float) -> bool:
        with self._lock:
            handle = self._handle
        if not handle:
            return True
        milliseconds = max(0, min(int(max(0.0, float(timeout)) * 1000), 0xFFFFFFFE))
        native_handle = ctypes.wintypes.HANDLE(handle)
        result = int(
            ctypes.windll.kernel32.WaitForSingleObject(native_handle, milliseconds)
        )
        if result == _WAIT_OBJECT_0:
            return True
        if result == _WAIT_TIMEOUT:
            return False
        return False

    def terminate(self) -> None:
        with self._lock:
            handle = self._handle
        if handle:
            ctypes.windll.kernel32.TerminateProcess(ctypes.wintypes.HANDLE(handle), 1)

    def close(self) -> None:
        with self._lock:
            handle = self._handle
            self._handle = 0
        if handle:
            ctypes.windll.kernel32.CloseHandle(ctypes.wintypes.HANDLE(handle))


def launch_elevated_capture_helper(
    port: int,
    token: str,
    working_directory: Path,
) -> ElevatedHelperProcess:
    if os.name != "nt":
        raise NetworkCaptureStartError("capture_windows_only")
    parameters = subprocess.list2cmdline(
        (
            "-B",
            "-m",
            "app.network.capture_helper",
            "--port",
            str(int(port)),
            "--token",
            str(token),
        )
    )
    info = _ShellExecuteInfoW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = str(Path(sys.executable).resolve())
    info.lpParameters = parameters
    info.lpDirectory = str(Path(working_directory).resolve())
    info.nShow = _SW_HIDE
    if not bool(ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info))):
        error = int(ctypes.windll.kernel32.GetLastError())
        reason = "capture_elevation_cancelled" if error == _ERROR_CANCELLED else "capture_helper_launch_failed"
        raise NetworkCaptureStartError(reason)
    if not info.hProcess:
        raise NetworkCaptureStartError("capture_helper_launch_failed")
    return WindowsElevatedHelperProcess(int(info.hProcess))


class ElevatedWindowsProtocolSource:
    """Run only raw packet capture in a short-lived elevated helper process."""

    def __init__(
        self,
        window_handles_provider: Callable[[], Iterable[int]],
        *,
        logger=None,
        helper_launcher: Callable[[int, str, Path], ElevatedHelperProcess] | None = None,
        startup_timeout: float = 25.0,
        keep_helper_alive: bool = False,
    ) -> None:
        self.window_handles_provider = window_handles_provider
        self.logger = logger or get_runtime_logger()
        self.helper_launcher = helper_launcher or launch_elevated_capture_helper
        self.startup_timeout = max(1.0, float(startup_timeout))
        self.keep_helper_alive = bool(keep_helper_alive)
        self.start_failure_reason = ""
        self._state_lock = threading.RLock()
        self._server: socket.socket | None = None
        self._connection: FramedJsonConnection | None = None
        self._process: ElevatedHelperProcess | None = None
        self._last_handles: tuple[int, ...] = ()
        self._pending_frames: list[dict[str, Any]] = []
        self._connected = False
        self._started = False

    @property
    def is_started(self) -> bool:
        with self._state_lock:
            return self._started

    def start(self) -> None:
        with self._state_lock:
            if self._started:
                return
            if self._connected and self._connection is not None:
                try:
                    handles = self._current_handles()
                    self._connection.send(self._handles_frame(handles))
                    self._connection.send({"kind": "resume"})
                    self._wait_for_control_frame(
                        self._connection,
                        expected_kind="resumed",
                        timeout=self.startup_timeout,
                    )
                except Exception as exc:
                    reason = str(
                        getattr(exc, "reason", "") or "capture_helper_resume_failed"
                    )
                    self.start_failure_reason = reason
                    self.close()
                    if isinstance(exc, NetworkCaptureStartError):
                        raise
                    raise NetworkCaptureStartError(reason) from exc
                self._last_handles = handles
                self._started = True
                return
            self.start_failure_reason = ""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        server.bind(("127.0.0.1", 0))
        server.listen(4)
        port = int(server.getsockname()[1])
        token = secrets.token_urlsafe(48)
        process: ElevatedHelperProcess | None = None
        connection: FramedJsonConnection | None = None
        try:
            process = self.helper_launcher(port, token, Path(__file__).resolve().parents[2])
            connection = self._accept_authenticated(server, token)
            handles = self._current_handles()
            connection.send(self._handles_frame(handles))
            ready = connection.receive(self.startup_timeout)
            if ready is None:
                raise NetworkCaptureStartError("capture_helper_timeout")
            if str(ready.get("kind") or "") == "error":
                raise NetworkCaptureStartError(str(ready.get("reason") or "capture_helper_start_failed"))
            if str(ready.get("kind") or "") != "ready":
                raise NetworkCaptureStartError("capture_helper_protocol_error")
            with self._state_lock:
                self._server = server
                self._connection = connection
                self._process = process
                self._last_handles = handles
                self._connected = True
                self._started = True
            server.close()
            with self._state_lock:
                self._server = None
        except Exception as exc:
            reason = str(getattr(exc, "reason", "") or "capture_helper_start_failed")
            self.start_failure_reason = reason
            try:
                server.close()
            except OSError:
                pass
            if connection is not None:
                connection.close()
            if process is not None:
                self._finish_process(process)
            if isinstance(exc, NetworkCaptureStartError):
                raise
            raise NetworkCaptureStartError(reason) from exc

    def stop(self) -> None:
        with self._state_lock:
            if self.keep_helper_alive and self._connected:
                if not self._started:
                    return
                connection = self._connection
                self._started = False
                if connection is not None:
                    try:
                        connection.send({"kind": "pause"})
                        self._wait_for_control_frame(
                            connection,
                            expected_kind="paused",
                            timeout=2.0,
                        )
                        discarded_count = len(self._pending_frames)
                        self._pending_frames.clear()
                        if discarded_count:
                            self.logger.warning(
                                "Capture pause boundary discarded %s buffered transport frames; "
                                "outgoing session data is not replayed into the next runtime.", discarded_count,
                            )
                            network_debug_log(
                                self.logger,
                                "[NETWORK][CAPTURE_CONTROL]",
                                action="discard_on_pause_handoff",
                                buffered_count=discarded_count,
                            )
                    except (CaptureIpcError, NetworkCaptureStartError):
                        self.close()
                return
        self.close()

    def close(self) -> None:
        with self._state_lock:
            connection = self._connection
            process = self._process
            server = self._server
            buffered_count = len(self._pending_frames)
            self._connection = None
            self._process = None
            self._server = None
            self._last_handles = ()
            self._pending_frames.clear()
            self._connected = False
            self._started = False
        if buffered_count:
            self.logger.warning("Capture close discarded %s buffered transport frames.", buffered_count)
            network_debug_log(
                self.logger,
                "[NETWORK][CAPTURE_CONTROL]",
                action="discard_on_close",
                buffered_count=buffered_count,
            )
        if connection is not None:
            try:
                connection.send({"kind": "stop"})
            except CaptureIpcError:
                pass
            connection.close()
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        if process is not None:
            self._finish_process(process)

    def read_item(self, timeout: float) -> ProtocolTransportItem | None:
        with self._state_lock:
            connection = self._connection
            started = self._started
            if not started or connection is None:
                return None
            frame = self._pending_frames.pop(0) if self._pending_frames else None
        self._publish_handles(connection)
        deadline = monotonic() + max(0.0, float(timeout))
        while True:
            if frame is None:
                try:
                    frame = connection.receive(max(0.0, deadline - monotonic()))
                except CaptureIpcDisconnected:
                    self.close()
                    raise CaptureIpcDisconnected("capture_helper_disconnected")
            if frame is None:
                return None
            if str(frame.get("kind") or "") == "diagnostic":
                self._log_capture_diagnostic(frame)
                frame = None
                continue
            return self._transport_item_from_frame(frame)

    @staticmethod
    def _transport_item_from_frame(frame: dict[str, Any]) -> ProtocolTransportItem:
        kind = str(frame.get("kind") or "")
        if kind == "message":
            try:
                payload = base64.b64decode(str(frame.get("payload") or ""), validate=True)
            except (ValueError, TypeError) as exc:
                raise RuntimeError("capture_helper_invalid_payload") from exc
            direction = str(frame.get("direction") or "server_to_client")
            if direction not in {"server_to_client", "client_to_server"}:
                raise RuntimeError("capture_helper_invalid_direction")
            return CapturedProtocolMessage(
                session_id=str(frame.get("session_id") or ""),
                type_url=str(frame.get("type_url") or ""),
                payload=payload,
                direction=direction,
            )
        if kind == "closed":
            return TransportSessionClosed(session_id=str(frame.get("session_id") or ""))
        if kind == "error":
            raise RuntimeError(str(frame.get("reason") or "capture_helper_error"))
        raise RuntimeError("capture_helper_protocol_error")

    def _accept_authenticated(
        self,
        server: socket.socket,
        token: str,
    ) -> FramedJsonConnection:
        deadline = monotonic() + self.startup_timeout
        while True:
            remaining = max(0.0, deadline - monotonic())
            if remaining <= 0.0:
                raise NetworkCaptureStartError("capture_helper_timeout")
            server.settimeout(remaining)
            try:
                sock, peer = server.accept()
            except TimeoutError as exc:
                raise NetworkCaptureStartError("capture_helper_timeout") from exc
            if peer[0] != "127.0.0.1":
                sock.close()
                continue
            connection = FramedJsonConnection(sock)
            try:
                hello = connection.receive(min(5.0, remaining))
            except CaptureIpcError:
                connection.close()
                continue
            if (
                hello is not None
                and str(hello.get("kind") or "") == "hello"
                and hello.get("version") == CAPTURE_IPC_VERSION
                and hmac.compare_digest(str(hello.get("token") or ""), token)
            ):
                return connection
            connection.close()

    def _wait_for_control_frame(
        self,
        connection: FramedJsonConnection,
        *,
        expected_kind: str,
        timeout: float,
    ) -> None:
        deadline = monotonic() + max(0.0, float(timeout))
        buffered_during_wait = 0
        while True:
            remaining = max(0.0, deadline - monotonic())
            if remaining <= 0.0:
                raise NetworkCaptureStartError("capture_helper_timeout")
            frame = connection.receive(remaining)
            if frame is None:
                raise NetworkCaptureStartError("capture_helper_timeout")
            kind = str(frame.get("kind") or "")
            if kind == expected_kind:
                if buffered_during_wait:
                    with self._state_lock:
                        pending_count = len(self._pending_frames)
                    network_debug_log(
                        self.logger,
                        "[NETWORK][CAPTURE_CONTROL]",
                        action="buffered_before_control_ack",
                        expected_kind=expected_kind,
                        buffered_count=buffered_during_wait,
                        pending_count=pending_count,
                    )
                return
            if kind in {"message", "closed"}:
                self._buffer_control_race_frame(frame)
                buffered_during_wait += 1
                continue
            if kind == "diagnostic":
                self._log_capture_diagnostic(frame)
                continue
            if kind == "error":
                raise NetworkCaptureStartError(
                    str(frame.get("reason") or "capture_helper_error")
                )
            raise NetworkCaptureStartError("capture_helper_protocol_error")

    def _buffer_control_race_frame(self, frame: dict[str, Any]) -> None:
        with self._state_lock:
            if len(self._pending_frames) >= _MAX_CONTROL_RACE_FRAMES:
                self.logger.error(
                    "Elevated capture control buffer overflow (%d frames).",
                    _MAX_CONTROL_RACE_FRAMES,
                )
                raise NetworkCaptureStartError("capture_helper_control_buffer_overflow")
            self._pending_frames.append(frame)

    def _publish_handles(self, connection: FramedJsonConnection) -> None:
        handles = self._current_handles()
        with self._state_lock:
            if handles == self._last_handles:
                return
            self._last_handles = handles
        connection.send(self._handles_frame(handles))

    @staticmethod
    def _handles_frame(handles: tuple[int, ...]) -> dict[str, Any]:
        return {
            "kind": "handles",
            "handles": list(handles),
            "diagnostics": network_debug_enabled(),
        }

    def _log_capture_diagnostic(self, frame: dict[str, Any]) -> None:
        fields = {
            key: max(0, int(frame.get(key) or 0))
            for key in (
                "npcap_backend_active",
                "capture_socket_count",
                "tracked_flow_count",
                "raw_packet_count",
                "parsed_tcp_packet_count",
                "matched_packet_count",
                "matched_payload_bytes",
                "reassembled_payload_bytes",
                "framed_message_count",
                "server_to_client_matched_packet_count",
                "server_to_client_matched_payload_bytes",
                "server_to_client_reassembled_payload_bytes",
                "server_to_client_framed_message_count",
                "client_to_server_matched_packet_count",
                "client_to_server_matched_payload_bytes",
                "client_to_server_reassembled_payload_bytes",
                "client_to_server_framed_message_count",
            )
        }
        network_debug_log(self.logger, "[NETWORK][CAPTURE_RAW]", **fields)

    def _current_handles(self) -> tuple[int, ...]:
        handles: list[int] = []
        try:
            candidates = self.window_handles_provider() or ()
        except Exception:
            self.logger.exception("Elevated capture window handle provider failed.")
            candidates = ()
        for raw_handle in candidates:
            try:
                handle = int(raw_handle)
            except (TypeError, ValueError, OverflowError):
                continue
            if handle > 0 and handle not in handles:
                handles.append(handle)
            if len(handles) >= _MAX_CAPTURE_HANDLES:
                break
        return tuple(handles)

    @staticmethod
    def _finish_process(process: ElevatedHelperProcess) -> None:
        try:
            if not process.wait(2.0):
                process.terminate()
                process.wait(1.0)
        finally:
            process.close()


__all__ = [
    "ElevatedWindowsProtocolSource",
    "NetworkCaptureStartError",
    "WindowsElevatedHelperProcess",
    "launch_elevated_capture_helper",
]
