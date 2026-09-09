from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
START_LOG = LOG_DIR / "start_log.txt"
PYSIDE_LOG = LOG_DIR / "session_manager_pyside.log"
RUNTIME_LOG = LOG_DIR / "session_runtime.log"
PROFILE_LOG = LOG_DIR / "startup_profile.jsonl"

_TIME_RE = re.compile(r"(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})(?:[,.](?P<fraction>\d+))?")
_PYSIDE_RE = re.compile(
    r"\[PYSIDE\]\s+(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2}(?:[,.]\d+)?)\s+-\s+\w+\s+-\s+(?P<message>.*)"
)
_RUNTIME_RE = re.compile(
    r"\[PYRUNTIME\]\s+(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2}(?:[,.]\d+)?)\s+-\s+\w+\s+-\s+(?P<message>.*)"
)
_MAX_STARTUP_PHASE_MS = 120_000.0


@dataclass(frozen=True)
class StartupReport:
    launcher_to_app_start_ms: float | None = None
    app_start_to_main_ms: float | None = None
    main_to_splash_ms: float | None = None
    splash_to_window_created_ms: float | None = None
    window_created_to_shown_ms: float | None = None
    app_start_to_first_ui_ms: float | None = None
    launcher_to_first_ui_ms: float | None = None
    main_to_runtime_ready_ms: float | None = None
    preflight_ms: float | None = None
    profile_total_ms: float | None = None
    profile_marks: tuple[tuple[str, float, float], ...] = ()


def _time_of_day_seconds(text: str) -> float | None:
    matches = list(_TIME_RE.finditer(str(text or "")))
    if not matches:
        return None
    match = matches[-1]
    fraction = match.group("fraction") or ""
    fraction_seconds = float(f"0.{fraction}") if fraction else 0.0
    return (
        int(match.group("hour")) * 3600.0
        + int(match.group("minute")) * 60.0
        + int(match.group("second"))
        + fraction_seconds
    )


def _elapsed_ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    delta = end - start
    if delta < 0.0:
        delta += 24.0 * 3600.0
    return round(delta * 1000.0, 1)


def _startup_elapsed_ms(start: float | None, end: float | None) -> float | None:
    elapsed = _elapsed_ms(start, end)
    if elapsed is None or elapsed > _MAX_STARTUP_PHASE_MS:
        return None
    return elapsed


def _last_prefixed_time(lines: list[str], prefix: str) -> float | None:
    for line in reversed(lines):
        if line.startswith(prefix):
            return _time_of_day_seconds(line)
    return None


def _last_preflight_ms(lines: list[str]) -> float | None:
    pattern = re.compile(r"startup preflight OK elapsed_ms=(\d+(?:\.\d+)?)")
    for line in reversed(lines):
        match = pattern.search(line)
        if match:
            return round(float(match.group(1)), 1)
    return None


def _pyside_markers(lines: list[str]) -> dict[str, float]:
    sessions: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for line in lines:
        match = _PYSIDE_RE.search(line)
        if not match:
            continue
        seconds = _time_of_day_seconds(match.group("time"))
        if seconds is None:
            continue
        message = match.group("message")
        if "[main] start " in message:
            current = {"main": seconds}
            sessions.append(current)
            continue
        if current is None:
            continue
        if "[main] splash shown" in message:
            current.setdefault("splash", seconds)
        elif "[main] AtlasWindow created" in message:
            current.setdefault("window_created", seconds)
        elif "[main] AtlasWindow shown" in message:
            current.setdefault("window_shown", seconds)
    return sessions[-1] if sessions else {}


def _runtime_ready_time(lines: list[str], main_started: float | None) -> float | None:
    candidates: list[float] = []
    for line in lines:
        match = _RUNTIME_RE.search(line)
        if not match or "Runtime Python demarre." not in match.group("message"):
            continue
        seconds = _time_of_day_seconds(match.group("time"))
        if seconds is not None:
            candidates.append(seconds)
    if main_started is None:
        return candidates[-1] if candidates else None
    for seconds in reversed(candidates):
        elapsed = _startup_elapsed_ms(main_started, seconds)
        if elapsed is not None:
            return seconds
    return None


