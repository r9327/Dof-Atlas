from __future__ import annotations

"""Fail-closed 5% measurement margin for the Phase 8 memory benchmark.

Targets remain the optimization objective; observations strictly above +5%
remain failures. This function never certifies an application or waives checks.
"""

from math import isfinite
from collections.abc import Mapping

MARGIN = 0.05


def hard_limit(target_mb: float) -> float:
    target = float(target_mb)
    if not isfinite(target) or target <= 0:
        raise ValueError("Memory target must be finite and positive")
    return target * (1.0 + MARGIN)


def classify(measured_mb: float, target_mb: float) -> str:
    """PASS within target, WARNING within +5%, FAIL beyond or invalid."""
    measured = float(measured_mb)
    if not isfinite(measured) or measured < 0:
        return "FAIL"
    limit = hard_limit(target_mb)
    if measured > limit:
        return "FAIL"
    if measured > target_mb:
        return "WARNING"
    return "PASS"


def require_peak_tree_rss(metrics: Mapping[str, object], *, preload_mb: float) -> float:
    """Reject absent, invalid or contradictory peak RSS evidence.

    A missing peak cannot be coerced to 0 MB: it would silently satisfy the
    220 MB budget despite the measurement never being collected.
    """
    if not isinstance(metrics, Mapping) or "peak_tree_rss_mb" not in metrics:
        raise ValueError("Missing peak process-tree RSS evidence")
    raw = metrics["peak_tree_rss_mb"]
    if type(raw) not in (int, float):
        raise ValueError("Invalid peak process-tree RSS observation")
    peak = float(raw)
    if not isfinite(peak) or peak <= 0:
        raise ValueError("Peak process-tree RSS must be finite and positive")
    if not isfinite(preload_mb) or preload_mb <= 0:
        raise ValueError("Invalid preload RSS reference")
    if peak < preload_mb:
        raise ValueError("Peak process-tree RSS is below the observed preload RSS")
    return peak
