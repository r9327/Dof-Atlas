from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services.guide_quest_view_model import quest_solution_blocks
from app.quest_catalog import read_json_file, resolve_local_asset_path, write_json_file


QUESTS_DIR = DATA_DIR / "encyclopedia" / "quests"
ENRICHED_PATH = QUESTS_DIR / "quests_enriched.json"
MAPPING_PATH = QUESTS_DIR / "source_mapping.json"
MANIFEST_PATH = QUESTS_DIR / "image_manifest.json"
IMAGES_ROOT = DATA_DIR / "encyclopedia" / "images" / "quests"
DEFAULT_JSON = ROOT_DIR / "artifacts" / "lot6_quest_visuals_audit.json"
DEFAULT_MARKDOWN = ROOT_DIR / "artifacts" / "lot6_quest_visuals_audit.md"


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT_DIR).as_posix()
    except (OSError, ValueError):
        return str(path)


def resolved_path(value: Any) -> Path | None:
    text = resolve_local_asset_path(value)
    return Path(text).resolve() if text else None


def enriched_visual_rows(row: dict[str, Any]) -> list[tuple[int, str, str, str]]:
    result: list[tuple[int, str, str, str]] = []
    blocks = row.get("solution_blocks", []) or []
    if blocks:
        for index, block in enumerate(blocks, 1):
            if not isinstance(block, dict) or str(block.get("type") or block.get("block_type") or "") != "image":
                continue
            path = str(block.get("image_path") or block.get("path") or "")
            if path:
                result.append(
                    (
                        int(block.get("order") or index),
                        path,
                        str(block.get("source_url") or ""),
                        str(block.get("caption") or ""),
                    )
                )
        return result
    order = 0
    for step in row.get("solution_steps", []) or []:
        if not isinstance(step, dict):
            continue
        for objective in step.get("objectives", []) or []:
            if not isinstance(objective, dict):
                continue
            images = objective.get("images", []) or []
            if not images and objective.get("image_path"):
                images = [{"path": objective.get("image_path"), "caption": objective.get("caption")}]
            for image in images:
                if not isinstance(image, dict):
                    continue
                path = str(image.get("path") or image.get("image_path") or "")
                if not path:
                    continue
                order += 1
                result.append(
                    (
                        order,
                        path,
                        str(image.get("source_url") or ""),
                        str(image.get("caption") or ""),
                    )
                )
    return result


