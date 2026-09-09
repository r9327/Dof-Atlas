from __future__ import annotations

import argparse
import html
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from app.constants import DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.tools.enrich_quests import (
    DPLN_BASE,
    DPLN_SITEMAP_URL,
    MetaParser,
    TokenParser,
    clean_text,
    full_url,
    request_bytes,
    skip_dpln_text,
    source_title_key,
    useful_image,
)
from app.quest_catalog import QuestCatalog, normalize_text, read_json_file, resolve_local_asset_path


QUESTS_DIR = DATA_DIR / "encyclopedia" / "quests"
DEFAULT_VISUAL_AUDIT = ROOT_DIR / "artifacts" / "lot6_quest_visuals_audit.json"
DEFAULT_LOCAL_AUDIT = ROOT_DIR / "artifacts" / "lot6_local_audit.json"
DEFAULT_JSON = ROOT_DIR / "artifacts" / "lot6_work_visual_verification.json"
DEFAULT_MARKDOWN = ROOT_DIR / "artifacts" / "lot6_work_visual_verification.md"
ENRICHED_PATH = QUESTS_DIR / "quests_enriched.json"
MAPPING_PATH = QUESTS_DIR / "source_mapping.json"
MANIFEST_PATH = QUESTS_DIR / "image_manifest.json"


