from __future__ import annotations

import json

from app.startup_timing import StartupTimeline


def _clock(values: list[float]):
    iterator = iter(values)
    return lambda: next(iterator)


def test_startup_timeline_records_first_occurrence_and_deltas(tmp_path) -> None:
    timeline = StartupTimeline(
        enabled=True,
        output_path=tmp_path / "startup.jsonl",
        clock=_clock([10.0, 10.125, 10.500, 10.900]),
    )

    timeline.mark("imports_ready")
    timeline.mark("imports_ready")
    timeline.mark("first_paint")

    snapshot = timeline.snapshot("paint")
    assert snapshot["total_ms"] == 500.0
    assert snapshot["phase"] == "paint"
    assert snapshot["marks"] == [
        {"name": "imports_ready", "elapsed_ms": 125.0, "delta_ms": 125.0},
        {"name": "first_paint", "elapsed_ms": 500.0, "delta_ms": 375.0},
    ]


def test_startup_timeline_uses_interpreter_baseline(tmp_path) -> None:
    timeline = StartupTimeline(
        enabled=True,
        output_path=tmp_path / "startup.jsonl",
        clock=_clock([20.0, 20.250]),
        started_at=19.500,
        launcher_started_at="2026-09-01 10:00:00.00",
    )

    timeline.mark("imports_ready")
    snapshot = timeline.snapshot("imports")

    assert snapshot["total_ms"] == 750.0
    assert snapshot["marks"] == [
        {"name": "imports_ready", "elapsed_ms": 750.0, "delta_ms": 750.0},
    ]
    assert snapshot["launcher_started_at"] == "2026-09-01 10:00:00.00"


def test_future_interpreter_baseline_falls_back_to_current_clock(tmp_path) -> None:
    timeline = StartupTimeline(
        enabled=True,
        output_path=tmp_path / "startup.jsonl",
        clock=_clock([5.0, 5.125]),
        started_at=50.0,
    )

    timeline.mark("ready")
    assert timeline.snapshot("ready")["total_ms"] == 125.0


def test_startup_timeline_flushes_one_json_line(tmp_path) -> None:
    output = tmp_path / "nested" / "startup.jsonl"
    timeline = StartupTimeline(
        enabled=True,
        output_path=output,
        clock=_clock([1.0, 1.250]),
    )
    timeline.mark("ready")
    timeline.flush("runtime_ready")

    rows = output.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["phase"] == "runtime_ready"
    assert payload["total_ms"] == 250.0
    assert payload["marks"][0]["name"] == "ready"


def test_disabled_startup_timeline_has_no_disk_side_effect(tmp_path) -> None:
    output = tmp_path / "startup.jsonl"
    timeline = StartupTimeline(
        enabled=False,
        output_path=output,
        clock=_clock([3.0]),
    )

    timeline.mark("ignored")
    timeline.flush("ignored")

    assert not output.exists()
    assert timeline.snapshot("ignored")["marks"] == []