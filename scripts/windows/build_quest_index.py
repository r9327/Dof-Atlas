"""Build the 1,976-Quest summary index once on CI, before any Guide details.

The release contains no quest walkthrough cache and no user progress.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(*, output: Path, source_sha: str) -> dict[str, object]:
    from app import quest_catalog_details as details
    from app.quest_index_prebuilt import publish_quest_index, verify_quest_index

    count = details.ensure_lazy_catalog_cache()
    if count < 1900:
        raise RuntimeError(f"Incomplete Quest catalogue: {count}")
    _signature, source = details._cache_identity(
        details.qc.RAW_QUEST_DATA_DIR, details._CACHE_ROOT,
    )
    result = publish_quest_index(source, output, source_sha=source_sha)
    if verify_quest_index(root=output) != count:
        raise RuntimeError("Portable Quest index failed real source verification")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build portable Quest catalog summary index")
    parser.add_argument("--output", type=Path, default=Path("data/bootstrap"))
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build(output=args.output, source_sha=args.source_sha), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
