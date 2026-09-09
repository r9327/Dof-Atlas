from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.constants import ROOT_DIR
from app.modules.encyclopedia.tools.enrich_quests import (
    QUEST_IMAGES_DIR,
    TokenParser,
    clean_text,
    extract_dpln_page_v2,
    first_coord,
    full_url,
    portable_asset_path,
    request_bytes,
    skip_dpln_text,
    useful_image,
)
from app.modules.encyclopedia.tools.verify_quest_visuals_work import (
    classify_page_for_quest,
    image_matches_signals,
    page_content,
    select_confirmed_pages,
)
from app.quest_catalog import QuestCatalog, normalize_text, read_json_file, resolve_local_asset_path, write_json_file


ARTIFACTS = ROOT_DIR / "artifacts"
QUESTS_DIR = ROOT_DIR / "data" / "encyclopedia" / "quests"
ENRICHED_PATH = QUESTS_DIR / "quests_enriched.json"
MAPPING_PATH = QUESTS_DIR / "source_mapping.json"
MANIFEST_PATH = QUESTS_DIR / "image_manifest.json"
DEFAULT_REGISTRY = ARTIFACTS / "lot6_work_final_for_codex.json"
DEFAULT_JOURNAL = ARTIFACTS / "lot6_codex_direct_validation.jsonl"
DEFAULT_STATE = ARTIFACTS / "lot6_codex_direct_integration_checkpoint.json"
DEFAULT_REPORT = ARTIFACTS / "lot6_codex_direct_integration.json"
DEFAULT_MARKDOWN = ARTIFACTS / "lot6_codex_direct_integration.md"
DEFAULT_AUTHORIZED_PLACEMENTS = ARTIFACTS / "lot6_codex_authorized_content_placements.jsonl"
DEFAULT_BACKUP = ARTIFACTS / "lot6_codex_direct_backup"

