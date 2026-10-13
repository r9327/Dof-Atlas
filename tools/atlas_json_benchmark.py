"""Fair-ish opt-in Quest lookup comparison; never changes runtime or source data.

Compares the existing byte-offset reader with derived shards over the same
deterministic quest IDs. Both use warm file-system caches; initialization,
verification, and timed lookups are reported separately. Do not extrapolate
these figures to Qt process-tree RAM or first application launch.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.quest_source_index import QuestSources
from tools.atlas_json_shards import (
    ROOT, current_directory, read_by_id, verify,
)


def benchmark(
    source: Path, output_root: Path, *, sample_count: int = 64,
) -> dict:
    if not 1 <= sample_count <= 1000:
        raise ValueError("sample_count hors limites")
    source, output_root = Path(source).resolve(), Path(output_root).resolve()
    directory = current_directory(output_root)

    # Baseline source and derived snapshots must be identical before timing.
    started = time.perf_counter_ns()
    manifest = verify(
        source, directory, cache_root=output_root / "source_offsets"
    )
    verify_seconds = (time.perf_counter_ns() - started) / 1e9

    sources = QuestSources(output_root / "benchmark_source_offsets")
    try:
        started = time.perf_counter_ns()
        mapping = sources.mapping(source, "quests", required=True)
        keys = sorted(mapping, key=int)
        index_seconds = (time.perf_counter_ns() - started) / 1e9
        if not keys:
            raise ValueError("Catalogue Quêtes vide : aucun benchmark possible")
        length = min(sample_count, len(keys))
        offsets = (
            [0] if length == 1 else
            [i * (len(keys) - 1) // (length - 1) for i in range(length)]
        )
        selected = [keys[i] for i in offsets]

        started = time.perf_counter_ns()
        baseline = [mapping[key] for key in selected]
        source_seconds = (time.perf_counter_ns() - started) / 1e9
        mapping.close()

        started = time.perf_counter_ns()
        derived = [read_by_id(output_root, int(key)) for key in selected]
        shard_seconds = (time.perf_counter_ns() - started) / 1e9
        if baseline != derived:
            raise ValueError("Parité de consultation ID incorrecte")
    finally:
        sources.close()
    return {
        "schema_version": 1,
        "source_sha256": manifest["source_sha256"],
        "record_count": manifest["record_count"],
        "sample_count": len(selected),
        "shard_count": len(manifest["shards"]),
        "verify_seconds": round(verify_seconds, 6),
        "source_index_seconds": round(index_seconds, 6),
        "source_offset_lookup_seconds": round(source_seconds, 6),
        "derived_shard_lookup_seconds": round(shard_seconds, 6),
        "lookup_values_equal": True,
        "runtime_consumers_changed": False,
        "measurement_limits": [
            "Opt-in offline timing; does not measure Qt UI, first app launch, disk I/O or process-tree RSS",
            "Same deterministic IDs; both runs follow verification and may benefit from OS file-system cache",
            "Source index includes loading/building its offset dictionary; lookup durations exclude this step",
            "Shards parse all records within each accessed partition and verify its SHA-256",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comparer offsets Quêtes existants et shards expérimentaux"
    )
    parser.add_argument(
        "--source", type=Path,
        default=ROOT / "data/encyclopedia/quests/quests_enriched.json"
    )
    parser.add_argument(
        "--shards", type=Path,
        default=ROOT / ".cache/dofus_atlas/quests_shards"
    )
    parser.add_argument("--sample-count", type=int, default=64)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = benchmark(args.source, args.shards, sample_count=args.sample_count)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
