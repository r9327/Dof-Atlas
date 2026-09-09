from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.providers import AchievementProvider
from app.modules.encyclopedia.achievement_catalog_policy import (
    ALIGNMENT_GUIDE_IDS,
    ALIGNMENT_ORDER_ACHIEVEMENT_RANKS,
    RETAINED_TOP_CATEGORY_IDS,
)
from app.modules.encyclopedia.services.guide_path_profiles import ORDER_QUEST_IDS


SOURCE_FILES = (
    "achievement_categories.json",
    "achievements.json",
    "achievement_objectives.json",
    "achievement_rewards.json",
    "quests.json",
    "dungeons.json",
    "monsters.json",
    "languages/fr.json",
)


def file_evidence(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "path": str(path.relative_to(ROOT_DIR)).replace("\\", "/"),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "sha256": digest.hexdigest(),
    }


def achievement_row(achievement: Any, category_positions: dict[tuple[int, int], int]) -> dict[str, Any]:
    raw_category_id = int(achievement.raw.get("categoryId") or achievement.category_id)
    return {
        "id": achievement.id,
        "name": achievement.name,
        "description": achievement.description,
        "category_id": achievement.category_id,
        "category": achievement.category_name,
        "subcategory_id": achievement.subcategory_id,
        "subcategory": achievement.subcategory_name,
        "region_or_zone": achievement.subcategory_name or achievement.category_name,
        "source_category_id": raw_category_id,
        "game_order": achievement.order,
        "game_position_in_category": category_positions.get((raw_category_id, achievement.id)),
        "level": achievement.level,
        "points": achievement.points,
        "objective_ids": list(achievement.objective_ids),
        "objectives": [
            {
                "id": objective.id,
                "order": objective.order,
                "text": objective.text,
                "criterion": objective.criterion,
                "type": objective.objective_type,
                "resolved_entity": (
                    {
                        "type": objective.entity_ref.entity_type,
                        "id": objective.entity_ref.entity_id,
                        "label": objective.entity_ref.label,
                    }
                    if objective.entity_ref is not None
                    else None
                ),
            }
            for objective in achievement.objectives
        ],
        "direct_linked_quests_in_objective_order": [
            {"id": ref.entity_id, "name": ref.label}
            for objective in achievement.objectives
            for ref in objective.entity_refs
            if ref.entity_type == "quest"
        ],
        "resolved_linked_quests_in_logical_order": [
            {"id": ref.entity_id, "name": ref.label} for ref in achievement.resolved_linked_quests
        ],
        "linked_monsters_in_objective_order": [
            {"id": ref.entity_id, "name": ref.label} for ref in achievement.resolved_linked_monsters
        ],
        "linked_dungeons_in_source_order": [
            {"id": ref.entity_id, "name": ref.label} for ref in achievement.resolved_linked_dungeons
        ],
        "reward_ids": list(achievement.reward_ids),
    }


