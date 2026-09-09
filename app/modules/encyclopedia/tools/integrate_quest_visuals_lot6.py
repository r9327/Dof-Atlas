from __future__ import annotations

import argparse
import gc
import hashlib
import json
import shutil
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.constants import ROOT_DIR
from app.modules.encyclopedia.tools.enrich_quests import (
    dpln_block_type,
    first_coord,
    flags_from_text,
    interaction_from_text,
    load_manifest,
    npc_from_text,
    portable_asset_path,
    request_bytes,
    save_image,
)
from app.quest_catalog import normalize_text, read_json_file, resolve_local_asset_path, write_json_file


QUESTS_DIR = ROOT_DIR / "data" / "encyclopedia" / "quests"
ENRICHED_PATH = QUESTS_DIR / "quests_enriched.json"
MAPPING_PATH = QUESTS_DIR / "source_mapping.json"
MANIFEST_PATH = QUESTS_DIR / "image_manifest.json"
DEFAULT_VERIFICATION = ROOT_DIR / "artifacts" / "lot6_work_visual_verification.json"
DEFAULT_REPORT = ROOT_DIR / "artifacts" / "lot6_final_integration.json"
DEFAULT_MARKDOWN = ROOT_DIR / "artifacts" / "lot6_final_integration.md"
DEFAULT_CHECKPOINT = ROOT_DIR / "artifacts" / "lot6_final_integration_checkpoint.json"
DEFAULT_BACKUP = ROOT_DIR / "artifacts" / "lot6_final_backup"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_backup(backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for source in (ENRICHED_PATH, MAPPING_PATH, MANIFEST_PATH):
        target = backup_dir / source.name
        if not target.exists():
            shutil.copy2(source, target)


def stream_write_json_file(path: Path, payload: Any) -> None:
    """Stream a large generated JSON payload without duplicating it in RAM."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def actionable_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in payload.get("quests", []) or []
        if isinstance(row, dict) and row.get("category") == "missing_to_integrate"
    ]


def confirmed_pages(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        page
        for page in row.get("pages", []) or []
        if isinstance(page, dict) and str(page.get("association") or "").startswith("confirmed")
    ]


def actionable_images(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        image
        for image in page.get("images", []) or []
        if isinstance(image, dict)
        and image.get("quest_relevance", "specific") == "specific"
        and image.get("local_state") in {"absent_local", "present_unconnected"}
        and image.get("source_url")
    ]


def fetch_with_retry(url: str, attempts: int = 3) -> bytes:
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            return request_bytes(url, timeout=60)
        except Exception as exc:  # reported after the final attempt
            error = exc
            if attempt + 1 < attempts:
                time.sleep(0.4 * (attempt + 1))
    assert error is not None
    raise error


def prefetch(urls: list[str], workers: int) -> dict[str, bytes | Exception]:
    unique = list(dict.fromkeys(url for url in urls if url))
    results: dict[str, bytes | Exception] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 8))) as pool:
        futures = {pool.submit(fetch_with_retry, url): url for url in unique}
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = exc
    return results


def text_block(content: str) -> dict[str, Any]:
    flags = flags_from_text(content)
    block_type = dpln_block_type(content, "", flags)
    return {
        "order": 0,
        "type": block_type,
        "content": content,
        "position": first_coord(content),
        "data": {
            "npc": npc_from_text(content),
            "interaction": interaction_from_text(content),
            **flags,
        },
    }


def image_block(image: dict[str, Any], path: str) -> dict[str, Any]:
    return {
        "order": 0,
        "type": "image",
        "caption": str(image.get("alt") or ""),
        "source_url": str(image.get("source_url") or ""),
        "image_path": portable_asset_path(path),
        "source_order": int(image.get("order") or 0),
        "source_passage_before": str(image.get("passage_before") or ""),
        "source_passage_after": str(image.get("passage_after") or ""),
    }


def block_content_key(block: dict[str, Any]) -> str:
    return normalize_text(str(block.get("content") or block.get("text") or ""))


def block_source_url(block: dict[str, Any]) -> str:
    if str(block.get("type") or block.get("block_type") or "") != "image":
        return ""
    return str(block.get("source_url") or "")


def find_text_index(blocks: list[dict[str, Any]], passage: str) -> int | None:
    key = normalize_text(passage)
    if not key:
        return None
    exact: list[int] = []
    compatible: list[int] = []
    for index, block in enumerate(blocks):
        block_key = block_content_key(block)
        if not block_key:
            continue
        if block_key == key:
            exact.append(index)
        elif len(key) >= 24 and (key in block_key or block_key in key):
            compatible.append(index)
    candidates = exact or compatible
    return candidates[-1] if candidates else None


def source_sequence(
    images: list[dict[str, Any]],
    paths: dict[str, str],
) -> list[dict[str, Any]]:
    ordered = sorted(images, key=lambda image: int(image.get("order") or 0))
    blocks: list[dict[str, Any]] = []
    last_text = ""
    for index, image in enumerate(ordered):
        before = str(image.get("passage_before") or "").strip()
        before_key = normalize_text(before)
        if before and before_key != last_text:
            blocks.append(text_block(before))
            last_text = before_key
        url = str(image.get("source_url") or "")
        if url in paths:
            blocks.append(image_block(image, paths[url]))
        after = str(image.get("passage_after") or "").strip()
        next_before = (
            str(ordered[index + 1].get("passage_before") or "").strip()
            if index + 1 < len(ordered)
            else ""
        )
        if after and normalize_text(after) != normalize_text(next_before):
            after_key = normalize_text(after)
            if after_key != last_text:
                blocks.append(text_block(after))
                last_text = after_key
    return blocks


def insert_images_into_existing(
    existing: list[dict[str, Any]],
    page: dict[str, Any],
    paths: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    blocks = [dict(block) for block in existing if isinstance(block, dict)]
    existing_urls = {block_source_url(block) for block in blocks if block_source_url(block)}
    page_images = [image for image in page.get("images", []) or [] if isinstance(image, dict)]
    targets = [image for image in actionable_images(page) if str(image.get("source_url") or "") in paths]
    added = 0

    if not blocks:
        built = source_sequence(targets, paths)
        return built, sum(str(block.get("type") or "") == "image" for block in built)

    page_order_by_url = {
        str(image.get("source_url") or ""): int(image.get("order") or 0)
        for image in page_images
        if image.get("source_url")
    }
    for image in sorted(targets, key=lambda item: int(item.get("order") or 0)):
        url = str(image.get("source_url") or "")
        if not url or url in existing_urls:
            continue
        source_order = int(image.get("order") or 0)
        known_indices = [
            (index, page_order_by_url.get(block_source_url(block)))
            for index, block in enumerate(blocks)
            if block_source_url(block) in page_order_by_url
        ]
        next_indices = [index for index, order in known_indices if order is not None and order > source_order]
        previous_indices = [index for index, order in known_indices if order is not None and order < source_order]
        before_index = find_text_index(blocks, str(image.get("passage_before") or ""))
        after_index = find_text_index(blocks, str(image.get("passage_after") or ""))

        if next_indices:
            insertion = min(next_indices)
        elif previous_indices:
            insertion = max(previous_indices) + 1
            while insertion < len(blocks) and str(blocks[insertion].get("type") or "") == "image":
                current_order = page_order_by_url.get(block_source_url(blocks[insertion]), -1)
                if current_order > source_order:
                    break
                insertion += 1
        elif before_index is not None:
            insertion = before_index + 1
            while insertion < len(blocks) and str(blocks[insertion].get("type") or "") == "image":
                insertion += 1
        elif after_index is not None:
            insertion = after_index
        elif source_order == 1:
            insertion = 0
        else:
            insertion = len(blocks)
            passage = str(image.get("passage_before") or "").strip()
            if passage and find_text_index(blocks, passage) is None:
                blocks.append(text_block(passage))
                insertion = len(blocks)

        blocks.insert(insertion, image_block(image, paths[url]))
        existing_urls.add(url)
        added += 1
    return blocks, added


def normalize_orders(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for order, block in enumerate(blocks, 1):
        row = {key: value for key, value in block.items() if value not in ("", {}, [])}
        row["order"] = order
        if row.get("type") == "image" and row.get("image_path"):
            row["image_path"] = portable_asset_path(str(row["image_path"]))
        normalized.append(row)
    return normalized


def manifest_path_key(value: Any) -> str:
    normalized = str(value or "").replace("\\", "/").casefold()
    marker = "data/encyclopedia/images/"
    position = normalized.find(marker)
    return normalized[position:] if position >= 0 else normalized


def visual_block_counter(row: dict[str, Any]) -> Counter[str]:
    values: list[str] = []
    for block in row.get("solution_blocks", []) or []:
        if not isinstance(block, dict) or str(block.get("type") or "") != "image":
            continue
        identity = str(block.get("source_url") or block.get("image_path") or "")
        if identity:
            values.append(identity)
    return Counter(values)


def recover_checkpoint_files(
    enriched: dict[str, Any],
    manifest: dict[str, Any],
    target_meta: list[dict[str, Any]],
    backup_dir: Path,
) -> list[dict[str, Any]]:
    """Restore exact checkpoint orphans only when every candidate has the same hash."""

    recovered: list[dict[str, Any]] = []
    by_url = manifest.setdefault("by_url", {})
    by_sha = manifest.setdefault("by_sha256", {})
    for meta in target_meta:
        qid = str(meta["quest_id"])
        row = enriched.get(qid, {}) if isinstance(enriched, dict) else {}
        if not isinstance(row, dict):
            continue
        for block in row.get("solution_blocks", []) or []:
            if not isinstance(block, dict) or str(block.get("type") or "") != "image":
                continue
            target = Path(resolve_local_asset_path(block.get("image_path")))
            if target.exists():
                continue
            source_url = str(block.get("source_url") or "")
            if not source_url:
                continue
            candidates = [
                candidate
                for candidate in backup_dir.rglob(target.name)
                if any(part == qid or part.endswith(f"_{qid}") for part in candidate.parts)
            ]
            if not candidates:
                continue
            candidates_by_hash: dict[str, list[Path]] = {}
            for candidate in candidates:
                digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                candidates_by_hash.setdefault(digest, []).append(candidate)
            if len(candidates_by_hash) != 1:
                continue
            sha256, matching = next(iter(candidates_by_hash.items()))
            candidate = sorted(matching, key=lambda path: str(path))[0]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
            entry = {
                "path": portable_asset_path(target),
                "sha256": sha256,
                "source_url": source_url,
            }
            by_url[source_url] = entry
            by_sha.setdefault(sha256, entry)
            recovered.append(
                {
                    "quest_id": int(qid),
                    "path": portable_asset_path(target),
                    "source_url": source_url,
                    "sha256": sha256,
                    "backup_source": portable_asset_path(candidate),
                }
            )
    return recovered


def reconcile_target_manifest(
    enriched: dict[str, Any],
    manifest: dict[str, Any],
    target_meta: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Index every confirmed visual URL against the exact active local file."""

    reconciled: list[dict[str, Any]] = []
    by_url = manifest.setdefault("by_url", {})
    by_sha = manifest.setdefault("by_sha256", {})
    for meta in target_meta:
        qid = str(meta["quest_id"])
        row = enriched.get(qid, {}) if isinstance(enriched, dict) else {}
        if not isinstance(row, dict):
            continue
        for block in row.get("solution_blocks", []) or []:
            if not isinstance(block, dict) or str(block.get("type") or "") != "image":
                continue
            source_url = str(block.get("source_url") or "")
            target = Path(resolve_local_asset_path(block.get("image_path")))
            if not source_url or not target.exists():
                continue
            existing = by_url.get(source_url)
            if isinstance(existing, dict) and manifest_path_key(existing.get("path")) == manifest_path_key(target):
                continue
            sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
            entry = {
                "path": portable_asset_path(target),
                "sha256": sha256,
                "source_url": source_url,
            }
            by_url[source_url] = entry
            by_sha.setdefault(sha256, entry)
            reconciled.append(
                {
                    "quest_id": int(qid),
                    "path": portable_asset_path(target),
                    "source_url": source_url,
                    "sha256": sha256,
                }
            )
    return reconciled


def merge_mapping(mapping_row: dict[str, Any], quest_row: dict[str, Any]) -> dict[str, Any]:
    row = dict(mapping_row)
    pages = confirmed_pages(quest_row)
    candidates = [
        {
            "title": str(page.get("title") or quest_row.get("name") or ""),
            "slug": Path(str(page.get("url") or "")).stem,
            "url": str(page.get("url") or ""),
            "match": "lot6_work_verified",
            "confidence": "HIGH",
            "signals": [
                "lot6_work_verified",
                *[str(value) for value in page.get("content_evidence", []) or []],
            ],
            "conflicts": [],
        }
        for page in pages
    ]
    existing = [item for item in row.get("dofus_pour_les_noobs", []) or [] if isinstance(item, dict)]
    by_url = {str(item.get("url") or ""): dict(item) for item in existing if item.get("url")}
    for candidate in candidates:
        by_url[candidate["url"]] = candidate
    row["dofus_pour_les_noobs"] = list(by_url.values())
    row["status"] = "matched"
    notes = [
        str(note)
        for note in row.get("notes", []) or []
        if "Mapping ambigu" not in str(note)
    ]
    notes.append("Association visuelle confirmée par artifacts/lot6_work_visual_verification.json.")
    row["notes"] = list(dict.fromkeys(notes))
    return row


def checkpoint(
    enriched_payload: dict[str, Any],
    mapping_payload: dict[str, Any],
    manifest: dict[str, Any],
    state: dict[str, Any],
    checkpoint_path: Path,
) -> None:
    enriched_payload["generated_at"] = now_iso()
    mapping_payload["generated_at"] = now_iso()
    stream_write_json_file(ENRICHED_PATH, enriched_payload)
    stream_write_json_file(MAPPING_PATH, mapping_payload)
    stream_write_json_file(MANIFEST_PATH, manifest)
    write_json_file(checkpoint_path, state)
    gc.collect()


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Lot 6 — Intégration finale CODEX",
        "",
        f"Généré le `{report['generated_at']}`.",
        "",
        "## Résultat",
        "",
        f"- Quêtes enrichies : {summary['quests_enriched']}",
        f"- Références visuelles ajoutées : {summary['visual_references_added']}",
        f"- Nouvelles images téléchargées : {summary['images_downloaded']}",
        f"- Images réutilisées depuis le manifeste : {summary['images_reused']}",
        f"- Fichiers de point de reprise restaurés : {summary['recovered_checkpoint_files']}",
        f"- Entrées de provenance manifeste complétées : {summary['reconciled_manifest_entries']}",
        f"- Échecs de téléchargement ou conversion : {summary['image_errors']}",
        f"- Occurrences WORK exclues car hors `missing_to_integrate` : {summary['excluded_unconfirmed_occurrences']}",
        "",
        "## Quêtes traitées",
        "",
        "| ID | Quête | Références ajoutées | Statut final |",
        "| ---: | --- | ---: | --- |",
    ]
    for row in report.get("quests", []):
        lines.append(
            f"| {row['quest_id']} | {str(row['name']).replace('|', '\\|')} | {row['visual_references_added']} | {row['final_status']} |"
        )
    if report.get("errors"):
        lines.extend(["", "## Erreurs", ""])
        for error in report["errors"]:
            lines.append(f"- Quête {error.get('quest_id')} — {error.get('url')}: {error.get('error')}")
    lines.append("")
    return "\n".join(lines)


