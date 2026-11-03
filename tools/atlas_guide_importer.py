"""Offline, read-only authorized guide creation preview for the shared Atlas UI.

The tool never scrapes a website or writes to installed routes or user saves.
A preview is not independent source proof or a certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from app.modules.encyclopedia.services.guide_shared_route_contract import (
    GuideRouteContractError,
    project_authorized_guide,
)

# Static contract for Atlas Doctor's derived AI tool catalog; no import side effects.
TOOL_SPEC = {
    "schema_version": 1,
    "id": "atlas-guide-importer",
    "role": "guide_authorized_preview",
    "capabilities": ["guide","generation"],
    "modes": ["dry_run","explicit_preview_output","partial_uncertified"],
    "cost_hint": "variable",
    "side_effects": "repo_mutation_explicit",
    "structured_output": True,
    "canonical": False,
    "recommended_tests": ["tests.test_atlas_guide_importer_preview"],
    "target_scopes": ["encyclopedia_guide"],
}

EXPECTED_GUIDES = 95
EXPECTED_STEPS = 7705


def _canonical_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def prepare_preview(
    source: dict[str, Any],
    *,
    expected_guides: int = EXPECTED_GUIDES,
    expected_steps: int = EXPECTED_STEPS,
    partial: bool = False,
) -> dict[str, Any]:
    """Fail closed on invalid/incomplete source exports and preserve authored order."""
    if not isinstance(source, dict):
        raise GuideRouteContractError("source: JSON object expected")
    if type(source.get("schema_version")) is not int or source["schema_version"] != 1:
        raise GuideRouteContractError("schema_version: expected 1")
    if source.get("rights_verified") is not True or source.get("reference_verified") is not True:
        raise GuideRouteContractError("source: provenance/rights evidence not declared")
    if source.get("complete") is not True and not partial:
        raise GuideRouteContractError("source: full inventory must declare complete=true")
    guides = source.get("guides")
    if not isinstance(guides, list) or not guides:
        raise GuideRouteContractError("guides: nonempty ordered list required")
    if type(expected_guides) is not int or type(expected_steps) is not int:
        raise GuideRouteContractError("expected counts must be integers")
    if expected_guides <= 0 or expected_steps <= 0:
        raise GuideRouteContractError("expected counts must be positive")
    if not partial and len(guides) != expected_guides:
        raise GuideRouteContractError(
            f"guides: expected {expected_guides}, got {len(guides)}"
        )
    if partial and len(guides) > expected_guides:
        raise GuideRouteContractError("partial: too many guides")
    projected = []
    seen: set[str] = set()
    step_total = 0
    action_total = 0
    for index, guide in enumerate(guides):
        projected_guide = project_authorized_guide(guide)
        identifier = str(guide["guide_id"])
        if identifier in seen:
            raise GuideRouteContractError(f"guides[{index}]: duplicate guide_id {identifier}")
        seen.add(identifier)
        step_total += len(projected_guide["steps"])
        action_total += sum(
            len(step["manual_runtime_metadata"]["source_step"]["actions"])
            for step in projected_guide["steps"]
        )
        projected.append(projected_guide)
    if not partial and step_total != expected_steps:
        raise GuideRouteContractError(
            f"steps: expected {expected_steps}, got {step_total}"
        )
    if partial and step_total > expected_steps:
        raise GuideRouteContractError("partial: too many steps")
    if source.get("complete") is True and partial and (
        len(guides) != expected_guides or step_total != expected_steps
    ):
        raise GuideRouteContractError(
            "partial inventory must not declare complete=true"
        )
    return {
        "schema_version": 1,
        "mode": "DRY_RUN_ONLY",
        "status": "PREVIEW_ONLY_NOT_CERTIFIED",
        "certified": False,
        "source_sha256": hashlib.sha256(_canonical_bytes(source)).hexdigest(),
        "guide_count": len(projected),
        "step_count": step_total,
        "action_count": action_total,
        "expected_guide_count": expected_guides,
        "expected_step_count": expected_steps,
        "is_partial": partial,
        "routes": projected,
    }


def _load_strict_json(path: Path) -> dict[str, Any]:
    """Parse only unambiguous, RFC-compatible JSON exports at the CLI boundary."""
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> Any:
        raise ValueError(f"non-finite JSON constant {value!r}")

    def finite_float(raw: str) -> float:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"out-of-range JSON float {raw!r}")
        return value

    document = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_pairs,
        parse_constant=reject_nonfinite,
        parse_float=finite_float,
    )
    if not isinstance(document, dict):
        raise ValueError("JSON root must be an object")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Authorized guide source -> Atlas shared cards, dry-run only"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional preview JSON outside installed data")
    parser.add_argument("--partial", action="store_true",
                        help="Explicitly plan a non-certified subset only")
    args = parser.parse_args(argv)
    try:
        source = _load_strict_json(args.source)
        result = prepare_preview(
            source, partial=args.partial,
        )
        if args.output is not None:
            # Do not follow symlinks while interpreting the user-selected path:
            # a dangling preview alias or a linked parent must not redirect a
            # supposedly harmless dry-run export to an unrelated location.
            output = args.output.absolute()
            # This tool never publishes live routes or alters user progress.
            # Confine optional output to a new file under an explicit path.
            if output.exists() or output.suffix.lower() != ".json":
                raise GuideRouteContractError("output must be a new .json preview")
            if any(part.casefold() in {"data", ".git", ".cache", "saves", "profiles", "user_data"}
                   for part in output.parts):
                raise GuideRouteContractError("output must not target app data/cache/git")
            if output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
                raise GuideRouteContractError("symlinked preview output is not supported")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        print(json.dumps({
            key: result[key] for key in (
                "status", "certified", "source_sha256", "guide_count",
                "step_count", "action_count", "is_partial"
            )
        }, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"GUIDE_PREVIEW_BLOCKED: {exc}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
