"""Compare native Windows lifecycle probes. This tool never certifies RAM."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

DOMAINS = ("quests", "achievements", "guide", "craft", "equipment")


def _probe(path: Path, min_cycles: int) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Invalid benchmark schema")
    env, metrics = payload.get("environment"), payload.get("metrics")
    if not isinstance(env, dict) or not isinstance(metrics, dict):
        raise ValueError("Missing environment or metrics")
    if env.get("platform") != "win32":
        raise ValueError("Native Windows measurements required")
    sha = metrics.get("git_head")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Exact 40-character source SHA required")
    cycles = metrics.get("navigation_cycles")
    if type(cycles) is not int or not min_cycles <= cycles <= 10:
        raise ValueError("Invalid cycle count")
    if metrics.get("include_heavy_views") is not True:
        raise ValueError("Craft/Equipment cycles are required")
    raw = metrics.get("round_trip_home")
    if not isinstance(raw, dict):
        raise ValueError("Missing round trip measurements")
    readings = {}
    for domain in DOMAINS:
        rows = raw.get(domain)
        if not isinstance(rows, list) or len(rows) != cycles:
            raise ValueError(f"{domain}: incomplete cycle measurements")
        readings[domain] = {}
        for metric in ("process_rss_mb", "tree_rss_mb"):
            numbers = []
            for i, row in enumerate(rows):
                value = row.get(metric) if isinstance(row, dict) else None
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{domain}[{i}].{metric}: missing numeric RSS")
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"{domain}[{i}].{metric}: invalid RSS")
                numbers.append(float(value))
            readings[domain][metric] = numbers
    peaks = {}
    for metric in ("peak_process_rss_mb", "peak_tree_rss_mb"):
        value = metrics.get(metric)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{metric}: missing numeric measured peak")
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{metric}: invalid measured peak")
        peaks[metric] = float(value)
    return {"environment": env, "sha": sha, "cycles": cycles,
            "readings": readings, "peaks": peaks}


def compare(before: Path, after: Path, *, min_cycles: int = 5) -> dict:
    old, new = _probe(before, min_cycles), _probe(after, min_cycles)
    if old["cycles"] != new["cycles"]:
        raise ValueError("Incompatible navigation cycle counts")
    for key in ("platform", "python", "qt_qpa_platform"):
        if not old["environment"].get(key) or old["environment"][key] != new["environment"].get(key):
            raise ValueError(f"Incompatible environment: {key}")
    result = {}
    for domain in DOMAINS:
        result[domain] = {}
        for metric in ("process_rss_mb", "tree_rss_mb"):
            a = old["readings"][domain][metric]
            b = new["readings"][domain][metric]
            result[domain][metric] = {
                "before_first_mb": a[0], "before_last_mb": a[-1],
                "before_drift_mb": round(a[-1] - a[0], 2),
                "after_first_mb": b[0], "after_last_mb": b[-1],
                "after_drift_mb": round(b[-1] - b[0], 2),
                "drift_change_mb": round((b[-1] - b[0]) - (a[-1] - a[0]), 2),
            }
    peak_deltas = {
        name: {
            "before_mb": old["peaks"][name],
            "after_mb": new["peaks"][name],
            "change_mb": round(new["peaks"][name] - old["peaks"][name], 2),
        }
        for name in ("peak_process_rss_mb", "peak_tree_rss_mb")
    }
    return {
        "peak_comparison": peak_deltas,
        "status": "MEASUREMENT_ONLY_NOT_CERTIFIED",
        "before_sha": old["sha"], "after_sha": new["sha"],
        "navigation_cycles": old["cycles"], "domains": result,
        "limitations": [
            "The machine, workload, and caches must also be comparable.",
            "RSS drift alone neither proves a leak nor certifies a release.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = compare(args.before, args.after)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Windows lifecycle comparison written to {args.output}; no RAM certification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
