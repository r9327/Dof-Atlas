from __future__ import annotations

import argparse
import json
from typing import Any

import tools.validate_guide_ultime_manual_transversals_v12 as v12

v9 = v12.v9
v9.EXPECTED_CHAPTERS["level_191_200"] = ("level_191_200_v5.json", 33)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transversal V13 du Guide Ultime manuel jusqu'au niveau200 avec checkpoints V5.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    manifest = v9.load(v9.MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    resolved = v9.resolve_canonical(hard, canonical)

    checks = {
        "level_70_100": v12.v11.check_level70,
        "level_120_150": v12.check_level120_v7,
        "level_150_170": v12.v11.check_level150,
        "level_171_180": v12.v11.check_level171,
        "level_181_190": v12.v11.check_level181,
        "level_191_200": v12.check_level200,
    }
    for chapter_id, check in checks.items():
        if chapter_id in resolved:
            check(hard, resolved[chapter_id])

    v12.check_bonta100(hard, canonical)
    v9.validate_orders(hard, canonical)
    v12.check_order100(hard, canonical)
    v12.v11.check_temporal11(hard, canonical)
    v9.validate_ocre(hard, canonical)

    level200 = resolved.get("level_191_200")
    if level200:
        stages = [x for x in level200.get("stages", []) or [] if isinstance(x, dict)]
        missing_pause = [
            str(stage.get("id") or "")
            for stage in stages
            if not (isinstance(stage.get("pause_checkpoint"), dict) or (isinstance(stage.get("pause"), list) and stage.get("pause")))
        ]
        if missing_pause:
            hard.append({"code": "level200_pause_checkpoint_missing", "stages": missing_pause})

    if not args.skip_catalog:
        try:
            catalog = v9.catalog_names()
        except Exception as exc:
            hard.append({"code": "quest_catalog_load_failed", "error": repr(exc)})
        else:
            for chapter_id, payload in resolved.items():
                v9.validate_catalog(hard, catalog, chapter_id, payload)

    result = {
        "schema_version": 13,
        "status": "STRICT_PASS" if not hard else "STRICT_FAIL",
        "hard_error_count": len(hard),
        "hard_errors": hard,
        "canonical_chapters_checked": sorted(resolved),
        "catalog_skipped": bool(args.skip_catalog),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and hard:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
