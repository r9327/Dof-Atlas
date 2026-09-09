from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from app.constants import DATA_DIR
from app.modules.encyclopedia.providers import GuideProvider

DUFFUS_BASE = "https://duffus.fr"
DUFFUS_SITEMAP = f"{DUFFUS_BASE}/sitemap.xml"
GUIDE_COMPLETE_URL = f"{DUFFUS_BASE}/guide-complet"
ARTIFACTS_DIR = DATA_DIR.parent / "artifacts"
FULL_AUDIT_PATH = ARTIFACTS_DIR / "duffus_guides_full_audit.json"
GUIDE_COMPLET_AUDIT_PATH = ARTIFACTS_DIR / "guide_complet_audit.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit build-time des guides Duffus vers des rapports locaux.")
    parser.add_argument("--output", type=Path, default=FULL_AUDIT_PATH)
    parser.add_argument("--guide-complet-output", type=Path, default=GUIDE_COMPLET_AUDIT_PATH)
    parser.add_argument("--no-network", action="store_true", help="Utilise uniquement les guides Atlas locaux.")
    args = parser.parse_args(argv)

    provider = GuideProvider()
    guides = provider.load_all()
    atlas_by_slug = {slug_for(guide.id): guide for guide in guides}
    atlas_by_title = {slug_for(guide.title): guide for guide in guides}
    checked_at = datetime.now(timezone.utc).isoformat()

    source_urls = [GUIDE_COMPLETE_URL]
    fetch_errors: list[str] = []
    if not args.no_network:
        try:
            source_urls.extend(url for url in sitemap_guide_urls(DUFFUS_SITEMAP) if url not in source_urls)
        except Exception as exc:
            fetch_errors.append(f"sitemap: {exc}")
    else:
        source_urls.extend(duffus_url_for_guide(guide) for guide in guides if guide.category in {"dofus", "alignements"})

    audits = []
    for url in sorted(set(source_urls), key=route_sort_key):
        guide_id = guide_id_from_url(url)
        slug = slug_for(guide_id)
        guide = atlas_by_slug.get(slug) or atlas_by_title.get(slug)
        html_title = ""
        page_error = ""
        if not args.no_network:
            try:
                html_title = extract_page_title(fetch_text(url))
            except Exception as exc:
                page_error = str(exc)
        audit = audit_from_local_guide(guide, guide_id, url, checked_at)
        if html_title and not audit["title"]:
            audit["title"] = html_title
        if page_error:
            audit["warnings"].append(f"page inaccessible: {page_error}")
        if fetch_errors:
            audit["warnings"].extend(fetch_errors)
        audits.append(audit)

    payload = {
        "schema_version": 1,
        "source": "duffus",
        "source_checked_at": checked_at,
        "runtime_dependency": False,
        "guides": audits,
        "summary": summarize(audits),
    }
    write_json(args.output, payload)
    guide_complet = next((row for row in audits if row["guide_id"] == "guide_complet"), None)
    write_json(args.guide_complet_output, guide_complet or {})
    print(f"Guides audités : {len(audits)}")
    print(f"Rapport : {args.output}")
    print(f"Guide complet : {args.guide_complet_output}")
    return 0


def sitemap_guide_urls(url: str) -> list[str]:
    xml_text = fetch_text(url)
    root = ElementTree.fromstring(xml_text)
    urls: list[str] = []
    for loc in root.findall(".//{*}loc"):
        text = (loc.text or "").strip()
        if re.search(r"/guide/[^/?#]+$", text):
            urls.append(text)
    return urls


def audit_from_local_guide(guide, guide_id: str, url: str, checked_at: str) -> dict[str, object]:
    if guide is None and guide_id == "guide_complet":
        guide = GuideProvider().get_by_id("guide_complet")
    parts = []
    chapters = []
    series_rows = []
    quest_ids: list[int] = []
    achievement_ids: set[int] = set()
    required_items = []
    activity_counts = {"quests": 0, "dungeons": 0, "solo_fights": 0, "group_fights": 0, "farm": 0}
    warnings: list[str] = []
    status = "draft"
    title = title_from_slug(guide_id)
    if guide is not None:
        status = guide.completeness_status
        title = guide.title
        for part in guide.parts:
            parts.append({"id": part.id, "title": part.title, "order": part.order, "coverage": "local"})
            for chapter in part.chapters:
                chapters.append({"id": chapter.id, "part_id": part.id, "title": chapter.title, "order": chapter.order})
                for series in chapter.series:
                    qids = [int(step.entity_id) for step in series.steps if step.step_type == "quest" and step.entity_id is not None]
                    quest_ids.extend(qids)
                    if series.achievement_id:
                        achievement_ids.add(int(series.achievement_id))
                    series_rows.append(
                        {
                            "id": series.id,
                            "chapter_id": chapter.id,
                            "title": series.title,
                            "achievement_id": series.achievement_id,
                            "quest_ids": qids,
                            "activity_counts": {"quests": len(set(qids))},
                        }
                    )
        for ref in guide.context_entities:
            if ref.entity_type == "achievement":
                achievement_ids.add(int(ref.entity_id))
        activity_counts["quests"] = len(set(quest_ids))
        coverage = 100 if status == "complete" else 55 if status == "partial" else 0
    else:
        coverage = 0
        warnings.append("route auditée uniquement : aucun guide Atlas actif relié localement")
    return {
        "guide_id": "guide_complet" if url.rstrip("/") == GUIDE_COMPLETE_URL else guide_id,
        "title": title,
        "source_url": url,
        "source_checked_at": checked_at,
        "parts": parts,
        "chapters": chapters,
        "series": series_rows,
        "quests": sorted(set(quest_ids)),
        "required_items": required_items,
        "activity_counts": activity_counts,
        "resolved_entities": {
            "guide_id": guide.id if guide is not None else None,
            "quest_ids": sorted(set(quest_ids)),
            "achievement_ids": sorted(achievement_ids),
            "item_ids": [guide.reward_item_id] if guide is not None and guide.reward_item_id else [],
        },
        "unresolved_entities": [],
        "coverage_percent": coverage,
        "status": status,
        "warnings": warnings,
    }


def summarize(rows: list[dict[str, object]]) -> dict[str, int]:
    return {
        "guides_audited": len(rows),
        "complete": sum(1 for row in rows if row.get("status") == "complete"),
        "partial": sum(1 for row in rows if row.get("status") == "partial"),
        "draft": sum(1 for row in rows if row.get("status") == "draft"),
        "resolved_quests": len({qid for row in rows for qid in row.get("quests", [])}),
    }


def duffus_url_for_guide(guide) -> str:
    if guide.id == "guide_complet":
        return GUIDE_COMPLETE_URL
    return f"{DUFFUS_BASE}/guide/{guide.id.replace('_', '-')}"


def guide_id_from_url(url: str) -> str:
    if url.rstrip("/") == GUIDE_COMPLETE_URL:
        return "guide_complet"
    return slug_for(url.rstrip("/").rsplit("/", 1)[-1])


def slug_for(value: str) -> str:
    text = str(value or "").casefold().replace("œ", "oe")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def title_from_slug(slug: str) -> str:
    return slug.replace("_", " ").title()


def route_sort_key(url: str) -> tuple[int, str]:
    if url.rstrip("/") == GUIDE_COMPLETE_URL:
        return 0, url
    return 1, url


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "DofusAtlasGuideAudit/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_page_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    sys.exit(main())
