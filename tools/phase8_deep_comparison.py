from __future__ import annotations

"""Compare *identical* deep first-use paths on two exact Git SHAs.

Crucial distinction: navigable tab != first rendered Quest/Guide/Success
detail. A single run is an observation, not a statistical performance proof.
"""
import math
import re
from typing import Any

SHA = re.compile(r"^[0-9a-f]{40}$")
COLD_DETAIL = ("deep_quest_detail_ms", "deep_guide_detail_ms",
               "deep_achievement_detail_ms")
FIRST_OPENS = ("quests_open_ms", "achievements_open_ms", "guide_open_ms",
               "craft_open_ms", "equipment_open_ms")
TIMED = ("preload_completed_from_constructor_ms", *FIRST_OPENS,
         *COLD_DETAIL, "deep_first_content_total_ms", "total_first_path_ms")
KEYS = ("quest_id", "guide_id", "achievement_id")


def _milliseconds(report: dict[str, Any], name: str) -> float:
    value = report.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Missing numeric performance metric: {name}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"Invalid performance metric: {name}")
    return result


def compare_deep_first_use(before: dict[str, Any], after: dict[str, Any],
                           *, base_sha: str, candidate_sha: str) -> dict[str, Any]:
    """Return verified accounting, never turn a missing deep action into PASS."""
    if (not isinstance(base_sha, str) or not SHA.fullmatch(base_sha)
            or not isinstance(candidate_sha, str) or not SHA.fullmatch(candidate_sha)
            or base_sha == candidate_sha):
        raise ValueError("Expected two distinct immutable Git candidate SHAs")
    if before.get("git_head") != base_sha or after.get("git_head") != candidate_sha:
        raise ValueError("Benchmark identity mismatch")
    b_deep = before.get("deep_first_content")
    a_deep = after.get("deep_first_content")
    if not isinstance(b_deep, dict) or not isinstance(a_deep, dict):
        raise ValueError("Deep first content evidence absent")
    if (b_deep.get("all_details_rendered") is not True
            or a_deep.get("all_details_rendered") is not True):
        raise ValueError("At least one real detail was not rendered")
    if any(b_deep.get(key) != a_deep.get(key) for key in KEYS):
        raise ValueError("Not the same Quest/Guide/Achievement detail fixture")
    values = {k: (_milliseconds(before, k), _milliseconds(after, k)) for k in TIMED}
    for label, item in (("base", before), ("candidate", after)):
        direct = sum(_milliseconds(item, k) for k in COLD_DETAIL)
        if abs(direct - _milliseconds(item, "deep_first_content_total_ms")) > 0.06:
            raise ValueError(f"{label} detail timing accounting is inconsistent")
        path = (sum(_milliseconds(item, k) for k in FIRST_OPENS)
                + _milliseconds(item, "preload_completed_from_constructor_ms")
                + direct)
        if abs(path - _milliseconds(item, "total_first_path_ms")) > 0.10:
            raise ValueError(f"{label} full-path timing accounting is inconsistent")
    delta = {k: round(v[1] - v[0], 2) for k, v in values.items()}
    gained_preload_ms = round(
        values["preload_completed_from_constructor_ms"][0]
        - values["preload_completed_from_constructor_ms"][1], 2
    )
    deep_deferral_ms = round(
        values["deep_first_content_total_ms"][1]
        - values["deep_first_content_total_ms"][0], 2
    )
    net_gain_ms = round(values["total_first_path_ms"][0] - values["total_first_path_ms"][1], 2)
    return {
        "schema_version": 1,
        "kind": "phase8_deep_first_use_comparison",
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "detail_ids": {key: a_deep[key] for key in KEYS},
        "before_after_ms": {
            key: {"before": values[key][0], "after": values[key][1]}
            for key in TIMED
        },
        "delta_after_minus_before_ms": delta,
        "preload_gain_ms": gained_preload_ms,
        "shifted_into_deep_details_ms": max(0.0, deep_deferral_ms),
        "net_full_first_use_gain_ms": net_gain_ms,
        "verdict": (
            "NET_REGRESSION" if net_gain_ms < -1_000
            else "NET_FASTER_WITH_DEFERRED_SHIFT" if net_gain_ms > 0 and deep_deferral_ms > 0
            else "NET_FASTER_WITHOUT_DEFERRED_SHIFT" if net_gain_ms > 0
            else "NEAR_EQUAL_OR_NOISY"
        ),
        "single_run_not_statistical_proof": True,
        "all_deep_details_rendered": True,
        "unmeasured": [
            "Other first-use workflows and long-session deferred callbacks",
            "Real Dofus network latency, Qt teardown and system CPU under load",
        ],
    }
