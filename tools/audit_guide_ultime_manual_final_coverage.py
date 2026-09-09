from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.encyclopedia.achievement_catalog_policy import RETAINED_TOP_CATEGORY_IDS
from app.modules.encyclopedia.providers import AchievementProvider
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.quest_catalog import normalize_text

BASE = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = BASE / "manifest_v1.json"
SUCCESS_CONTRACT_FILES = (
    BASE / "success_contracts_v2.json",
    BASE / "success_contracts_pandala_v1.json",
)


def norm(value: Any) -> str:
    return normalize_text(str(value or ""))


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return value


def collect_route_evidence() -> dict[str, Any]:
    manifest = load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    quest_names: set[str] = set()
    success_names: set[str] = set()
    text_tokens: set[str] = set()
    stage_sources: dict[str, list[str]] = defaultdict(list)
    chapter_stage_counts: dict[str, int] = {}

    for row in canonical.get("chapters", []) or []:
        if not isinstance(row, dict):
            continue
        chapter_id = str(row.get("id") or "")
        filename = str(row.get("file") or "")
        payload = load_manual_chapter(BASE / filename)
        stages = [stage for stage in payload.get("stages", []) or [] if isinstance(stage, dict)]
        chapter_stage_counts[chapter_id] = len(stages)
        for stage in stages:
            stage_id = str(stage.get("id") or "")
            # The manual route has three structured ways to declare quest work.
            # Coverage must consume all three, just like the prerequisite audit
            # and runtime do, otherwise quest_sequence/parallel_quests become
            # invisible and produce false success gaps.
            for field in ("quest_sequence", "parallel_quests", "quests"):
                raw_field = stage.get(field)
                values = raw_field if isinstance(raw_field, list) else [raw_field] if raw_field else []
                for raw in values:
                    name = str(raw or "").strip()
                    if name and not name.startswith("conditional:"):
                        key = norm(name)
                        quest_names.add(key)
                        stage_sources[key].append(f"{chapter_id}:{stage_id}:{field}")
            for raw in stage.get("successes", []) or []:
                name = str(raw or "").strip()
                if name:
                    key = norm(name)
                    success_names.add(key)
                    stage_sources[key].append(f"{chapter_id}:{stage_id}:success")
            stack: list[Any] = [stage]
            while stack:
                current = stack.pop()
                if isinstance(current, dict):
                    stack.extend(current.values())
                elif isinstance(current, list):
                    stack.extend(current)
                elif isinstance(current, str):
                    token = norm(current)
                    if token:
                        text_tokens.add(token)

    return {
        "manifest": manifest,
        "quest_names": quest_names,
        "success_names": success_names,
        "text_tokens": text_tokens,
        "stage_sources": stage_sources,
        "chapter_stage_counts": chapter_stage_counts,
    }


def label_is_explicit(label: str, evidence: dict[str, Any]) -> bool:
    key = norm(label)
    if not key:
        return False
    if key in evidence["quest_names"] or key in evidence["success_names"]:
        return True
    return any(key == text or key in text for text in evidence["text_tokens"])


def refs(achievement: Any, entity_type: str) -> list[dict[str, Any]]:
    if entity_type == "quest":
        source = achievement.resolved_linked_quests
    elif entity_type == "monster":
        source = achievement.resolved_linked_monsters
    elif entity_type == "dungeon":
        source = achievement.resolved_linked_dungeons
    else:
        return []
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for ref in source:
        key = (entity_type, int(ref.entity_id))
        if key in seen:
            continue
        seen.add(key)
        result.append({"id": int(ref.entity_id), "name": ref.label})
    return result


def classify(achievement: Any, evidence: dict[str, Any]) -> dict[str, Any]:
    direct_success = norm(achievement.name) in evidence["success_names"]
    linked: dict[str, list[dict[str, Any]]] = {}
    missing: dict[str, list[dict[str, Any]]] = {}
    total_refs = 0
    covered_refs = 0
    for entity_type in ("quest", "monster", "dungeon"):
        rows = refs(achievement, entity_type)
        linked[entity_type] = rows
        total_refs += len(rows)
        absent = [row for row in rows if not label_is_explicit(str(row["name"]), evidence)]
        missing[entity_type] = absent
        covered_refs += len(rows) - len(absent)

    if direct_success:
        state = "covered_direct_success"
    elif total_refs and covered_refs == total_refs:
        state = "covered_all_linked_entities"
    elif covered_refs:
        state = "partial"
    else:
        state = "uncovered"

    return {
        "id": int(achievement.id),
        "name": achievement.name,
        "category_id": int(achievement.category_id),
        "category": achievement.category_name,
        "subcategory": achievement.subcategory_name,
        "level": achievement.level,
        "points": achievement.points,
        "state": state,
        "direct_success_contract": direct_success,
        "linked": linked,
        "missing": missing,
        "linked_entity_count": total_refs,
        "covered_linked_entity_count": covered_refs,
    }


