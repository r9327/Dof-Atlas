from __future__ import annotations

import argparse
import gc
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]


def _quiet_call(function, *args):
    stream = StringIO()
    with redirect_stdout(stream):
        result = function(*args)
    return result


def _relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(Path(path).resolve()).replace("\\", "/")


def _guide_domain() -> dict[str, object]:
    from app.modules.encyclopedia.providers import dofus_item_provider as item_provider
    from app.modules.encyclopedia.providers import memory_bound_guide_provider as guide_provider
    from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
        MANUAL_RUNTIME_COMPACT_CACHE,
    )

    if guide_provider._guide_compact_cache_valid(
        guide_provider.GUIDE_COMPACT_CACHE,
        guides_dir=guide_provider.GUIDES_DIR,
    ):
        try:
            with guide_provider.GUIDE_COMPACT_CACHE.open("r", encoding="utf-8") as stream:
                guide_count = sum(1 for line in stream if '"kind":"guide"' in line)
        except OSError:
            guide_count = 0
    else:
        code = int(
            _quiet_call(
                guide_provider._build_compact_guide_cache,
                guide_provider.GUIDE_COMPACT_CACHE,
            )
            or 0
        )
        if code != 0:
            raise RuntimeError(f"Guide compact cache build failed with code {code}")
        with guide_provider.GUIDE_COMPACT_CACHE.open("r", encoding="utf-8") as stream:
            guide_count = sum(1 for line in stream if '"kind":"guide"' in line)

    manual_count = int(
        guide_provider._build_manual_runtime_compact_cache_in_worker()
        or 0
    )
    gc.collect()

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
        cached_items = item_provider._read_guide_items_index(
            data_dir=item_provider.RAW_QUEST_DATA_DIR,
            path=item_provider.GUIDE_ITEMS_INDEX,
        )
    if cached_items is None:
        raise RuntimeError("Guide item index unavailable after build")
    item_count = len(cached_items)

    return {
        "domain": "guide",
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
    _signature, cache_path = details._cache_identity(
        details.qc.RAW_QUEST_DATA_DIR,
        details._CACHE_ROOT,
    )
    return {
        "domain": "quest",
        "quest_count": max(0, count),
        "cache_files": [_relative(cache_path)],
    }


def _success_domain() -> dict[str, object]:
    from app.modules.encyclopedia.providers import (
        memory_bound_achievement_provider as achievement_provider,
    )
    from app.modules.encyclopedia.services import achievement_index_warmup

    cache_path = achievement_provider.ACHIEVEMENT_COMPACT_CACHE
    index_path = achievement_provider._achievement_compact_index_path(cache_path)

    if not achievement_provider._achievement_compact_cache_valid(
        cache_path,
        data_dir=achievement_provider.RAW_QUEST_DATA_DIR,
    ):
        code = int(
            _quiet_call(
                achievement_provider._build_compact_cache,
                cache_path,
            )
            or 0
        )
        if code != 0:
            raise RuntimeError(f"Success compact cache build failed with code {code}")

    try:
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Success compact index unavailable after build") from exc

    achievement_count = max(0, int(index_payload.get("achievement_count") or 0))
    retained_count = max(0, int(index_payload.get("retained_count") or 0))
    name_count = int(achievement_index_warmup.write_achievement_name_index() or 0)
    gc.collect()

    return {
        "domain": "success",
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