ENTITY_SLUG_PARTS = {
    "agrave": "a",
    "aacute": "a",
    "acirc": "a",
    "auml": "a",
    "ccedil": "c",
    "eacute": "e",
    "egrave": "e",
    "ecirc": "e",
    "euml": "e",
    "icirc": "i",
    "iuml": "i",
    "ocirc": "o",
    "ouml": "o",
    "ugrave": "u",
    "ucirc": "u",
    "uuml": "u",
    "oelig": "oe",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def portable_path(value: str | Path) -> str:
    resolved = Path(resolve_local_asset_path(value))
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except (OSError, ValueError):
        return str(value or "")


def canonical_slug(value: str) -> str:
    text = html.unescape(value).casefold()
    for encoded, decoded in ENTITY_SLUG_PARTS.items():
        text = text.replace(encoded, decoded)
    return source_title_key(text.replace("-", " "))


def title_similarity(left: str, right: str) -> float:
    left_key = source_title_key(left)
    right_key = source_title_key(right)
    if not left_key or not right_key:
        return 0.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def sitemap_urls(payload: bytes) -> dict[str, str]:
    root = ElementTree.fromstring(payload)
    rows: dict[str, str] = {}
    for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
        url = str(loc.text or "").strip()
        parsed = urlparse(url)
        if parsed.path.endswith(".html"):
            rows[Path(parsed.path).stem.casefold()] = url
    return rows


def dpln_mapping_rows(mapping_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows = mapping_row.get("dofus_pour_les_noobs", []) if isinstance(mapping_row, dict) else []
    return [row for row in rows if isinstance(row, dict) and row.get("url")]


def candidate_urls(
    quest_name: str,
    mapping_row: dict[str, Any],
    sitemap: dict[str, str],
) -> list[dict[str, Any]]:
    existing = dpln_mapping_rows(mapping_row)
    results = [
        {
            "url": str(row["url"]),
            "origin": "source_mapping",
            "slug_score": round(title_similarity(quest_name, canonical_slug(Path(urlparse(str(row["url"])).path).stem)), 4),
        }
        for row in existing
    ]

    target = source_title_key(quest_name)
    ranked: list[tuple[float, str, str]] = []
    for slug, url in sitemap.items():
        candidate = canonical_slug(slug)
        score = SequenceMatcher(None, target, candidate).ratio() if target and candidate else 0.0
        if target and candidate and (target in candidate or candidate in target):
            score = max(score, 0.9)
        if score >= 0.875:
            ranked.append((score, slug, url))
    ranked.sort(key=lambda row: (-row[0], len(row[1]), row[1]))
    known_urls = {row["url"] for row in results}
    results.extend(
        {"url": url, "origin": "sitemap_near_title", "slug_score": round(score, 4)}
        for score, _slug, url in ranked[:3]
        if url not in known_urls
    )
    return results


def page_content(payload: bytes, page_url: str, quest_name: str) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="replace")
    meta = MetaParser()
    meta.feed(text)
    parser = TokenParser()
    parser.feed(text)

    ordered: list[dict[str, Any]] = []
    all_text: list[str] = []
    previous_text = ""
    image_order = 0
    pending_images: list[dict[str, Any]] = []
    for token in parser.tokens:
        if token.get("type") == "image":
            src = full_url(str(token.get("src") or ""), page_url)
            if not useful_image(src, "dpln"):
                continue
            image_order += 1
            row = {
                "order": image_order,
                "source_url": src,
                "alt": clean_text(token.get("alt", "")),
                "passage_before": previous_text,
                "passage_after": "",
            }
            ordered.append(row)
            pending_images.append(row)
            continue

        raw = clean_text(token.get("text", ""))
        if skip_dpln_text(raw, quest_name):
            continue
        if pending_images:
            for image in pending_images:
                image["passage_after"] = raw
            pending_images.clear()
        previous_text = raw
        all_text.append(raw)

    return {
        "title": meta.title,
        "url": page_url,
        "text": "\n".join(all_text),
        "images": ordered,
    }


def connected_visuals(enriched_row: dict[str, Any]) -> dict[str, str]:
    connected: dict[str, str] = {}
    for block in enriched_row.get("solution_blocks", []) or []:
        if not isinstance(block, dict) or str(block.get("type") or block.get("block_type") or "") != "image":
            continue
        url = str(block.get("source_url") or "")
        path = str(block.get("image_path") or block.get("path") or "")
        if url:
            connected[url] = path
    if connected:
        return connected
    for step in enriched_row.get("solution_steps", []) or []:
        if not isinstance(step, dict):
            continue
        for objective in step.get("objectives", []) or []:
            if not isinstance(objective, dict):
                continue
            for image in objective.get("images", []) or []:
                if isinstance(image, dict) and image.get("source_url"):
                    connected[str(image["source_url"])] = str(image.get("path") or image.get("image_path") or "")
    return connected


def manifest_path(manifest: dict[str, Any], source_url: str) -> str:
    row = (manifest.get("by_url", {}) or {}).get(source_url)
    if not isinstance(row, dict) or not row.get("path"):
        return ""
    resolved = Path(resolve_local_asset_path(row["path"]))
    return portable_path(resolved) if resolved.exists() else ""


def local_evidence(quest: Any) -> list[str]:
    rows: list[str] = []
    for prerequisite in getattr(quest, "prerequisites", []) or []:
        rows.append(str(prerequisite))
    for step in getattr(quest, "steps", []) or []:
        for value in (getattr(step, "name", ""), getattr(step, "description", "")):
            if value:
                rows.append(str(value))
        for objective in getattr(step, "objectives", []) or []:
            text = str(getattr(objective, "text", "") or "")
            if text:
                rows.append(text)
    return rows


def distinctive_signals(quest: Any) -> list[str]:
    signals: list[str] = []
    quest_key = source_title_key(str(getattr(quest, "name", "")))
    for row in local_evidence(quest):
        for coord in re.findall(r"\[\s*-?\d+\s*,\s*-?\d+\s*\]", row):
            signals.append(coord.replace(" ", ""))
        clean = clean_text(row)
        patterns = (
            r"(?:vaincre|battre)\s+x?\d*\s*([^\[,]+?)(?:\s+en\s+un\s+seul\s+combat|\s*\[|$)",
            r"(?:aller voir|retourner voir|ramener à|parler à)\s+([^\[,]+?)(?:\s*\[|:|$)",
        )
        for pattern in patterns:
            for match in re.findall(pattern, clean, flags=re.IGNORECASE):
                key = source_title_key(match)
                if len(key) >= 5 and key != quest_key:
                    signals.append(key)
    result: list[str] = []
    for value in signals:
        if value and value not in result:
            result.append(value)
    return result


def evidence_matches(quest: Any, page_text: str) -> list[str]:
    return signal_matches(distinctive_signals(quest), page_text)


def signal_matches(signals: list[str], page_text: str) -> list[str]:
    normalized_page = source_title_key(page_text)
    compact_page = page_text.replace(" ", "")
    matches: list[str] = []
    for signal in signals:
        if signal.startswith("["):
            if signal in compact_page:
                matches.append(signal)
        elif signal in normalized_page:
            matches.append(signal)
    return matches


def duplicate_unique_signals(quest: Any, duplicate_ids: list[int], catalog: QuestCatalog) -> list[str]:
    own = distinctive_signals(quest)
    sibling_signals = {
        signal
        for quest_id in duplicate_ids
        if quest_id != int(getattr(quest, "id", 0)) and quest_id in catalog.by_id
        for signal in distinctive_signals(catalog.by_id[quest_id])
    }
    return [signal for signal in own if signal not in sibling_signals]


def image_matches_signals(image: dict[str, Any], signals: list[str]) -> bool:
    context = "\n".join(
        str(image.get(key) or "")
        for key in ("passage_before", "passage_after", "alt")
    )
    return bool(signal_matches(signals, context))


def image_utility(image: dict[str, Any]) -> str:
    context = clean_text(image.get("passage_before") or image.get("passage_after") or image.get("alt") or "")
    key = normalize_text(context)
    if re.search(r"\[\s*-?\d+\s*,\s*-?\d+\s*\]", context):
        return "Repère visuel associé à une position ou un déplacement indiqué par la source."
    if any(token in key for token in ("combat", "vaincre", "sort", "attaque", "boss")):
        return "Illustration de combat, de cible ou de mécanique associée au passage source."
    if any(token in key for token in ("clique", "interagir", "parlez", "parler", "donnez", "utilisez")):
        return "Repère d’interaction associé au passage source."
    return "Contexte visuel du passage source ; utilité précise à confirmer lors de l’intégration."


def classify_page_for_quest(
    quest: Any,
    page: dict[str, Any],
    duplicate_ids: list[int],
    catalog: QuestCatalog,
) -> dict[str, Any]:
    similarity = title_similarity(str(getattr(quest, "name", "")), str(page.get("title") or ""))
    matches = evidence_matches(quest, str(page.get("text") or ""))
    unique_signals = duplicate_unique_signals(quest, duplicate_ids, catalog) if len(duplicate_ids) > 1 else []
    unique_matches = signal_matches(unique_signals, str(page.get("text") or ""))
    exact_title = source_title_key(str(getattr(quest, "name", ""))) == source_title_key(str(page.get("title") or ""))
    compatible_title = exact_title or similarity >= 0.94
    if not compatible_title:
        association = "rejected_title"
    elif len(duplicate_ids) <= 1:
        association = "confirmed_unique_title"
    elif unique_matches:
        association = "confirmed_duplicate_by_content"
    else:
        association = "unresolved_duplicate"
    return {
        "association": association,
        "title_similarity": round(similarity, 4),
        "exact_title": exact_title,
        "content_evidence": matches,
        "duplicate_unique_signals": unique_signals,
        "duplicate_unique_evidence": unique_matches,
    }


def select_confirmed_pages(quest: Any, pages: list[dict[str, Any]]) -> None:
    """Keep only source pages demonstrated for this local quest.

    Exact-title alternatives are old/current revisions on DPLN. Content
    evidence selects the current local variant. Explicit ``partie N`` pages
    are complementary fragments and may therefore remain selected together.
    """

    available = [
        page
        for page in pages
        if page.get("association") not in {"fetch_error", "rejected_title"}
    ]
    if not available:
        target = source_title_key(str(getattr(quest, "name", "")))
        title_extensions = [
            page
            for page in pages
            if page.get("association") == "rejected_title"
            and source_title_key(str(page.get("title") or "")).startswith(target + "_")
            and len(page.get("content_evidence", [])) >= 2
        ]
        if title_extensions:
            multipart = [
                page
                for page in title_extensions
                if source_title_key(str(page.get("title") or "")).startswith(target + "_partie_")
            ]
            selected = multipart if multipart else title_extensions[:1]
            for page in selected:
                page["association"] = (
                    "confirmed_multipart_by_content" if multipart else "confirmed_title_extension_by_content"
                )
            return
        # A punctuation or suffix difference is acceptable only with multiple
        # quest-specific objective/coordinate signals in the page body.
        supported = [
            page
            for page in pages
            if page.get("association") == "rejected_title"
            and len(page.get("content_evidence", [])) >= 2
            and float(page.get("title_similarity") or 0.0) >= 0.84
        ]
        if len(supported) == 1:
            supported[0]["association"] = "confirmed_by_content"
        elif supported:
            multipart = [
                page
                for page in supported
                if source_title_key(str(page.get("title") or "")).startswith(target + "_partie_")
            ]
            if len(multipart) == len(supported):
                for page in multipart:
                    page["association"] = "confirmed_multipart_by_content"
        return

    exact = [page for page in available if page.get("exact_title")]
    if len(exact) == 1:
        selected = exact[0]
        for page in available:
            if page is not selected:
                page["association"] = "rejected_alternative"
        return
    if len(exact) > 1:
        ranked = sorted(exact, key=lambda page: len(page.get("content_evidence", [])), reverse=True)
        best_count = len(ranked[0].get("content_evidence", []))
        second_count = len(ranked[1].get("content_evidence", []))
        if best_count > second_count:
            selected = ranked[0]
            for page in available:
                if page is not selected:
                    page["association"] = "rejected_alternative"
        else:
            for page in exact:
                page["association"] = "unresolved_alternative"
        return

    target = source_title_key(str(getattr(quest, "name", "")))
    multipart = [
        page
        for page in available
        if source_title_key(str(page.get("title") or "")).startswith(target + "_partie_")
        and page.get("content_evidence")
    ]
    if multipart and len(multipart) == len(available):
        for page in multipart:
            page["association"] = "confirmed_multipart_by_content"
        return

    ranked = sorted(
        available,
        key=lambda page: (len(page.get("content_evidence", [])), float(page.get("title_similarity") or 0.0)),
        reverse=True,
    )
    best = ranked[0]
    best_rank = (len(best.get("content_evidence", [])), float(best.get("title_similarity") or 0.0))
    second_rank = (
        len(ranked[1].get("content_evidence", [])),
        float(ranked[1].get("title_similarity") or 0.0),
    ) if len(ranked) > 1 else (-1, -1.0)
    if best_rank > second_rank and (best_rank[0] >= 2 or best_rank[1] >= 0.98):
        for page in available:
            if page is not best:
                page["association"] = "rejected_alternative"


def quest_category(row: dict[str, Any]) -> str:
    confirmed = [
        page
        for page in row.get("pages", [])
        if str(page.get("association") or "").startswith("confirmed")
    ]
    if not row.get("candidate_urls"):
        return "no_dpln_page_found"
    if len(confirmed) != 1:
        return "impossible_to_confirm"
    page = confirmed[0]
    relevant_images = [
        image
        for confirmed_page in confirmed
        for image in confirmed_page.get("images", [])
        if image.get("quest_relevance", "specific") == "specific"
    ]
    if not relevant_images and any(page.get("images") for page in confirmed) and row.get("local_duplicate_quest_ids"):
        return "impossible_to_confirm"
    image_states = Counter(image.get("local_state") for image in relevant_images)
    if image_states.get("absent_local", 0) or image_states.get("present_unconnected", 0):
        return "missing_to_integrate"
    if not relevant_images:
        return "no_visual_on_dpln"
    if row.get("input_status") == "ambiguous":
        return "ambiguous_resolved"
    return "already_present_locally"


def build_verification(delay: float = 0.08) -> dict[str, Any]:
    visual_audit = read_json_file(DEFAULT_VISUAL_AUDIT, {})
    _local_audit = read_json_file(DEFAULT_LOCAL_AUDIT, {})
    enriched_payload = read_json_file(ENRICHED_PATH, {"quests": {}})
    mapping_payload = read_json_file(MAPPING_PATH, {"quests": {}})
    manifest = read_json_file(MANIFEST_PATH, {"by_url": {}})
    enriched = enriched_payload.get("quests", {}) if isinstance(enriched_payload, dict) else {}
    mappings = mapping_payload.get("quests", {}) if isinstance(mapping_payload, dict) else {}
    catalog = QuestCatalog.load()

    classification = visual_audit.get("classification", {}) if isinstance(visual_audit, dict) else {}
    priority_rows = classification.get("partial_or_ambiguous", []) or []
    source_insufficient = classification.get("source_insufficient", []) or []
    without_visuals = classification.get("without_connected_visuals", []) or []
    audit_by_id = {
        int(row["quest_id"]): row
        for group in (priority_rows, source_insufficient, without_visuals)
        for row in group
        if isinstance(row, dict) and row.get("quest_id") is not None
    }
    scope_ids = sorted(audit_by_id)

    sitemap_payload = request_bytes(DPLN_SITEMAP_URL)
    sitemap = sitemap_urls(sitemap_payload)
    page_cache: dict[str, dict[str, Any]] = {}
    fetch_errors: dict[str, str] = {}
    rows: list[dict[str, Any]] = []

    for index, quest_id in enumerate(scope_ids, 1):
        quest = catalog.by_id[quest_id]
        audit_row = audit_by_id[quest_id]
        mapping_row = mappings.get(str(quest_id), {}) if isinstance(mappings, dict) else {}
        enriched_row = enriched.get(str(quest_id), {}) if isinstance(enriched, dict) else {}
        candidates = candidate_urls(str(quest.name), mapping_row, sitemap)
        connected = connected_visuals(enriched_row if isinstance(enriched_row, dict) else {})
        duplicate_ids = list(mapping_row.get("local_duplicate_quest_ids", []) or []) if isinstance(mapping_row, dict) else []
        pages: list[dict[str, Any]] = []

        for candidate in candidates:
            url = str(candidate["url"])
            if url not in page_cache and url not in fetch_errors:
                try:
                    if page_cache or fetch_errors:
                        time.sleep(max(0.0, delay))
                    page_cache[url] = page_content(request_bytes(url), url, str(quest.name))
                except Exception as exc:  # network evidence must remain diagnosable in the report
                    fetch_errors[url] = f"{type(exc).__name__}: {exc}"
            if url in fetch_errors:
                pages.append({**candidate, "association": "fetch_error", "error": fetch_errors[url], "images": []})
                continue
            page = dict(page_cache[url])
            association = classify_page_for_quest(quest, page, duplicate_ids, catalog)
            images: list[dict[str, Any]] = []
            unique_signals = list(association.get("duplicate_unique_signals", []) or [])
            for source_image in page.get("images", []):
                image = dict(source_image)
                source_url = str(image.get("source_url") or "")
                connected_path = connected.get(source_url, "")
                known_path = manifest_path(manifest, source_url)
                if connected_path and Path(resolve_local_asset_path(connected_path)).exists():
                    state = "connected"
                    local_path = portable_path(connected_path)
                elif known_path:
                    state = "present_unconnected"
                    local_path = known_path
                else:
                    state = "absent_local"
                    local_path = ""
                image.update(
                    {
                        "local_state": state,
                        "local_path": local_path,
                        "utility": image_utility(image),
                        "quest_relevance": (
                            "specific"
                            if len(duplicate_ids) <= 1 or image_matches_signals(image, unique_signals)
                            else "shared_or_unassigned"
                        ),
                    }
                )
                images.append(image)
            page.update(candidate)
            page.update(association)
            page["images"] = images
            page.pop("text", None)
            pages.append(page)

        select_confirmed_pages(quest, pages)

        row = {
            "quest_id": quest_id,
            "name": str(quest.name),
            "input_status": str(audit_row.get("status") or ""),
            "input_source": str(audit_row.get("source") or ""),
            "input_connected_visual_count": int(audit_row.get("visual_count") or 0),
            "priority": any(int(item.get("quest_id")) == quest_id for item in priority_rows if isinstance(item, dict)),
            "local_duplicate_quest_ids": duplicate_ids,
            "candidate_urls": candidates,
            "pages": pages,
        }
        row["category"] = quest_category(row)
        row["ambiguous_association_resolved"] = bool(
            row["input_status"] == "ambiguous"
            and any(str(page.get("association") or "").startswith("confirmed") for page in pages)
        )
        rows.append(row)
        if index % 100 == 0:
            print(f"Vérification WORK : {index}/{len(scope_ids)} quêtes")

    categories = Counter(row["category"] for row in rows)
    missing_images = [
        image
        for row in rows
        for page in row["pages"]
        if str(page.get("association") or "").startswith("confirmed")
        for image in page.get("images", [])
        if image.get("quest_relevance", "specific") == "specific"
        if image.get("local_state") in {"absent_local", "present_unconnected"}
    ]
    connected_specific_images = [
        image
        for row in rows
        for page in row["pages"]
        if str(page.get("association") or "").startswith("confirmed")
        for image in page.get("images", [])
        if image.get("quest_relevance", "specific") == "specific"
        and image.get("local_state") == "connected"
    ]
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "source": {
            "dofus_noob_sitemap": DPLN_SITEMAP_URL,
            "robots_respected": True,
            "search_endpoint_used": False,
            "images_downloaded": False,
            "html_pages_fetched": len(page_cache),
            "fetch_errors": fetch_errors,
        },
        "scope": {
            "quests": len(rows),
            "priority_needs_review": sum(row["input_status"] == "needs_review" for row in rows),
            "priority_ambiguous": sum(row["input_status"] == "ambiguous" for row in rows),
            "source_insufficient": sum(row["input_status"] == "source_insufficient" for row in rows),
            "without_connected_visuals": sum(row["input_connected_visual_count"] == 0 for row in rows),
        },
        "summary": {
            "quest_categories": dict(categories),
            "ambiguous_associations_resolved": sum(row["ambiguous_association_resolved"] for row in rows),
            "missing_visual_records": len(missing_images),
            "unique_missing_source_urls": len({str(image.get("source_url") or "") for image in missing_images}),
            "absent_local_visual_records": sum(image["local_state"] == "absent_local" for image in missing_images),
            "present_unconnected_visual_records": sum(
                image["local_state"] == "present_unconnected" for image in missing_images
            ),
            "connected_specific_visual_occurrences": len(connected_specific_images),
            "quests_with_connected_specific_visuals": sum(
                any(
                    image.get("quest_relevance", "specific") == "specific"
                    and image.get("local_state") == "connected"
                    for page in row["pages"]
                    if str(page.get("association") or "").startswith("confirmed")
                    for image in page.get("images", [])
                )
                for row in rows
            ),
            "shared_or_unassigned_visual_occurrences": sum(
                image.get("quest_relevance") == "shared_or_unassigned"
                for row in rows
                for page in row["pages"]
                if str(page.get("association") or "").startswith("confirmed")
                for image in page.get("images", [])
            ),
        },
        "quests": rows,
    }


