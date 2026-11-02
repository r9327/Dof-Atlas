"""Read-only Ganymède catalogue metadata for the Guides library.

The public index does not contain offline route steps. A metadata-only
entry may link to its official source page but must never be treated as a
native playable route or have progress inferred from listed step counts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.constants import DATA_DIR

INDEX_PATH = DATA_DIR / "encyclopedia" / "guides" / "ganymede_main_index.json"
CATEGORIES = (
    ("optimized", "Guides optimisés"),
    ("alignements", "Alignements"),
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
        return "alignements"
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
    """Hide caller-declared native equivalents; keep distinct source links."""
    query = search.casefold().strip()
    return [
        entry for entry in listings
        if entry.category == category
        and ATLAS_EQUIVALENTS.get(entry.source_id) not in existing_guide_ids
        and (not query or query in entry.title.casefold())
    ]

# Fourteen sources retain their older descriptive filenames; all others use
# the numeric source ID. Only factual observations, never editorial guide text.
_LOCAL_OBSERVATION_ALIASES = {
    2251: "master", 2204: "ou_sont_les_dofus",
    2207: "bwork_camps", 2219: "otomai_1",
    2228: "sufokia", 2206: "valonia_1",
    2224: "sidimote_1", 2230: "krosmoz",
    2227: "koalaks", 2237: "enudorado_1",
    2250: "ecaflipus_1", 2220: "otomai_2",
    2240: "xelorium_1", 2252: "otomai_3",
}


def load_ganymede_local_observations(
    entry: GanymedeListing, *, data_dir: Path | None = None,
) -> tuple[dict, ...]:
    """Read one source's observed factual steps lazily, without Internet.

    Observations are NOT certified gameplay instructions; never derive an
    objective from an observed coordinate, linked quest or DofusDB ID.
    """
    if (not isinstance(entry, GanymedeListing)
            or type(entry.source_id) is not int
            or type(entry.step_count) is not int
            or entry.step_count <= 0):
        raise ValueError("Invalid offline source listing")
    stem = _LOCAL_OBSERVATION_ALIASES.get(entry.source_id, str(entry.source_id))
    root = Path(data_dir) if data_dir is not None else INDEX_PATH.parent
    payload = json.loads(
        (root / f"ganymede_{stem}_observed_links.json").read_text(encoding="utf-8")
    )
    source = payload.get("source")
    steps = payload.get("steps")
    if (payload.get("schema_version") != 1
            or not isinstance(source, dict)
            or source.get("guide_id") != entry.source_id
            or source.get("editorial_text_imported") is not False
            or source.get("extraction_scope") != "factual_link_occurrences_only"
            or not isinstance(steps, list)
            or len(steps) != entry.step_count):
        raise ValueError(f"Missing or mismatched offline facts: {entry.source_id}")
    for number, step in enumerate(steps, 1):
        if (not isinstance(step, dict)
                or step.get("source_step_number") != number
                or not isinstance(step.get("coordinate_mentions"), list)
                or not isinstance(step.get("linked_guide_ids"), list)
                or not isinstance(step.get("external_dofusdb_ids"), dict)):
            raise ValueError(f"Invalid offline source step {entry.source_id}:{number}")
        if any(
            not isinstance(pair, list) or len(pair) != 2
            or any(type(coord) is not int for coord in pair)
            for pair in step["coordinate_mentions"]
        ):
            raise ValueError(f"Invalid coordinates at {entry.source_id}:{number}")
        facts = step["external_dofusdb_ids"]
        for ids in (step["linked_guide_ids"], *(facts.get(kind) for kind in (
            "quest", "dungeon", "object", "monster",
        ))):
            if (not isinstance(ids, list)
                    or any(type(value) is not int or value <= 0 for value in ids)):
                raise ValueError(f"Invalid links at {entry.source_id}:{number}")
    return tuple(steps)


# Strict optional contract for *real* offline instructions. An observed-link
# snapshot is never promoted to authored actions. Only a fully supplied route
# can use this reader. Guides are loaded lazily on selection, not at Home load.
_INSTRUCTION_KINDS = frozenset({
    "travel", "talk", "interact", "fight", "prepare", "use_item", "deliver",
    "craft", "information",
})
_MISSING_INSTRUCTIONS = frozenset({
    "", "todo", "tbd", "à compléter", "a completer",
    "voir le guide", "voir ganymède", "voir ganymede",
})


def load_ganymede_local_instructions(
    entry: GanymedeListing, *, data_dir: Path | None = None,
) -> tuple[dict, ...] | None:
    """Load a completely authored offline route, or return None if not supplied.

    This *does not* scrape or fabricate Ganymède text. Content must be original
    Atlas writing or licensed for distribution and provided by an author.
    Corrupt/partial routes fail closed, never reverting to a quest checklist.
    """
    if (not isinstance(entry, GanymedeListing)
            or type(entry.source_id) is not int or entry.source_id <= 0
            or type(entry.step_count) is not int or entry.step_count <= 0):
        raise ValueError("Invalid Ganymède instruction catalogue entry")
    root = Path(data_dir) if data_dir is not None else INDEX_PATH.parent
    file = root / f"ganymede_{entry.source_id}_instructions.json"
    if not file.exists():
        return None
    if not file.is_file() or file.is_symlink() or file.stat().st_size > 8_000_000:
        raise ValueError(f"Unsafe/oversized Ganymède instructions {entry.source_id}")
    payload = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid Ganymède instructions {entry.source_id}")
    steps = payload.get("steps")
    if (payload.get("schema_version") != 1
            or payload.get("source_guide_id") != entry.source_id
            or payload.get("source_url") != entry.source_url
            or payload.get("expected_source_step_count") != entry.step_count
            or payload.get("rights_basis") not in {
                "atlas_original", "redistribution_permission",
            }
            or not isinstance(steps, list)
            or len(steps) != entry.step_count):
        raise ValueError(f"Unverified/partial Ganymède instructions {entry.source_id}")
    if payload["rights_basis"] == "redistribution_permission":
        evidence = payload.get("permission_reference")
        attribution = payload.get("attribution")
        if (not isinstance(evidence, str) or not evidence.strip()
                or not isinstance(attribution, str) or not attribution.strip()):
            raise ValueError(f"Missing redistribution permission evidence {entry.source_id}")
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ValueError(f"Invalid Ganymède instruction step {entry.source_id}:{number}")
        title = step.get("title")
        detail = step.get("instructions")
        actions = step.get("actions")
        if (type(step.get("source_step_number")) is not int
                or step["source_step_number"] != number
                or not isinstance(title, str) or not title.strip()
                or not isinstance(detail, str)
                or detail.casefold().strip() in _MISSING_INSTRUCTIONS
                or not isinstance(actions, list) or not actions):
            raise ValueError(f"Incomplete Ganymède instruction step {entry.source_id}:{number}")
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError(f"Invalid Ganymède action {entry.source_id}:{number}")
            text = action.get("text")
            if (action.get("kind") not in _INSTRUCTION_KINDS
                    or not isinstance(text, str)
                    or text.casefold().strip() in _MISSING_INSTRUCTIONS):
                raise ValueError(f"Unverified Ganymède action {entry.source_id}:{number}")
            coords = action.get("coordinates")
            if coords is not None and (
                not isinstance(coords, list) or len(coords) != 2
                or any(type(v) is not int for v in coords)
            ):
                raise ValueError(f"Invalid Ganymède action coordinates {entry.source_id}:{number}")
    return tuple(steps)