def build_audit() -> dict[str, Any]:
    provider = AchievementProvider()
    achievements = provider.load_all()
    categories = provider.get_categories()
    by_id = {achievement.id: achievement for achievement in achievements}
    top_categories = sorted(
        (category for category in categories if category.parent_id == 0),
        key=lambda category: (category.order, category.id),
    )
    retained_ids = set(RETAINED_TOP_CATEGORY_IDS)

    category_positions: dict[tuple[int, int], int] = {}
    for category in categories:
        for position, achievement_id in enumerate(category.achievement_ids, 1):
            category_positions[(category.id, int(achievement_id))] = position

    target = [achievement for achievement in achievements if achievement.category_id in retained_ids]
    excluded = [achievement for achievement in achievements if achievement.category_id not in retained_ids]
    current_visible = [
        achievement
        for achievement in achievements
        if any(
            ref.entity_type == "quest"
            for objective in achievement.objectives
            for ref in objective.entity_refs
        )
    ]
    current_kept = [achievement for achievement in current_visible if achievement.category_id in retained_ids]
    current_removed = [achievement for achievement in current_visible if achievement.category_id not in retained_ids]

    missing_membership = []
    wrong_membership = []
    duplicate_orders = []
    for category in categories:
        listed = [int(value) for value in category.achievement_ids]
        for achievement_id in listed:
            achievement = by_id.get(achievement_id)
            if achievement is None:
                missing_membership.append({"category_id": category.id, "achievement_id": achievement_id})
                continue
            raw_category_id = int(achievement.raw.get("categoryId") or achievement.category_id)
            if raw_category_id != category.id:
                wrong_membership.append(
                    {
                        "category_id": category.id,
                        "achievement_id": achievement_id,
                        "actual_category_id": raw_category_id,
                    }
                )
        rows = [
            achievement
            for achievement in target
            if int(achievement.raw.get("categoryId") or achievement.category_id) == category.id
        ]
        orders: dict[int, list[int]] = defaultdict(list)
        for achievement in rows:
            orders[int(achievement.order)].append(int(achievement.id))
            if achievement.id not in listed:
                missing_membership.append({"category_id": category.id, "achievement_id": achievement.id})
        for order, ids in sorted(orders.items()):
            if len(ids) > 1:
                duplicate_orders.append({"category_id": category.id, "order": order, "achievement_ids": ids})

    objective_code_counts = Counter(
        objective.objective_type or "Sans type"
        for achievement in target
        for objective in achievement.objectives
    )
    missing_objective_rows = []
    objective_order_mismatches = []
    for achievement in target:
        loaded = [objective.id for objective in achievement.objectives]
        loaded_set = set(loaded)
        expected_loaded = [objective_id for objective_id in achievement.objective_ids if objective_id in loaded_set]
        missing = [objective_id for objective_id in achievement.objective_ids if objective_id not in loaded_set]
        if missing:
            missing_objective_rows.append({"achievement_id": achievement.id, "missing_objective_ids": missing})
        if loaded != expected_loaded:
            objective_order_mismatches.append(
                {
                    "achievement_id": achievement.id,
                    "declared_present_objective_ids": expected_loaded,
                    "loaded_objective_ids": loaded,
                }
            )

    alignment_choices = []
    for side, orders in ORDER_QUEST_IDS.items():
        for order_name, quest_ids in orders.items():
            quests = []
            for rank, quest_id in enumerate(quest_ids, 1):
                quest = provider.quest_provider.get_quest(int(quest_id))
                quests.append(
                    {
                        "rank": rank,
                        "quest_id": int(quest_id),
                        "name": quest.name if quest is not None else None,
                        "local_quest_present": quest is not None,
                    }
                )
            alignment_choices.append(
                {
                    "side": side,
                    "order": order_name,
                    "quests": quests,
                    "valid_five_unique_quests": len(quest_ids) == 5 and len(set(quest_ids)) == 5 and all(row["local_quest_present"] for row in quests),
                }
            )

    return {
        "schema_version": 1,
        "lot": 7,
        "phase": "WORK - audit, tri et preparation des donnees",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_policy": {
            "order_source": "Champs order et achievementIds des donnees locales extraites du jeu; aucun tri alphabetique de contenu.",
            "content_source": "Catalogue local Doduda utilise par Dofus Atlas.",
            "retention_rule": "Uniquement Donjons, Monstres, Quetes et Evenements; aucune autre categorie n'etait explicitement validee dans le Lot 7.",
            "source_files": [file_evidence(RAW_QUEST_DATA_DIR / relative) for relative in SOURCE_FILES],
        },
        "summary": {
            "loaded_achievements": len(achievements),
            "currently_displayed_quest_linked_achievements": len(current_visible),
            "currently_displayed_retained": len(current_kept),
            "currently_displayed_removed": len(current_removed),
            "target_retained_achievements": len(target),
            "source_achievements_excluded_by_category": len(excluded),
            "retained_top_categories": len(RETAINED_TOP_CATEGORY_IDS),
            "excluded_top_categories": len(top_categories) - len(RETAINED_TOP_CATEGORY_IDS),
        },
        "definitive_category_order": [
            {
                "id": category.id,
                "order": category.order,
                "name": category.name,
                "achievement_count": len(provider.get_by_category(category.id)),
                "subcategories": [
                    {
                        "id": child.id,
                        "order": child.order,
                        "name": child.name,
                        "achievement_count": len(provider.get_by_category(child.id)),
                    }
                    for child in provider.get_subcategories(category.id)
                ],
            }
            for category in top_categories
            if category.id in retained_ids
        ],
        "excluded_categories": [
            {
                "id": category.id,
                "order": category.order,
                "name": category.name,
                "achievement_count": len(provider.get_by_category(category.id)),
                "reason": "Categorie non retenue par le perimetre explicite du Lot 7.",
            }
            for category in top_categories
            if category.id not in retained_ids
        ],
        "retained_achievements": [achievement_row(achievement, category_positions) for achievement in target],
        "excluded_achievements": [
            {
                "id": achievement.id,
                "name": achievement.name,
                "category_id": achievement.category_id,
                "category": achievement.category_name,
                "subcategory": achievement.subcategory_name,
                "reason": "Categorie parente non retenue.",
            }
            for achievement in excluded
        ],
        "currently_displayed_achievements_removed": [
            {
                "id": achievement.id,
                "name": achievement.name,
                "category": achievement.category_name,
                "subcategory": achievement.subcategory_name,
            }
            for achievement in current_removed
        ],
        "alignment_orders": {
            "rule": "Une selection de personnage choisit un seul Ordre. Les cinq succes de rang utilisent alors, dans l'ordre, une seule des cinq quetes de cet Ordre; les autres branches restent alternatives.",
            "affected_achievement_ranks": ALIGNMENT_ORDER_ACHIEVEMENT_RANKS,
            "choices": alignment_choices,
            "guide_redirects": ALIGNMENT_GUIDE_IDS,
        },
        "checks": {
            "objective_type_counts": dict(sorted(objective_code_counts.items())),
            "missing_or_unlisted_category_memberships": missing_membership,
            "wrong_category_memberships": wrong_membership,
            "duplicate_achievement_orders": duplicate_orders,
            "missing_objective_rows": missing_objective_rows,
            "objective_order_mismatches": objective_order_mismatches,
            "alignment_choices_all_valid": all(row["valid_five_unique_quests"] for row in alignment_choices),
        },
        "known_special_cases": [
            "L'ancien ecran ne retenait que les succes ayant une quete Qf directement resolue; les meta-succes OA et les contenus Monstres/Donjons etaient donc masques.",
            "Les criteres Pr des Ordres expriment des branches alternatives et ne sont pas des identifiants de quetes.",
            "Les objectifs techniques non resolus restent conserves textuellement; ils ne sont pas inventes ni transformes en quetes.",
            "Les Lots 8 et 9 devront completer les interactions specialisees Monstres et Donjons sans changer cette organisation source.",
        ],
    }


