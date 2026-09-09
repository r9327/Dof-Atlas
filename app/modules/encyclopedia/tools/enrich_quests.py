from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from PIL import Image

from app.constants import DATA_DIR, ROOT_DIR
from app.quest_catalog import (
    QuestCatalog,
    build_image_index,
    doduda_rows,
    localized_name,
    normalize_text,
    read_json_file,
    resolve_local_asset_path,
    safe_int,
    write_json_file,
)


QUESTS_DIR = DATA_DIR / "encyclopedia" / "quests"
QUEST_IMAGES_DIR = DATA_DIR / "encyclopedia" / "images" / "quests"
SOURCE_MAPPING_FILE = QUESTS_DIR / "source_mapping.json"
ENRICHED_QUESTS_FILE = QUESTS_DIR / "quests_enriched.json"
IMAGE_MANIFEST_FILE = QUESTS_DIR / "image_manifest.json"
REPORT_FILE = QUESTS_DIR / "enrichment_report.json"
EXTRACTION_SCHEMA_VERSION = 2

DUFFUS_SUPABASE_URL = "https://nprujxwstlfevahfnytz.supabase.co"
DUFFUS_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5wcnVqeHdzdGxmZXZhaGZueXR6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTMzNzg5NzAsImV4cCI6MjA2ODk1NDk3MH0."
    "ZZnG7x3PAEH3xD15-cWYSy7KjwW-CofVAhPa3PnD5l4"
)
DPLN_BASE = "https://www.dofuspourlesnoobs.com/"
DPLN_SITEMAP_URL = DPLN_BASE + "sitemap.xml"
USER_AGENT = "DofusAtlasQuestEnricher/1.0 (+local offline dataset build)"


ACCENT_ENTITY_MAP = {
    "à": "agrave",
    "á": "aacute",
    "â": "acirc",
    "ä": "auml",
    "ç": "ccedil",
    "é": "eacute",
    "è": "egrave",
    "ê": "ecirc",
    "ë": "euml",
    "î": "icirc",
    "ï": "iuml",
    "ô": "ocirc",
    "ö": "ouml",
    "ù": "ugrave",
    "û": "ucirc",
    "ü": "uuml",
    "œ": "oelig",
}


@dataclass
class SourceCandidate:
    source: str
    title: str
    url: str = ""
    slug: str = ""
    source_row_id: str | int | None = None
    has_solution: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedStep:
    title: str
    text: str
    position: str = ""
    npc: str = ""
    interaction: str = ""
    combat: bool = False
    group: bool = False
    tactical: bool = False
    dungeon: bool = False
    farm: bool = False
    monsters: list[str] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ExtractedBlock:
    block_type: str
    content: str = ""
    position: str = ""
    source_url: str = ""
    caption: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class TokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_content = False
        self.content_depth = 0
        self.current_tag = ""
        self.current_attrs: dict[str, str] = {}
        self.current_text: list[str] = []
        self.tokens: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        if tag == "div" and attrs_map.get("id") == "wsite-content":
            self.in_content = True
            self.content_depth = 1
            return
        if self.in_content:
            if tag == "div":
                self.content_depth += 1
            if tag == "br":
                self.current_text.append("\n")
            if tag == "img":
                src = image_src_from_attrs(attrs_map)
                if src:
                    self._flush_text()
                    self.tokens.append({"type": "image", "src": src, "alt": attrs_map.get("alt", "")})
            if self._is_text_block(tag, attrs_map):
                self._flush_text()
                self.current_tag = tag
                self.current_attrs = attrs_map
                self.current_text = []

    def handle_endtag(self, tag: str) -> None:
        if self.in_content and tag == self.current_tag:
            self._flush_text()
            self.current_tag = ""
            self.current_attrs = {}
        if self.in_content and tag == "div":
            self.content_depth -= 1
            if self.content_depth <= 0:
                self._flush_text()
                self.in_content = False

    def handle_data(self, data: str) -> None:
        if self.in_content and self.current_tag:
            self.current_text.append(data)

    def _is_text_block(self, tag: str, attrs: dict[str, str]) -> bool:
        if tag in {"h1", "h2", "h3", "h4", "p", "li"}:
            return True
        classes = set(attrs.get("class", "").split())
        return tag == "div" and "paragraph" in classes

    def _flush_text(self) -> None:
        text = clean_text(" ".join(self.current_text))
        if text:
            self.tokens.append({"type": "text", "text": text, "tag": self.current_tag})
        self.current_text = []


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            name = attrs_map.get("property") or attrs_map.get("name")
            if name:
                self.meta[name] = attrs_map.get("content", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return clean_text(self.meta.get("og:title") or " ".join(self.title_parts))


class MiniHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.images: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        if tag == "br":
            self.text_parts.append("\n")
        elif tag == "img" and attrs_map.get("src"):
            self.images.append({"src": attrs_map.get("src", ""), "alt": attrs_map.get("alt", "")})

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)

    @property
    def text(self) -> str:
        return clean_text(" ".join(self.text_parts))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def request_bytes(url: str, headers: dict[str, str] | None = None, timeout: int = 45) -> bytes:
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    req = Request(url, headers=request_headers)
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def request_json(url: str, headers: dict[str, str] | None = None) -> Any:
    return json.loads(request_bytes(url, headers=headers).decode("utf-8"))


def supabase_all(table: str, select: str = "*", extra_query: str = "", page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    headers = {
        "apikey": DUFFUS_ANON_KEY,
        "Authorization": f"Bearer {DUFFUS_ANON_KEY}",
        "Accept": "application/json",
    }
    offset = 0
    while True:
        query = f"select={quote(select, safe='*,().:')}&limit={page_size}&offset={offset}"
        if extra_query:
            query += "&" + extra_query.lstrip("&")
        batch = request_json(f"{DUFFUS_SUPABASE_URL}/rest/v1/{table}?{query}", headers=headers)
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"[ ]+", " ", text)
    return text.strip(" \n")


