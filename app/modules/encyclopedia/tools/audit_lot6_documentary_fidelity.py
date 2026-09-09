from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.constants import ROOT_DIR
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services.guide_quest_view_model import (
    quest_solution_blocks,
    quest_solution_steps,
    quest_start_info,
)
from app.quest_catalog import normalize_text, resolve_local_asset_path


QUESTS_PATH = ROOT_DIR / "data" / "encyclopedia" / "quests" / "quests_enriched.json"
WORK_REPORT_PATH = ROOT_DIR / "artifacts" / "lot6_work_visual_verification.json"
JSON_REPORT_PATH = ROOT_DIR / "artifacts" / "lot6_documentary_fidelity_audit.json"
MARKDOWN_REPORT_PATH = ROOT_DIR / "artifacts" / "lot6_documentary_fidelity_audit.md"
SAMPLE_IDS = (72, 26, 29, 595, 2157, 2464)


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def legacy_visual_count(row: dict[str, Any]) -> int:
    count = 0
    for step in row.get("solution_steps") or []:
        if not isinstance(step, dict):
            continue
        for objective in step.get("objectives") or []:
            if not isinstance(objective, dict):
                continue
            images = [image for image in objective.get("images") or [] if isinstance(image, dict)]
            count += len(images) if images else int(bool(objective.get("image_path")))
    return count


def documentary_text_count(row: dict[str, Any]) -> int:
    return sum(
        1
        for block in row.get("solution_blocks") or []
        if isinstance(block, dict)
        and str(block.get("type") or block.get("block_type") or "") != "image"
        and str(block.get("content") or block.get("text") or "").strip()
    )


def build_report() -> dict[str, Any]:
    raw = read_json(QUESTS_PATH, {}).get("quests", {})
    work = read_json(WORK_REPORT_PATH, {})
    work_summary = work.get("summary") if isinstance(work, dict) else {}
    provider = QuestProvider()
    catalog = provider.get_catalog()

    counts = Counter()
    broken_images: list[dict[str, Any]] = []
    order_anomalies: list[dict[str, Any]] = []
    sample: list[dict[str, Any]] = []

    for quest_id_text, row in raw.items():
        if not isinstance(row, dict):
            continue
        counts["quests"] += 1
        explicit_blocks = [block for block in row.get("solution_blocks") or [] if isinstance(block, dict)]
        documentary_texts = documentary_text_count(row)
        legacy_steps = [step for step in row.get("solution_steps") or [] if isinstance(step, dict)]
        legacy_visuals = legacy_visual_count(row)

        if explicit_blocks and documentary_texts:
            counts["documentary_complete"] += 1
        elif legacy_steps:
            counts["simplified_objective_fallback"] += 1
        else:
            counts["no_enriched_local_text"] += 1
        if not (explicit_blocks and documentary_texts):
            counts["insufficient_documentary_text"] += 1

        source_meta = row.get("source_meta") if isinstance(row.get("source_meta"), dict) else {}
        launch = row.get("launch_position") if isinstance(row.get("launch_position"), dict) else {}
        if launch.get("position") or source_meta.get("startCoords"):
            counts["launch_position"] += 1
        if source_meta.get("startMapImage"):
            counts["raw_start_map_reference"] += 1
            resolved = resolve_local_asset_path(source_meta.get("startMapImage"))
            if resolved and Path(resolved).is_file():
                counts["raw_start_map_local"] += 1

        quest = catalog.by_id.get(int(quest_id_text))
        if quest is not None:
            start = quest_start_info(quest)
            if start.map_image_path:
                counts["displayed_start_map"] += 1
            visible_blocks = quest_solution_blocks(quest)
            visible_images = [block for block in visible_blocks if block.block_type == "image"]
            counts["visible_documentary_images"] += len(visible_images)
            counts["hidden_unproven_legacy_images"] += legacy_visuals if not explicit_blocks else 0
            for block in visible_images:
                if not Path(block.image_path).is_file():
                    broken_images.append(
                        {"quest_id": int(quest_id_text), "name": quest.name, "path": block.image_path}
                    )

        orders = [int(block.get("order") or index) for index, block in enumerate(explicit_blocks, 1)]
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            order_anomalies.append(
                {"quest_id": int(quest_id_text), "name": str(row.get("name") or ""), "orders": orders}
            )

    counts["without_displayable_start_map"] = counts["quests"] - counts["displayed_start_map"]
    counts["without_raw_start_map_reference"] = counts["quests"] - counts["raw_start_map_reference"]
    unresolved_associations = max(
        0,
        int((work.get("scope") or {}).get("priority_ambiguous") or 0)
        - int((work_summary or {}).get("ambiguous_associations_resolved") or 0),
    )

    for quest_id in SAMPLE_IDS:
        quest = catalog.by_id.get(quest_id)
        row = raw.get(str(quest_id), {})
        if quest is None:
            continue
        start = quest_start_info(quest)
        display_blocks = quest_solution_blocks(quest)
        sample.append(
            {
                "quest_id": quest_id,
                "name": quest.name,
                "documentary_status": (
                    "complete_local_blocks"
                    if row.get("solution_blocks") and documentary_text_count(row)
                    else "simplified_objectives_only"
                    if row.get("solution_steps")
                    else "insufficient_local_text"
                ),
                "documentary_text_blocks": sum(block.block_type != "image" for block in display_blocks),
                "documentary_images": sum(block.block_type == "image" for block in display_blocks),
                "hidden_legacy_images": legacy_visual_count(row) if not row.get("solution_blocks") else 0,
                "fallback_objective_groups": len(quest_solution_steps(quest)) if not display_blocks else 0,
                "launch_position": start.position,
                "launch_zone": start.zone,
                "launch_map_displayed": bool(start.map_image_path),
                "artificial_step_headings_displayed": sum(
                    block.block_type == "heading"
                    and normalize_text(block.content.rstrip(" :")).replace("etape_", "").isdigit()
                    for block in display_blocks
                ),
            }
        )

    colonie = next((row for row in sample if row["quest_id"] == 2464), {})
    colonie_conclusion = (
        f"Position {colonie.get('launch_position') or 'absente'} et zone "
        f"{colonie.get('launch_zone') or 'absente'}. "
        f"Le document local contient {colonie.get('documentary_text_blocks', 0)} bloc(s) de texte, "
        f"{colonie.get('documentary_images', 0)} image(s) de déroulement et "
        f"{'une map de lancement locale' if colonie.get('launch_map_displayed') else 'aucune map de lancement locale'}. "
        f"Les références legacy non documentaires restent masquées."
    )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Lot 6 local documentary rendering only; no network or downloads",
        "texts": {
            "quests_total": counts["quests"],
            "documentary_complete": counts["documentary_complete"],
            "simplified_objective_fallback": counts["simplified_objective_fallback"],
            "insufficient_documentary_text_total": counts["insufficient_documentary_text"],
            "no_enriched_local_text": counts["no_enriched_local_text"],
        },
        "launch": {
            "with_launch_position": counts["launch_position"],
            "with_displayed_local_start_map": counts["displayed_start_map"],
            "without_displayable_local_start_map": counts["without_displayable_start_map"],
            "raw_start_map_references": counts["raw_start_map_reference"],
            "raw_start_map_references_resolved_locally": counts["raw_start_map_local"],
            "without_raw_start_map_reference": counts["without_raw_start_map_reference"],
        },
        "images": {
            "currently_displayed_documentary_references": counts["visible_documentary_images"],
            "hidden_unproven_legacy_references": counts["hidden_unproven_legacy_images"],
            "documentary_references_kept": counts["visible_documentary_images"],
            "unresolved_associations": unresolved_associations,
            "broken_displayed_references": len(broken_images),
            "broken_displayed_reference_details": broken_images,
        },
        "order": {
            "anomalies": len(order_anomalies),
            "details": order_anomalies,
        },
        "work_constraints_preserved": {
            "impossible_to_confirm": int(
                ((work_summary or {}).get("quest_categories") or {}).get("impossible_to_confirm") or 0
            ),
            "unresolved_ids": [517, 775] if unresolved_associations == 2 else [],
        },
        "representative_sample": sample,
        "colonie_de_vaillance_conclusion": colonie_conclusion,
    }


