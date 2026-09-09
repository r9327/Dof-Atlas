from __future__ import annotations

import json
from pathlib import Path

from tools.analyze_startup import _elapsed_ms, build_report


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_build_report_merges_launcher_pyside_runtime_and_profile(tmp_path) -> None:
    start = _write(
        tmp_path / "start_log.txt",
        "\n".join(
            (
                "START",
                "LAUNCHER_START 01/09/2026 12:00:00,00",
                "startup preflight OK elapsed_ms=245.7",
                "PREFLIGHT_OK 01/09/2026 12:00:00,30",
                "APP_START 01/09/2026 12:00:00,50",
                "APP_START_SENT 01/09/2026 12:00:00,51",
            )
        ),
    )
    pyside = _write(
        tmp_path / "session_manager_pyside.log",
        "\n".join(
            (
                "[PYSIDE] 2026-09-01 12:00:02,000 - INFO - [main] start argv=[] cwd=C:\\Atlas",
                "[PYSIDE] 2026-09-01 12:00:02,250 - INFO - [main] splash shown size=420x200",
                "[PYSIDE] 2026-09-01 12:00:04,000 - INFO - [main] AtlasWindow created visible=False title='Dofus Atlas'",
                "[PYSIDE] 2026-09-01 12:00:04,050 - INFO - [main] AtlasWindow shown visible=True title='Dofus Atlas'",
            )
        ),
    )
    runtime = _write(
        tmp_path / "session_runtime.log",
        "[PYRUNTIME] 2026-09-01 12:00:05,500 - INFO - Runtime Python demarre.\n",
    )
    profile = tmp_path / "startup_profile.jsonl"
    profile.write_text(
        json.dumps(
            {
                "timestamp": "2026-09-01T12:00:04.200+02:00",
                "phase": "first_ui_tick",
                "total_ms": 2100.0,
                "marks": [
                    {"name": "home_banner_construct", "elapsed_ms": 100.0, "delta_ms": 100.0},
                    {"name": "ui_first_tick", "elapsed_ms": 2100.0, "delta_ms": 2000.0},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_report(start, pyside, runtime, profile)

    assert report.launcher_to_app_start_ms == 500.0
    assert report.preflight_ms == 245.7
    assert report.app_start_to_main_ms == 1500.0
    assert report.main_to_splash_ms == 250.0
    assert report.splash_to_window_created_ms == 1750.0
    assert report.window_created_to_shown_ms == 50.0
    assert report.app_start_to_first_ui_ms == 3700.0
    assert report.launcher_to_first_ui_ms == 4200.0
    assert report.main_to_runtime_ready_ms == 3500.0
    assert report.profile_total_ms == 2100.0
    assert report.profile_marks[-1] == ("ui_first_tick", 2100.0, 2000.0)


def test_elapsed_ms_handles_midnight_rollover() -> None:
    assert _elapsed_ms(23 * 3600 + 59 * 60 + 59.5, 0.25) == 750.0


def test_build_report_ignores_stale_runtime_ready_from_previous_launch(tmp_path) -> None:
    start = _write(tmp_path / "start_log.txt", "APP_START 01/09/2026 12:00:00,00\n")
    pyside = _write(
        tmp_path / "session_manager_pyside.log",
        "[PYSIDE] 2026-09-01 12:00:01,000 - INFO - [main] start argv=[] cwd=C:\\Atlas\n",
    )
    runtime = _write(
        tmp_path / "session_runtime.log",
        "[PYRUNTIME] 2026-09-01 11:30:00,000 - INFO - Runtime Python demarre.\n",
    )

    report = build_report(start, pyside, runtime, tmp_path / "missing_profile.jsonl")

    assert report.main_to_runtime_ready_ms is None


def test_build_report_tolerates_missing_and_corrupt_files(tmp_path) -> None:
    profile = tmp_path / "startup_profile.jsonl"
    profile.write_text("not-json\n", encoding="utf-8")

    report = build_report(
        tmp_path / "missing_start.txt",
        tmp_path / "missing_pyside.log",
        tmp_path / "missing_runtime.log",
        profile,
    )

    assert report.launcher_to_first_ui_ms is None
    assert report.app_start_to_main_ms is None
    assert report.profile_marks == ()
