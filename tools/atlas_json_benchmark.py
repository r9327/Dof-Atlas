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
import io
import json
import statistics
import time
import zlib
from pathlib import Path

TOOL_SPEC = {
    "schema_version": 1,
    "id": "quest_json_benchmark",
    "role": "offline quest JSON comparison and evidence, not a runtime migration",
    "capabilities": ["json_data", "quest_data", "performance"],
    "modes": ["bench", "compare_parsers", "compare_streaming", "compare_compression"],
    "cost_hint": "variable",
    "side_effects": "artifact_output",
    "structured_output": True,
    "canonical": True,
    "recommended_tests": ["tests.test_atlas_json_benchmark"],
    "target_scopes": ["json_data", "quest_data", "quality_ci"],
}

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
    supplied = Path(source)
    # Resolve only after rejecting a link: the resolved target is never a
    # symlink, so checking is_symlink() *after* resolve would silently bypass it.
    if supplied.is_symlink():
        raise ValueError("Parser source must be a regular file, not a symlink")
    path = supplied.resolve(strict=True)
    if not path.is_file() or path.stat().st_size > max_bytes:
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
        except Exception as exc:
            reports.append({"name": name, "status": "ERROR",
                            "error_type": type(exc).__name__,
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

def compare_json_streaming(source: Path, *, max_bytes: int = 128 * 1024 * 1024) -> dict:
    """On-demand ijson trial against the exact existing quests source.

    Compares every quest ID and value, not a fuzzy or partial sample. Reading
    bytes once is intentional: this is a correctness/time study, not a claim
    about memory saved by streaming or the application's startup.
    """
    if not 1 <= max_bytes <= 256 * 1024 * 1024:
        raise ValueError("Invalid streaming size budget")
    supplied = Path(source)
    # Resolve only after rejecting a link: the resolved target is never a
    # symlink, so checking is_symlink() *after* resolve would silently bypass it.
    if supplied.is_symlink():
        raise ValueError("Parser source must be a regular file, not a symlink")
    path = supplied.resolve(strict=True)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("Invalid or oversized streaming input")
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError("Streaming source grew during read")
    baseline = json.loads(raw)
    quests = baseline.get("quests") if isinstance(baseline, dict) else None
    if not isinstance(quests, dict):
        raise ValueError("Expected the canonical quests object")
    try:
        ijson = importlib.import_module("ijson")
    except (ImportError, OSError):
        return {"schema_version": 1, "status": "NOT_AVAILABLE",
                "tool": "ijson", "executed": False, "runtime_consumer_changed": False}
    seen = set()
    started = time.perf_counter_ns()
    try:
        for quest_id, quest in ijson.kvitems(io.BytesIO(raw), "quests", use_float=True):
            if quest_id in seen or quest_id not in quests or quests[quest_id] != quest:
                raise ValueError("Streaming quest ID/value mismatch")
            seen.add(quest_id)
        if len(seen) != len(quests):
            raise ValueError("Streaming quest coverage incomplete")
    except (ValueError, TypeError, UnicodeError, OverflowError):
        return {"schema_version": 1, "status": "PARITY_FAIL", "tool": "ijson",
                "executed": True, "runtime_consumer_changed": False}
    except Exception as exc:
        return {"schema_version": 1, "status": "ERROR", "tool": "ijson",
                "error_type": type(exc).__name__,
                "executed": True, "runtime_consumer_changed": False}
    return {
        "schema_version": 1, "status": "PARITY_PASS", "tool": "ijson",
        "executed": True, "record_count": len(seen),
        "stream_seconds": round((time.perf_counter_ns() - started) / 1e9, 6),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "runtime_consumer_changed": False,
        "limitation": "All source bytes and stdlib baseline remain resident; this is not a streaming RSS benchmark",
    }


def compare_json_compression(source: Path, *, max_bytes: int = 128 * 1024 * 1024) -> dict:
    """Offline JSON compression trial; never changes launcher pack formats.

    Both algorithms operate on exactly the same source bytes and verify a
    lossless round trip before reporting any size/timing. No network or writes.
    """
    if not 1 <= max_bytes <= 256 * 1024 * 1024:
        raise ValueError("Invalid compression size budget")
    supplied = Path(source)
    if supplied.is_symlink():
        raise ValueError("Compression trial rejects symlinked sources")
    path = supplied.resolve(strict=True)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("Compression input missing or oversized")
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError("Compression input grew during read")
    reports: list[dict] = []
    for name in ("zlib", "zstandard"):
        if name == "zlib":
            compress = lambda data: zlib.compress(data, level=6)
            decompress = zlib.decompress
        else:
            try:
                zstd = importlib.import_module("zstandard")
            except (ImportError, OSError):
                reports.append({"name": name, "status": "NOT_AVAILABLE",
                                "executed": False})
                continue
            compress = lambda data: zstd.ZstdCompressor(level=3).compress(data)
            decompress = lambda data: zstd.ZstdDecompressor().decompress(
                data, max_output_size=len(raw))
        try:
            started = time.perf_counter_ns()
            packed = compress(raw)
            packed_ms = (time.perf_counter_ns() - started) / 1_000_000
            if not isinstance(packed, bytes):
                raise TypeError("Compressor did not return bytes")
            started = time.perf_counter_ns()
            decoded = decompress(packed)
            unpacked_ms = (time.perf_counter_ns() - started) / 1_000_000
            if decoded != raw:
                raise ValueError("Compression round trip differs from source")
        except Exception as exc:
            reports.append({"name": name, "status": "ERROR",
                            "executed": True, "error_type": type(exc).__name__})
            continue
        reports.append({
            "name": name, "status": "PARITY_PASS", "executed": True,
            "compressed_bytes": len(packed),
            "compression_ratio": round(len(packed) / max(1, len(raw)), 6),
            "compress_ms": round(packed_ms, 6),
            "decompress_ms": round(unpacked_ms, 6),
        })
    return {
        "schema_version": 1,
        "source": "tools.atlas_json_benchmark.compare_json_compression",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "status": ("COMPARE_COMPLETE" if all(row["status"] == "PARITY_PASS"
                                              for row in reports)
                   else "REVIEW"),
        "results": reports, "runtime_consumer_changed": False,
        "limits": [
            "Only lossless offline round-trip and compression time/ratio",
            "Not a measured app install, updater delta or cold-load speedup",
            "No launcher/release pack format or runtime dependency changed",
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
    parser.add_argument("--compare-streaming", action="store_true",
                        help="Explicit offline ijson quest-ID streaming parity trial")
    parser.add_argument("--compare-compression", action="store_true",
                        help="Explicit offline zlib/zstandard lossless compression trial")
    parser.add_argument("--json", action="store_true",
                        help="Sortie JSON (déjà la sortie par défaut)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if sum((args.compare_parsers, args.compare_streaming,
            args.compare_compression)) > 1:
        parser.error("Select only one optional JSON comparison mode")
    result = (compare_json_compression(args.source) if args.compare_compression
              else compare_json_streaming(args.source) if args.compare_streaming
              else compare_json_parsers(args.source, repeats=args.parser_repeats)
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