def slugify_plain(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("'", " ").replace("’", " ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def slugify_dpln(value: str) -> str:
    text = unicodedata.normalize("NFC", value).casefold()
    parts: list[str] = []
    for char in text:
        parts.append(ACCENT_ENTITY_MAP.get(char, char))
    text = "".join(parts).replace("'", " ").replace("’", " ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def dpln_slug_candidates(title: str) -> set[str]:
    plain = slugify_plain(title)
    entity = slugify_dpln(title)
    candidates = {plain, entity}
    candidates.add(plain.replace("oe", "oelig"))
    candidates.add(entity.replace("oelig", "oe"))
    return {candidate for candidate in candidates if candidate}


def recommended_level_ranges(prerequisites: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for prerequisite in prerequisites:
        clean = clean_text(prerequisite)
        match = re.search(
            r"niveau\s+recommand(?:e|é)\s*:?[ ]*(\d+)(?:\s*[-àa]\s*(\d+))?",
            clean,
            re.IGNORECASE,
        )
        if not match:
            continue
        lower = int(match.group(1))
        upper = int(match.group(2) or lower)
        ranges.append((min(lower, upper), max(lower, upper)))
    return ranges


def dpln_mapping_confidence(
    quest: Any,
    candidate: dict[str, Any],
    extracted: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    """Classify a live DPLN page without fuzzy or positional matching."""

    signals: list[str] = []
    conflicts: list[str] = []
    source_title = str(extracted.get("title") or "")
    if source_title_key(source_title) == source_title_key(str(quest.name)):
        signals.append("normalized_title_exact")
    elif corrupt_source_title_compatible(source_title, str(quest.name)):
        signals.append("normalized_title_corrupt_compatible")
        conflicts.append("source_title_encoding_corrupt")
    else:
        return "AMBIGUOUS", signals, ["source_title_mismatch"]

    slug = str(candidate.get("slug") or "").casefold()
    if slug and slug in dpln_slug_candidates(str(quest.name)):
        signals.append("generated_slug_exact")
    else:
        conflicts.append("slug_not_demonstrated")

    ranges = recommended_level_ranges(list(extracted.get("prerequisites") or []))
    local_level = int(getattr(quest, "level_min", 0) or 0)
    if ranges and local_level:
        if any(lower <= local_level <= upper for lower, upper in ranges):
            signals.append("recommended_level_compatible")
        else:
            conflicts.append("recommended_level_conflict")

    local_prerequisites = [normalize_text(value) for value in getattr(quest, "prerequisites", []) or []]
    source_prerequisites = [normalize_text(value) for value in extracted.get("prerequisites", []) or []]
    if any(
        source_value and any(source_value in local_value or local_value in source_value for local_value in local_prerequisites)
        for source_value in source_prerequisites
    ):
        signals.append("prerequisite_overlap")

    if "generated_slug_exact" not in signals:
        return "AMBIGUOUS", signals, conflicts
    if conflicts:
        return "HIGH", signals, conflicts
    if any(signal in signals for signal in ("recommended_level_compatible", "prerequisite_overlap")):
        return "EXACT", signals, conflicts
    return "HIGH", signals, conflicts


def source_title_key(title: str) -> str:
    # DPLN mixes typographic ligatures and their ASCII spellings depending on
    # the age of a page (oeuf/oe-ligature, coeur/coeur-ligature). They are the
    # same normalized title signal; the previous replace was a no-op.
    canonical = (
        str(title or "")
        .replace("œ", "oe")
        .replace("Œ", "OE")
        .replace("æ", "ae")
        .replace("Æ", "AE")
    )
    return normalize_text(canonical)


def corrupt_source_title_compatible(source_title: str, local_title: str) -> bool:
    source_key = source_title_key(source_title)
    local_key = source_title_key(local_title)
    if "�" not in source_key:
        return False
    pattern = "^" + re.escape(source_key).replace(re.escape("�"), ".") + "$"
    return re.fullmatch(pattern, local_key) is not None


def dpln_sitemap_urls() -> dict[str, str]:
    payload = request_bytes(DPLN_SITEMAP_URL)
    root = ElementTree.fromstring(payload)
    urls: dict[str, str] = {}
    for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
        value = (loc.text or "").strip()
        parsed = urlparse(value)
        if not parsed.path.endswith(".html"):
            continue
        slug = Path(parsed.path).stem.casefold()
        urls.setdefault(slug, value)
    return urls


def index_by_key(candidates: list[SourceCandidate]) -> dict[str, list[SourceCandidate]]:
    indexed: dict[str, list[SourceCandidate]] = {}
    for candidate in candidates:
        key = source_title_key(candidate.title)
        if key:
            indexed.setdefault(key, []).append(candidate)
    return indexed


def build_mapping(
    local_quests: list[Any],
    duffus_quests: list[dict[str, Any]],
    duffus_pages: list[dict[str, Any]],
    dpln_urls: dict[str, str],
) -> dict[str, Any]:
    local_by_key: dict[str, list[int]] = {}
    for quest in local_quests:
        local_by_key.setdefault(source_title_key(quest.name), []).append(int(quest.id))

    duffus_candidates = [
        SourceCandidate(
            source="duffus",
            title=str(row.get("name") or ""),
            source_row_id=row.get("id"),
            has_solution=False,
            payload=row,
        )
        for row in duffus_quests
        if row.get("name")
    ]
    duffus_page_candidates = [
        SourceCandidate(
            source="duffus",
            title=str((row.get("meta") or {}).get("title") or ""),
            slug=str(row.get("slug") or ""),
            url=f"https://duffus.fr/quete/{row.get('slug')}",
            source_row_id=row.get("id"),
            has_solution=True,
            payload=row,
        )
        for row in duffus_pages
        if isinstance(row.get("meta"), dict) and (row.get("meta") or {}).get("title")
    ]
    duffus_by_key = index_by_key(duffus_candidates)
    duffus_pages_by_key = index_by_key(duffus_page_candidates)

    quests: dict[str, Any] = {}
    for quest in sorted(local_quests, key=lambda item: int(item.id)):
        quest_id = str(int(quest.id))
        key = source_title_key(quest.name)
        local_duplicates = sorted(local_by_key.get(key, []))
        dpln_matches = []
        for slug in sorted(dpln_slug_candidates(quest.name)):
            if slug in dpln_urls:
                dpln_matches.append(
                    {
                        "title": quest.name,
                        "slug": slug,
                        "url": dpln_urls[slug],
                        "match": "generated_slug",
                    }
                )
        duffus_rows = duffus_by_key.get(key, [])
        duffus_page_rows = duffus_pages_by_key.get(key, [])
        status = "matched" if duffus_rows or duffus_page_rows or dpln_matches else "missing"
        if len(local_duplicates) > 1 or len(duffus_rows) > 1 or len(duffus_page_rows) > 1 or len(dpln_matches) > 1:
            status = "ambiguous"
        quests[quest_id] = {
            "quest_id": int(quest.id),
            "name": quest.name,
            "normalized_name": key,
            "status": status,
            "local_duplicate_quest_ids": local_duplicates if len(local_duplicates) > 1 else [],
            "duffus": [
                {
                    "title": row.title,
                    "source_row_id": row.source_row_id,
                    "has_solution": row.has_solution,
                    "slug": row.slug,
                    "url": row.url,
                }
                for row in [*duffus_rows, *duffus_page_rows]
            ],
            "dofus_pour_les_noobs": dpln_matches,
            "notes": [] if status != "ambiguous" else ["Mapping ambigu: aucune association automatique arbitraire."],
        }
    return {
        "version": 1,
        "generated_at": now_iso(),
        "method": "name_normalized_exact_with_generated_dpln_slug_candidates",
        "quests": quests,
    }


def full_url(src: str, base: str) -> str:
    if src.startswith("//"):
        return "https:" + src
    return urljoin(base, src)


def image_src_from_attrs(attrs: dict[str, str]) -> str:
    for key in ("src", "data-src", "data-original", "data-lazy-src"):
        value = str(attrs.get(key) or "").strip()
        if value:
            return value
    srcset = str(attrs.get("srcset") or attrs.get("data-srcset") or "").strip()
    if srcset:
        return srcset.split(",", 1)[0].strip().split(" ", 1)[0]
    return ""


def useful_image(src: str, source: str) -> bool:
    lowered = src.casefold()
    if not src:
        return False
    blocked = ("favicon", "logo", "promo", "card/", "arrowup", "/ads/", "banner", "background", "custom_themes")
    if any(token in lowered for token in blocked):
        return False
    if source == "duffus":
        return any(token in lowered for token in ("quest-assets", "/renderer/", "/images/pnj/"))
    if source == "dpln":
        return "/uploads/1/3/0/1/13010384/" in lowered and re.search(r"/[^/.]+(?:_orig)?\.(?:jpg|jpeg|png|webp)(?:\?|$)", lowered)
    return False


def load_manifest() -> dict[str, Any]:
    manifest = read_json_file(IMAGE_MANIFEST_FILE, {"version": 1, "by_url": {}, "by_sha256": {}})
    if not isinstance(manifest, dict):
        return {"version": 1, "by_url": {}, "by_sha256": {}}
    manifest.setdefault("version", 1)
    manifest.setdefault("by_url", {})
    manifest.setdefault("by_sha256", {})
    return manifest


def portable_asset_path(value: str | Path) -> str:
    resolved = Path(resolve_local_asset_path(value))
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except (OSError, ValueError):
        return str(value)


def save_image(
    url: str,
    quest_id: int,
    step_index: int,
    image_index: int,
    manifest: dict[str, Any],
    stats: dict[str, int],
    dry_run: bool = False,
    raw_data: bytes | None = None,
) -> str:
    by_url = manifest.setdefault("by_url", {})
    by_sha = manifest.setdefault("by_sha256", {})
    existing = by_url.get(url)
    if isinstance(existing, dict):
        path = resolve_local_asset_path(existing.get("path"))
        if path and Path(path).exists():
            stored_path = portable_asset_path(path)
            existing["path"] = stored_path
            stats["images_reused"] += 1
            return stored_path
    if dry_run:
        return ""
    raw = raw_data if raw_data is not None else request_bytes(url)
    sha = hashlib.sha256(raw).hexdigest()
    reused = by_sha.get(sha)
    if isinstance(reused, dict):
        path = resolve_local_asset_path(reused.get("path"))
        if path and Path(path).exists():
            stored_path = portable_asset_path(path)
            by_url[url] = {"path": stored_path, "sha256": sha}
            stats["images_reused"] += 1
            return stored_path
    folder = QUEST_IMAGES_DIR / str(int(quest_id))
    folder.mkdir(parents=True, exist_ok=True)
    suffix = "" if image_index == 1 else f"_{image_index:02d}"
    path = folder / f"step_{step_index:02d}{suffix}.webp"
    counter = 2
    while path.exists():
        path = folder / f"step_{step_index:02d}{suffix}_{counter}.webp"
        counter += 1
    image = Image.open(BytesIO(raw))
    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA")
    image.save(path, format="WEBP", quality=85, method=6)
    local_path = portable_asset_path(path)
    row = {"path": local_path, "sha256": sha, "source_url": url}
    by_url[url] = row
    by_sha[sha] = row
    stats["images_downloaded"] += 1
    return local_path


def prefetch_image_bytes(urls: list[str], workers: int) -> dict[str, bytes | Exception]:
    """Fetch page images concurrently without mutating the shared manifest."""
    unique_urls = list(dict.fromkeys(url for url in urls if url))
    if not unique_urls:
        return {}
    results: dict[str, bytes | Exception] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 8))) as pool:
        futures = {pool.submit(request_bytes, url): url for url in unique_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = exc
    return results


def extract_duffus_steps(content_html: str) -> list[ExtractedStep]:
    steps: list[ExtractedStep] = []
    pattern = re.compile(r'(<div class="qstep(?:\s|").*?)(?=<div class="qstep(?:\s|")|$)', re.IGNORECASE | re.DOTALL)
    for index, match in enumerate(pattern.finditer(content_html or ""), 1):
        block = match.group(1)
        parser = MiniHTMLParser()
        parser.feed(block)
        text = clean_duffus_step_text(parser.text)
        if not text or len(text) < 3:
            continue
        position = first_coord(text) or first_attr(block, "data-coords") or coord_from_xy_attrs(block)
        step = ExtractedStep(
            title="",
            text=text,
            position=position,
            npc=first_attr(block, "data-npc"),
            interaction=interaction_from_text(text),
            **flags_from_text(text),
        )
        for image in parser.images:
            src = full_url(image.get("src", ""), "https://duffus.fr/")
            if useful_image(src, "duffus"):
                step.images.append({"source_url": src, "caption": clean_text(image.get("alt", ""))})
        steps.append(step)
    return steps


def clean_duffus_step_text(text: str) -> str:
    lines = [
        line
        for line in extract_lines(text)
        if normalize_text(line) not in {"mini_carte", "l_apercu_de_la_carte_sera_affiche_ici_sur_le_site"}
    ]
    return clean_text(" ".join(lines))


def extract_dpln_page(payload: bytes, url: str, title: str) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="replace")
    meta = MetaParser()
    meta.feed(text)
    parser = TokenParser()
    parser.feed(text)
    steps: list[ExtractedStep] = []
    prerequisites: list[str] = []
    rewards: list[str] = []
    required_items: list[dict[str, Any]] = []
    current: ExtractedStep | None = None
    phase = "intro"
    for token in parser.tokens:
        if token.get("type") == "image":
            src = full_url(str(token.get("src") or ""), url)
            if current is not None and useful_image(src, "dpln"):
                current.images.append({"source_url": src, "caption": clean_text(token.get("alt", ""))})
            continue
        raw_text = clean_text(token.get("text", ""))
        if skip_dpln_text(raw_text, title):
            continue
        lowered = normalize_text(raw_text)
        if "prerequis" in lowered:
            phase = "prerequisites"
            prerequisites.extend(extract_lines(raw_text))
            continue
        if "recompenses" in lowered:
            phase = "rewards"
            rewards.extend(extract_lines(raw_text))
            continue
        if "a_prevoir" in lowered or "prevoir" in lowered:
            phase = "required"
            for line in extract_lines(raw_text):
                item = parse_quantity_line(line)
                if item:
                    required_items.append(item)
            continue
        if phase == "prerequisites" and not looks_like_action(raw_text):
            prerequisites.extend(extract_lines(raw_text))
            continue
        if phase == "rewards" and not looks_like_action(raw_text):
            rewards.extend(extract_lines(raw_text))
            continue
        if phase == "required" and not looks_like_action(raw_text):
            for line in extract_lines(raw_text):
                item = parse_quantity_line(line)
                if item:
                    required_items.append(item)
            continue
        phase = "solution"
        flags = flags_from_text(raw_text)
        current = ExtractedStep(
            title="",
            text=raw_text,
            position=first_coord(raw_text),
            npc=npc_from_text(raw_text),
            interaction=interaction_from_text(raw_text),
            **flags,
        )
        steps.append(current)
    return {
        "title": meta.title,
        "source_url": url,
        "steps": steps,
        "prerequisites": unique_strings(prerequisites),
        "rewards": unique_strings(rewards),
        "required_items": dedupe_items(required_items),
    }


def extract_dpln_page_v2(payload: bytes, url: str, title: str) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="replace")
    meta = MetaParser()
    meta.feed(text)
    parser = TokenParser()
    parser.feed(text)
    steps: list[ExtractedStep] = []
    blocks: list[ExtractedBlock] = []
    prerequisites: list[str] = []
    rewards: list[str] = []
    required_items: list[dict[str, Any]] = []
    preparation: list[str] = []
    launch_position: dict[str, Any] = {}
    current: ExtractedStep | None = None
    phase = "intro"
    solution_started = False
    skipped_text_blocks = 0
    source_text_blocks = 0
    useful_image_count = 0

    for token in parser.tokens:
        if token.get("type") == "image":
            src = full_url(str(token.get("src") or ""), url)
            if useful_image(src, "dpln"):
                useful_image_count += 1
                caption = clean_text(token.get("alt", ""))
                if solution_started:
                    blocks.append(ExtractedBlock("image", source_url=src, caption=caption))
                    if current is not None:
                        current.images.append({"source_url": src, "caption": caption})
            continue

        raw_text = clean_text(token.get("text", ""))
        if skip_dpln_text(raw_text, title):
            skipped_text_blocks += 1
            continue
        source_text_blocks += 1
        lowered = normalize_text(raw_text)
        launch_position = launch_position or launch_position_from_text(raw_text)

        if "prerequis" in lowered:
            phase = "prerequisites"
            for line in extract_lines(raw_text):
                if normalize_text(line) not in {"prerequis"} and not launch_position_line(line):
                    prerequisites.append(line)
            continue
        if "recompenses" in lowered:
            phase = "rewards"
            for line in extract_lines(raw_text):
                if normalize_text(line) not in {"recompenses"}:
                    rewards.append(line)
            continue
        if "a_prevoir" in lowered or "prevoir" in lowered:
            phase = "required"
            _collect_required_or_preparation(raw_text, required_items, preparation)
            continue
        if phase == "prerequisites" and not solution_text_starts(raw_text):
            for line in extract_lines(raw_text):
                collect_prerequisite_metadata_line(line, prerequisites, required_items, preparation, rewards)
            continue
        if phase == "rewards" and not solution_text_starts(raw_text):
            rewards.extend(extract_lines(raw_text))
            continue
        if phase == "required" and not solution_text_starts(raw_text):
            _collect_required_or_preparation(raw_text, required_items, preparation)
            continue

        phase = "solution"
        solution_started = True
        tag = str(token.get("tag") or "")
        flags = flags_from_text(raw_text)
        current = ExtractedStep(
            title=raw_text if looks_like_heading(raw_text, tag) else "",
            text=raw_text,
            position=first_coord(raw_text),
            npc=npc_from_text(raw_text),
            interaction=interaction_from_text(raw_text),
            **flags,
        )
        steps.append(current)
        blocks.append(
            ExtractedBlock(
                dpln_block_type(raw_text, tag, flags),
                content=raw_text,
                position=first_coord(raw_text),
                data={
                    "npc": current.npc,
                    "interaction": current.interaction,
                    "combat": current.combat,
                    "group": current.group,
                    "tactical": current.tactical,
                    "dungeon": current.dungeon,
                    "farm": current.farm,
                },
            )
        )

    image_blocks = sum(1 for block in blocks if block.block_type == "image")
    text_blocks = sum(1 for block in blocks if block.block_type != "image")
    fidelity_alerts: list[str] = []
    if useful_image_count and not image_blocks:
        fidelity_alerts.append(f"{useful_image_count} image(s) source detectee(s), 0 conservee.")
    if source_text_blocks >= 10 and text_blocks < max(3, source_text_blocks // 3):
        fidelity_alerts.append(f"Extraction texte suspecte: {text_blocks}/{source_text_blocks} bloc(s).")

    return {
        "title": meta.title,
        "source_url": url,
        "steps": steps,
        "blocks": blocks,
        "prerequisites": unique_strings(prerequisites),
        "rewards": unique_strings(rewards),
        "required_items": dedupe_items(required_items),
        "preparation": unique_strings(preparation),
        "launch_position": launch_position,
        "quality": {
            "source_text_blocks": source_text_blocks,
            "skipped_text_blocks": skipped_text_blocks,
            "solution_block_count": len(blocks),
            "text_block_count": text_blocks,
            "source_image_count": useful_image_count,
            "image_block_count": image_blocks,
            "position_count": len({block.position for block in blocks if block.position}),
            "heading_count": sum(1 for block in blocks if block.block_type == "heading"),
            "fidelity_alerts": fidelity_alerts,
        },
    }


def skip_dpln_text(text: str, title: str) -> bool:
    key = normalize_text(text)
    if not key:
        return True
    blocked_prefixes = (
        "mis_en_ligne",
        "derniere_mise_a_jour",
        "signaler_un_probleme",
        "commentaires",
        "ajouter_un_commentaire",
        "dofus_est_un_mmorpg",
    )
    if key == normalize_text(title) or any(key.startswith(prefix) for prefix in blocked_prefixes):
        return True
    return len(text) <= 2


def extract_lines(text: str) -> list[str]:
    rows = re.split(r"\n+|(?:^|\s)[•*-]\s+", text)
    return [clean_text(row).strip(". ") for row in rows if clean_text(row).strip(". ")]


def parse_quantity_line(text: str) -> dict[str, Any] | None:
    clean = clean_text(text).strip(". ")
    # A DPLN paragraph may mention several prices/items in prose. Treating the
    # first ``N x`` occurrence as the whole item name produced corrupt rows such
    # as "Pandneken et 1 x Alcool ...". Only accept a standalone item line.
    match = re.fullmatch(r"(\d+)\s*x\s+([^,;:.]{1,120})", clean, re.IGNORECASE)
    if not match:
        return None
    name = clean_text(match.group(2)).strip(". ")
    if not name:
        return None
    return {"name": name, "quantity": int(match.group(1)), "source_text": clean}


def _collect_required_or_preparation(
    text: str,
    required_items: list[dict[str, Any]],
    preparation: list[str],
) -> None:
    for line in extract_lines(text):
        key = normalize_text(line)
        if not key or key in {"a_prevoir", "prevoir"}:
            continue
        if preparation_line(line):
            preparation.append(line)
            continue
        item = parse_quantity_line(line)
        if item:
            required_items.append(item)


def collect_prerequisite_metadata_line(
    line: str,
    prerequisites: list[str],
    required_items: list[dict[str, Any]],
    preparation: list[str],
    rewards: list[str],
) -> None:
    clean = clean_text(line)
    key = normalize_text(clean)
    if not clean or key in {"prerequis"}:
        return
    if key.endswith("_xp") or "kamas" in key:
        rewards.append(clean)
        return
    if preparation_line(clean):
        preparation.append(clean)
        return
    item = parse_quantity_line(clean)
    if item:
        rewards.append(clean)
        return
    prerequisites.append(clean)


def preparation_line(text: str) -> bool:
    key = normalize_text(text)
    return any(
        token in key
        for token in (
            "combat",
            "donjon",
            "drop",
            "droper",
            "monstre",
            "boss",
            "groupe",
            "seul",
            "tactique",
            "zone",
        )
    )


def launch_position_line(text: str) -> bool:
    return "position_de_lancement" in normalize_text(text)


def launch_position_from_text(text: str) -> dict[str, Any]:
    key = normalize_text(text)
    if not launch_position_line(text) and not ("quete_se_lance" in key or "qu_te_se_lance" in key):
        return {}
    position = first_coord(text)
    if not position:
        return {}
    return {"position": position, "source_text": clean_text(text)}


def solution_text_starts(text: str) -> bool:
    key = normalize_text(text)
    if not key:
        return False
    if key in {"prerequis", "recompenses", "a_prevoir", "prevoir"}:
        return False
    if first_coord(text):
        return True
    return looks_like_action(text) and not preparation_line(text)


def looks_like_heading(text: str, tag: str = "") -> bool:
    clean = clean_text(text).strip()
    if not clean:
        return False
    key = normalize_text(clean)
    if key in {"sorts_a_venir"}:
        return False
    if tag in {"h2", "h3", "h4"}:
        return True
    if len(clean) > 90:
        return False
    if first_coord(clean):
        return False
    if looks_like_action(clean):
        return False
    return clean.endswith(":")


def dpln_block_type(text: str, tag: str, flags: dict[str, bool]) -> str:
    if looks_like_heading(text, tag):
        return "heading"
    key = normalize_text(text)
    if key.startswith("attention") or key.startswith("note"):
        return "warning" if key.startswith("attention") else "information"
    if flags.get("combat"):
        return "combat"
    if first_coord(text):
        return "position"
    return "text"


def looks_like_action(text: str) -> bool:
    key = normalize_text(text)
    return any(
        token in key
        for token in (
            "allez",
            "rendez",
            "parlez",
            "combat",
            "cliquez",
            "utilisez",
            "entrez",
            "sortez",
            "retournez",
            "dirigez",
            "vaincre",
            "defiez",
            "traversez",
            "obtenez",
        )
    )


def first_coord(text: str) -> str:
    match = re.search(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]", text or "")
    return f"[{int(match.group(1))},{int(match.group(2))}]" if match else ""


def first_attr(text: str, attr: str) -> str:
    match = re.search(rf'\b{re.escape(attr)}="([^"]*)"', text or "", re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else ""


def coord_from_xy_attrs(text: str) -> str:
    x = first_attr(text, "data-x")
    y = first_attr(text, "data-y")
    if x and y:
        return f"[{x},{y}]"
    return ""


def npc_from_text(text: str) -> str:
    match = re.search(r"\b(?:Parlez|Retournez voir|Allez voir)\s+(?:à|a|au|aux)?\s*([^.,:]+)", text, re.IGNORECASE)
    return clean_text(match.group(1)).strip(" :") if match else ""


def interaction_from_text(text: str) -> str:
    key = normalize_text(text)
    if "cliquez" in key or "clique" in key:
        return "click"
    if "parlez" in key:
        return "talk"
    if "utilisez" in key:
        return "use"
    if "combat" in key or "vaincre" in key or "defiez" in key:
        return "fight"
    if "craft" in key or "fabriquer" in key:
        return "craft"
    return ""


def flags_from_text(text: str) -> dict[str, bool]:
    key = normalize_text(text)
    return {
        "combat": any(token in key for token in ("combat", "vaincre", "defiez", "boss")),
        "group": any(token in key for token in ("groupe", "plusieurs")),
        "tactical": "tactique" in key,
        "dungeon": any(token in key for token in ("donjon", "boss")),
        "farm": any(token in key for token in ("farm", "drop", "droper", "recuperer", "ressource")),
    }


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = normalize_text(text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        name = clean_text(item.get("name", ""))
        key = normalize_text(name)
        if not key:
            continue
        quantity = int(item["quantity"]) if item.get("quantity") not in (None, "") else None
        if key in merged:
            previous_quantity = merged[key].get("quantity")
            if quantity is not None and previous_quantity is None:
                merged[key]["quantity"] = quantity
            elif quantity is not None and previous_quantity is not None and quantity != previous_quantity:
                conflicts = merged[key].setdefault("quantity_conflicts", [])
                for value in (int(previous_quantity), quantity):
                    if value not in conflicts:
                        conflicts.append(value)
        else:
            row = dict(item)
            row["name"] = name
            row["quantity"] = quantity
            merged[key] = row
    return sorted(merged.values(), key=lambda item: normalize_text(item["name"]))


def merge_required_items(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge source lists without adding quantities from duplicate evidence.

    DPLN is the primary enrichment source. Duffus can fill a missing item, but
    the same item reported by both sources is corroboration, not two separate
    requirements to add together.
    """

    merged = {normalize_text(item.get("name", "")): dict(item) for item in dedupe_items(primary)}
    for item in dedupe_items(secondary):
        key = normalize_text(item.get("name", ""))
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(item)
            continue
        primary_quantity = merged[key].get("quantity")
        secondary_quantity = item.get("quantity")
        if (
            primary_quantity not in (None, "")
            and secondary_quantity not in (None, "")
            and int(primary_quantity) != int(secondary_quantity)
        ):
            merged[key]["secondary_quantity"] = int(secondary_quantity)
            merged[key]["quantity_source_conflict"] = True
    return sorted(merged.values(), key=lambda item: normalize_text(item.get("name", "")))


def enrichment_row_is_current(row: Any) -> bool:
    return isinstance(row, dict) and safe_int(row.get("extraction_version")) == EXTRACTION_SCHEMA_VERSION


def load_item_lookup(data_dir: Path = None) -> dict[str, dict[str, Any]]:
    data_dir = data_dir or (DATA_DIR / "cache" / "dofus_maps" / "raw" / "doduda_cli")
    language = read_json_file(data_dir / "languages" / "fr.json", {"entries": {}})
    entries = language.get("entries", {}) if isinstance(language, dict) else {}
    if not isinstance(entries, dict):
        entries = {}
    image_index = build_image_index(DATA_DIR / "images")
    lookup: dict[str, dict[str, Any]] = {}
    for item_id, row in doduda_rows(data_dir / "items.json").items():
        name = localized_name(row, entries, "")
        key = normalize_text(name)
        if not key:
            continue
        icon_id = safe_int(row.get("iconId"))
        lookup.setdefault(
            key,
            {
                "item_id": int(item_id),
                "name": name,
                "image_path": image_index.get(str(icon_id), "") if icon_id is not None else "",
                "source": "doduda",
            },
        )
    return lookup


def resolve_required_items(items: list[dict[str, Any]], item_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    resolved = []
    for item in dedupe_items(items):
        name = clean_text(item.get("name", ""))
        if not name:
            continue
        row = {
            "name": name,
            "quantity": item.get("quantity"),
            "source_text": item.get("source_text", ""),
            "preparable": True,
            "consumed": item.get("consumed") if "consumed" in item else None,
            "source": item.get("source") or "dofus_pour_les_noobs",
        }
        local = item_lookup.get(normalize_text(name))
        if local:
            row.update(
                {
                    "item_id": local.get("item_id"),
                    "name": local.get("name") or name,
                    "image_path": local.get("image_path") or "",
                    "resolved_from": local.get("source") or "local",
                }
            )
        else:
            row["unresolved"] = True
        resolved.append(row)
    return sorted(resolved, key=lambda item: normalize_text(item.get("name", "")))


def step_to_json(
    step: ExtractedStep,
    quest_id: int,
    step_index: int,
    manifest: dict[str, Any],
    stats: dict[str, int],
    images: bool,
    prefetched: dict[str, bytes | Exception] | None = None,
) -> dict[str, Any]:
    image_rows = []
    for image_index, image in enumerate(step.images, 1):
        url = image.get("source_url", "")
        path = ""
        if images:
            try:
                raw = (prefetched or {}).get(url)
                if isinstance(raw, Exception):
                    raise raw
                path = save_image(url, quest_id, step_index, image_index, manifest, stats, raw_data=raw)
            except Exception as exc:
                stats["image_errors"] += 1
                image_rows.append({"source_url": url, "caption": image.get("caption", ""), "error": str(exc)})
                continue
        image_rows.append({"source_url": url, "path": path, "caption": image.get("caption", "")})
    return {
        "title": step.title,
        "description": "",
        "objectives": [
            {
                "text": step.text,
                "position": step.position,
                "npc": step.npc,
                "interaction": step.interaction,
                "combat": step.combat,
                "group": step.group,
                "tactical": step.tactical,
                "dungeon": step.dungeon,
                "farm": step.farm,
                "monsters": step.monsters,
                "images": image_rows,
                "image_path": next((row["path"] for row in image_rows if row.get("path")), ""),
                "caption": next((row["caption"] for row in image_rows if row.get("caption")), ""),
            }
        ],
    }


def block_to_json(
    block: ExtractedBlock,
    quest_id: int,
    block_index: int,
    manifest: dict[str, Any],
    stats: dict[str, int],
    images: bool,
    prefetched: dict[str, bytes | Exception] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "order": int(block_index),
        "type": block.block_type,
        "content": block.content,
        "position": block.position,
        "caption": block.caption,
        "source_url": block.source_url,
        "data": block.data,
    }
    if block.block_type == "image" and block.source_url:
        if images:
            try:
                raw = (prefetched or {}).get(block.source_url)
                if isinstance(raw, Exception):
                    raise raw
                row["image_path"] = save_image(
                    block.source_url,
                    quest_id,
                    block_index,
                    1,
                    manifest,
                    stats,
                    raw_data=raw,
                )
            except Exception as exc:
                stats["image_errors"] += 1
                row["error"] = str(exc)
        else:
            row["image_path"] = ""
    return {key: value for key, value in row.items() if value not in ("", {}, [])}


def enrich(args: argparse.Namespace) -> dict[str, Any]:
    QUESTS_DIR.mkdir(parents=True, exist_ok=True)
    catalog = QuestCatalog.load()
    previous = read_json_file(ENRICHED_QUESTS_FILE, {"quests": {}})
    previous_quests = previous.get("quests", {}) if isinstance(previous, dict) else {}
    stats: dict[str, int] = {
        "total": len(catalog.quests),
        "complete": 0,
        "completed": 0,
        "corrected": 0,
        "new": 0,
        "ambiguous": 0,
        "missing": 0,
        "images_downloaded": 0,
        "images_reused": 0,
        "image_errors": 0,
        "errors": 0,
    }

    print("Chargement Duffus/Doflex Supabase...")
    duffus_quests = supabase_all("quests", "id,name,level_min,level_max,start_criterion,is_dungeon_quest,is_party_quest,type,is_event,repeat_type,step_ids_json")
    duffus_pages = supabase_all("quest_pages", "*", "published=eq.true")
    duffus_resources = supabase_all("quest_resources", "quest_id,quest,name,qty")
    print("Chargement sitemap DPLN...")
    dpln_urls = dpln_sitemap_urls()

    mapping = build_mapping(catalog.quests, duffus_quests, duffus_pages, dpln_urls)
    for qid, mapping_row in mapping.get("quests", {}).items():
        previous_row = previous_quests.get(qid, {}) if isinstance(previous_quests, dict) else {}
        previous_sources = previous_row.get("sources", {}) if isinstance(previous_row, dict) else {}
        previous_dpln = previous_sources.get("dofus_pour_les_noobs", []) if isinstance(previous_sources, dict) else []
        annotations_by_url = {
            str(candidate.get("url") or ""): candidate
            for candidate in previous_dpln
            if isinstance(candidate, dict) and candidate.get("confidence")
        }
        for candidate in mapping_row.get("dofus_pour_les_noobs", []) or []:
            previous_candidate = annotations_by_url.get(str(candidate.get("url") or ""))
            if previous_candidate:
                for key in ("confidence", "signals", "conflicts"):
                    if key in previous_candidate:
                        candidate[key] = previous_candidate[key]
    write_json_file(SOURCE_MAPPING_FILE, mapping)

    duffus_pages_by_key = {
        source_title_key(str((row.get("meta") or {}).get("title") or "")): row
        for row in duffus_pages
        if isinstance(row.get("meta"), dict)
    }
    duffus_quests_by_key = {
        source_title_key(str(row.get("name") or "")): row
        for row in duffus_quests
        if row.get("name")
    }
    resources_by_title: dict[str, list[dict[str, Any]]] = {}
    for row in duffus_resources:
        title = str(row.get("quest") or "")
        name = clean_text(row.get("name") or "")
        qty = int(row.get("qty") or 0) if str(row.get("qty") or "").isdigit() else 0
        if title and name and qty > 0:
            resources_by_title.setdefault(source_title_key(title), []).append(
                {"name": name, "quantity": qty, "source": "duffus"}
            )

    requested_quest_ids = {int(value) for value in getattr(args, "quest_id", []) or []}
    semantic_audit_path = getattr(args, "semantic_audit", None)
    selection_requested = bool(requested_quest_ids) or bool(semantic_audit_path)
    if semantic_audit_path:
        semantic_audit = read_json_file(Path(semantic_audit_path), {})
        for audit_row in semantic_audit.get("quests", []) if isinstance(semantic_audit, dict) else []:
            if not isinstance(audit_row, dict):
                continue
            needs_correction = (
                audit_row.get("image") == "IMAGE_MISSING"
                or audit_row.get("text") in {"TEXT_PARTIAL", "TEXT_MISSING"}
                or audit_row.get("objects") == "OBJECTS_WRONG"
            )
            if (
                audit_row.get("mapping") in {"EXACT", "HIGH"}
                and needs_correction
            ):
                requested_quest_ids.add(int(audit_row["quest_id"]))
    item_lookup = load_item_lookup()
    manifest = load_manifest()
    enriched_quests: dict[str, Any] = {}
    source_errors: list[dict[str, Any]] = []
    if isinstance(previous_quests, dict) and not args.force:
        enriched_quests.update(previous_quests)
    processed = 0

    for quest in catalog.quests:
        quest_id = int(quest.id)
        qid = str(quest_id)
        if selection_requested and quest_id not in requested_quest_ids:
            if qid in previous_quests:
                enriched_quests[qid] = previous_quests[qid]
            continue
        previous_row = previous_quests.get(qid) if isinstance(previous_quests, dict) else None
        if not args.force and qid in previous_quests and enrichment_row_is_current(previous_row):
            continue
        if args.limit and processed >= args.limit:
            if qid in previous_quests:
                enriched_quests[qid] = previous_quests[qid]
            continue
        processed += 1
        row_mapping = mapping["quests"][qid]
        if row_mapping["status"] == "ambiguous":
            stats["ambiguous"] += 1
            enriched_quests[qid] = base_enriched_quest(quest, row_mapping, status="ambiguous")
            continue

        key = source_title_key(quest.name)
        duffus_page = duffus_pages_by_key.get(key)
        source = ""
        source_url = ""
        extracted_steps: list[ExtractedStep] = []
        extracted_blocks: list[ExtractedBlock] = []
        prerequisites: list[str] = []
        rewards: list[str] = []
        duffus_required_items: list[dict[str, Any]] = resources_by_title.get(key, [])
        required_items: list[dict[str, Any]] = list(duffus_required_items)
        preparation: list[str] = []
        launch_position: dict[str, Any] = {}
        source_quality: dict[str, Any] = {}
        source_meta: dict[str, Any] = {}
        mapping_confidence = ""
        mapping_signals: list[str] = []
        mapping_conflicts: list[str] = []
        dpln_mapping_rejected = False

        dpln_rows = row_mapping.get("dofus_pour_les_noobs") or []
        if dpln_rows:
            url = dpln_rows[0]["url"]
            try:
                time.sleep(max(0.0, float(args.delay)))
                page = request_bytes(url)
                dpln = extract_dpln_page_v2(page, url, quest.name)
                mapping_confidence, mapping_signals, mapping_conflicts = dpln_mapping_confidence(
                    quest,
                    dpln_rows[0],
                    dpln,
                )
                dpln_rows[0]["confidence"] = mapping_confidence
                dpln_rows[0]["signals"] = mapping_signals
                dpln_rows[0]["conflicts"] = mapping_conflicts
                if mapping_confidence in {"EXACT", "HIGH"}:
                    source = "dofus_pour_les_noobs"
                    source_url = url
                    extracted_steps = dpln["steps"]
                    extracted_blocks = dpln["blocks"]
                    prerequisites = dpln["prerequisites"]
                    rewards = dpln["rewards"]
                    required_items = merge_required_items(dpln["required_items"], duffus_required_items)
                    preparation = dpln["preparation"]
                    launch_position = dpln["launch_position"]
                    source_quality = dpln["quality"]
                    source_meta = {"title": dpln["title"]}
                else:
                    dpln_mapping_rejected = True
                    row_mapping["status"] = "ambiguous"
                    row_mapping.setdefault("notes", []).append(f"Titre DPLN divergent: {dpln['title']}")
            except Exception as exc:
                stats["errors"] += 1
                source_errors.append({"quest_id": quest_id, "source": "dofus_pour_les_noobs", "url": url, "error": str(exc)})

        if not extracted_steps and duffus_page and not dpln_mapping_rejected:
            source = "duffus"
            mapping_confidence = mapping_confidence or "HIGH"
            mapping_signals = mapping_signals or ["normalized_title_exact"]
            source_url = f"https://duffus.fr/quete/{duffus_page.get('slug')}"
            source_meta = dict(duffus_page.get("meta") or {})
            extracted_steps = extract_duffus_steps(str(duffus_page.get("content_html") or ""))
            prerequisites = [clean_text(item) for item in array_from_any(duffus_page.get("prereqs"))]
            rewards_payload = duffus_page.get("rewards")
            if isinstance(rewards_payload, dict):
                rewards = unique_strings(
                    [
                        str(rewards_payload.get("xp") or ""),
                        str(rewards_payload.get("kamas") or ""),
                        *[
                            f"{item.get('qty', 1)} x {item.get('label', '')}"
                            for item in array_from_any(rewards_payload.get("items"))
                            if isinstance(item, dict)
                        ],
                        *[str(item) for item in array_from_any(rewards_payload.get("others"))],
                    ]
                )

        duffus_row = duffus_quests_by_key.get(key)
        local_mismatches = []
        if duffus_row:
            local_level = int(getattr(quest, "level_min", 0) or 0)
            source_level = int(duffus_row.get("level_min") or 0)
            if local_level and source_level and local_level != source_level:
                local_mismatches.append({"field": "level_min", "local": local_level, "duffus": source_level})

        status = "complete" if extracted_steps else "source_insufficient"
        if row_mapping["status"] == "missing" and not extracted_steps:
            status = "missing"
            stats["missing"] += 1
        elif extracted_steps:
            stats["complete"] += 1
            stats["completed"] += 1
        elif row_mapping["status"] == "ambiguous":
            stats["ambiguous"] += 1
        else:
            stats["missing"] += 1

        if local_mismatches:
            status = "needs_review"
            stats["corrected"] += 0

        image_urls = [
            str(image.get("source_url") or "")
            for step in extracted_steps
            for image in step.images
            if image.get("source_url")
        ]
        image_urls.extend(
            block.source_url
            for block in extracted_blocks
            if block.block_type == "image" and block.source_url
        )
        manifest_by_url = manifest.get("by_url", {}) if isinstance(manifest, dict) else {}
        pending_image_urls = [
            url
            for url in image_urls
            if not (
                isinstance(manifest_by_url.get(url), dict)
                and manifest_by_url[url].get("path")
                and Path(resolve_local_asset_path(manifest_by_url[url]["path"])).exists()
            )
        ]
        prefetched_images = (
            prefetch_image_bytes(pending_image_urls, getattr(args, "image_workers", 6))
            if pending_image_urls and not args.no_images
            else {}
        )
        solution_steps = [
            step_to_json(
                step,
                quest_id,
                index,
                manifest,
                stats,
                images=not args.no_images,
                prefetched=prefetched_images,
            )
            for index, step in enumerate(extracted_steps, 1)
        ]
        solution_blocks = [
            block_to_json(
                block,
                quest_id,
                index,
                manifest,
                stats,
                images=not args.no_images,
                prefetched=prefetched_images,
            )
            for index, block in enumerate(extracted_blocks, 1)
        ]
        image_count = sum(1 for block in solution_blocks if block.get("type") == "image" and block.get("image_path"))
        fidelity_alerts = list(source_quality.get("fidelity_alerts", [])) if isinstance(source_quality, dict) else []
        if solution_blocks and source_quality.get("source_image_count", 0) and not image_count:
            fidelity_alerts.append("Images source detectees mais non telechargees ou non referencees.")
        if fidelity_alerts and status == "complete":
            status = "needs_review"

        enriched_quests[qid] = {
            **base_enriched_quest(quest, row_mapping, status=status),
            "source": source,
            "source_url": source_url,
            "source_meta": source_meta,
            "mapping_confidence": mapping_confidence,
            "mapping_signals": mapping_signals,
            "mapping_conflicts": mapping_conflicts,
            "solution_blocks": solution_blocks,
            "solution_steps": solution_steps,
            "prerequisites": unique_strings([*getattr(quest, "prerequisites", []), *prerequisites]),
            "launch_position": launch_position,
            "preparation": unique_strings([*preparation]),
            "required_items": resolve_required_items(required_items, item_lookup),
            "rewards": unique_strings(rewards),
            "quality": {
                "local_name": quest.name,
                "source_title": source_meta.get("title") or quest.name,
                "step_count": len(solution_steps),
                "block_count": len(solution_blocks),
                "image_count": image_count,
                "local_mismatches": local_mismatches,
                "fidelity": source_quality,
                "fidelity_alerts": fidelity_alerts,
                "unresolved": status in {"missing", "source_insufficient", "ambiguous", "needs_review"},
            },
        }

        if processed % 100 == 0:
            write_outputs(enriched_quests, mapping, manifest, stats, source_errors)
            print(f"Traité {len(enriched_quests)}/{len(catalog.quests)}")

    write_outputs(enriched_quests, mapping, manifest, stats, source_errors)
    return compute_final_stats(enriched_quests, source_errors)


def array_from_any(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def base_enriched_quest(quest: Any, mapping: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "extraction_version": EXTRACTION_SCHEMA_VERSION,
        "quest_id": int(quest.id),
        "name": quest.name,
        "status": status,
        "mapping_status": mapping.get("status", ""),
        "sources": {
            "duffus": mapping.get("duffus", []),
            "dofus_pour_les_noobs": mapping.get("dofus_pour_les_noobs", []),
        },
    }


def write_outputs(
    enriched_quests: dict[str, Any],
    mapping: dict[str, Any],
    manifest: dict[str, Any],
    stats: dict[str, int],
    source_errors: list[dict[str, Any]],
) -> None:
    final_stats = compute_final_stats(enriched_quests, source_errors)
    if stats.get("image_errors"):
        final_stats["image_errors"] = max(final_stats.get("image_errors", 0), stats["image_errors"])
    all_rows_current = bool(enriched_quests) and all(enrichment_row_is_current(row) for row in enriched_quests.values())
    write_json_file(
        ENRICHED_QUESTS_FILE,
        {
            "version": EXTRACTION_SCHEMA_VERSION if all_rows_current else 1,
            "target_version": EXTRACTION_SCHEMA_VERSION,
            "generated_at": now_iso(),
            "source_mapping_file": str(SOURCE_MAPPING_FILE),
            "quests": dict(sorted(enriched_quests.items(), key=lambda item: int(item[0]))),
        },
    )
    write_json_file(SOURCE_MAPPING_FILE, mapping)
    write_json_file(IMAGE_MANIFEST_FILE, manifest)
    write_json_file(
        REPORT_FILE,
        {
            "version": 1,
            "generated_at": now_iso(),
            "stats": final_stats,
            "errors": source_errors,
            "files": {
                "source_mapping": str(SOURCE_MAPPING_FILE),
                "enriched_quests": str(ENRICHED_QUESTS_FILE),
                "image_manifest": str(IMAGE_MANIFEST_FILE),
            },
        },
    )


def compute_final_stats(enriched_quests: dict[str, Any], source_errors: list[dict[str, Any]]) -> dict[str, int]:
    statuses: dict[str, int] = {}
    image_paths: list[str] = []
    image_errors = 0
    for row in enriched_quests.values():
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        for step in row.get("solution_steps", []) or []:
            if not isinstance(step, dict):
                continue
            for objective in step.get("objectives", []) or []:
                if not isinstance(objective, dict):
                    continue
                for image in objective.get("images", []) or []:
                    if not isinstance(image, dict):
                        continue
                    if image.get("error"):
                        image_errors += 1
                    path = str(image.get("path") or "")
                    if path:
                        image_paths.append(path)
        for block in row.get("solution_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            if block.get("error"):
                image_errors += 1
            path = str(block.get("image_path") or "")
            if path:
                image_paths.append(path)
    unique_images = {
        resolve_local_asset_path(path)
        for path in image_paths
        if Path(resolve_local_asset_path(path)).exists()
    }
    return {
        "total": len(enriched_quests),
        "complete": statuses.get("complete", 0),
        "completed": statuses.get("complete", 0),
        "corrected": statuses.get("corrected", 0),
        "new": statuses.get("new", 0),
        "ambiguous": statuses.get("ambiguous", 0),
        "missing": statuses.get("missing", 0) + statuses.get("source_insufficient", 0),
        "needs_review": statuses.get("needs_review", 0),
        "images_downloaded": len(unique_images),
        "images_reused": max(0, len(image_paths) - len(unique_images)),
        "image_errors": image_errors,
        "errors": len(source_errors),
    }


def build_parser() -> argparse.ArgumentParser:
    quest_id_help = "Traiter uniquement ce quest_id interne. Peut etre repete."
    parser = argparse.ArgumentParser(description="Enrichit les quêtes locales depuis Duffus/DPLN.")
    parser.add_argument("--limit", type=int, default=0, help="Limiter le nombre de quêtes traitées pour diagnostic.")
    parser.add_argument("--delay", type=float, default=0.03, help="Pause entre deux pages DPLN.")
    parser.add_argument("--no-images", action="store_true", help="Ne pas télécharger les images.")
    parser.add_argument("--force", action="store_true", help="Recalculer les quêtes déjà présentes.")
    parser.add_argument("--image-workers", type=int, default=6, help="Telechargements d'images concurrents (1-8).")
    parser.add_argument(
        "--semantic-audit",
        type=Path,
        help="Limiter la regeneration aux corrections certaines d'un rapport semantique JSON.",
    )
    parser.add_argument("--quest-id", type=int, action="append", default=[], help=quest_id_help)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    stats = enrich(args)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