def _present_quests(names: list[Any], evidence: dict[str, Any]) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for raw in names:
        name = str(raw or "").strip()
        if not name:
            continue
        if norm(name) in evidence["quest_names"]:
            present.append(name)
        else:
            missing.append(name)
    return present, missing


def _evaluate_contract(contract: dict[str, Any], evidence: dict[str, Any], registry: str) -> dict[str, Any]:
    success = str(contract.get("success") or "").strip()
    mode = str(contract.get("mode") or "all").strip()
    required = list(contract.get("required_quests", []) or [])
    present, missing = _present_quests(required, evidence)
    row: dict[str, Any] = {
        "registry": registry,
        "success": success,
        "zone": str(contract.get("zone") or ""),
        "mode": mode,
        "source": str(contract.get("source") or ""),
        "required_quests": required,
        "present_required_quests": present,
        "missing_required_quests": missing,
    }

    passed = False
    if mode == "all":
        passed = not missing
    elif mode == "one_complete_branch":
        branch_rows: dict[str, Any] = {}
        complete_branches: list[str] = []
        for branch_name, branch_quests in (contract.get("branches") or {}).items():
            b_present, b_missing = _present_quests(list(branch_quests or []), evidence)
            branch_rows[str(branch_name)] = {"present": b_present, "missing": b_missing, "complete": not b_missing}
            if not b_missing:
                complete_branches.append(str(branch_name))
        row["branches"] = branch_rows
        row["complete_branches"] = complete_branches
        passed = bool(complete_branches)
    elif mode == "all_plus_one_of":
        one_of = list(contract.get("one_of", []) or [])
        one_present, one_missing = _present_quests(one_of, evidence)
        row["one_of"] = one_of
        row["present_one_of"] = one_present
        row["missing_one_of"] = one_missing
        passed = not missing and bool(one_present)
    elif mode == "explicit_success":
        row["explicit_success_present"] = norm(success) in evidence["success_names"]
        passed = bool(row["explicit_success_present"])
    else:
        row["error"] = f"Mode de contrat inconnu: {mode}"
        passed = False

    row["state"] = "covered" if passed else "gap"
    return row


