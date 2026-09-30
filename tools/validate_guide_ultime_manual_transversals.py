from __future__ import annotations

"""Canonical Guide Ultime transversal validator.

This unversioned module owns the current manifest compatibility contract. The
large audited v15 implementation remains an internal dependency until its rules
are migrated, but no orchestrator or CI entry point should target a versioned
wrapper.
"""

from tools import validate_guide_ultime_manual_transversals_v15 as _impl

_REPLACED_CHAPTER_FILES = {
    "level_191_200_v20.json": "level_191_200_v22.json",
    "level_200_plus_v9.json": "level_200_plus_v11.json",
}

_impl.EXPECTED_CHAPTERS = tuple(
    (chapter_id, _REPLACED_CHAPTER_FILES.get(filename, filename), stage_count)
    for chapter_id, filename, stage_count in _impl.EXPECTED_CHAPTERS
)

_original_validate_orders = _impl._validate_orders
_original_validate_key_causality = _impl._validate_key_causality


def _validate_orders(hard, canonical):
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
    stage = _impl._need_stage(hard, by, stage_id)
    if stage is None:
        return
    missing = sorted(set(wanted) - set(_success_values(stage)))
    if missing:
        _impl._error(hard, "required_successes_missing", stage=stage_id, missing=missing)


def _validate_key_causality(hard, resolved):
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

    _, level100 = _impl._stage_index(resolved.get("level_100_120", {}))
    _impl._need_quests(hard, level100, "L100-00", {"À la croisée des mondes"})

    _, level200 = _impl._stage_index(resolved.get("level_191_200", {}))
    _need_successes(hard, level200, "L200-ENUT-CLOSE", {"Le roi et moi"})


_impl._validate_orders = _validate_orders
_impl._validate_key_causality = _validate_key_causality


def audit(*, skip_catalog: bool = False):
    return _impl.audit(skip_catalog=skip_catalog)


def main() -> int:
    return _impl.main()


if __name__ == "__main__":
    raise SystemExit(main())
