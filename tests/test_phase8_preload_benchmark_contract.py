from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "tools" / "benchmark_phase8_preload.py"


def test_preload_benchmark_wait_does_not_sample_memory_in_poll_loop() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    helper = source[
        source.index("def wait_until("),
        source.index("def page_loaded("),
    ]
    assert "memory_mb()" not in helper
    assert "poll_seconds" in helper
    assert "time.sleep(interval)" in helper


def test_functional_preload_uses_low_churn_poll_interval() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    measurement = source[
        source.index("preload_duration_ms"),
        source.index("preload_completed_from_constructor_ms"),
    ]
    assert "poll_seconds=0.02" in measurement
