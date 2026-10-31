from __future__ import annotations

import argparse
import gc
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]


def _quiet_call(function, *args):
    # These builders can print an unbounded number of lines while handling
    # tens of thousands of Dofus records. Capturing discarded output in
    # StringIO retains that entire text during the largest RAM peak.
    with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink):
        return function(*args)


def _relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(Path(path).resolve()).replace("\\", "/")


def _count_valid_compact_guides(path: Path) -> int:
    """Reject header-only/truncated JSONL rather than permanently reusing it."""
    count = 0
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict) or row.get("kind") not in {
                    "meta", "guide", "entity_index",
                }:
                    return 0
                if row["kind"] == "guide":
                    if not isinstance(row.get("value"), dict):
                        return 0
                    count += 1
    except (OSError, UnicodeError, TypeError, ValueError):
        return 0
    return count


def _guide_domain() -> dict[str, object]:
    from app.modules.encyclopedia.providers import memory_bound_guide_provider as guide_provider

    timings: dict[str, float] = {}
    guide_started = perf_counter()
    from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
        MANUAL_RUNTIME_COMPACT_CACHE,
    )

    guide_count = 0
    if guide_provider._guide_compact_cache_valid(
        guide_provider.GUIDE_COMPACT_CACHE,
        guides_dir=guide_provider.GUIDES_DIR,
    ):
        guide_count = _count_valid_compact_guides(guide_provider.GUIDE_COMPACT_CACHE)
    if guide_count <= 0:
        code = int(
            _quiet_call(
                guide_provider._build_compact_guide_cache,
                guide_provider.GUIDE_COMPACT_CACHE,
            )
            or 0
        )
        if code != 0:
            raise RuntimeError(f"Guide compact cache build failed with code {code}")
        guide_count = _count_valid_compact_guides(guide_provider.GUIDE_COMPACT_CACHE)
        if guide_count <= 0:
            raise RuntimeError("Guide compact cache remains empty or corrupt after build")

    timings["catalogue"] = round((perf_counter() - guide_started) * 1000.0, 2)

    manual_started = perf_counter()
    manual_count = int(
        guide_provider._build_manual_runtime_compact_cache_in_worker()
        or 0
    )
    timings["manual_route"] = round((perf_counter() - manual_started) * 1000.0, 2)
    gc.collect()

    items_started = perf_counter()

    # Import the item stack only after the Guide graph is released so the fused
    # worker saves process startup without stacking both heavy heaps.
    from app.modules.encyclopedia.providers import dofus_item_provider as item_provider

    cached_items = item_provider._read_guide_items_index(
        data_dir=item_provider.RAW_QUEST_DATA_DIR,
        path=item_provider.GUIDE_ITEMS_INDEX,
    )
    if cached_items is None:
        code = int(
            _quiet_call(
                item_provider._build_guide_items_index,
                item_provider.GUIDE_ITEMS_INDEX,
            )
            or 0
        )
        if code != 0:
            raise RuntimeError(f"Guide item index build failed with code {code}")
        try:
            built_payload = json.loads(
                item_provider.GUIDE_ITEMS_INDEX.read_text(encoding="utf-8")
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Guide item index unavailable after build") from exc
        built_items = built_payload.get("items") if isinstance(built_payload, dict) else None
        if not isinstance(built_items, dict):
            raise RuntimeError("Guide item index unavailable after build")
        item_count = len(built_items)
    else:
        item_count = len(cached_items)
    timings["items"] = round((perf_counter() - items_started) * 1000.0, 2)

    return {
        "domain": "guide",
        "timings_ms": timings,
        "tasks": {
            "guide": {
                "guide_count": int(guide_count),
                "manual_card_count": int(manual_count),
                "path": str(guide_provider.GUIDE_COMPACT_CACHE),
            },
            "guide_items": {
                "item_count": int(item_count),
                "path": str(item_provider.GUIDE_ITEMS_INDEX),
            },
        },
        "cache_files": [
            _relative(guide_provider.GUIDE_COMPACT_CACHE),
            _relative(item_provider.GUIDE_ITEMS_INDEX),
            _relative(MANUAL_RUNTIME_COMPACT_CACHE),
        ],
    }


def _quest_domain() -> dict[str, object]:
    from app import quest_catalog_details as details

    count = int(details.ensure_lazy_catalog_cache() or 0)
    detail_indexes: list[Path] = []
    detail_source_index_count = int(
        details.ensure_detail_source_offsets(indexed_paths=detail_indexes) or 0
    )
    _signature, cache_path = details._cache_identity(
        details.qc.RAW_QUEST_DATA_DIR,
        details._CACHE_ROOT,
    )
    return {
        "domain": "quest",
        "quest_count": max(0, count),
        "detail_source_index_count": max(0, detail_source_index_count),
        "detail_index_artifact_count": len(detail_indexes),
        # The first file is the Quest catalogue; the rest are immutable
        # source-offset indexes used by the first rich Quest detail. Their
        # absence must invalidate warmup instead of rebuilding on the UI path.
        "cache_files": [_relative(cache_path), *(_relative(path) for path in detail_indexes)],
    }


def _read_compact_success_counts(index_path: Path, schema: int) -> tuple[int, int] | None:
    """A sidecar with a valid filename but broken contents is not reusable."""
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        return None
    total = payload.get("achievement_count")
    retained = payload.get("retained_count")
    retained_ids = payload.get("retained_ids")
    offsets = payload.get("offsets")
    if (
        payload["schema_version"] != schema
        or type(total) is not int or type(retained) is not int
        or not (0 < retained <= total)
        or not isinstance(retained_ids, list) or len(retained_ids) != retained
        or not all(type(item) is int for item in retained_ids)
        or not isinstance(offsets, dict) or len(offsets) != retained
    ):
        return None
    return total, retained


def _success_domain() -> dict[str, object]:
    from app.modules.encyclopedia.providers import (
        memory_bound_achievement_provider as achievement_provider,
    )
    from app.modules.encyclopedia.services import achievement_index_warmup

    timings: dict[str, float] = {}
    compact_started = perf_counter()
    cache_path = achievement_provider.ACHIEVEMENT_COMPACT_CACHE
    index_path = achievement_provider._achievement_compact_index_path(cache_path)

    index_counts = None
    metadata_valid = achievement_provider._achievement_compact_cache_valid(
        cache_path,
        data_dir=achievement_provider.RAW_QUEST_DATA_DIR,
    )
    if metadata_valid:
        index_counts = _read_compact_success_counts(
            index_path, achievement_provider._ACHIEVEMENT_COMPACT_SCHEMA,
        )
    if index_counts is None:
        # Bypass the constructor's metadata-only early return if the JSONL
        # header is fine but the offsets sidecar is broken. The canonical
        # writer still owns the lock, rebuild and atomic publications.
        build_args = (cache_path, True) if metadata_valid else (cache_path,)
        code = int(
            _quiet_call(
                achievement_provider._build_compact_cache,
                *build_args,
            )
            or 0
        )
        if code != 0:
            raise RuntimeError(f"Success compact cache build failed with code {code}")
        index_counts = _read_compact_success_counts(
            index_path, achievement_provider._ACHIEVEMENT_COMPACT_SCHEMA,
        )
        if index_counts is None:
            raise RuntimeError("Success compact index missing or invalid after build")

    achievement_count, retained_count = index_counts
    timings["catalogue"] = round((perf_counter() - compact_started) * 1000.0, 2)

    names_started = perf_counter()
    name_count = int(achievement_index_warmup.write_achievement_name_index() or 0)
    timings["names"] = round((perf_counter() - names_started) * 1000.0, 2)
    gc.collect()

    return {
        "domain": "success",
        "timings_ms": timings,
        "tasks": {
            "success": {
                "achievement_count": achievement_count,
                "retained_count": retained_count,
                "path": str(cache_path),
            },
            "success_names": {
                "warmed_source_count": 0,
                "achievement_name_count": name_count,
            },
        },
        "cache_files": [
            _relative(cache_path),
            _relative(index_path),
            _relative(achievement_index_warmup._ACHIEVEMENT_NAMES_FILE),
        ],
    }


_DOMAIN_RUNNERS = {
    "guide": _guide_domain,
    "quest": _quest_domain,
    "success": _success_domain,
}


def run_domain(domain: str) -> dict[str, object]:
    name = str(domain or "").strip().casefold()
    runner = _DOMAIN_RUNNERS.get(name)
    if runner is None:
        raise ValueError(f"Unknown startup cache domain: {domain!r}")
    started = perf_counter()
    payload = dict(runner())
    payload["elapsed_ms"] = round((perf_counter() - started) * 1000.0, 2)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dofus Atlas disposable cache-domain worker")
    parser.add_argument("--domain", choices=tuple(_DOMAIN_RUNNERS), required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = run_domain(args.domain)
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
