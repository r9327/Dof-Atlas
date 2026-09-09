from __future__ import annotations

"""Compatibility lock for the current canonical Guide Ultime manifest.

The v15 validator remains the audited implementation. This thin layer updates only
contracts that moved in the canonical route after v15 was written, while retaining
all other v15 checks unchanged.
"""

from tools import validate_guide_ultime_manual_transversals_v15 as v15


_REPLACED_CHAPTER_FILES = {
    "level_191_200_v20.json": "level_191_200_v22.json",
    "level_200_plus_v9.json": "level_200_plus_v11.json",
}

v15.EXPECTED_CHAPTERS = tuple(
    (chapter_id, _REPLACED_CHAPTER_FILES.get(filename, filename), stage_count)
    for chapter_id, filename, stage_count in v15.EXPECTED_CHAPTERS
)

_original_validate_orders = v15._validate_orders
_original_validate_key_causality = v15._validate_key_causality


def _validate_orders(hard, canonical):
    """Accept the current explicit alias for hidden unselected order routes."""
    local_errors = []
    _original_validate_orders(local_errors, canonical)
    for error in local_errors:
        if error.get("code") == "order_payload_policy_invalid":
            policy = error.get("policy") if isinstance(error.get("policy"), dict) else {}
            hidden = policy.get("unselected_hidden") is True or policy.get("unselected_routes_hidden") is True
            if policy.get("exactly_one") is True and hidden:
                continue
        hard.append(error)


def _success_values(stage):
    raw = stage.get("successes")
    rows = raw if isinstance(raw, list) else [raw] if raw else []
    return [value.strip() for value in rows if isinstance(value, str) and value.strip()]


def _need_successes(hard, by, stage_id, wanted):
    stage = v15._need_stage(hard, by, stage_id)
    if stage is None:
        return
    missing = sorted(set(wanted) - set(_success_values(stage)))
    if missing:
        v15._error(hard, "required_successes_missing", stage=stage_id, missing=missing)


def _validate_key_causality(hard, resolved):
    """Track current quest moves and preserve success-vs-quest semantics."""
    local_errors = []
    _original_validate_key_causality(local_errors, resolved)
    for error in local_errors:
        if error.get("code") == "required_quests_missing" and error.get("stage") == "L100-15":
            missing = [name for name in error.get("missing", []) if name != "À la croisée des mondes"]
            if missing:
                hard.append({**error, "missing": missing})
            continue
        if error.get("code") == "required_quests_missing" and error.get("stage") == "L200-ENUT-CLOSE":
            missing = [name for name in error.get("missing", []) if name != "Le roi et moi"]
            if missing:
                hard.append({**error, "missing": missing})
            continue
        hard.append(error)

    _, level100 = v15._stage_index(resolved.get("level_100_120", {}))
    v15._need_quests(hard, level100, "L100-00", {"À la croisée des mondes"})

    _, level200 = v15._stage_index(resolved.get("level_191_200", {}))
    _need_successes(hard, level200, "L200-ENUT-CLOSE", {"Le roi et moi"})


v15._validate_orders = _validate_orders
v15._validate_key_causality = _validate_key_causality


if __name__ == "__main__":
    raise SystemExit(v15.main())