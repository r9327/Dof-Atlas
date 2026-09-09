from __future__ import annotations

import argparse
import base64
import logging
import os
import socket
from time import monotonic
from typing import Iterable

from app.core.admin import current_process_is_admin
from app.network.capture_ipc import (
    CAPTURE_IPC_VERSION,
    CaptureIpcDisconnected,
    CaptureIpcError,
    FramedJsonConnection,
)
from app.network.transport import CapturedProtocolMessage, TransportSessionClosed
from app.network.npcap_capture import (
    NpcapCaptureError,
    NpcapUnavailableError,
    NpcapWindowsProtocolSource,
)
from app.network.windows_capture import WindowsRawProtocolSource


_MAX_CAPTURE_HANDLES = 32
_DIAGNOSTIC_INTERVAL_SECONDS = 1.0


def _preferred_capture_source(handles_provider, *, logger):
    try:
        return NpcapWindowsProtocolSource(handles_provider, logger=logger)
    except (NpcapUnavailableError, NpcapCaptureError, OSError):
        return WindowsRawProtocolSource(handles_provider, logger=logger)


def _safe_handles(values: object) -> tuple[int, ...]:
    if not isinstance(values, list):
        return ()
    handles: list[int] = []
    for raw_handle in values:
        try:
            handle = int(raw_handle)
        except (TypeError, ValueError, OverflowError):
            continue
        if handle > 0 and handle not in handles:
            handles.append(handle)
        if len(handles) >= _MAX_CAPTURE_HANDLES:
            break
    return tuple(handles)


def run_capture_helper(port: int, token: str) -> int:
    if os.name != "nt" or not current_process_is_admin():
        return 2
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15.0)
    try:
        sock.connect(("127.0.0.1", int(port)))
        sock.settimeout(None)
        connection = FramedJsonConnection(sock)
        connection.send(
            {
                "kind": "hello",
                "version": CAPTURE_IPC_VERSION,
                "token": str(token),
            }
        )
        initial = connection.receive(15.0)
        if initial is None or str(initial.get("kind") or "") != "handles":
            return 3
        current_handles = _safe_handles(initial.get("handles"))
        diagnostics_enabled = bool(initial.get("diagnostics"))

        def handles_provider() -> Iterable[int]:
            return current_handles

        helper_logger = logging.getLogger("DofusAtlasCaptureHelper")
        helper_logger.handlers[:] = [logging.NullHandler()]
        helper_logger.propagate = False
        source = _preferred_capture_source(handles_provider, logger=helper_logger)
        try:
            source.start()
        except NpcapCaptureError:
            source.stop()
            source = WindowsRawProtocolSource(handles_provider, logger=helper_logger)
            try:
                source.start()
            except Exception:
                connection.send({"kind": "error", "reason": "capture_helper_source_start_failed"})
                return 4
        except Exception:
            connection.send({"kind": "error", "reason": "capture_helper_source_start_failed"})
            return 4
        connection.send({"kind": "ready"})
        capture_active = True
        last_diagnostic: dict[str, int] | None = None
        next_diagnostic_at = 0.0
        try:
            while True:
                command = connection.receive(0.001 if capture_active else 0.05)
                if command is not None:
                    kind = str(command.get("kind") or "")
                    if kind == "stop":
                        return 0
                    if kind == "handles":
                        current_handles = _safe_handles(command.get("handles"))
                        diagnostics_enabled = bool(command.get("diagnostics"))
                    elif kind == "pause":
                        if capture_active:
                            source.stop()
                            capture_active = False
                        connection.send({"kind": "paused"})
                    elif kind == "resume":
                        if not capture_active:
                            source.start()
                            capture_active = True
                        connection.send({"kind": "resumed"})
                    else:
                        return 5
                item = source.read_item(0.05) if capture_active else None
                if isinstance(item, CapturedProtocolMessage):
                    connection.send(
                        {
                            "kind": "message",
                            "session_id": item.session_id,
                            "type_url": item.type_url,
                            "payload": base64.b64encode(item.payload).decode("ascii"),
                            "direction": item.direction,
                        }
                    )
                elif isinstance(item, TransportSessionClosed):
                    connection.send({"kind": "closed", "session_id": item.session_id})
                now = monotonic()
                if diagnostics_enabled and capture_active and now >= next_diagnostic_at:
                    diagnostic = source.diagnostic_snapshot()
                    if diagnostic != last_diagnostic:
                        connection.send({"kind": "diagnostic", **diagnostic})
                        last_diagnostic = diagnostic
                    next_diagnostic_at = now + _DIAGNOSTIC_INTERVAL_SECONDS
        except CaptureIpcDisconnected:
            return 0
        finally:
            if capture_active:
                source.stop()
    except (CaptureIpcError, OSError, ValueError):
        return 6
    finally:
        try:
            sock.close()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--token", required=True)
    args = parser.parse_args(argv)
    return run_capture_helper(args.port, args.token)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_capture_helper"]
