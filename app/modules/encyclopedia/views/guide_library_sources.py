"""Read-only Ganymède catalogue metadata for the Guides library.

The public index does not contain playable route steps. Never expose a launch
action for metadata-only entries or infer progress from listed step counts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.constants import DATA_DIR

INDEX_PATH = DATA_DIR / "encyclopedia" / "guides" / "ganymede_main_index.json"
CATEGORIES = (
    ("dofus", "Dofus"),
    ("dimensions", "Dimensions divines"),
    ("eliocalypse", "Éliocalypse"),
    ("regions", "Zones et régions"),
    ("events", "Événements"),
    ("adventures", "Autres aventures"),
    ("islands", "Îles et territoires"),
)
# Same story already has a playable Atlas card. Suppress only the duplicate
# metadata card, never the real guide or the source-index record.
ATLAS_EQUIVALENTS = {
    2203: "dofus_argente", 2205: "dofus_cawotte", 2208: "dokoko",
    2211: "dofus_emeraude", 2276: "dofus_pourpre", 2217: "dofus_turquoise",
    2269: "dofus_abyssal", 2261: "dofus_ebene", 2256: "dofus_ivoire",
    2218: "dofus_ocre", 2260: "dofus_vulbis", 2216: "dofus_des_glaces",
    2209: "dofus_des_veilleurs", 2212: "domakuro", 2221: "dorigami",
    2248: "dolmanax", 2283: "dofus_du_cauchemar",
    2287: "dofus_forgelave", 2271: "dofus_tachete",
    2247: "dofus_nebuleux", 2285: "dofus_dom_de_pin",
    2290: "dofus_sylvestre",
    2249: "alignement_bonta", 2263: "alignement_brakmar",
}

@dataclass(frozen=True)
class GanymedeListing:
    source_id: int
    title: str
    category: str
    level: int | None
    step_count: int | None
    source_url: str
    playable: bool = False


def classify_title(title: str) -> str:
    text = title.casefold()
    if ("dofus" in text or text in {
        "dokoko", "dolmanax", "domakuro", "dorigami", "amber ochre",
        "six out of six", "four over five", "pine done",
    }):
        return "dofus"
    if "alignment" in text or text == "bonta / brakmar":
        return "adventures"
    if any(k in text for k in ("xelorium", "srambad", "enudorado", "ecaflipus")):
        return "dimensions"
    if any(k in text for k in ("eliocalypse", "resonance", "corruption",
                              "servitude", "misery", "war", "destroyed")):
        return "eliocalypse"
    if text in {"al howin", "kwismas", "fleaster", "vulkania"}:
        return "events"
    if any(k in text for k in ("otoma", "pandala", "sufokia", "nimaltopia",
                              "osavora", "crocuzko", "atoll of")):
        return "islands"
    if any(k in text for k in ("frigost", "cania", "sidimote", "ohwymi",
                              "valonia", "koalaks", "amakna", "evil forest",
                              "bwork", "goblin")):
        return "regions"
    return "adventures"


def load_ganymede_listings(path: Path = INDEX_PATH) -> tuple[GanymedeListing, ...]:
    """Validate source IDs and keep all listings, including unavailable ones."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc["guides"]
    if not isinstance(rows, list):
        raise ValueError("Invalid Ganymède catalogue")
    seen: set[int] = set()
    listings: list[GanymedeListing] = []
    for row in rows:
        source_id = row["ganymede_guide_id"]
        title = row["title"]
        url = row["source_url"]
        if (type(source_id) is not int or source_id in seen
                or not isinstance(title, str) or not title.strip()
                or not isinstance(url, str)
                or url != f"https://ganymede-app.com/guides/{source_id}"):
            raise ValueError("Invalid/duplicate Ganymède metadata")
        seen.add(source_id)
        level = row.get("recommended_level_min")
        count = row.get("listed_step_count")
        listings.append(GanymedeListing(
            source_id, title, classify_title(title),
            level if type(level) is int else None,
            count if type(count) is int else None, url,
        ))
    return tuple(listings)


def displayable_listings(
    listings: tuple[GanymedeListing, ...],
    existing_guide_ids: set[str],
    category: str,
    search: str = "",
) -> list[GanymedeListing]:
    """No duplicate Atlas equivalent and no clickable metadata-only routes."""
    query = search.casefold().strip()
    return [
        entry for entry in listings
        if entry.category == category
        and ATLAS_EQUIVALENTS.get(entry.source_id) not in existing_guide_ids
        and (not query or query in entry.title.casefold())
    ]
