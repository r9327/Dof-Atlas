from __future__ import annotations

import base64
import json
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.network import elevated_capture
from app.network import capture_helper
from app.network.capture_ipc import CaptureIpcDisconnected, FramedJsonConnection
from app.network.elevated_capture import (
    ElevatedWindowsProtocolSource,
    NetworkCaptureStartError,
)
from app.network.transport import CapturedProtocolMessage


class FakeProcess:
    def __init__(self, stopped: threading.Event) -> None:
        self.stopped = stopped
        self.terminated = False
        self.closed = False

    def wait(self, timeout: float) -> bool:
        return self.stopped.wait(timeout)

    def terminate(self) -> None:
        self.terminated = True
        self.stopped.set()

    def close(self) -> None:
        self.closed = True


class FakeHelperLauncher:
    def __init__(self) -> None:
        self.initial_handles: tuple[int, ...] = ()
        self.updated_handles: tuple[int, ...] = ()
        self.stopped = threading.Event()
        self.handles_updated = threading.Event()
        self.process = FakeProcess(self.stopped)
        self.thread: threading.Thread | None = None

    def __call__(self, port: int, token: str, working_directory):
        del working_directory

        def worker() -> None:
            sock = socket.create_connection(("127.0.0.1", port), timeout=2.0)
            connection = FramedJsonConnection(sock)
            try:
                connection.send({"kind": "hello", "version": 1, "token": token})
                initial = connection.receive(2.0)
                self.initial_handles = tuple(initial.get("handles") or ())
                connection.send({"kind": "ready"})
                connection.send(
                    {
                        "kind": "message",
                        "session_id": "tcp:44:1",
                        "type_url": "type.ankama.com/idr",
                        "payload": base64.b64encode(b"journal").decode("ascii"),
                    }
                )
                while True:
                    command = connection.receive(2.0)
                    if command is None:
                        continue
                    if command.get("kind") == "stop":
                        return
                    if command.get("kind") == "handles":
                        self.updated_handles = tuple(command.get("handles") or ())
                        self.handles_updated.set()
                    elif command.get("kind") == "pause":
                        connection.send({"kind": "paused"})
                    elif command.get("kind") == "resume":
                        connection.send({"kind": "resumed"})
            except CaptureIpcDisconnected:
                # Windows may reset the loopback socket after the parent has
                # already completed deterministic helper cleanup. That is the
                # expected terminal state for this fake helper, not a leaked
                # background-thread failure.
                return
            finally:
                connection.close()
                self.stopped.set()

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()
        return self.process