CONTENT_KEY = "content_images_pending_direct_validation"
MAP_KEY = "start_maps_pending_direct_validation"
TERMINAL_STATUSES = {"confirmed", "rejected", "uncertain"}
VALIDATOR_VERSION = 2
BASE_CHECKS = (
    "page_opened_directly_on_dofus_noob",
    "correct_dofus_noob_page",
    "quest_match_confirmed",
    "image_present_in_guide_body",
    "exact_image_confirmed",
    "previous_block_confirmed",
    "next_block_confirmed",
    "relative_visual_order_confirmed",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_with_retry(url: str, attempts: int, timeout: int) -> bytes:
    error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return request_bytes(url, timeout=timeout)
        except Exception as exc:  # preserved in the candidate report
            error = exc
            if attempt + 1 < attempts:
                time.sleep(0.4 * (attempt + 1))
    assert error is not None
    raise error


def prefetch_candidate_images(
    candidates: list[dict[str, Any]],
    attempts: int,
    timeout: int,
    workers: int,
) -> dict[str, bytes | Exception]:
    urls = list(
        dict.fromkeys(
            str(candidate.get("image", {}).get("source_url") or "")
            for candidate in candidates
            if candidate.get("image", {}).get("source_url")
        )
    )
    results: dict[str, bytes | Exception] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 8))) as executor:
        futures = {executor.submit(fetch_with_retry, url, attempts, timeout): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = exc
    return results


def ordered_metadata(payload: bytes, page_url: str, quest_name: str) -> list[dict[str, Any]]:
    parser = TokenParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    blocks: list[dict[str, Any]] = []
    image_order = 0
    for token in parser.tokens:
        if token.get("type") == "image":
            source_url = full_url(str(token.get("src") or ""), page_url)
            if useful_image(source_url, "dpln"):
                image_order += 1
                blocks.append(
                    {
                        "order": len(blocks) + 1,
                        "type": "image",
                        "source_url": source_url,
                        "source_image_order": image_order,
                        "alt": clean_text(token.get("alt") or ""),
                    }
                )
            continue
        text = clean_text(token.get("text") or "")
        if skip_dpln_text(text, quest_name):
            continue
        blocks.append(
            {
                "order": len(blocks) + 1,
                "type": "text",
                "word_count": len(text.split()),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "position": first_coord(text),
                "content": text,
            }
        )
    return blocks


def registry_candidates(registry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups = registry.get("work_whitelist_candidates")
    if not isinstance(groups, dict):
        raise RuntimeError("Le registre CODEX ne contient pas work_whitelist_candidates.")
    content = [row for row in groups.get(CONTENT_KEY, []) or [] if isinstance(row, dict)]
    maps = [row for row in groups.get(MAP_KEY, []) or [] if isinstance(row, dict)]
    if len(content) != 9068 or len(maps) != 363:
        raise RuntimeError(f"Périmètre candidat inattendu: contenu={len(content)}, maps={len(maps)}")
    identifiers = [str(row.get("candidate_id") or "") for row in [*content, *maps]]
    if not all(identifiers) or len(set(identifiers)) != len(identifiers):
        raise RuntimeError("Les candidate_id du registre ne sont pas complets et uniques.")
    return content, maps


def append_journal(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()


def journal_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Journal invalide ligne {line_number}: {exc}") from exc
            candidate_id = str(row.get("candidate_id") or "")
            if candidate_id and row.get("event") == "validation":
                rows[candidate_id] = row
    return rows


def apply_validation(candidate: dict[str, Any], event: dict[str, Any]) -> None:
    previous_integration = dict(candidate.get("integration") or {})
    candidate["integration_authorized"] = bool(event.get("integration_authorized"))
    candidate["direct_validation"] = dict(event.get("direct_validation") or {})
    event_integration = dict(event.get("integration") or {})
    if (
        previous_integration.get("status") == "integrated"
        and candidate["integration_authorized"]
        and previous_integration.get("local_path") == event_integration.get("local_path")
    ):
        candidate["integration"] = previous_integration
    else:
        candidate["integration"] = event_integration


def restore_journal(registry_index: dict[str, dict[str, Any]], journal: Path) -> int:
    restored = 0
    for candidate_id, event in journal_rows(journal).items():
        candidate = registry_index.get(candidate_id)
        if candidate is None:
            raise RuntimeError(f"Le journal référence un candidat absent du registre: {candidate_id}")
        apply_validation(candidate, event)
        restored += 1
    return restored


def ensure_backup(path: Path, registry_path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for source in (ENRICHED_PATH, MAPPING_PATH, MANIFEST_PATH, registry_path):
        target = path / source.name
        if not target.exists():
            shutil.copy2(source, target)


def page_context(
    payload: bytes,
    page_url: str,
    quest_name: str,
) -> dict[str, Any]:
    content = page_content(payload, page_url, quest_name)
    extraction = extract_dpln_page_v2(payload, page_url, quest_name)
    return {
        "payload": payload,
        "page_sha256": hashlib.sha256(payload).hexdigest(),
        "content": content,
        "extraction": extraction,
        "ordered": ordered_metadata(payload, page_url, quest_name),
        "association": "",
        "fetch_error": "",
    }


def fetch_quest_pages(
    quest: Any,
    candidates: list[dict[str, Any]],
    duplicate_ids: list[int],
    catalog: QuestCatalog,
    attempts: int,
    timeout: int,
    delay: float,
) -> dict[str, dict[str, Any]]:
    urls = list(dict.fromkeys(str(row["quest"]["page_url"]) for row in candidates))
    contexts: dict[str, dict[str, Any]] = {}
    association_rows: list[dict[str, Any]] = []
    for index, url in enumerate(urls):
        if index and delay:
            time.sleep(delay)
        try:
            context = page_context(fetch_with_retry(url, attempts, timeout), url, str(quest.name))
            association = classify_page_for_quest(quest, context["content"], duplicate_ids, catalog)
            context["association"] = str(association.get("association") or "")
            context["association_evidence"] = association
            association_row = {**context["content"], **association}
            association_rows.append(association_row)
        except Exception as exc:
            context = {
                "fetch_error": f"{type(exc).__name__}: {exc}",
                "association": "fetch_error",
                "association_evidence": {},
                "ordered": [],
                "content": {"images": []},
                "extraction": {"blocks": [], "quality": {}, "launch_position": {}},
            }
            association_rows.append({"url": url, "association": "fetch_error"})
        contexts[url] = context
    select_confirmed_pages(quest, association_rows)
    for row in association_rows:
        url = str(row.get("url") or "")
        if url in contexts:
            contexts[url]["association"] = str(row.get("association") or contexts[url]["association"])
            contexts[url]["association_evidence"] = {
                key: row.get(key)
                for key in (
                    "association",
                    "title_similarity",
                    "exact_title",
                    "content_evidence",
                    "duplicate_unique_signals",
                    "duplicate_unique_evidence",
                )
                if key in row
            }
    return contexts


def nearest_text(ordered: list[dict[str, Any]], index: int, reverse: bool) -> dict[str, Any]:
    rows = reversed(ordered[:index]) if reverse else iter(ordered[index + 1 :])
    return next((row for row in rows if row.get("type") == "text"), {})


def image_context_at(context: dict[str, Any], source_image_order: int) -> dict[str, Any]:
    images = context.get("content", {}).get("images", []) or []
    if 1 <= source_image_order <= len(images):
        return images[source_image_order - 1]
    return {}


def source_body_boundary(context: dict[str, Any]) -> int:
    quality = context.get("extraction", {}).get("quality", {}) or {}
    return max(0, int(quality.get("source_image_count") or 0) - int(quality.get("image_block_count") or 0))


def launch_role_confirmed(context: dict[str, Any], image_row: dict[str, Any]) -> bool:
    passage = "\n".join(
        str(image_row.get(key) or "") for key in ("passage_before", "passage_after", "alt")
    )
    key = normalize_text(passage)
    context_position = first_coord(passage).replace(" ", "")
    launch = context.get("extraction", {}).get("launch_position", {}) or {}
    launch_position = str(launch.get("position") or "").replace(" ", "")
    marker = any(value in key for value in ("quete_se_lance", "position_de_lancement", "lancer_la_quete"))
    return bool(marker and context_position and launch_position and context_position == launch_position)


def active_manifest_path(entry: Any) -> str:
    if not isinstance(entry, dict) or not entry.get("path"):
        return ""
    resolved = Path(resolve_local_asset_path(entry["path"]))
    return portable_asset_path(resolved) if resolved.is_file() else ""


def store_image(
    candidate: dict[str, Any],
    payload: bytes,
    manifest: dict[str, Any],
) -> tuple[str, str, str]:
    url = str(candidate["image"]["source_url"])
    by_url = manifest.setdefault("by_url", {})
    by_sha = manifest.setdefault("by_sha256", {})
    existing_path = active_manifest_path(by_url.get(url))
    raw_sha256 = hashlib.sha256(payload).hexdigest()
    if existing_path:
        return existing_path, raw_sha256, "manifest_url_reuse"
    reused_path = active_manifest_path(by_sha.get(raw_sha256))
    if reused_path:
        row = {"path": reused_path, "sha256": raw_sha256, "source_url": url}
        by_url[url] = row
        return reused_path, raw_sha256, "manifest_sha256_reuse"

    quest_id = int(candidate["quest"]["quest_id"])
    folder = QUEST_IMAGES_DIR / str(quest_id)
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"lot6_{str(candidate['candidate_id'])[:20]}"
    target = folder / f"{stem}.webp"
    suffix = 2
    while target.exists():
        try:
            with Image.open(target) as previous, Image.open(BytesIO(payload)) as source:
                if previous.size == source.size:
                    local = portable_asset_path(target)
                    row = {"path": local, "sha256": raw_sha256, "source_url": url}
                    by_url[url] = row
                    by_sha.setdefault(raw_sha256, row)
                    return local, raw_sha256, "deterministic_file_reuse"
        except (OSError, UnidentifiedImageError):
            pass
        target = folder / f"{stem}_{suffix}.webp"
        suffix += 1

    with Image.open(BytesIO(payload)) as source:
        source.load()
        image = source if source.mode in {"RGB", "RGBA"} else source.convert("RGBA")
        image.save(target, format="WEBP", quality=85, method=6)
    local = portable_asset_path(target)
    row = {"path": local, "sha256": raw_sha256, "source_url": url}
    by_url[url] = row
    by_sha.setdefault(raw_sha256, row)
    return local, raw_sha256, "downloaded"


def reconcile_authorized_manifest(
    candidates: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> int:
    by_url = manifest.setdefault("by_url", {})
    by_sha = manifest.setdefault("by_sha256", {})
    reconciled = 0
    for candidate in candidates:
        if not candidate.get("integration_authorized"):
            continue
        integration = candidate.get("integration") or {}
        local_path = str(integration.get("local_path") or "")
        resolved = Path(resolve_local_asset_path(local_path))
        source_url = str((candidate.get("image") or {}).get("source_url") or "")
        sha256 = str(
            ((candidate.get("direct_validation") or {}).get("evidence") or {}).get("direct_image_sha256")
            or ""
        )
        if not source_url or not sha256 or not resolved.is_file():
            continue
        portable = portable_asset_path(resolved)
        existing = by_url.get(source_url)
        if isinstance(existing, dict) and active_manifest_path(existing) == portable:
            continue
        entry = {"path": portable, "sha256": sha256, "source_url": source_url}
        by_url[source_url] = entry
        by_sha.setdefault(sha256, entry)
        reconciled += 1
    return reconciled


def validation_event(
    candidate: dict[str, Any],
    context: dict[str, Any],
    duplicate_ids: list[int],
    catalog: QuestCatalog,
    manifest: dict[str, Any],
    attempts: int,
    timeout: int,
    image_delay: float,
    prefetched_images: dict[str, bytes | Exception] | None = None,
) -> dict[str, Any]:
    candidate_id = str(candidate["candidate_id"])
    is_map = str(candidate.get("work_classification") or "") == "start_map_only"
    checks: dict[str, bool | None] = {key: None for key in BASE_CHECKS}
    if is_map:
        checks["launch_map_role_confirmed"] = None
    reasons: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    status = "rejected"
    image_payload: bytes | None = None

    if context.get("fetch_error"):
        checks["page_opened_directly_on_dofus_noob"] = False
        reasons.append({"code": "page_fetch_error", "detail": str(context["fetch_error"])})
        status = "uncertain"
    else:
        checks["page_opened_directly_on_dofus_noob"] = True
        requested_url = str(candidate["quest"]["page_url"])
        checks["correct_dofus_noob_page"] = bool(
            requested_url.startswith("https://www.dofuspourlesnoobs.com/")
            and str(context.get("content", {}).get("url") or "") == requested_url
        )
        association = str(context.get("association") or "")
        checks["quest_match_confirmed"] = association.startswith("confirmed")
        if association.startswith("unresolved"):
            status = "uncertain"
            reasons.append({"code": "quest_association_uncertain", "detail": association})
        elif not checks["quest_match_confirmed"]:
            reasons.append({"code": "quest_association_rejected", "detail": association})

        image = candidate.get("image", {}) or {}
        document_order = int(
            (candidate.get("documentary_placement") or {}).get("image_documentary_order") or 0
        )
        source_order = int(image.get("source_image_order") or 0)
        ordered = context.get("ordered", []) or []
        index = document_order - 1
        direct_block = ordered[index] if 0 <= index < len(ordered) else {}
        direct_image = image_context_at(context, source_order)
        source_url = str(image.get("source_url") or "")
        direct_url_match = bool(
            direct_block.get("type") == "image"
            and direct_block.get("source_url") == source_url
            and direct_image.get("source_url") == source_url
        )
        boundary = source_body_boundary(context)
        checks["image_present_in_guide_body"] = bool(direct_url_match and source_order > boundary)

        previous = nearest_text(ordered, index, reverse=True) if direct_block else {}
        following = nearest_text(ordered, index, reverse=False) if direct_block else {}
        expected_placement = candidate.get("documentary_placement", {}) or {}
        checks["previous_block_confirmed"] = bool(
            previous
            and previous.get("sha256") == (expected_placement.get("previous_block") or {}).get("sha256")
        )
        checks["next_block_confirmed"] = bool(
            following
            and following.get("sha256") == (expected_placement.get("next_block") or {}).get("sha256")
        )
        checks["relative_visual_order_confirmed"] = bool(
            direct_url_match
            and int(direct_block.get("source_image_order") or 0) == source_order
            and int(direct_block.get("order") or 0) == document_order
        )

        membership_confirmed = True
        if len(duplicate_ids) > 1:
            signals = list((context.get("association_evidence") or {}).get("duplicate_unique_signals") or [])
            membership_confirmed = bool(signals and image_matches_signals(direct_image, signals))
            checks["quest_match_confirmed"] = bool(checks["quest_match_confirmed"] and membership_confirmed)
            if not membership_confirmed:
                reasons.append({"code": "image_quest_membership_uncertain", "detail": "duplicate quest context"})
                status = "uncertain"

        if is_map:
            checks["launch_map_role_confirmed"] = bool(direct_url_match and launch_role_confirmed(context, direct_image))

        if direct_url_match:
            if image_delay:
                time.sleep(image_delay)
            try:
                prefetched = (prefetched_images or {}).get(source_url)
                if isinstance(prefetched, Exception):
                    raise prefetched
                image_payload = prefetched if isinstance(prefetched, bytes) else fetch_with_retry(source_url, attempts, timeout)
                with Image.open(BytesIO(image_payload)) as direct_source:
                    direct_source.load()
                    expected_dimensions = image.get("fingerprint_dimensions") or {}
                    expected_size = (
                        int(expected_dimensions.get("width") or 0),
                        int(expected_dimensions.get("height") or 0),
                    )
                    checks["exact_image_confirmed"] = bool(
                        direct_source.width > 0
                        and direct_source.height > 0
                        and (expected_size == (0, 0) or direct_source.size == expected_size)
                    )
                    evidence["direct_image_dimensions"] = {
                        "width": direct_source.width,
                        "height": direct_source.height,
                    }
                evidence["direct_image_sha256"] = hashlib.sha256(image_payload).hexdigest()
            except Exception as exc:
                checks["exact_image_confirmed"] = None
                reasons.append({"code": "image_fetch_error", "detail": f"{type(exc).__name__}: {exc}"})
                status = "uncertain"
        else:
            checks["exact_image_confirmed"] = False
            reasons.append({"code": "image_absent_or_moved", "detail": source_url})

        for check, value in checks.items():
            if value is False and not any(reason["code"] == check for reason in reasons):
                reasons.append({"code": check, "detail": "direct check failed"})
        evidence.update(
            {
                "direct_page_sha256": str(context.get("page_sha256") or ""),
                "direct_documentary_order": int(direct_block.get("order") or 0),
                "direct_source_image_order": int(direct_block.get("source_image_order") or 0),
                "solution_body_boundary": boundary,
            }
        )

    required = [*BASE_CHECKS, *(("launch_map_role_confirmed",) if is_map else ())]
    authorized = all(checks.get(key) is True for key in required)
    local_path = ""
    storage = ""
    if authorized and image_payload is not None:
        try:
            local_path, image_sha256, storage = store_image(candidate, image_payload, manifest)
            evidence["direct_image_sha256"] = image_sha256
            evidence["local_path"] = local_path
            evidence["storage"] = storage
            status = "confirmed"
        except Exception as exc:
            authorized = False
            status = "uncertain"
            reasons.append({"code": "image_storage_error", "detail": f"{type(exc).__name__}: {exc}"})
    elif status != "uncertain":
        status = "rejected"

    direct_validation = {
        "validator_version": VALIDATOR_VERSION,
        "status": status,
        "checked_at": now_iso(),
        "checks": checks,
        "decision": "integrate" if authorized else "leave_hidden_and_report",
        "reasons": reasons,
        "evidence": evidence,
    }
    return {
        "event": "validation",
        "candidate_id": candidate_id,
        "quest_id": int(candidate["quest"]["quest_id"]),
        "quest_name": str(candidate["quest"]["name"]),
        "page_url": str(candidate["quest"]["page_url"]),
        "source_url": str(candidate["image"]["source_url"]),
        "work_classification": str(candidate.get("work_classification") or ""),
        "integration_authorized": authorized,
        "direct_validation": direct_validation,
        "integration": {
            "status": "ready" if authorized else "not_integrated",
            "local_path": local_path,
        },
    }


def extracted_block_json(block: Any, order: int) -> dict[str, Any]:
    row = {
        "order": order,
        "type": str(block.block_type),
        "content": str(block.content or ""),
        "position": str(block.position or ""),
        "caption": str(block.caption or ""),
        "source_url": str(block.source_url or ""),
        "data": block.data if isinstance(block.data, dict) else {},
    }
    return {key: value for key, value in row.items() if value not in ("", {}, [])}


def integrate_quest_row(
    quest_id: int,
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    contexts: dict[str, dict[str, Any]],
) -> dict[str, int]:
    authorized_content: dict[tuple[str, int, str], dict[str, Any]] = {}
    authorized_maps: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate.get("integration_authorized"):
            continue
        local_path = str((candidate.get("integration") or {}).get("local_path") or "")
        if not local_path or not Path(resolve_local_asset_path(local_path)).is_file():
            continue
        page_url = str(candidate["quest"]["page_url"])
        image = candidate["image"]
        if candidate.get("work_classification") == "start_map_only":
            authorized_maps.append(candidate)
        else:
            authorized_content[(page_url, int(image["source_image_order"]), str(image["source_url"]))] = candidate

    blocks: list[dict[str, Any]] = []
    page_urls = list(dict.fromkeys(str(candidate["quest"]["page_url"]) for candidate in candidates))
    if authorized_content:
        for page_url in page_urls:
            context = contexts.get(page_url, {})
            extraction = context.get("extraction", {}) or {}
            source_order = source_body_boundary(context)
            for block in extraction.get("blocks", []) or []:
                if str(block.block_type) == "image":
                    source_order += 1
                    key = (page_url, source_order, str(block.source_url or ""))
                    candidate = authorized_content.get(key)
                    if candidate is None:
                        continue
                    local_path = str((candidate.get("integration") or {}).get("local_path") or "")
                    blocks.append(
                        {
                            "order": len(blocks) + 1,
                            "type": "image",
                            "image_path": local_path,
                            "caption": str(block.caption or ""),
                            "source_url": str(block.source_url or ""),
                            "data": {"lot6_candidate_id": str(candidate["candidate_id"])},
                        }
                    )
                    continue
                blocks.append(extracted_block_json(block, len(blocks) + 1))

    map_paths = [
        str((candidate.get("integration") or {}).get("local_path") or "")
        for candidate in authorized_maps
        if (candidate.get("integration") or {}).get("local_path")
    ]
    if blocks:
        row["solution_blocks"] = blocks
    source_meta = dict(row.get("source_meta") or {})
    if map_paths:
        source_meta["startMapImages"] = map_paths
        source_meta["startMapImage"] = map_paths[0]
    if blocks or map_paths:
        row["source"] = "dofus_pour_les_noobs"
        row["source_url"] = page_urls[0]
        source_meta["title"] = str(candidates[0]["quest"]["name"])
        source_meta["lot6DirectValidation"] = "artifacts/lot6_codex_direct_validation.jsonl"
        row["source_meta"] = source_meta
        for page_url in page_urls:
            launch = contexts.get(page_url, {}).get("extraction", {}).get("launch_position", {}) or {}
            if launch:
                row["launch_position"] = launch
                break
        quality = dict(row.get("quality") or {})
        quality["block_count"] = len(blocks)
        quality["image_count"] = sum(block.get("type") == "image" for block in blocks)
        quality["lot6_codex_direct_integration"] = {
            "integrated_at": now_iso(),
            "candidate_count": len(candidates),
            "authorized_content": len(authorized_content),
            "authorized_start_maps": len(map_paths),
            "rejected": sum((candidate.get("direct_validation") or {}).get("status") == "rejected" for candidate in candidates),
            "uncertain": sum((candidate.get("direct_validation") or {}).get("status") == "uncertain" for candidate in candidates),
            "source_pages": page_urls,
        }
        row["quality"] = quality

    integrated_ids = {
        str((block.get("data") or {}).get("lot6_candidate_id") or "")
        for block in blocks
        if block.get("type") == "image"
    }
    integrated_ids.update(str(candidate["candidate_id"]) for candidate in authorized_maps if map_paths)
    for candidate in candidates:
        if str(candidate["candidate_id"]) in integrated_ids:
            candidate.setdefault("integration", {})["status"] = "integrated"
        elif candidate.get("integration_authorized"):
            candidate.setdefault("integration", {})["status"] = "reference_missing"
            candidate["integration_authorized"] = False
    return {
        "content_integrated": sum(block.get("type") == "image" for block in blocks),
        "maps_integrated": len(map_paths),
    }


def checkpoint(
    enriched_payload: dict[str, Any],
    manifest: dict[str, Any],
    registry: dict[str, Any],
    state: dict[str, Any],
    registry_path: Path,
    state_path: Path,
) -> None:
    enriched_payload["generated_at"] = now_iso()
    manifest["generated_at"] = now_iso()
    registry["direct_validation_updated_at"] = now_iso()
    write_json_file(ENRICHED_PATH, enriched_payload)
    write_json_file(MANIFEST_PATH, manifest)
    write_json_file(registry_path, registry)
    write_json_file(state_path, state)


def report_payload(registry: dict[str, Any], enriched: dict[str, Any]) -> dict[str, Any]:
    content, maps = registry_candidates(registry)
    whitelist = registry.get("work_whitelist_candidates", {}) or {}
    annexes = whitelist.get("leave_hidden_annexes", []) or []
    ambiguous = whitelist.get("leave_hidden_ambiguous", []) or []
    candidates = [*content, *maps]
    statuses = Counter(str((row.get("direct_validation") or {}).get("status") or "pending") for row in candidates)
    authorized = [row for row in candidates if row.get("integration_authorized")]
    integrated = [row for row in candidates if (row.get("integration") or {}).get("status") == "integrated"]
    broken = [
        row
        for row in candidates
        if any(
            str(reason.get("code") or "") in {"page_fetch_error", "image_fetch_error", "image_storage_error"}
            for reason in (row.get("direct_validation") or {}).get("reasons", []) or []
            if isinstance(reason, dict)
        )
    ]
    missing = [
        row
        for row in candidates
        if any(
            str(reason.get("code") or "") == "image_absent_or_moved"
            for reason in (row.get("direct_validation") or {}).get("reasons", []) or []
            if isinstance(reason, dict)
        )
    ]
    authorized_missing_local = [
        row
        for row in authorized
        if not Path(resolve_local_asset_path((row.get("integration") or {}).get("local_path"))).is_file()
    ]
    colonie = [row for row in candidates if int(row["quest"]["quest_id"]) == 2464]
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "source_registry": portable_asset_path(DEFAULT_REGISTRY),
        "summary": {
            "candidates": len(candidates),
            "verified": sum(statuses[status] for status in TERMINAL_STATUSES),
            "authorized": len(authorized),
            "integrated": len(integrated),
            "rejected": statuses["rejected"],
            "uncertain": statuses["uncertain"],
            "pending": statuses["pending"],
            "content_authorized": sum(row.get("integration_authorized") for row in content),
            "content_rejected": sum((row.get("direct_validation") or {}).get("status") == "rejected" for row in content),
            "maps_authorized": sum(row.get("integration_authorized") for row in maps),
            "maps_rejected": sum((row.get("direct_validation") or {}).get("status") == "rejected" for row in maps),
            "maps_uncertain": sum((row.get("direct_validation") or {}).get("status") == "uncertain" for row in maps),
            "annexes_left_hidden": len(annexes),
            "ambiguous_left_hidden": len(ambiguous),
            "broken_references": len(broken),
            "missing_images": len(missing),
            "authorized_missing_local_file": len(authorized_missing_local),
        },
        "broken_references": broken,
        "missing_images": missing,
        "authorized_missing_local_file": authorized_missing_local,
        "rejected_candidates": [row for row in candidates if (row.get("direct_validation") or {}).get("status") == "rejected"],
        "uncertain_candidates": [row for row in candidates if (row.get("direct_validation") or {}).get("status") == "uncertain"],
        "colonie_de_vaillance": {
            "quest_id": 2464,
            "candidate_count": len(colonie),
            "authorized": sum(row.get("integration_authorized") for row in colonie),
            "integrated": sum((row.get("integration") or {}).get("status") == "integrated" for row in colonie),
            "rejected": sum((row.get("direct_validation") or {}).get("status") == "rejected" for row in colonie),
            "uncertain": sum((row.get("direct_validation") or {}).get("status") == "uncertain" for row in colonie),
            "content_authorized": sum(row.get("integration_authorized") and row.get("work_classification") == "content_display_eligible" for row in colonie),
            "maps_authorized": sum(row.get("integration_authorized") and row.get("work_classification") == "start_map_only" for row in colonie),
            "solution_image_blocks": sum(
                isinstance(block, dict) and block.get("type") == "image"
                for block in (enriched.get("2464", {}) or {}).get("solution_blocks", []) or []
            ),
            "start_map_paths": list(((enriched.get("2464", {}) or {}).get("source_meta") or {}).get("startMapImages") or []),
            "candidates": colonie,
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    colonie = report["colonie_de_vaillance"]
    lines = [
            "# Lot 6 — validation directe et intégration CODEX",
            "",
            f"Généré le `{report['generated_at']}`.",
            "",
            "## Résultat",
            "",
            f"- Candidats vérifiés : **{summary['verified']} / {summary['candidates']}**",
            f"- Autorisés : **{summary['authorized']}**",
            f"- Intégrés : **{summary['integrated']}**",
            f"- Rejetés : **{summary['rejected']}**",
            f"- Incertains : **{summary['uncertain']}**",
            f"- Restant pending : **{summary['pending']}**",
            f"- Maps autorisées : **{summary['maps_authorized']}**",
            f"- Maps rejetées : **{summary['maps_rejected']}**",
            f"- Maps incertaines : **{summary['maps_uncertain']}**",
            f"- Annexes laissées masquées : **{summary['annexes_left_hidden']}**",
            f"- Occurrences ambiguës laissées masquées : **{summary['ambiguous_left_hidden']}**",
            f"- Placements de contenu autorisés exportés : **{summary.get('authorized_content_placements_exported', 0)}**",
            f"- Références cassées : **{summary['broken_references']}**",
            f"- Images absentes de la page directe : **{summary['missing_images']}**",
            f"- Autorisations sans fichier local : **{summary['authorized_missing_local_file']}**",
            f"- Entrées de manifeste réconciliées depuis le journal direct : **{summary.get('manifest_entries_reconciled_from_direct_journal', 0)}**",
            "",
            "## Colonie de vaillance",
            "",
            f"- Candidats : **{colonie['candidate_count']}**",
            f"- Contenus autorisés : **{colonie['content_authorized']}**",
            f"- Maps autorisées : **{colonie['maps_authorized']}**",
            f"- Intégrés : **{colonie['integrated']}**",
            f"- Rejetés : **{colonie['rejected']}**",
            f"- Incertains : **{colonie['uncertain']}**",
            f"- Blocs image dans le déroulement : **{colonie['solution_image_blocks']}**",
            "",
            "Les annexes et les occurrences ambiguës WORK n'ont pas été reclassifiées. Aucun fichier physique n'a été supprimé.",
            "",
        ]
    rejected = report.get("rejected_candidates", []) or []
    if rejected:
        lines.extend(
            [
                "## Candidats rejetés",
                "",
                "| ID quête | Quête | Classe WORK | Image | Motifs directs |",
                "| ---: | --- | --- | --- | --- |",
            ]
        )
        for candidate in rejected:
            reasons = ", ".join(
                str(reason.get("code") or "")
                for reason in (candidate.get("direct_validation") or {}).get("reasons", []) or []
                if isinstance(reason, dict) and reason.get("code")
            )
            quest = candidate.get("quest") or {}
            image = candidate.get("image") or {}
            lines.append(
                f"| {quest.get('quest_id')} | {str(quest.get('name') or '').replace('|', '\\|')} | "
                f"{candidate.get('work_classification')} | {image.get('source_url')} | {reasons} |"
            )
        lines.append("")
    uncertain = report.get("uncertain_candidates", []) or []
    if uncertain:
        lines.extend(["## Candidats incertains", ""])
        for candidate in uncertain:
            quest = candidate.get("quest") or {}
            lines.append(f"- {quest.get('quest_id')} — {quest.get('name')} — {candidate.get('candidate_id')}")
        lines.append("")
    return "\n".join(lines)


def write_authorized_content_placements(path: Path, registry: dict[str, Any]) -> int:
    content, _maps = registry_candidates(registry)
    rows: list[str] = []
    for candidate in content:
        if not candidate.get("integration_authorized"):
            continue
        validation = candidate.get("direct_validation") or {}
        evidence = validation.get("evidence") or {}
        rows.append(
            json.dumps(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "quest": candidate.get("quest"),
                    "previous_block": (candidate.get("documentary_placement") or {}).get("previous_block"),
                    "next_block": (candidate.get("documentary_placement") or {}).get("next_block"),
                    "image_documentary_order": (candidate.get("documentary_placement") or {}).get(
                        "image_documentary_order"
                    ),
                    "image": candidate.get("image"),
                    "direct_validation": {
                        "checked_at": validation.get("checked_at"),
                        "checks": validation.get("checks"),
                        "direct_page_sha256": evidence.get("direct_page_sha256"),
                        "direct_image_sha256": evidence.get("direct_image_sha256"),
                    },
                    "integration": candidate.get("integration"),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    temporary.replace(path)
    return len(rows)


def integrate(args: argparse.Namespace) -> dict[str, Any]:
    registry = read_json_file(args.registry, {})
    if int(registry.get("schema_version") or 0) < 3:
        raise RuntimeError("Le registre CODEX doit utiliser le schéma 3 ou supérieur.")
    content, maps = registry_candidates(registry)
    candidates = [*content, *maps]
    index = {str(row["candidate_id"]): row for row in candidates}
    restored = restore_journal(index, args.journal)
    enriched_payload = read_json_file(ENRICHED_PATH, {"quests": {}})
    enriched = enriched_payload.get("quests", {}) if isinstance(enriched_payload, dict) else {}
    mappings_payload = read_json_file(MAPPING_PATH, {"quests": {}})
    mappings = mappings_payload.get("quests", {}) if isinstance(mappings_payload, dict) else {}
    manifest = read_json_file(MANIFEST_PATH, {"version": 1, "by_url": {}, "by_sha256": {}})
    manifest_reconciled = reconcile_authorized_manifest(candidates, manifest)
    catalog = QuestCatalog.load()
    ensure_backup(args.backup_dir, args.registry)

    by_quest: dict[int, list[dict[str, Any]]] = defaultdict(list)
    quest_order: list[int] = []
    for candidate in candidates:
        quest_id = int(candidate["quest"]["quest_id"])
        if quest_id not in by_quest:
            quest_order.append(quest_id)
        by_quest[quest_id].append(candidate)
    if args.quest_id:
        if args.quest_id not in by_quest:
            raise RuntimeError(f"Quête absente des candidats: {args.quest_id}")
        quest_order = [args.quest_id]

    state = read_json_file(args.state, {"schema_version": 1, "completed_quest_ids": []})
    completed = set(int(value) for value in state.get("completed_quest_ids", []) or [])
    processed = 0
    for position, quest_id in enumerate(quest_order, 1):
        quest = catalog.by_id.get(quest_id)
        row = enriched.get(str(quest_id))
        if quest is None or not isinstance(row, dict):
            raise RuntimeError(f"Quête locale introuvable: {quest_id}")
        quest_candidates = by_quest[quest_id]
        checkpoint_complete = bool(
            quest_id in completed
            and all(
                int((candidate.get("direct_validation") or {}).get("validator_version") or 0)
                == VALIDATOR_VERSION
                and str((candidate.get("direct_validation") or {}).get("status") or "")
                in TERMINAL_STATUSES
                and (
                    not candidate.get("integration_authorized")
                    or (
                        (candidate.get("integration") or {}).get("status") == "integrated"
                        and Path(
                            resolve_local_asset_path(
                                (candidate.get("integration") or {}).get("local_path")
                            )
                        ).is_file()
                    )
                )
                for candidate in quest_candidates
            )
        )
        if checkpoint_complete:
            continue
        mapping = mappings.get(str(quest_id), {}) if isinstance(mappings, dict) else {}
        duplicate_ids = [int(value) for value in mapping.get("local_duplicate_quest_ids", []) or []]
        contexts = fetch_quest_pages(
            quest,
            quest_candidates,
            duplicate_ids,
            catalog,
            args.attempts,
            args.timeout,
            args.page_delay,
        )
        pending_candidates = [
            candidate
            for candidate in quest_candidates
            if not (
                str((candidate.get("direct_validation") or {}).get("status") or "pending") in TERMINAL_STATUSES
                and int((candidate.get("direct_validation") or {}).get("validator_version") or 0) == VALIDATOR_VERSION
            )
        ]
        prefetched_images = prefetch_candidate_images(
            pending_candidates,
            args.attempts,
            args.timeout,
            args.image_workers,
        )
        validated_now = 0
        for candidate in quest_candidates:
            validation = candidate.get("direct_validation") or {}
            status = str(validation.get("status") or "pending")
            if status in TERMINAL_STATUSES and int(validation.get("validator_version") or 0) == VALIDATOR_VERSION:
                continue
            page_url = str(candidate["quest"]["page_url"])
            event = validation_event(
                candidate,
                contexts[page_url],
                duplicate_ids,
                catalog,
                manifest,
                args.attempts,
                args.timeout,
                args.image_delay,
                prefetched_images,
            )
            append_journal(args.journal, event)
            apply_validation(candidate, event)
            validated_now += 1
            if validated_now % 25 == 0:
                print(
                    f"Quête {quest_id} — {validated_now}/{len(quest_candidates)} candidats contrôlés directement",
                    flush=True,
                )

        integration = integrate_quest_row(quest_id, row, quest_candidates, contexts)
        enriched[str(quest_id)] = row
        completed.add(quest_id)
        processed += 1
        state.update(
            {
                "updated_at": now_iso(),
                "completed_quest_ids": sorted(completed),
                "last_quest_id": quest_id,
                "journal_candidates_restored": restored,
            }
        )
        print(
            f"Lot 6 direct : quête {quest_id} ({position}/{len(quest_order)}), "
            f"validés maintenant={validated_now}, contenu intégré={integration['content_integrated']}, "
            f"maps intégrées={integration['maps_integrated']}",
            flush=True,
        )
        if processed % max(1, args.checkpoint_every) == 0 or position == len(quest_order):
            checkpoint(enriched_payload, manifest, registry, state, args.registry, args.state)
        if args.max_quests and processed >= args.max_quests:
            break

    report = report_payload(registry, enriched)
    report["summary"]["manifest_entries_reconciled_from_direct_journal"] = manifest_reconciled
    if manifest_reconciled:
        manifest["generated_at"] = now_iso()
        write_json_file(MANIFEST_PATH, manifest)
    report["summary"]["authorized_content_placements_exported"] = write_authorized_content_placements(
        args.authorized_placements,
        registry,
    )
    write_json_file(args.report, report)
    args.markdown.write_text(markdown_report(report), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valide directement puis intègre candidat par candidat les visuels du Lot 6."
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--authorized-placements", type=Path, default=DEFAULT_AUTHORIZED_PLACEMENTS)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--quest-id", type=int, default=0)
    parser.add_argument("--max-quests", type=int, default=0)
    parser.add_argument("--checkpoint-every", type=int, default=5)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--page-delay", type=float, default=0.08)
    parser.add_argument("--image-delay", type=float, default=0.02)
    parser.add_argument("--image-workers", type=int, default=6)
    return parser


def main(argv: list[str] | None = None) -> int:
    report = integrate(build_parser().parse_args(argv))
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)
    return 0 if not report["summary"]["pending"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
