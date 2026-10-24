from __future__ import annotations

"""Fail-closed 5% measurement margin for the Phase 8 memory benchmark.

Targets remain the optimization objective; observations strictly above +5%
remain failures. This function never certifies an application or waives checks.
"""

from math import isfinite

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
