from __future__ import annotations

"""Deterministic cost/quality routing for ROAD IA work cards.

The router deliberately uses relative cost ranks instead of embedding provider
prices. Model identifiers are resolved from environment variables so the task
policy stays stable while providers, prices and available models evolve.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / ".ai" / "task_profiles.json"
TOOL_SPEC = {
    "schema_version": 1,
    "id": "agent_task_profiles",
    "role": "ai_cost_quality_routing",
    "capabilities": ["ai_context"],
    "modes": ["route"],
    "cost_hint": "cheap",
    "side_effects": "read_only",
    "structured_output": True,
    "canonical": True,
    "recommended_tests": ["tests.test_agent_task_profiles"],
    "target_scopes": [],
}
_VALID_TASK_TYPES = (
    "read_only",
    "tiny_edit",
    "localized_fix",
    "feature",
    "refactor",
    "structural",
    "certification",
)


class TaskProfileError(RuntimeError):
    pass


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskProfileError(f"Unable to load task profiles: {path}: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise TaskProfileError("Unsupported task profile schema_version; expected 1.")
    if not isinstance(payload.get("quality_levels"), dict):
        raise TaskProfileError("task_profiles.json must define quality_levels.")
    if not isinstance(payload.get("model_tiers"), list) or not payload["model_tiers"]:
        raise TaskProfileError("task_profiles.json must define at least one model tier.")
    if not isinstance(payload.get("task_profiles"), dict):
        raise TaskProfileError("task_profiles.json must define task_profiles.")
    return payload


def _quality_rank(config: dict[str, Any], quality: str) -> int:
    row = config["quality_levels"].get(quality)
    if not isinstance(row, dict) or not isinstance(row.get("rank"), int):
        allowed = ", ".join(sorted(config["quality_levels"]))
        raise TaskProfileError(f"Unknown quality '{quality}'. Expected one of: {allowed}.")
    return int(row["rank"])


def infer_task_type(
    paths: Iterable[str], *, work_depth: str = "SOFT", structural: bool = False,
) -> str:
    normalized = [str(path).replace("\\", "/") for path in paths]
    depth = work_depth.upper()
    if structural:
        return "structural"
    if any(
        path.startswith(".github/")
        or path in {"tools/atlas_integrity.py", "tools/atlas_doctor.py"}
        for path in normalized
    ):
        return "certification"
    if not normalized:
        return "read_only"
    if depth == "HARD":
        return "refactor"
    if depth == "MEDIUM" or len(normalized) > 1:
        return "feature"
    if len(normalized) == 1 and normalized[0].startswith(("docs/", ".ai/")):
        return "tiny_edit"
    return "localized_fix"


def select_work_card(
    *,
    task_type: str,
    requested_quality: str | None = None,
    work_depth: str = "SOFT",
    config: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved = config or load_config()
    env = os.environ if environ is None else environ
    task_type = task_type.casefold()
    if task_type not in resolved["task_profiles"]:
        allowed = ", ".join(sorted(resolved["task_profiles"]))
        raise TaskProfileError(f"Unknown task type '{task_type}'. Expected one of: {allowed}.")
    depth = work_depth.upper()
    floors = resolved.get("work_depth_quality_floor", {})
    if depth not in floors:
        raise TaskProfileError("work_depth must be SOFT, MEDIUM or HARD.")

    requested = (
        requested_quality
        or resolved.get("default_requested_quality")
        or "balanced"
    ).casefold()
    profile = resolved["task_profiles"][task_type]
    task_floor = str(profile["minimum_quality"]).casefold()
    depth_floor = str(floors[depth]).casefold()
    requested_rank = _quality_rank(resolved, requested)
    task_floor_rank = _quality_rank(resolved, task_floor)
    depth_floor_rank = _quality_rank(resolved, depth_floor)
    effective_rank = max(requested_rank, task_floor_rank, depth_floor_rank)

    eligible = [
        row
        for row in resolved["model_tiers"]
        if int(row.get("quality_rank", 0)) >= effective_rank
    ]
    if not eligible:
        raise TaskProfileError(
            f"No model tier satisfies quality rank {effective_rank} for {task_type}."
        )
    selected = min(
        eligible,
        key=lambda row: (
            int(row.get("cost_rank", 10**9)),
            int(row.get("quality_rank", 10**9)),
            str(row.get("id", "")),
        ),
    )
    effective_names = [
        name
        for name, row in resolved["quality_levels"].items()
        if int(row.get("rank", -1)) == effective_rank
    ]
    effective_quality = (
        sorted(effective_names)[0] if effective_names else str(effective_rank)
    )
    escalations: list[str] = []
    if task_floor_rank > requested_rank:
        escalations.append(
            f"task floor {task_floor} exceeds requested quality {requested}"
        )
    if depth_floor_rank > max(requested_rank, task_floor_rank):
        escalations.append(f"{depth} work depth requires at least {depth_floor}")

    model_env = str(selected.get("model_env") or "")
    resolved_model = env.get(model_env) if model_env else None
    return {
        "schema_version": 1,
        "task_type": task_type,
        "description": str(profile.get("description") or ""),
        "requested_quality": requested,
        "recommended_quality": str(
            profile.get("recommended_quality") or task_floor
        ),
        "task_minimum_quality": task_floor,
        "work_depth": depth,
        "work_depth_quality_floor": depth_floor,
        "effective_quality": effective_quality,
        "selected_tier": str(selected["id"]),
        "quality_rank": int(selected["quality_rank"]),
        "cost_rank": int(selected["cost_rank"]),
        "reasoning_effort": str(selected.get("reasoning_effort") or ""),
        "model_env": model_env,
        "resolved_model": resolved_model,
        "model_resolution": "environment" if resolved_model else "tier_only",
        "escalations": escalations,
        "selection_rule": (
            "cheapest configured tier satisfying requested quality, task floor "
            "and work-depth floor"
        ),
    }


def route_for_plan(
    paths: Iterable[str],
    *,
    work_depth: str,
    structural: bool = False,
    requested_quality: str | None = None,
    task_type: str | None = None,
) -> dict[str, Any]:
    paths = list(paths)
    resolved_task = (
        infer_task_type(paths, work_depth=work_depth, structural=structural)
        if task_type in {None, "", "auto"}
        else str(task_type).casefold()
    )
    return select_work_card(
        task_type=resolved_task,
        requested_quality=requested_quality,
        work_depth=work_depth,
    )


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(
        description=(
            "Select the cheapest ROAD IA model tier that satisfies a task "
            "quality floor."
        )
    )
    parser.add_argument(
        "--task", choices=("auto", *_VALID_TASK_TYPES), default="auto"
    )
    parser.add_argument(
        "--quality", choices=tuple(config["quality_levels"]), default=None
    )
    parser.add_argument(
        "--depth", choices=("SOFT", "MEDIUM", "HARD"), default="SOFT"
    )
    parser.add_argument("--structural", action="store_true")
    parser.add_argument("--path", dest="paths", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        card = route_for_plan(
            args.paths,
            work_depth=args.depth,
            structural=args.structural,
            requested_quality=args.quality,
            task_type=args.task,
        )
    except TaskProfileError as exc:
        parser.error(str(exc))
        return 2
    if args.json:
        print(json.dumps(card, indent=2, ensure_ascii=False))
    else:
        for key, value in card.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