def integrate(args: argparse.Namespace) -> dict[str, Any]:
    verification = read_json_file(args.verification, {})
    targets = actionable_rows(verification)
    if len(targets) != 194:
        raise RuntimeError(f"Le rapport WORK doit contenir 194 quêtes actionnables, trouvé: {len(targets)}")

    actionable_occurrences = sum(
        len(actionable_images(page))
        for row in targets
        for page in confirmed_pages(row)
    )
    all_confirmed_missing = sum(
        1
        for row in verification.get("quests", []) or []
        for page in confirmed_pages(row)
        for image in page.get("images", []) or []
        if isinstance(image, dict)
        and image.get("quest_relevance", "specific") == "specific"
        and image.get("local_state") in {"absent_local", "present_unconnected"}
    )
    excluded_unconfirmed = all_confirmed_missing - actionable_occurrences
    if actionable_occurrences != 4642 or excluded_unconfirmed != 363:
        raise RuntimeError(
            "Le périmètre WORK a dérivé: "
            f"actionnable={actionable_occurrences}, exclu_non_confirmé={excluded_unconfirmed}"
        )

    target_meta = [
        {"quest_id": int(row["quest_id"]), "name": str(row.get("name") or "")}
        for row in targets
    ]
    target_count = len(target_meta)
    state = read_json_file(args.checkpoint, {"version": 1, "completed_quest_ids": []})
    state.setdefault("started_at", now_iso())
    state.setdefault("completed_quest_ids", [])
    completed = {int(value) for value in state["completed_quest_ids"]}
    work_targets = [
        row for row in targets if int(row["quest_id"]) not in completed
    ]
    if args.max_quests:
        work_targets = work_targets[: args.max_quests]
    del verification
    del targets
    gc.collect()

    make_backup(args.backup_dir)
    enriched_payload = read_json_file(ENRICHED_PATH, {"quests": {}})
    mapping_payload = read_json_file(MAPPING_PATH, {"quests": {}})
    enriched = enriched_payload.setdefault("quests", {})
    mappings = mapping_payload.setdefault("quests", {})
    manifest = load_manifest()
    stats = dict(state.get("stats") or {"images_downloaded": 0, "images_reused": 0})
    stats.setdefault("images_downloaded", 0)
    stats.setdefault("images_reused", 0)
    errors: list[dict[str, Any]] = [error for error in state.get("errors", []) or [] if isinstance(error, dict)]
    report_by_id: dict[str, dict[str, Any]] = {
        str(key): value
        for key, value in (state.get("quest_reports", {}) or {}).items()
        if isinstance(value, dict)
    }

    processed_this_run = 0
    stopped_early = False
    for index, quest_row in enumerate(work_targets, 1):
        quest_id = int(quest_row["quest_id"])
        qid = str(quest_id)
        if quest_id in completed:
            continue
        errors = [error for error in errors if int(error.get("quest_id") or -1) != quest_id]
        error_count_before = len(errors)
        row = enriched.get(qid, {}) if isinstance(enriched, dict) else {}
        row = dict(row) if isinstance(row, dict) else {}
        existing_blocks = [block for block in row.get("solution_blocks", []) or [] if isinstance(block, dict)]
        existing_urls = {block_source_url(block) for block in existing_blocks if block_source_url(block)}
        pages = confirmed_pages(quest_row)
        required_images = [image for page in pages for image in actionable_images(page)]
        paths: dict[str, str] = {}
        images_to_process = [
            image
            for image in required_images
            if str(image["source_url"]) not in existing_urls
        ]
        for offset in range(0, len(images_to_process), 8):
            image_chunk = images_to_process[offset : offset + 8]
            raw_by_url = prefetch(
                [
                    str(image["source_url"])
                    for image in image_chunk
                    if not (
                        isinstance(
                            (manifest.get("by_url", {}) or {}).get(str(image["source_url"])),
                            dict,
                        )
                        and Path(
                            resolve_local_asset_path(
                                manifest["by_url"][str(image["source_url"])].get("path")
                            )
                        ).exists()
                    )
                ],
                args.workers,
            )
            for image in image_chunk:
                url = str(image["source_url"])
                raw = raw_by_url.get(url)
                if isinstance(raw, Exception):
                    errors.append(
                        {"quest_id": quest_id, "url": url, "error": f"{type(raw).__name__}: {raw}"}
                    )
                    continue
                try:
                    paths[url] = save_image(
                        url,
                        quest_id,
                        int(image.get("order") or 1),
                        1,
                        manifest,
                        stats,
                        raw_data=raw if isinstance(raw, bytes) else None,
                    )
                except Exception as exc:
                    errors.append(
                        {"quest_id": quest_id, "url": url, "error": f"{type(exc).__name__}: {exc}"}
                    )
            raw_by_url.clear()
            del raw_by_url
            gc.collect()

        merged = existing_blocks
        added = 0
        for page in pages:
            merged, page_added = insert_images_into_existing(merged, page, paths)
            added += page_added
        merged = normalize_orders(merged)
        row["solution_blocks"] = merged
        row["source"] = "dofus_pour_les_noobs"
        row["source_url"] = str(pages[0].get("url") or row.get("source_url") or "") if pages else str(row.get("source_url") or "")
        row["source_meta"] = {"title": str(pages[0].get("title") or quest_row.get("name") or "")} if pages else row.get("source_meta", {})
        if str(row.get("status") or "") in {"source_insufficient", "ambiguous", "missing"}:
            row["status"] = "needs_review"
        row["mapping_status"] = "matched"
        row["mapping_confidence"] = "HIGH"
        row["mapping_signals"] = ["lot6_work_verified"]
        quality = dict(row.get("quality") or {})
        quality["block_count"] = len(merged)
        quality["image_count"] = sum(str(block.get("type") or "") == "image" for block in merged)
        quality["lot6_final_integration"] = {
            "integrated_at": now_iso(),
            "source_report": "artifacts/lot6_work_visual_verification.json",
            "visual_references_added": added,
            "source_pages": [str(page.get("url") or "") for page in pages],
        }
        quality["fidelity_alerts"] = [
            alert
            for alert in quality.get("fidelity_alerts", []) or []
            if "image" not in str(alert).casefold()
        ]
        quality["unresolved"] = bool(quality.get("fidelity_alerts"))
        row["quality"] = quality
        enriched[qid] = row
        mappings[qid] = merge_mapping(mappings.get(qid, {}) if isinstance(mappings, dict) else {}, quest_row)

        previous_added = int(
            (report_by_id.get(qid) or {}).get("visual_references_added")
            or (quality.get("lot6_final_integration") or {}).get("visual_references_added")
            or 0
        )
        quest_report = {
            "quest_id": quest_id,
            "name": str(quest_row.get("name") or ""),
            "visual_references_added": previous_added + added,
            "final_status": str(row.get("status") or ""),
        }
        report_by_id[qid] = quest_report
        if len(errors) == error_count_before:
            completed.add(quest_id)
            processed_this_run += 1
        state["completed_quest_ids"] = sorted(completed)
        state["last_quest_id"] = quest_id
        state["updated_at"] = now_iso()
        state["quest_reports"] = report_by_id
        state["stats"] = stats
        state["errors"] = errors
        if args.max_quests and processed_this_run >= args.max_quests:
            checkpoint(enriched_payload, mapping_payload, manifest, state, args.checkpoint)
            print(
                f"Lot 6 CODEX : reprise limitée à {processed_this_run} quête(s), "
                f"{len(completed)}/{target_count} validées au total",
                flush=True,
            )
            stopped_early = True
            break
        if not args.max_quests and (index % args.checkpoint_every == 0 or index == len(work_targets)):
            checkpoint(enriched_payload, mapping_payload, manifest, state, args.checkpoint)
            print(
                f"Lot 6 CODEX : {index}/{target_count} quêtes, "
                f"{stats['images_downloaded']} téléchargées, {stats['images_reused']} réutilisées, "
                f"{len(errors)} erreur(s)",
                flush=True,
            )

    if not stopped_early and work_targets:
        checkpoint(enriched_payload, mapping_payload, manifest, state, args.checkpoint)
    recovered_files = recover_checkpoint_files(enriched, manifest, target_meta, args.backup_dir)
    reconciled_entries = reconcile_target_manifest(enriched, manifest, target_meta)
    if recovered_files or reconciled_entries:
        stream_write_json_file(MANIFEST_PATH, manifest)
        known_recovered = {
            str(item.get("path")): item
            for item in state.get("recovered_checkpoint_files", []) or []
            if isinstance(item, dict)
        }
        for item in recovered_files:
            known_recovered[item["path"]] = item
        state["recovered_checkpoint_files"] = list(known_recovered.values())
        known_reconciled = {
            str(item.get("source_url")): item
            for item in state.get("reconciled_manifest_entries", []) or []
            if isinstance(item, dict)
        }
        for item in reconciled_entries:
            known_reconciled[item["source_url"]] = item
        state["reconciled_manifest_entries"] = list(known_reconciled.values())
        state["updated_at"] = now_iso()
        write_json_file(args.checkpoint, state)
    if len(completed) < target_count:
        return {
            "summary": {
                "quests_completed": len(completed),
                "quests_targeted": target_count,
                "images_downloaded": stats["images_downloaded"],
                "images_reused": stats["images_reused"],
                "image_errors": len(errors),
            },
            "errors": errors,
            "incomplete": True,
        }
    backup_enriched_payload = read_json_file(args.backup_dir / ENRICHED_PATH.name, {"quests": {}})
    backup_enriched = backup_enriched_payload.get("quests", {}) or {}
    quest_reports: list[dict[str, Any]] = []
    for meta in target_meta:
        qid = str(meta["quest_id"])
        current_row = enriched.get(qid, {}) if isinstance(enriched, dict) else {}
        previous_row = backup_enriched.get(qid, {}) if isinstance(backup_enriched, dict) else {}
        current_counter = visual_block_counter(current_row if isinstance(current_row, dict) else {})
        previous_counter = visual_block_counter(previous_row if isinstance(previous_row, dict) else {})
        added = sum((current_counter - previous_counter).values())
        quest_reports.append(
            {
                "quest_id": meta["quest_id"],
                "name": meta["name"],
                "visual_references_added": added,
                "final_status": str(current_row.get("status") or "")
                if isinstance(current_row, dict)
                else "",
            }
        )
    visual_references_added = sum(row["visual_references_added"] for row in quest_reports)
    backup_manifest = read_json_file(args.backup_dir / MANIFEST_PATH.name, {"by_url": {}})
    original_by_url = backup_manifest.get("by_url", {}) or {}
    current_by_url = manifest.get("by_url", {}) or {}
    original_paths = {
        manifest_path_key(entry.get("path"))
        for entry in original_by_url.values()
        if isinstance(entry, dict) and entry.get("path")
    }
    new_manifest_entries = [
        entry
        for url, entry in current_by_url.items()
        if url not in original_by_url and isinstance(entry, dict)
    ]
    new_physical_paths = {
        manifest_path_key(entry.get("path"))
        for entry in new_manifest_entries
        if entry.get("path") and manifest_path_key(entry.get("path")) not in original_paths
    }
    images_downloaded = len(new_physical_paths)
    images_reused = max(0, visual_references_added - images_downloaded)
    report = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "source_report": portable_asset_path(args.verification),
        "backup_dir": portable_asset_path(args.backup_dir),
        "summary": {
            "quests_enriched": sum(row["visual_references_added"] > 0 for row in quest_reports),
            "quests_targeted": target_count,
            "visual_references_added": visual_references_added,
            "images_downloaded": images_downloaded,
            "images_reused": images_reused,
            "new_manifest_urls": len(new_manifest_entries),
            "recovered_checkpoint_files": len(state.get("recovered_checkpoint_files", []) or []),
            "reconciled_manifest_entries": len(state.get("reconciled_manifest_entries", []) or []),
            "image_errors": len(errors),
            "excluded_unconfirmed_occurrences": excluded_unconfirmed,
        },
        "quests": quest_reports,
        "errors": errors,
    }
    write_json_file(args.report, report)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown_report(report), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Intègre uniquement le contenu visuel confirmé par WORK pour le Lot 6.")
    parser.add_argument("--verification", type=Path, default=DEFAULT_VERIFICATION)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--checkpoint-every", type=int, default=5)
    parser.add_argument(
        "--max-quests",
        type=int,
        default=0,
        help="Limite le nombre de nouvelles quêtes de cette reprise (0 = sans limite).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = integrate(args)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