def evaluate_success_contracts(evidence: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    registries: list[dict[str, Any]] = []
    for path in SUCCESS_CONTRACT_FILES:
        if not path.is_file():
            errors.append(f"Fichier absent: {path}")
            continue
        payload = load(path)
        registry = str(payload.get("contract_id") or path.name)
        registries.append({
            "file": path.name,
            "contract_id": registry,
            "status": str(payload.get("status") or ""),
            "as_of": str(payload.get("as_of") or ""),
        })
        for contract in payload.get("contracts", []) or []:
            if isinstance(contract, dict):
                rows.append(_evaluate_contract(contract, evidence, registry))

    failed = sum(1 for row in rows if row["state"] != "covered") + len(errors)
    return {
        "status": "CONTRACTS_COVERED" if failed == 0 else "CONTRACT_GAPS_REMAIN",
        "registries": registries,
        "contract_count": len(rows),
        "failed_contract_count": failed,
        "contracts": rows,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit final de couverture du Guide Ultime manuel sur les succès retenus Lot7.")
    parser.add_argument("--strict", action="store_true", help="Échoue si un succès est partiel/absent ou si un contrat vérifié est cassé.")
    parser.add_argument(
        "--allow-missing-achievement-catalog",
        action="store_true",
        help="Autorise uniquement l'absence totale du catalogue Succès; les contrats vérifiés restent stricts.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Écrit aussi le rapport JSON à cet emplacement.")
    args = parser.parse_args()

    evidence = collect_route_evidence()
    contract_report = evaluate_success_contracts(evidence)
    provider = AchievementProvider()
    loaded_achievements = list(provider.load_all())
    achievement_catalog_available = bool(loaded_achievements)
    achievements = [
        achievement
        for achievement in loaded_achievements
        if achievement.category_id in set(RETAINED_TOP_CATEGORY_IDS)
    ]
    rows = [classify(achievement, evidence) for achievement in achievements]

    state_counts = Counter(row["state"] for row in rows)
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    subcategory_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        category_counts[str(row["category"])][row["state"]] += 1
        subcategory_counts[f"{row['category']} / {row['subcategory']}"][row["state"]] += 1

    buckets: dict[str, dict[str, dict[str, Any]]] = {"quest": {}, "monster": {}, "dungeon": {}}
    for row in rows:
        for entity_type, target in buckets.items():
            for item in row["missing"][entity_type]:
                key = f"{item['id']}:{item['name']}"
                current = target.setdefault(key, {**item, "achievement_ids": [], "achievement_names": []})
                current["achievement_ids"].append(row["id"])
                current["achievement_names"].append(row["name"])

    uncovered = [row for row in rows if row["state"] == "uncovered"]
    partial = [row for row in rows if row["state"] == "partial"]
    contract_failed = int(contract_report.get("failed_contract_count") or 0)

    if contract_failed or (achievement_catalog_available and (uncovered or partial)):
        status = "GAPS_REMAIN"
    elif not achievement_catalog_available:
        status = "ACHIEVEMENT_CATALOG_UNAVAILABLE"
    else:
        status = "COMPLETE_BY_EVIDENCE"

    report = {
        "schema_version": 5,
        "status": status,
        "audit_complete": achievement_catalog_available,
        "achievement_catalog_available": achievement_catalog_available,
        "provider_achievement_count": len(loaded_achievements),
        "scope": "Lot7 retained categories + verified Frigost/Pandala success contracts",
        "canonical_chapters": evidence["chapter_stage_counts"],
        "canonical_stage_count": sum(evidence["chapter_stage_counts"].values()),
        "explicit_route_quest_name_count": len(evidence["quest_names"]),
        "explicit_route_success_name_count": len(evidence["success_names"]),
        "achievement_count": len(rows),
        "state_counts": dict(sorted(state_counts.items())),
        "category_counts": {key: dict(sorted(value.items())) for key, value in sorted(category_counts.items())},
        "subcategory_counts": {key: dict(sorted(value.items())) for key, value in sorted(subcategory_counts.items())},
        "verified_success_contracts": contract_report,
        "missing_unique_quests": sorted(buckets["quest"].values(), key=lambda x: (str(x["name"]), int(x["id"]))),
        "missing_unique_monsters": sorted(buckets["monster"].values(), key=lambda x: (str(x["name"]), int(x["id"]))),
        "missing_unique_dungeons": sorted(buckets["dungeon"].values(), key=lambda x: (str(x["name"]), int(x["id"]))),
        "partial_achievements": partial,
        "uncovered_achievements": uncovered,
        "all_achievements": rows,
        "infrastructure_warnings": [] if achievement_catalog_available else [
            {
                "code": "achievement_catalog_unavailable",
                "message": "AchievementProvider n'a chargé aucun succès; la couverture Lot7 globale n'est pas auditable dans cet environnement."
            }
        ],
        "interpretation": [
            "covered_direct_success signifie que le succès est explicitement nommé dans une macro-stage.",
            "covered_all_linked_entities signifie que toutes les quêtes/monstres/donjons résolus par AchievementProvider sont explicitement présents dans la route.",
            "Les contrats déterministes imposent les quêtes exactes; explicit_success est réservé aux routes dont la variante dépend réellement d'un état aléatoire/journalier runtime.",
            "Les contrats Frigost/Pandala restent vérifiés même lorsque le catalogue Succès est absent et peuvent toujours faire échouer --strict.",
            "ACHIEVEMENT_CATALOG_UNAVAILABLE n'est jamais présenté comme COMPLETE_BY_EVIDENCE; un run local final doit charger le vrai AchievementProvider.",
            "Aucun fuzzy matching n'est utilisé; l'audit préfère des faux négatifs à de faux PASS.",
        ],
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    strict_failure = bool(contract_failed)
    if achievement_catalog_available:
        strict_failure = strict_failure or bool(uncovered or partial)
    elif not args.allow_missing_achievement_catalog:
        strict_failure = True
    if args.strict and strict_failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
