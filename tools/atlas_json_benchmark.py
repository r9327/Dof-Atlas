"""Fair-ish opt-in Quest lookup comparison; never changes runtime or source data.

Compares the existing byte-offset reader with derived shards over the same
deterministic quest IDs. Both use warm file-system caches; initialization,
verification, and timed lookups are reported separately. Do not extrapolate
these figures to Qt process-tree RAM or first application launch.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import statistics
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



def compare_json_parsers(
    source: Path, *, candidates: tuple[str, ...] = ("stdlib", "orjson", "msgspec"),
    repeats: int = 3, max_bytes: int = 128 * 1024 * 1024,
) -> dict:
    """Explicit offline parser trial on identical bytes; never affects Atlas runtime.

    Imports of optional packages happen only when this comparison is requested.
    The source is read once and shared by every candidate. Cold startup, RSS,
    Qt lifecycle, offset indexes and streaming are explicitly out of scope.
    """
    if not 1 <= repeats <= 7 or not 1 <= max_bytes <= 256 * 1024 * 1024:
        raise ValueError("Invalid bounded parser comparison budget")
    if not candidates or len(set(candidates)) != len(candidates) or any(
        name not in {"stdlib", "orjson", "msgspec"} for name in candidates
    ):
        raise ValueError("Unsupported or duplicate parser candidate")
    path = Path(source).resolve(strict=True)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError("Parser source missing, linked or exceeds size budget")
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError("Parser source changed during read")
    baseline = json.loads(raw)
    reports = []
    for name in candidates:
        if name == "stdlib":
            loads = json.loads
        else:
            try:
                loads = importlib.import_module(name).loads
            except (ImportError, AttributeError, OSError):
                reports.append({"name": name, "status": "NOT_AVAILABLE",
                                "executed": False})
                continue
        samples = []
        try:
            for _ in range(repeats):
                started = time.perf_counter_ns()
                decoded = loads(raw)
                duration = (time.perf_counter_ns() - started) / 1_000_000
                if decoded != baseline:
                    raise ValueError("Decoded JSON differs from stdlib")
                samples.append(round(duration, 6))
        except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
            reports.append({"name": name, "status": "PARITY_FAIL",
                            "executed": True, "measurements_ms": samples})
            continue
        reports.append({
            "name": name, "status": "PARITY_PASS", "executed": True,
            "repeats": len(samples), "median_ms": round(statistics.median(samples), 6),
            "min_ms": min(samples), "max_ms": max(samples),
            "measurements_ms": samples,
        })
    return {
        "schema_version": 1, "source": "tools.atlas_json_benchmark.compare_json_parsers",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_size_bytes": len(raw), "candidate_count": len(candidates),
        "status": ("COMPARE_COMPLETE" if all(row["status"] == "PARITY_PASS"
                                              for row in reports)
                   else "REVIEW"),
        "results": reports, "runtime_consumer_changed": False,
        "limitations": [
            "Explicit developer-only trial; optional imports are not loaded at Atlas startup",
            "Warm repeated decode on identical bytes, no Qt cold start or process-tree RSS",
            "No streaming or byte-offset index parity claim; baseline Python JSON is authoritative",
            "Candidate speed is not an adoption decision without full workload and Windows measurements",
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
    parser.add_argument("--compare-parsers", action="store_true",
                        help="Explicit opt-in: compare installed stdlib/orjson/msgspec decoders")
    parser.add_argument("--parser-repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = (compare_json_parsers(args.source, repeats=args.parser_repeats)
              if args.compare_parsers else
              benchmark(args.source, args.shards, sample_count=args.sample_count))
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