def markdown_report(report: dict[str, Any]) -> str:
    texts = report["texts"]
    launch = report["launch"]
    images = report["images"]
    lines = [
        "# Lot 6 — audit de fidélité documentaire locale",
        "",
        "> Périmètre : rendu local uniquement, sans Internet ni téléchargement.",
        "",
        "## Textes",
        "",
        f"- Quêtes avec blocs documentaires complets : **{texts['documentary_complete']}**",
        f"- Quêtes encore affichées via objectifs simplifiés : **{texts['simplified_objective_fallback']}**",
        f"- Quêtes sans texte documentaire local suffisant : **{texts['insufficient_documentary_text_total']}**",
        f"- Dont sans texte enrichi exploitable : **{texts['no_enriched_local_text']}**",
        "",
        "## Départ de quête",
        "",
        f"- Positions de lancement explicites : **{launch['with_launch_position']}**",
        f"- Maps de départ explicitement raccordées à un fichier local : **{launch['with_displayed_local_start_map']}**",
        f"- Sans visuel de départ local affichable : **{launch['without_displayable_local_start_map']}**",
        f"- Références brutes de map de départ non raccordées localement : **{launch['raw_start_map_references'] - launch['raw_start_map_references_resolved_locally']}**",
        f"- Sans référence source de map de départ : **{launch['without_raw_start_map_reference']}**",
        "",
        "## Images de solution",
        "",
        f"- Références documentaires affichées/conservées : **{images['currently_displayed_documentary_references']}**",
        f"- Références legacy masquées faute de preuve documentaire : **{images['hidden_unproven_legacy_references']}**",
        f"- Associations restant non résolues : **{images['unresolved_associations']}**",
        f"- Références affichées cassées : **{images['broken_displayed_references']}**",
        "",
        "## Échantillon représentatif",
        "",
        "| ID | Quête | Statut texte | Position | Map | Images doc. | Images masquées |",
        "|---:|---|---|---|---:|---:|---:|",
    ]
    for row in report["representative_sample"]:
        lines.append(
            f"| {row['quest_id']} | {row['name']} | {row['documentary_status']} | "
            f"{row['launch_zone']} {row['launch_position']} | "
            f"{'oui' if row['launch_map_displayed'] else 'non'} | "
            f"{row['documentary_images']} | {row['hidden_legacy_images']} |"
        )
    lines.extend(
        [
            "",
            "## Cas obligatoire : Colonie de vaillance",
            "",
            report["colonie_de_vaillance_conclusion"],
            "",
            "## Intégrité",
            "",
            f"- Anomalies d'ordre des blocs explicites : **{report['order']['anomalies']}**",
            f"- Quêtes toujours impossibles à confirmer selon WORK : **{report['work_constraints_preserved']['impossible_to_confirm']}**",
            f"- IDs ambigus non forcés : **{', '.join(map(str, report['work_constraints_preserved']['unresolved_ids'])) or 'aucun'}**",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=JSON_REPORT_PATH)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN_REPORT_PATH)
    args = parser.parse_args()
    report = build_report()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("texts", "launch", "images", "order")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
