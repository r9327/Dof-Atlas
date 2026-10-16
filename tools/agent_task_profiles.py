from __future__ import annotations

"""Deterministic quality/consumption routing for ROAD IA work cards.

Task topology, requested output quality and estimated AI consumption are a
separate concern from Atlas Doctor validation levels. This module only selects
an AI work profile; it never selects or weakens repository validation depth.
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
    "role": "ai_quality_consumption_routing",
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
    paths: Iterable[str], *, structural: bool = False, certification: bool = False,
) -> str:
    normalized = [str(path).replace("\\", "/") for path in paths]
    if certification:
        return "certification"
    if structural:
        return "structural"
    if not normalized:
        return "read_only"
    if len(normalized) == 1 and normalized[0].startswith(("docs/", ".ai/")):
        return "tiny_edit"
    if len(normalized) == 1:
        return "localized_fix"
    if len(normalized) <= 4:
        return "feature"
    return "refactor"


def select_work_card(
    *,
    task_type: str,
    requested_quality: str | None = None,
    config: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved = config or load_config()
    env = os.environ if environ is None else environ
    task_type = task_type.casefold()
    if task_type not in resolved["task_profiles"]:
        allowed = ", ".join(sorted(resolved["task_profiles"]))
        raise TaskProfileError(f"Unknown task type '{task_type}'. Expected one of: {allowed}.")

    profile = resolved["task_profiles"][task_type]
    recommended = str(
        profile.get("recommended_quality")
        or resolved.get("default_requested_quality")
        or "balanced"
    ).casefold()
    selected_quality = (requested_quality or recommended).casefold()
    selected_rank = _quality_rank(resolved, selected_quality)

    eligible = [
        row
        for row in resolved["model_tiers"]
        if int(row.get("quality_rank", 0)) >= selected_rank
    ]
    if not eligible:
        raise TaskProfileError(
            f"No model tier satisfies quality rank {selected_rank} for {task_type}."
        )
    selected = min(
        eligible,
        key=lambda row: (
            int(row.get("consumption_rank", 10**9)),
            int(row.get("quality_rank", 10**9)),
            str(row.get("id", "")),
        ),
    )

    model_env = str(selected.get("model_env") or "")
    resolved_model = env.get(model_env) if model_env else None
    return {
        "schema_version": 1,
        "task_type": task_type,
        "description": str(profile.get("description") or ""),
        "recommended_quality": recommended,
        "requested_quality": requested_quality.casefold() if requested_quality else None,
        "selected_quality": selected_quality,
        "user_override": requested_quality is not None and selected_quality != recommended,
        "selected_tier": str(selected["id"]),
        "quality_rank": int(selected["quality_rank"]),
        "consumption_rank": int(selected["consumption_rank"]),
        "consumption_label": str(selected.get("consumption_label") or "unknown"),
        "reasoning_effort": str(selected.get("reasoning_effort") or ""),
        "model_env": model_env,
        "resolved_model": resolved_model,
        "model_resolution": "environment" if resolved_model else "tier_only",
        "selection_rule": (
            "lowest-consumption configured tier satisfying the selected quality; "
            "task topology only supplies a recommendation"
        ),
        "doctor_validation": "independent",
    }


def route_for_task(
    paths: Iterable[str], *, structural: bool = False, certification: bool = False,
    requested_quality: str | None = None, task_type: str | None = None,
) -> dict[str, Any]:
    paths = list(paths)
    resolved_task = (
        infer_task_type(paths, structural=structural, certification=certification)
        if task_type in {None, "", "auto"}
        else str(task_type).casefold()
    )
    return select_work_card(
        task_type=resolved_task,
        requested_quality=requested_quality,
    )


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(
        description=(
            "Propose a quality/consumption profile by task topology and select "
            "the lowest-consumption tier satisfying the chosen quality."
        )
    )
    parser.add_argument(
        "--task", choices=("auto", *_VALID_TASK_TYPES), default="auto"
    )
    parser.add_argument(
        "--quality", choices=tuple(config["quality_levels"]), default=None
    )
    parser.add_argument("--structural", action="store_true")
    parser.add_argument("--certification", action="store_true")
    parser.add_argument("--path", dest="paths", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        card = route_for_task(
            args.paths,
            structural=args.structural,
            certification=args.certification,
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