def build_audit() -> dict[str, Any]:
    catalog = QuestProvider().get_catalog()
    enriched_payload = read_json_file(ENRICHED_PATH, {"quests": {}})
    enriched = enriched_payload.get("quests", {}) if isinstance(enriched_payload, dict) else {}
    mapping_payload = read_json_file(MAPPING_PATH, {"quests": {}})
    mappings = mapping_payload.get("quests", {}) if isinstance(mapping_payload, dict) else {}
    manifest = read_json_file(MANIFEST_PATH, {"by_url": {}, "by_sha256": {}})

    statuses: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    block_types: Counter[str] = Counter()
    quests_with_visuals: list[dict[str, Any]] = []
    quests_without_visuals: list[dict[str, Any]] = []
    partial_quests: list[dict[str, Any]] = []
    source_insufficient: list[dict[str, Any]] = []
    broken_references: list[dict[str, Any]] = []
    association_mismatches: list[dict[str, Any]] = []
    cross_quest_reuses: list[dict[str, Any]] = []
    references_without_source_url: list[dict[str, Any]] = []
    order_anomalies: list[dict[str, Any]] = []
    referenced_paths: set[Path] = set()
    reference_occurrences = 0
    visual_counts: Counter[int] = Counter()
    manifest_by_url = manifest.get("by_url", {}) if isinstance(manifest, dict) else {}

    for quest in catalog.quests:
        qid = int(quest.id)
        row = enriched.get(str(qid), {}) if isinstance(enriched, dict) else {}
        row = row if isinstance(row, dict) else {}
        status = str(row.get("status") or "unknown")
        source = str(row.get("source") or "none")
        statuses[status] += 1
        sources[source] += 1
        for block in row.get("solution_blocks", []) or []:
            if isinstance(block, dict):
                block_types[str(block.get("type") or block.get("block_type") or "unknown")] += 1

        visuals = enriched_visual_rows(row)
        reference_occurrences += len(visuals)
        visual_counts[len(visuals)] += 1
        quest_row = {
            "quest_id": qid,
            "name": quest.name,
            "status": status,
            "source": source,
            "visual_count": len(visuals),
        }
        if visuals:
            quests_with_visuals.append(quest_row)
        else:
            quests_without_visuals.append(quest_row)
        if status in {"needs_review", "ambiguous"}:
            partial_quests.append(quest_row)
        if status == "source_insufficient":
            source_insufficient.append(quest_row)

        orders = [order for order, _path, _url, _caption in visuals]
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            order_anomalies.append({**quest_row, "orders": orders})
        for order, raw_path, source_url, caption in visuals:
            path = resolved_path(raw_path)
            if path is None or not path.exists():
                broken_references.append(
                    {**quest_row, "order": order, "path": raw_path, "source_url": source_url}
                )
                continue
            referenced_paths.add(path)
            if path.parent.name != str(qid):
                cross_quest_reuses.append(
                    {
                        **quest_row,
                        "order": order,
                        "path": relative(path),
                        "directory_quest_id": path.parent.name,
                        "caption": caption,
                    }
                )
            if not source_url:
                references_without_source_url.append(
                    {**quest_row, "order": order, "path": relative(path)}
                )
                continue
            manifest_row = manifest_by_url.get(source_url) if isinstance(manifest_by_url, dict) else None
            manifest_path = resolved_path(manifest_row.get("path")) if isinstance(manifest_row, dict) else None
            if manifest_path is None or manifest_path != path:
                association_mismatches.append(
                    {
                        **quest_row,
                        "order": order,
                        "path": relative(path),
                        "source_url": source_url,
                        "manifest_path": relative(manifest_path) if manifest_path is not None else "",
                    }
                )

    physical_paths = {
        path.resolve()
        for path in IMAGES_ROOT.rglob("*")
        if path.is_file()
    }
    unused_paths = physical_paths - referenced_paths
    manifest_paths = {
        path
        for row in (manifest.get("by_sha256", {}) or {}).values()
        if isinstance(row, dict)
        for path in [resolved_path(row.get("path"))]
        if path is not None and path.exists()
    }
    unused_with_manifest = sorted(unused_paths & manifest_paths)
    legacy_orphans = sorted(unused_paths - manifest_paths)
    unknown_quest_directories = sorted(
        path
        for path in unused_paths
        if not path.parent.name.isdigit() or int(path.parent.name) not in catalog.by_id
    )

    runtime_image_paths = {
        Path(block.image_path).resolve()
        for quest in catalog.quests
        for block in quest_solution_blocks(quest)
        if block.block_type == "image" and block.image_path and Path(block.image_path).exists()
    }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "network_used": False,
        "catalog_quests": len(catalog.quests),
        "mapping_rows": len(mappings) if isinstance(mappings, dict) else 0,
        "status_counts": dict(statuses),
        "source_counts": dict(sources),
        "ordered_block_types": dict(block_types),
        "quests_with_connected_visuals": len(quests_with_visuals),
        "quests_without_connected_visuals": len(quests_without_visuals),
        "quests_with_one_visual": visual_counts.get(1, 0),
        "quests_with_multiple_visuals": sum(count for amount, count in visual_counts.items() if amount > 1),
        "visual_reference_occurrences": reference_occurrences,
        "unique_connected_visual_files": len(referenced_paths),
        "runtime_shared_sheet_visual_files": len(runtime_image_paths),
        "physical_quest_image_files": len(physical_paths),
        "present_but_not_connected": len(unused_paths),
        "present_with_manifest_but_not_connected": len(unused_with_manifest),
        "legacy_orphan_files": len(legacy_orphans),
        "unknown_quest_directory_files": len(unknown_quest_directories),
        "broken_visual_references": len(broken_references),
        "source_manifest_mismatches": len(association_mismatches),
        "references_without_source_url": len(references_without_source_url),
        "cross_quest_reused_visual_occurrences": len(cross_quest_reuses),
        "visual_order_anomalies": len(order_anomalies),
        "partial_or_ambiguous_quests": len(partial_quests),
        "source_insufficient_quests": len(source_insufficient),
    }
    return {
        "schema_version": 1,
        "summary": summary,
        "classification": {
            "complete_source_rows": [
                row for row in [*quests_with_visuals, *quests_without_visuals] if row["status"] == "complete"
            ],
            "present_but_not_connected": [relative(path) for path in sorted(unused_paths)],
            "present_with_manifest_but_not_connected": [relative(path) for path in unused_with_manifest],
            "legacy_orphans": [relative(path) for path in legacy_orphans],
            "partial_or_ambiguous": partial_quests,
            "source_insufficient": source_insufficient,
            "without_connected_visuals": quests_without_visuals,
            "broken_references": broken_references,
        },
        "integrity": {
            "source_manifest_mismatches": association_mismatches,
            "references_without_source_url": references_without_source_url,
            "cross_quest_reuses": cross_quest_reuses,
            "visual_order_anomalies": order_anomalies,
            "unknown_quest_directory_files": [relative(path) for path in unknown_quest_directories],
        },
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    statuses = summary["status_counts"]
    return "\n".join(
        [
            "# Lot 6 — Audit local des visuels de quêtes",
            "",
            f"Généré le `{summary['generated_at']}`. Aucun accès Internet n'a été utilisé.",
            "",
            "## Bilan",
            "",
            f"- Quêtes du catalogue : {summary['catalog_quests']}",
            f"- Sources locales complètes : {statuses.get('complete', 0)}",
            f"- Quêtes partielles ou ambiguës : {summary['partial_or_ambiguous_quests']}",
            f"- Sources locales insuffisantes : {summary['source_insufficient_quests']}",
            f"- Quêtes avec visuels raccordés : {summary['quests_with_connected_visuals']}",
            f"- Quêtes sans preuve visuelle locale raccordée : {summary['quests_without_connected_visuals']}",
            f"- Quêtes avec plusieurs visuels : {summary['quests_with_multiple_visuals']}",
            f"- Fichiers visuels uniques raccordés : {summary['unique_connected_visual_files']}",
            f"- Fichiers physiques présents : {summary['physical_quest_image_files']}",
            f"- Présents mais non raccordés : {summary['present_but_not_connected']}",
            f"  - encore connus du manifeste : {summary['present_with_manifest_but_not_connected']}",
            f"  - orphelins historiques hors manifeste : {summary['legacy_orphan_files']}",
            "",
            "## Intégrité",
            "",
            f"- Références cassées : {summary['broken_visual_references']}",
            f"- Divergences URL source / manifeste : {summary['source_manifest_mismatches']}",
            f"- Références sans URL source : {summary['references_without_source_url']}",
            f"- Réutilisations démontrées d'un même visuel entre plusieurs quêtes : {summary['cross_quest_reused_visual_occurrences']}",
            f"- Anomalies d'ordre : {summary['visual_order_anomalies']}",
            f"- Fichiers dans un dossier de quête inconnu : {summary['unknown_quest_directory_files']}",
            "",
            "Les listes exhaustives sont conservées dans le rapport JSON associé. Les fichiers non raccordés ne sont pas supprimés ni associés automatiquement sans preuve de leur passage exact.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit 100 % local des images et indications visuelles des quêtes.")
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args(argv)
    payload = build_audit()
    write_json_file(args.output, payload)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
