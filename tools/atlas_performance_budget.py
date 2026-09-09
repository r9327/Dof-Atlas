from __future__ import annotations

from typing import Any


def evaluate_metric(value: float, budget: dict[str, Any]) -> dict[str, Any]:
    baseline = float(budget["baseline"])
    regression_limit = float(budget["regression_limit"])
    hard_limit = float(budget["hard_limit"])
    measured = float(value)
    if not baseline <= regression_limit <= hard_limit:
        raise ValueError("performance budget limits must satisfy baseline <= regression <= hard")
    if measured > hard_limit:
        status = "HARD_LIMIT_EXCEEDED"
    elif measured > regression_limit:
        status = "REGRESSION_LIMIT_EXCEEDED"
    else:
        status = "PASS"
    return {
        "status": status,
        "value": measured,
        "baseline": baseline,
        "regression_limit": regression_limit,
        "hard_limit": hard_limit,
    }