def markdown_report(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# Lot 7 - Audit WORK des Succes",
        "",
        f"Genere le `{audit['generated_at']}` depuis le catalogue local actuellement utilise par Dofus Atlas.",
        "",
        "## Decision de perimetre",
        "",
        "Ordre definitif du jeu pour les categories conservees : **Donjons -> Monstres -> Quetes -> Evenements**.",
        "Aucune autre categorie n'est retenue, faute de validation explicite dans le Lot 7.",
        "",
        "## Inventaire",
        "",
        f"- {summary['loaded_achievements']} succes charges par le fournisseur actuel.",
        f"- {summary['currently_displayed_quest_linked_achievements']} succes seulement etaient affichables par l'ancien ecran (filtre Qf direct).",
        f"- {summary['target_retained_achievements']} succes composent le catalogue cible des quatre categories.",
        f"- {summary['source_achievements_excluded_by_category']} succes sont ecartes car leur categorie n'est pas retenue.",
        "",
        "## Categories conservees et ordre des zones",
        "",
        "| Ordre | Categorie | Succes | Sous-categories / zones dans l'ordre du jeu |",
        "| ---: | --- | ---: | --- |",
    ]
    for category in audit["definitive_category_order"]:
        children = ", ".join(child["name"] for child in category["subcategories"]) or "Sans sous-categorie"
        lines.append(f"| {category['order']} | {category['name']} | {category['achievement_count']} | {children} |")
    lines.extend(
        [
            "",
            "## Categories supprimees",
            "",
            "| Ordre source | Categorie | Succes ecartes |",
            "| ---: | --- | ---: |",
        ]
    )
    for category in audit["excluded_categories"]:
        lines.append(f"| {category['order']} | {category['name']} | {category['achievement_count']} |")
    lines.extend(
        [
            "",
            "## Ordres d'alignement",
            "",
            "Les six Ordres sont conserves comme branches exclusives. Un personnage selectionne Bonta ou Brakmar puis un Ordre; le suivi utilise exactement ses cinq quetes, dans les rangs 1 a 5.",
            "",
            "| Cite | Ordre | Quetes 1 a 5 | Verification locale |",
            "| --- | --- | --- | --- |",
        ]
    )
    for choice in audit["alignment_orders"]["choices"]:
        quests = " -> ".join(f"{row['name']} (#{row['quest_id']})" for row in choice["quests"])
        lines.append(f"| {choice['side']} | {choice['order']} | {quests} | {'OK' if choice['valid_five_unique_quests'] else 'A VERIFIER'} |")
    checks = audit["checks"]
    lines.extend(
        [
            "",
            "## Controles et donnees incoherentes",
            "",
            f"- Appartenances absentes ou non listees : {len(checks['missing_or_unlisted_category_memberships'])}.",
            f"- Appartenances dans une mauvaise categorie : {len(checks['wrong_category_memberships'])}.",
            f"- Ordres de succes dupliques dans une meme sous-categorie : {len(checks['duplicate_achievement_orders'])}.",
            f"- References d'objectifs declarees mais absentes du fichier source : {len(checks['missing_objective_rows'])} succes concernes.",
            f"- Listes d'objectifs dont l'ordre charge diverge de l'ordre declare : {len(checks['objective_order_mismatches'])}.",
            f"- Six choix d'Ordre avec cinq quetes locales uniques : {'oui' if checks['alignment_choices_all_valid'] else 'non'}.",
            "",
            "Le fichier JSON voisin contient la liste exhaustive des succes conserves et ecartes, chaque objectif, son critere brut, les quetes/monstres/donjons resolus et sa position source.",
            "",
            "## Cas particuliers",
            "",
        ]
    )
    lines.extend(f"- {row}" for row in audit["known_special_cases"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit reproductible du Lot 7 Succès.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA_DIR / "encyclopedia" / "achievements",
    )
    args = parser.parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    audit = build_audit()
    json_path = output_dir / "lot7_work_audit.json"
    markdown_path = output_dir / "lot7_work_audit.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(audit), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "summary": audit["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