class NetworkElevatedCaptureTests(unittest.TestCase):
    def test_capture_helper_import_does_not_hydrate_application_stacks(self) -> None:
        root = Path(__file__).resolve().parents[1]
        modules = (
            "app.network.application_coordinator",
            "app.network.bootstrap",
            "app.network.calibration_bootstrap",
            "app.network.controller",
            "app.network.calibration_controller",
            "app.network.progress_bridge",
            "app.modules.encyclopedia.services.quest_progress_service",
            "app.modules.encyclopedia.services.serialized_achievement_progress_service",
            "PySide6",
            "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineWidgets",
        )
        code = (
            "import json, sys; "
            "import app.network.capture_helper; "
            f"modules={modules!r}; "
            "print(json.dumps({name: name in sys.modules for name in modules}))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout.strip())
        self.assertEqual(payload, {module_name: False for module_name in modules})

    def test_windows_launcher_uses_runas_and_retains_native_process_handle(self) -> None:
        class FakeKernel32:
            def __init__(self) -> None:
                self.terminated = False
                self.closed = False

            def WaitForSingleObject(self, handle, milliseconds) -> int:
                self.wait_handle = handle
                self.wait_milliseconds = milliseconds
                return elevated_capture._WAIT_OBJECT_0

            def TerminateProcess(self, handle, exit_code) -> int:
                self.terminated = True
                self.terminate_handle = handle
                self.exit_code = exit_code
                return 1

            def CloseHandle(self, handle) -> int:
                self.closed = True
                self.close_handle = handle
                return 1

            def GetLastError(self) -> int:
                return 0

        class FakeShell32:
            def ShellExecuteExW(self, pointer) -> int:
                self.info = pointer._obj
                self.info.hProcess = 321
                return 1

        kernel = FakeKernel32()
        shell = FakeShell32()
        windll = type("FakeWindll", (), {"kernel32": kernel, "shell32": shell})()
        fake_os = type("FakeOs", (), {"name": "nt"})()
        with (
            patch.object(elevated_capture, "os", fake_os),
            patch.object(elevated_capture.ctypes, "windll", windll, create=True),
        ):
            process = elevated_capture.launch_elevated_capture_helper(
                4444,
                "secret-token",
                Path.cwd(),
            )
            self.assertEqual(shell.info.lpVerb, "runas")
            self.assertIn("app.network.capture_helper", shell.info.lpParameters)
            self.assertIn("secret-token", shell.info.lpParameters)
            self.assertTrue(process.wait(0.25))
            process.terminate()
            process.close()

        self.assertTrue(kernel.terminated)
        self.assertTrue(kernel.closed)

    def test_windows_launcher_reports_uac_cancellation(self) -> None:
        class FakeKernel32:
            @staticmethod
            def GetLastError() -> int:
                return elevated_capture._ERROR_CANCELLED

        class FakeShell32:
            @staticmethod
            def ShellExecuteExW(pointer) -> int:
                del pointer
                return 0

        windll = type(
            "FakeWindll",
            (),
            {"kernel32": FakeKernel32(), "shell32": FakeShell32()},
        )()
        fake_os = type("FakeOs", (), {"name": "nt"})()
        with (
            patch.object(elevated_capture, "os", fake_os),
            patch.object(elevated_capture.ctypes, "windll", windll, create=True),
            self.assertRaises(NetworkCaptureStartError) as raised,
        ):
            elevated_capture.launch_elevated_capture_helper(
                4444,
                "secret-token",
                Path.cwd(),
            )

        self.assertEqual(raised.exception.reason, "capture_elevation_cancelled")

    def test_elevated_helper_has_no_ui_or_persistent_write_surface(self) -> None:
        helper = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "network"
            / "capture_helper.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("PySide6", helper)
        self.assertNotIn("QtWebEngine", helper)
        self.assertNotIn("write_text", helper)
        self.assertNotIn("open(", helper)

    def test_authenticated_helper_roundtrip_and_dynamic_handles(self) -> None:
        handles = [11]
        launcher = FakeHelperLauncher()
        source = ElevatedWindowsProtocolSource(
            lambda: tuple(handles),
            helper_launcher=launcher,
            startup_timeout=2.0,
        )

        source.start()
        self.assertEqual(launcher.initial_handles, (11,))
        item = source.read_item(1.0)
        self.assertEqual(item.session_id, "tcp:44:1")
        self.assertEqual(item.type_url, "type.ankama.com/idr")
        self.assertEqual(item.payload, b"journal")

        handles[:] = [22]
        self.assertIsNone(source.read_item(0.05))
        self.assertTrue(launcher.handles_updated.wait(1.0))
        self.assertEqual(launcher.updated_handles, (22,))

        source.stop()
        self.assertTrue(launcher.stopped.wait(1.0))
        self.assertFalse(launcher.process.terminated)
        self.assertTrue(launcher.process.closed)

    def test_diagnostic_frame_is_logged_and_not_returned_as_transport(self) -> None:
        class FakeConnection:
            def __init__(self) -> None:
                self.frames = [
                    {
                        "kind": "diagnostic",
                        "npcap_backend_active": 1,
                        "capture_socket_count": 1,
                        "tracked_flow_count": 2,
                        "raw_packet_count": 3,
                        "parsed_tcp_packet_count": 3,
                        "matched_packet_count": 2,
                        "matched_payload_bytes": 40,
                        "reassembled_payload_bytes": 30,
                        "framed_message_count": 0,
                        "server_to_client_matched_packet_count": 1,
                        "server_to_client_matched_payload_bytes": 25,
                        "server_to_client_reassembled_payload_bytes": 20,
                        "server_to_client_framed_message_count": 0,
                        "client_to_server_matched_packet_count": 1,
                        "client_to_server_matched_payload_bytes": 15,
                        "client_to_server_reassembled_payload_bytes": 10,
                        "client_to_server_framed_message_count": 0,
                    }
                ]

            def receive(self, timeout: float):
                del timeout
                return self.frames.pop(0) if self.frames else None

            def send(self, frame) -> None:
                del frame

        source = ElevatedWindowsProtocolSource(lambda: ())
        source._connection = FakeConnection()  # type: ignore[assignment]
        source._connected = True
        source._started = True

        with patch("app.network.elevated_capture.network_debug_log") as debug_log:
            self.assertIsNone(source.read_item(0.01))

        debug_log.assert_called_once()
        self.assertEqual(debug_log.call_args.args[1], "[NETWORK][CAPTURE_RAW]")
        self.assertEqual(debug_log.call_args.kwargs["npcap_backend_active"], 1)
        self.assertEqual(debug_log.call_args.kwargs["raw_packet_count"], 3)
        self.assertEqual(
            debug_log.call_args.kwargs["server_to_client_matched_payload_bytes"],
            25,
        )
        self.assertEqual(
            debug_log.call_args.kwargs["client_to_server_matched_payload_bytes"],
            15,
        )

    def test_helper_runs_only_raw_capture_and_obeys_parent_stop(self) -> None:
        class FakeRawSource:
            instance = None

            def __init__(self, handles_provider, *, logger) -> None:
                self.handles_provider = handles_provider
                self.logger = logger
                self.started = False
                self.stopped = False
                self.items = [
                    CapturedProtocolMessage(
                        "tcp:55:1",
                        "type.ankama.com/idr",
                        b"journal",
                    )
                ]
                FakeRawSource.instance = self

            def start(self) -> None:
                self.started = True

            def stop(self) -> None:
                self.stopped = True

            def read_item(self, timeout: float):
                if self.items:
                    return self.items.pop(0)
                time.sleep(min(timeout, 0.001))
                return None

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        result: list[int] = []
        token = "test-token"

        def run() -> None:
            result.append(capture_helper.run_capture_helper(port, token))

        with (
            patch.object(capture_helper.os, "name", "nt"),
            patch.object(capture_helper, "current_process_is_admin", return_value=True),
            patch.object(
                capture_helper,
                "NpcapWindowsProtocolSource",
                side_effect=capture_helper.NpcapUnavailableError("test fallback"),
            ),
            patch.object(capture_helper, "WindowsRawProtocolSource", FakeRawSource),
        ):
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            sock, _peer = server.accept()
            connection = FramedJsonConnection(sock)
            hello = connection.receive(1.0)
            self.assertEqual(hello["token"], token)
            connection.send({"kind": "handles", "handles": [55]})
            self.assertEqual(connection.receive(1.0), {"kind": "ready"})
            message = connection.receive(1.0)
            self.assertEqual(message["kind"], "message")
            self.assertEqual(
                base64.b64decode(message["payload"]),
                b"journal",
            )
            connection.send({"kind": "stop"})
            thread.join(1.0)
            self.assertFalse(thread.is_alive())

        connection.close()
        server.close()
        self.assertEqual(result, [0])
        self.assertTrue(FakeRawSource.instance.started)
        self.assertTrue(FakeRawSource.instance.stopped)

    def test_framing_preserves_partial_reads_between_timeouts(self) -> None:
        left, right = socket.socketpair()
        receiver = FramedJsonConnection(right)
        payload = b'{"kind":"ready"}'
        frame = len(payload).to_bytes(4, "big") + payload
        try:
            left.sendall(frame[:7])
            self.assertIsNone(receiver.receive(0.01))
            left.sendall(frame[7:])
            self.assertEqual(receiver.receive(1.0), {"kind": "ready"})
        finally:
            left.close()
            receiver.close()

    def test_invalid_handle_values_never_reach_helper(self) -> None:
        launcher = FakeHelperLauncher()
        source = ElevatedWindowsProtocolSource(
            lambda: (0, -4, "bad", 31, 31),
            helper_launcher=launcher,
            startup_timeout=2.0,
        )
        source.start()
        try:
            self.assertEqual(launcher.initial_handles, (31,))
        finally:
            source.stop()

    def test_persistent_helper_is_reused_across_calibration_runtime_handoff(self) -> None:
        launcher = FakeHelperLauncher()
        launch_count = 0

        def launch_once(port, token, working_directory):
            nonlocal launch_count
            launch_count += 1
            return launcher(port, token, working_directory)

        source = ElevatedWindowsProtocolSource(
            lambda: (11,),
            helper_launcher=launch_once,
            startup_timeout=2.0,
            keep_helper_alive=True,
        )
        source.start()
        source.stop()
        self.assertFalse(source.is_started)
        self.assertFalse(launcher.stopped.is_set())
        source.start()
        self.assertEqual(launch_count, 1)
        self.assertIsNone(source.read_item(0.05))
        source.close()
        self.assertTrue(launcher.stopped.wait(1.0))


if __name__ == "__main__":
    unittest.main()
