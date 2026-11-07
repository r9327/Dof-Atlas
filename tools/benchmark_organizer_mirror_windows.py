"""Isolated Windows desktop input stress probe for Organizer PR #325.

The fixtures are ordinary Tk windows, *not* DOFUS or Unity. This records
SendInput -> Tk event acknowledgment, never Unity render time. No user accounts,
credentials, game process or hook interception is involved. The production
DOFUS-only identity guard must refuse these fixtures.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from collections import defaultdict

COUNTS = (1, 2, 4, 6, 8)
GESTURES = ("left", "right", "double", "wheel", "key")
MAX_FAILURES = 20


def percentiles(samples: list[float]) -> dict[str, float | int] | None:
    """Nearest-rank percentiles; failed/unacknowledged actions are excluded."""
    if not samples:
        return None
    ordered = sorted(samples)
    return {
        "count": len(ordered),
        **{
            f"p{p}_ms": round(ordered[math.ceil(len(ordered) * p / 100) - 1], 3)
            for p in (50, 95, 99)
        },
    }


def working_set_mb() -> float | None:
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("page_faults", wintypes.DWORD),
            ("peak_working_set", ctypes.c_size_t),
            ("working_set", ctypes.c_size_t),
            ("peak_paged_pool", ctypes.c_size_t),
            ("paged_pool", ctypes.c_size_t),
            ("peak_nonpaged_pool", ctypes.c_size_t),
            ("nonpaged_pool", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        ]

    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        return None
    return round(counters.working_set / 1024**2, 3)


def run(expected_sha: str, iterations: int) -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Only a real Windows desktop can run this probe")
    actual_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, timeout=15,
    ).strip()
    if actual_sha != expected_sha:
        raise RuntimeError("SHA mismatch: refusing a stale benchmark")

    import tkinter as tk

    from app.input.input_state import SyntheticInputGuard
    from app.macros.input_tools import key_down, key_up
    from app.macros.mirror_plan import is_dofus_unity_process
    from app.windows.clicks import (
        current_cursor_pos, send_screen_click, send_screen_wheel, set_cursor_pos,
    )

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_int

    logger = logging.getLogger("atlas-stress-fixtures")
    logger.addHandler(logging.NullHandler())
    guard = SyntheticInputGuard(logger)
    root = tk.Tk()
    root.withdraw()
    windows = []
    counts = defaultdict(lambda: defaultdict(int))
    original_cursor = None
    report = {
        "schema_version": 1,
        "kind": "synthetic_native_windows_sendinput_stress",
        "candidate_sha": actual_sha,
        "environment": {
            "platform": sys.platform,
            "iterations_per_window_and_gesture": iterations,
            "requested_clients": list(COUNTS),
            "fixture": "Tk window / Win32 SendInput; NOT DOFUS Unity",
        },
        "render_unity": "NOT_RUN",
        "real_dofus_clients": "NOT_RUN",
        "input_hooks_e2e": "NOT_RUN",
        "results": {},
        "status": "NOT_RUN",
    }
    try:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        width = max(110, min(180, (screen_w - 40) // 4))
        height = max(90, min(155, (screen_h - 100) // 2))
        for i in range(8):
            win = tk.Toplevel(root)
            win.title(f"Atlas synthetic fixture {i + 1}")
            x = 10 + (i % 4) * width
            y = 10 + (i // 4) * height
            win.geometry(f"{width - 8}x{height - 8}+{x}+{y}")
            win.configure(background="#dce7fa")
            for sequence, gesture in (
                ("<ButtonRelease-1>", "left"),
                ("<ButtonRelease-3>", "right"),
                ("<MouseWheel>", "wheel"),
                ("<KeyRelease>", "key"),
            ):
                win.bind(
                    sequence,
                    lambda event, index=i, kind=gesture: counts[index].__setitem__(
                        kind, counts[index][kind] + 1
                    ),
                )
            windows.append(win)
        root.update()

        handles = [
            int(user32.GetAncestor(ctypes.c_void_p(win.winfo_id()), 2))
            for win in windows
        ]
        if len(set(handles)) != 8 or not all(handles):
            raise RuntimeError("Unable to establish eight distinct native HWND fixtures")
        # The app MUST NOT start accepting Tk windows as DOFUS Unity clients.
        if any(is_dofus_unity_process(handle) for handle in handles):
            raise RuntimeError("DOFUS identity guard accepted a synthetic fixture")
        report["identity_guard_rejects_all_8"] = True

        try:
            original_cursor = current_cursor_pos()
        except OSError:
            pass
        failures = []
        ack_total = 0
        attempts_total = 0
        cpu_start = time.process_time()
        wall_start = time.perf_counter()
        for roster_size in COUNTS:
            observed = []
            attempts = 0
            acknowledged = 0
            outcomes = defaultdict(int)
            # Every participant receives identical gesture types/iterations.
            # The 1-client case checks native input, not mirrored delivery.
            for _ in range(iterations):
                for index in range(roster_size):
                    win = windows[index]
                    hwnd = handles[index]
                    for gesture in GESTURES:
                        attempts += 1
                        attempts_total += 1
                        root.update()
                        win.lift()
                        win.focus_force()
                        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
                        root.update()
                        time.sleep(0.02)  # desktop compositor after foreground change
                        if int(user32.GetForegroundWindow() or 0) != hwnd:
                            outcomes["focus_refused"] += 1
                            if len(failures) < MAX_FAILURES:
                                failures.append({
                                    "clients": roster_size, "gesture": gesture,
                                    "reason": "foreground_not_fixture",
                                })
                            continue

                        before = counts[index]["left" if gesture == "double" else gesture]
                        expected = before + (2 if gesture == "double" else 1)
                        cx = win.winfo_rootx() + win.winfo_width() // 2
                        cy = win.winfo_rooty() + win.winfo_height() // 2
                        started = time.perf_counter()
                        try:
                            if gesture in ("left", "right", "double"):
                                sent = send_screen_click(
                                    cx, cy,
                                    "left" if gesture == "double" else gesture,
                                    2 if gesture == "double" else 1,
                                    0, 30 if gesture == "double" else 0,
                                    0, 0, guard, logger,
                                    should_stop=lambda: int(user32.GetForegroundWindow() or 0) != hwnd,
                                )
                            elif gesture == "wheel":
                                set_cursor_pos(cx, cy)
                                sent = send_screen_wheel(120)
                            else:
                                key_down(0x41)  # Only the harmless letter A; no account input.
                                try:
                                    sent = True
                                finally:
                                    key_up(0x41)
                        except (OSError, RuntimeError, ValueError):
                            sent = False
                        if not sent:
                            outcomes["send_refused"] += 1
                            if len(failures) < MAX_FAILURES:
                                failures.append({
                                    "clients": roster_size, "gesture": gesture,
                                    "reason": "sendinput_refused",
                                })
                            continue

                        deadline = time.perf_counter() + 0.16
                        while counts[index]["left" if gesture == "double" else gesture] < expected:
                            root.update()
                            if time.perf_counter() >= deadline:
                                break
                            time.sleep(0.002)
                        if counts[index]["left" if gesture == "double" else gesture] >= expected:
                            observed.append((time.perf_counter() - started) * 1000)
                            acknowledged += 1
                            ack_total += 1
                        else:
                            outcomes["unacknowledged"] += 1
                            if len(failures) < MAX_FAILURES:
                                failures.append({
                                    "clients": roster_size, "gesture": gesture,
                                    "reason": "no_tk_callback",
                                })
            report["results"][str(roster_size)] = {
                "attempts": attempts,
                "acknowledged": acknowledged,
                "not_delivered": attempts - acknowledged,
                "failure_reasons": dict(outcomes),
                "sendinput_to_tk_ack_ms": percentiles(observed),
            }
        wall_s = max(time.perf_counter() - wall_start, 0.001)
        report["total_attempts"] = attempts_total
        report["total_acknowledged"] = ack_total
        report["failure_examples"] = failures
        report["wall_seconds"] = round(wall_s, 3)
        report["cpu_percent_one_core"] = round(
            100 * (time.process_time() - cpu_start) / wall_s, 2,
        )
        report["working_set_mb"] = working_set_mb()
        report["status"] = (
            "UNAVAILABLE_INTERACTIVE_DESKTOP" if not ack_total else
            "PASS" if ack_total == attempts_total else "FAIL"
        )
    finally:
        if original_cursor is not None:
            try:
                set_cursor_pos(*original_cursor)
            except OSError:
                pass
        try:
            for win in windows:
                win.destroy()
            root.destroy()
        except tk.TclError:
            pass
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--iterations", type=int, default=6)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if not 1 <= args.iterations <= 30:
        p.error("--iterations must be in 1..30")
    if len(args.expected_sha) != 40 or any(c not in "0123456789abcdef" for c in args.expected_sha):
        p.error("expected_sha must be an exact lowercase commit SHA")
    try:
        result = run(args.expected_sha, args.iterations)
    except Exception as exc:
        result = {
            "schema_version": 1, "kind": "synthetic_native_windows_sendinput_stress",
            "candidate_sha": args.expected_sha, "status": "NOT_RUN",
            "reason": f"{type(exc).__name__}: {exc}",
            "render_unity": "NOT_RUN", "real_dofus_clients": "NOT_RUN",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if result["status"] in ("FAIL", "NOT_RUN") else 0


if __name__ == "__main__":
    raise SystemExit(main())