def markdown_escape(value: object) -> str:
    return clean_text(value).replace("|", "\\|").replace("\n", " ")


def markdown_report(payload: dict[str, Any]) -> str:
    categories = payload["summary"]["quest_categories"]
    rows = payload["quests"]
    labels = {
        "no_dpln_page_found": "Aucune page Dofus Noob trouvée dans le sitemap public",
        "no_visual_on_dpln": "Page confirmée sans visuel de contenu",
        "already_present_locally": "Visuels Dofus Noob déjà présents et raccordés",
        "ambiguous_resolved": "Association ambiguë résolue",
        "missing_to_integrate": "Contenu réellement manquant à intégrer",
        "impossible_to_confirm": "Association restant impossible à confirmer",
    }
    lines = [
        "# Lot 6 — Vérification WORK de la couverture visuelle restante",
        "",
        f"Généré le `{payload['generated_at']}` à partir du sitemap public et des pages Dofus Noob. ",
        "Aucune image n'a été téléchargée et aucune donnée de quête existante n'a été modifiée.",
        "",
        "## Périmètre et méthode",
        "",
        f"- Quêtes distinctes contrôlées : {payload['scope']['quests']}",
        f"- Priorité `needs_review` : {payload['scope']['priority_needs_review']}",
        f"- Priorité `ambiguous` : {payload['scope']['priority_ambiguous']}",
        f"- Sources locales insuffisantes : {payload['scope']['source_insufficient']}",
        f"- Sans visuel local raccordé dans ce périmètre : {payload['scope']['without_connected_visuals']}",
        f"- Pages HTML Dofus Noob consultées : {payload['source']['html_pages_fetched']}",
        "- Le moteur `/apps/search` n'a pas été utilisé, conformément à `robots.txt`.",
        "- Une absence signifie donc : aucune page candidate suffisamment proche trouvée dans le sitemap public ; ce n'est pas une preuve que la quête n'a jamais existé ailleurs.",
        "",
        "## Bilan",
        "",
        "Les résultats principaux sont exclusifs, sauf la ligne `Association ambiguë résolue`, qui constitue un axe de vérification indépendant et peut recouvrir un contenu manquant ou un visuel restant impossible à attribuer.",
        "",
        "| Catégorie | Quêtes |",
        "| --- | ---: |",
    ]
    for key in labels:
        count = (
            payload["summary"]["ambiguous_associations_resolved"]
            if key == "ambiguous_resolved"
            else categories.get(key, 0)
        )
        lines.append(f"| {labels[key]} | {count} |")
    lines.extend(
        [
            "",
            f"Occurrences visuelles à préparer : **{payload['summary']['missing_visual_records']}**, soit **{payload['summary']['unique_missing_source_urls']} URL source uniques** ",
            f"({payload['summary']['absent_local_visual_records']} absents localement, ",
            f"{payload['summary']['present_unconnected_visual_records']} déjà présents mais non raccordés).",
            f"Associations ambiguës résolues avec preuve : **{payload['summary']['ambiguous_associations_resolved']} / {payload['scope']['priority_ambiguous']}**.",
            f"Occurrences visuelles communes laissées sans attribution automatique : **{payload['summary']['shared_or_unassigned_visual_occurrences']}**.",
            f"Occurrences déjà correctement raccordées sur les pages confirmées : **{payload['summary']['connected_specific_visual_occurrences']}** sur **{payload['summary']['quests_with_connected_specific_visuals']} quêtes** (y compris les quêtes partiellement incomplètes).",
            "",
            "## Associations ambiguës résolues",
            "",
            "| ID | Quête | Page confirmée | Preuves de contenu |",
            "| ---: | --- | --- | --- |",
        ]
    )
    resolved = [row for row in rows if row.get("ambiguous_association_resolved")]
    if not resolved:
        lines.append("| — | Aucune | — | — |")
    for row in resolved:
        page = next(page for page in row["pages"] if page.get("association", "").startswith("confirmed"))
        evidence = ", ".join(
            (page.get("duplicate_unique_evidence") or page.get("content_evidence") or [])[:8]
        ) or "titre unique confirmé"
        lines.append(
            f"| {row['quest_id']} | {markdown_escape(row['name'])} | {page['url']} | {markdown_escape(evidence)} |"
        )

    lines.extend(["", "## Contenu réellement manquant à intégrer", ""])
    missing_rows = [row for row in rows if row["category"] == "missing_to_integrate"]
    if not missing_rows:
        lines.append("Aucun élément réellement manquant n'a été confirmé.")
    for row in missing_rows:
        lines.extend([f"### {row['quest_id']} — {row['name']}", ""])
        for page in row["pages"]:
            if not page.get("association", "").startswith("confirmed"):
                continue
            for image in page.get("images", []):
                if image.get("local_state") not in {"absent_local", "present_unconnected"}:
                    continue
                if image.get("quest_relevance", "specific") != "specific":
                    continue
                passage = image.get("passage_before") or image.get("passage_after") or image.get("alt") or "À VÉRIFIER"
                local = (
                    f"déjà présent : `{image['local_path']}` mais non raccordé"
                    if image["local_state"] == "present_unconnected"
                    else "absent localement"
                )
                lines.extend(
                    [
                        f"- Ordre source : {image['order']} — {local}",
                        f"  - Passage exact : {markdown_escape(passage)}",
                        f"  - Indication / utilité : {markdown_escape(image['utility'])}",
                        f"  - Source : {image['source_url']}",
                    ]
                )
        lines.append("")

    lines.extend(
        [
            "## Déjà présent localement",
            "",
            "| ID | Quête | Visuels raccordés confirmés |",
            "| ---: | --- | ---: |",
        ]
    )
    present_rows = [row for row in rows if row["category"] == "already_present_locally"]
    if not present_rows:
        lines.append("| — | Aucun | 0 |")
    for row in present_rows:
        count = sum(
            image.get("local_state") == "connected"
            for page in row["pages"]
            if page.get("association", "").startswith("confirmed")
            for image in page.get("images", [])
            if image.get("quest_relevance", "specific") == "specific"
        )
        lines.append(f"| {row['quest_id']} | {markdown_escape(row['name'])} | {count} |")

    lines.extend(
        [
            "",
            "## Aucun visuel nécessaire / aucune page Dofus Noob trouvée",
            "",
            "| ID | Quête | Conclusion |",
            "| ---: | --- | --- |",
        ]
    )
    empty_rows = [row for row in rows if row["category"] in {"no_dpln_page_found", "no_visual_on_dpln"}]
    for row in empty_rows:
        conclusion = labels[row["category"]]
        lines.append(f"| {row['quest_id']} | {markdown_escape(row['name'])} | {conclusion} |")

    lines.extend(
        [
            "",
            "## Cas restant impossible à confirmer",
            "",
            "| ID | Quête | Candidats | Motif |",
            "| ---: | --- | --- | --- |",
        ]
    )
    unresolved = [row for row in rows if row["category"] == "impossible_to_confirm"]
    if not unresolved:
        lines.append("| — | Aucun | — | — |")
    for row in unresolved:
        urls = "<br>".join(page.get("url", "") for page in row["pages"]) or "—"
        if row.get("ambiguous_association_resolved") and row.get("local_duplicate_quest_ids"):
            reasons = "page confirmée, mais aucun visuel attribuable sans ambiguïté à cet ID"
        else:
            reasons = ", ".join(sorted({str(page.get("association") or "") for page in row["pages"]})) or "aucune preuve"
        lines.append(f"| {row['quest_id']} | {markdown_escape(row['name'])} | {urls} | {reasons} |")

    lines.extend(
        [
            "",
            "## Garde-fous pour CODEX",
            "",
            "- Intégrer uniquement les entrées de `Contenu réellement manquant à intégrer`.",
            "- Réutiliser les chemins signalés `présent_unconnected` sans nouveau téléchargement.",
            "- Ne rien associer pour les cas `impossible_to_confirm`.",
            "- Ne pas intégrer les occurrences `shared_or_unassigned` d'une page couvrant plusieurs IDs.",
            "- Conserver l'ordre source et le passage exact fournis dans le JSON exhaustif.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vérification WORK du Lot 6 sans intégration ni téléchargement d'images.")
    parser.add_argument("--delay", type=float, default=0.08, help="Pause entre les pages Dofus Noob.")
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args(argv)

    payload = build_verification(delay=args.delay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps({"scope": payload["scope"], "summary": payload["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
