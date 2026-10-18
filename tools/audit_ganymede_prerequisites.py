"""Review Atlas guide prerequisites alongside Doduda startCriterion expressions.

Preserves AND/OR branches and unresolved atoms; never treats an OR as an
AND, never marks a route/quest as mandatory and never changes progression.
No implicit quest completion, character state, shopping or route execution.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path

from app import quest_catalog as qc
from app.quest_source_index import QuestSourceError, QuestSources
from tools.audit_ganymede_master_refs import INDEX, ROOT
from tools.build_ganymede_id_registry import build_ganymede_id_registry

ATOM = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)(<=|>=|!=|=|<|>)(-?[0-9]+)$")
MAX_BRANCHES = 64
MAX_TOKENS = 512


class UnreviewableCriterion(ValueError):
    pass


def parse_start_criterion(expression: str) -> dict[str, object]:
    """Return bounded alternative AND branches, with no inferred truth values."""
    if not isinstance(expression, str) or len(expression) > 8192:
        return {"status": "REVIEW_UNPARSED", "raw": expression,
                "reason": "invalid/oversized criterion"}
    expr = expression.strip()
    if expr in ("", "BT=1"):
        return {"status": "REVIEW_NO_RESTRICTIVE_CRITERION",
                "raw": expr, "alternative_branches": [[]],
                "has_or": False, "unknown_atoms": []}
    tokens = [x.strip() for x in re.findall(r"[&|()]|[^&|()]+", expr)]
    if not tokens or len(tokens) > MAX_TOKENS:
        return {"status": "REVIEW_UNPARSED", "raw": expr,
                "reason": "empty/oversized criterion"}
    pos = 0

    def combine(a: list[list[str]], b: list[list[str]]) -> list[list[str]]:
        if len(a) * len(b) > MAX_BRANCHES:
            raise UnreviewableCriterion("alternative branch expansion cap")
        return [left + right for left in a for right in b]

    def parse_factor(depth: int) -> list[list[str]]:
        nonlocal pos
        if depth > 32 or pos >= len(tokens):
            raise UnreviewableCriterion("invalid nesting or incomplete expression")
        token = tokens[pos]
        if token == "(":
            pos += 1
            result = parse_or(depth + 1)
            if pos >= len(tokens) or tokens[pos] != ")":
                raise UnreviewableCriterion("unbalanced parentheses")
            pos += 1
            return result
        if token in (")", "&", "|") or not token:
            raise UnreviewableCriterion("empty/invalid condition")
        pos += 1
        return [[token]]

    def parse_and(depth: int) -> list[list[str]]:
        nonlocal pos
        branches = parse_factor(depth)
        while pos < len(tokens) and tokens[pos] == "&":
            pos += 1
            branches = combine(branches, parse_factor(depth))
        return branches

    def parse_or(depth: int) -> list[list[str]]:
        nonlocal pos
        branches = parse_and(depth)
        while pos < len(tokens) and tokens[pos] == "|":
            pos += 1
            branches += parse_and(depth)
            if len(branches) > MAX_BRANCHES:
                raise UnreviewableCriterion("too many OR branches")
        return branches

    try:
        raw_branches = parse_or(0)
        if pos != len(tokens):
            raise UnreviewableCriterion("unexpected trailing criterion tokens")
    except UnreviewableCriterion as exc:
        return {"status": "REVIEW_UNPARSED", "raw": expr,
                "reason": str(exc), "alternative_branches": []}

    def atom(value: str) -> dict[str, object]:
        canonical = re.sub(r"\s+", "", value)
        matched = ATOM.fullmatch(canonical)
        if matched is None:
            return {"raw": value, "semantic": "OPAQUE_UNINTERPRETED"}
        kind, op, raw_value = matched.groups()
        semantic = {
            "Qf": "QUEST_COMPLETION_CONDITION_REVIEW",
            "Qa": "QUEST_ORDERING_CONTEXT_REVIEW",
            "Sc": "ACHIEVEMENT_OR_SCORE_CONDITION_REVIEW",
            "PL": "LEVEL_CONDITION_REVIEW",
        }.get(kind, "OPAQUE_UNINTERPRETED")
        return {"raw": value, "kind": kind, "op": op, "value": int(raw_value),
                "semantic": semantic}

    branches = [[atom(v) for v in raw] for raw in raw_branches]
    unknown = sorted({x["raw"] for b in branches for x in b
                      if x["semantic"] == "OPAQUE_UNINTERPRETED"})
    return {
        "status": "REVIEW_BRANCHES_PRESERVED",
        "raw": expr,
        "alternative_branches": branches,
        "has_or": len(branches) > 1,
        "unknown_atoms": unknown,
        "mandatory_quest_ids_inferred": [],
    }


def audit_ganymede_prerequisites(
    root: Path, *, raw_quests_path: Path | None = None
) -> dict[str, object]:
    root = Path(root).resolve()
    registry = build_ganymede_id_registry(root)
    if registry.get("status") != "REVIEW_REQUIRED":
        return {
            "schema_version": 1, "status": "FAIL",
            "issues": [{"code": "invalid_id_registry",
                        "detail": str(registry.get("issues", []))}],
            "certified_prerequisites": 0, "certified_routes": 0,
        }

    by_id = registry["quest_by_id"]
    reviews: dict[str, dict] = {}
    unresolved: list[dict] = []
    for quest_id, quest in by_id.items():
        declarations = []
        for occurrence in quest["atlas_occurrences"]:
            conditions = occurrence["local_declared_prerequisites"]
            alternatives = occurrence["local_alternative_groups"]
            optional = occurrence["local_optional"] is True
            relation = occurrence["local_relation"]
            for cond in conditions:
                if (cond["type"] == "quest" and
                        str(cond["entity_id"]) not in by_id):
                    unresolved.append({
                        "quest_id": int(quest_id),
                        "atlas_guide_id": occurrence["atlas_guide_id"],
                        "unresolved_ref_type": "quest",
                        "unresolved_ref_id": cond["entity_id"],
                    })
            declarations.append({
                "atlas_guide_id": occurrence["atlas_guide_id"],
                "atlas_step_id": occurrence["atlas_step_id"],
                "locally_declared_dependencies": conditions,
                "local_optional": optional,
                "local_relation": relation,
                "local_alternative_groups": alternatives,
                "all_or_branches_mandatory": False,
                "status": "REVIEW_UNCERTIFIED_GUIDE_DECLARATION",
            })
        reviews[quest_id] = {
            "quest_id": int(quest_id),
            "atlas_declarations": declarations,
            "raw_start_criterion": None,
            "raw_criterion_review": None,
            "verified_required_quests": [],
            "verified_required_achievements": [],
            "verified_required_objects": [],
            "satisfied_for_any_character": None,
            "prerequisites_certified": False,
        }

    default = (
        qc.RAW_QUEST_DATA_DIR / "quests.json" if root == ROOT.resolve()
        else root / "data/cache/dofus_maps/raw/doduda_cli/quests.json"
    )
    raw_path = Path(raw_quests_path) if raw_quests_path else default
    problems: list[dict[str, str]] = []
    raw_available = raw_path.is_file()
    if raw_available:
        try:
            with tempfile.TemporaryDirectory(prefix="atlas-guide-prereq-") as temp:
                sources = QuestSources(Path(temp), disk_backed=True)
                try:
                    quests = sources.rows(raw_path)
                    for key, review in reviews.items():
                        raw = quests.get(int(key))
                        if raw is None:
                            review["raw_criterion_review"] = {
                                "status": "REVIEW_QUEST_ABSENT_FROM_INSTALLED_DODUDA"
                            }
                            continue
                        if not isinstance(raw, dict):
                            raise ValueError(f"malformed quest row {key}")
                        ident = raw.get("id")
                        if ident is not None and ident != int(key):
                            review["raw_criterion_review"] = {
                                "status": "REVIEW_CANONICAL_ID_MISMATCH",
                                "source_id": ident,
                            }
                            continue
                        criterion = raw.get("startCriterion", "")
                        if not isinstance(criterion, str):
                            review["raw_criterion_review"] = {
                                "status": "REVIEW_NONSTRING_CRITERION"
                            }
                            continue
                        review["raw_start_criterion"] = criterion
                        review["raw_criterion_review"] = parse_start_criterion(criterion)
                finally:
                    sources.close()
        except (QuestSourceError, OSError, RuntimeError, ValueError, KeyError) as exc:
            problems.append({"code": "unreadable_canonical_quests",
                             "detail": str(exc)})

    main_index = json.loads((root / INDEX).read_text(encoding="utf-8"))
    guide_prerequisites = []
    for guide in main_index["guides"]:
        guide_prerequisites.append({
            "source_guide_id": guide["ganymede_guide_id"],
            "source_prerequisite_guide_ids":
                guide.get("public_tree_prerequisite_guide_ids", []),
            "level": "GUIDE_LEVEL_REFERENCE_ONLY",
            "not_assigned_to_every_quest": True,
        })
    return {
        "schema_version": 1,
        "status": "FAIL" if problems else (
            "REVIEW_RAW_AND_ATLAS_PREREQUISITES"
            if raw_available else "REVIEW_ATLAS_ONLY_CANONICAL_UNAVAILABLE"
        ),
        "evidence_level": "local_guide_declarations_and_raw_criterion_structure_only",
        "source_registry": "tools.build_ganymede_id_registry",
        "raw_source_path": str(raw_path),
        "raw_doduda_available": raw_available,
        "quest_by_id": reviews,
        "ganymede_guide_prerequisites": guide_prerequisites,
        "unresolved_local_quest_references": unresolved,
        "quest_ids_reviewed": len(reviews),
        "quests_with_local_declarations": sum(
            bool(r["atlas_declarations"]) for r in reviews.values()
        ),
        "quests_with_raw_criteria": sum(
            r["raw_criterion_review"] is not None for r in reviews.values()
        ),
        "raw_criteria_with_or": sum(
            (r["raw_criterion_review"] or {}).get("has_or", False)
            for r in reviews.values()
        ),
        "certified_prerequisites": 0,
        "certified_routes": 0,
        "issues": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--raw-quests", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_ganymede_prerequisites(
        args.root, raw_quests_path=args.raw_quests
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