def _latest_profile(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    latest: dict[str, object] = {}
    try:
        with path.open("r", encoding="utf-8") as stream:
            for raw in stream:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    latest = payload
    except OSError:
        return {}
    return latest


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def build_report(
    start_log: Path = START_LOG,
    pyside_log: Path = PYSIDE_LOG,
    runtime_log: Path = RUNTIME_LOG,
    profile_log: Path = PROFILE_LOG,
) -> StartupReport:
    start_lines = _read_lines(start_log)
    pyside_lines = _read_lines(pyside_log)
    runtime_lines = _read_lines(runtime_log)

    launcher_start = _last_prefixed_time(start_lines, "LAUNCHER_START ")
    app_start = _last_prefixed_time(start_lines, "APP_START ")
    shell = _pyside_markers(pyside_lines)
    runtime_ready = _runtime_ready_time(runtime_lines, shell.get("main"))
    profile = _latest_profile(profile_log)

    first_ui = _time_of_day_seconds(str(profile.get("timestamp") or ""))
    profile_marks: list[tuple[str, float, float]] = []
    for mark in profile.get("marks") or []:
        if not isinstance(mark, dict):
            continue
        try:
            profile_marks.append(
                (
                    str(mark.get("name") or ""),
                    float(mark.get("elapsed_ms") or 0.0),
                    float(mark.get("delta_ms") or 0.0),
                )
            )
        except (TypeError, ValueError):
            continue

    profile_total: float | None
    try:
        profile_total = round(float(profile["total_ms"]), 1)
    except (KeyError, TypeError, ValueError):
        profile_total = None

    return StartupReport(
        launcher_to_app_start_ms=_startup_elapsed_ms(launcher_start, app_start),
        app_start_to_main_ms=_startup_elapsed_ms(app_start, shell.get("main")),
        main_to_splash_ms=_startup_elapsed_ms(shell.get("main"), shell.get("splash")),
        splash_to_window_created_ms=_startup_elapsed_ms(shell.get("splash"), shell.get("window_created")),
        window_created_to_shown_ms=_startup_elapsed_ms(shell.get("window_created"), shell.get("window_shown")),
        app_start_to_first_ui_ms=_startup_elapsed_ms(app_start, first_ui),
        launcher_to_first_ui_ms=_startup_elapsed_ms(launcher_start, first_ui),
        main_to_runtime_ready_ms=_startup_elapsed_ms(shell.get("main"), runtime_ready),
        preflight_ms=_last_preflight_ms(start_lines),
        profile_total_ms=profile_total,
        profile_marks=tuple(profile_marks),
    )


def _format_ms(value: float | None) -> str:
    if value is None:
        return "n/d"
    if value >= 1000.0:
        return f"{value / 1000.0:.3f} s"
    return f"{value:.1f} ms"


def _print_report(report: StartupReport) -> None:
    rows = (
        ("Launcher -> envoi Python", report.launcher_to_app_start_ms),
        ("  dont preflight", report.preflight_ms),
        ("Python lance -> main()", report.app_start_to_main_ms),
        ("main() -> splash", report.main_to_splash_ms),
        ("splash -> AtlasWindow construit", report.splash_to_window_created_ms),
        ("AtlasWindow construit -> show()", report.window_created_to_shown_ms),
        ("Python lance -> premier tick UI", report.app_start_to_first_ui_ms),
        ("Launcher -> premier tick UI", report.launcher_to_first_ui_ms),
        ("main() -> runtime hooks prets", report.main_to_runtime_ready_ms),
    )
    print("\nDOFUS ATLAS - STARTUP REPORT")
    print("=" * 38)
    for label, value in rows:
        print(f"{label:<34} {_format_ms(value):>12}")

    if report.profile_marks:
        print("\nMarqueurs internes du profiler :")
        for name, elapsed, delta in report.profile_marks:
            print(f"  {name:<28} total={_format_ms(elapsed):>10}  +{_format_ms(delta)}")

    if report.launcher_to_first_ui_ms is None:
        print("\nProfil incomplet : lance Dofus_Atlas.bat une fois puis relance cet analyseur.")
    else:
        total = report.launcher_to_first_ui_ms
        if total >= 12000.0:
            verdict = "demarrage encore tres lent"
        elif total >= 8000.0:
            verdict = "demarrage encore lent"
        elif total >= 5000.0:
            verdict = "demarrage moyen"
        else:
            verdict = "demarrage rapide"
        print(f"\nVerdict premier affichage : {verdict} ({_format_ms(total)}).")


def main(argv: list[str] | None = None) -> int:
    _ = argv if argv is not None else sys.argv[1:]
    _print_report(build_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
