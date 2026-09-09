from __future__ import annotations

"""DOFUS ATLAS — GUIDE ULTIME — FINAL CONTENT-LOCK GENERATOR

Run from the Dofus Atlas repository root:

    py -3.13 .\tools\build_guide_ultime_final.py --strict

Optional integration write (only after the strict audit passes):

    py -3.13 .\tools\build_guide_ultime_final.py --strict --apply

This generator deliberately does NOT use the visual order of an older guide as a
hard dependency. Real quest prerequisites come from local quest data; the legacy
1134-quest guide is only an ordering seed supplied by the companion master JSON.
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "app").exists():
    candidate = Path.cwd()
    if (candidate / "app").exists():
        ROOT = candidate
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.quest_catalog import doduda_rows, normalize_text
from tools.guide_ultime_scope_v5 import (
    branch_combination_counts,
    fill_to_qq_threshold,
    max_qq_requirement,
    meta_achievement_ids,
    mandatory_qf_ids,
    positive_qf_ids,
    residual_qf_alternatives,
    transitive_closure,
    choose_one_candidate,
)

ARTIFACTS = ROOT / "artifacts"
DEFAULT_OVERLAY_CANDIDATES = (
    ROOT / "tools" / "guide_ultime_master_2026-08-22.json",
    ARTIFACTS / "guide_ultime_master_2026-08-22.json",
    ROOT / "guide_ultime_master_2026-08-22.json",
)
OUT_GUIDE = ARTIFACTS / "guide_ultime_final.json"
OUT_AUDIT = ARTIFACTS / "guide_ultime_final_audit.json"
OUT_CSV = ARTIFACTS / "guide_ultime_final_manifest.csv"
OUT_TXT = ARTIFACTS / "guide_ultime_final_summary.txt"
APPLY_PATH = DATA_DIR / "encyclopedia" / "guides" / "guide_ultime.json"

QREF_RE = re.compile(r"\bQ[fa]\s*[=><!]+\s*(\d+)", re.IGNORECASE)
QF_RE = re.compile(r"\bQf\s*=\s*(\d+)", re.IGNORECASE)
RANK_RE = re.compile(r"\bPa\s*=\s*(\d+)\b", re.IGNORECASE)
SIDE_RE = re.compile(r"\bPs\s*=\s*(\d+)\b", re.IGNORECASE)
CRITERION_CODE_RE = re.compile(
    r"\b([A-Za-z]{1,5})\s*(?:!=|>=|<=|=|>|<)\s*(?:-?\d+|[A-Za-z_]+)",
    re.IGNORECASE,
)
KNOWN_CRITERION_CODES = {"bt", "pl", "qf", "qa", "sc", "ps", "pa", "pr", "qq", "bi", "ea"}
RUNTIME_GATE_CODES = {
    "ad", "qo", "po", "pz", "qc", "pg", "pj", "pm", "st",
    "dd", "oa", "we", "dh", "dm", "sv", "ha", "sh", "ei", "em",
}

CLASS_QUESTS = {
    "Crâ": "C'est pour ta pomme",
    "Ecaflip": "Au petit malheur la chance",
    "Eliotrope": "Un rayon de soleil",
    "Eniripsa": "Piques de solution",
    "Enutrof": "La fête de la chocopépite",
    "Féca": "Tournée d'inspection",
    "Forgelance": "La routine anodine du chevalier citadin",
    "Huppermage": "Les paroles s'envolent, les aigris restent",
    "Iop": "Iop et hop",
    "Ouginak": "Une vie de milichien",
    "Osamodas": "Série animalière",
    "Pandawa": "Trempette dans un verre d'eau",
    "Roublard": "Braquage à la Roublard",
    "Sacrieur": "Souffre-douleur",
    "Sadida": "C'est pourtant naturel",
    "Sram": "Crime et châtiment",
    "Steamer": "L'étrange créature de l'étang bleu",
    "Xélor": "Tarot, t'es très fort",
    "Zobal": "Zobal Hibaba et les 40 Roublards",
}
CLASS_BY_NAME = {normalize_text(name): klass for klass, name in CLASS_QUESTS.items()}

ORDER_QUEST_IDS = {
    "bonta": {
        "Ordre du Cœur Vaillant": (433, 109, 120, 421, 1916),
        "Ordre de l'Esprit Salvateur": (434, 111, 121, 423, 1917),
        "Ordre de l'Œil Attentif": (435, 110, 122, 425, 1918),
    },
    "brakmar": {
        "Ordre du Cœur Saignant": (436, 112, 123, 422, 1919),
        "Ordre de l'Esprit Malsain": (437, 114, 124, 424, 1920),
        "Ordre de l'Œil Putride": (438, 113, 125, 426, 1921),
    },
}
ORDER_LEVELS = (20, 40, 60, 80, 100)

# Repeatables that are part of the Guide Ultime despite not necessarily having a
# direct quest-achievement edge in local data.
MANDATORY_REPEATABLES = {
    normalize_text("Fight club"): {
        "reason": "succès Quêtes Chahuteur clandestin -> une validation seulement",
        "runtime_policy": "complete_once_for_success",
        "counter": None,
    },
}
DARWIN_CHOICE = {
    normalize_text(name)
    for name in (
        "Blouson noir",
        "Boîte de conserve",
        "Le cinquième élément",
        "Pousse mousse",
        "Trop sinistre",
    )
}

EVENT_TOKENS = {
    "vulkania", "pwak", "halouine", "nowel",
    "sain ballotin", "saison emeraude", "saison turquoise", "saison pourpre",
    "saison ocre", "saison ivoire", "saison ebene",
}
# Generic words such as "événement" are too broad for quest titles: Valonia's
# permanent quest "Un événement inattendu" must never become a calendar branch
# just because its name contains that word.  Generic event markers are accepted
# only from the quest category; named seasonal markers above may appear anywhere.
EVENT_CATEGORY_TOKENS = {"evenement", "event"}
ALMANAX_TOKENS = {"almanax", "dolmanax", "offrande"}

# V5 = FULL SUCCÈS. Dungeon achievements are first-class targets.
DUNGEON_ACHIEVEMENT_POLICY_NOTE = (
    "FULL SUCCÈS: succès Donjons (Duo/Premier/Spécial/Statue/etc.) inclus; "
    "le GPS doit les greffer au premier passage compatible ou les signaler comme non routés."
)


def safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def norm(value: Any) -> str:
    return normalize_text(str(value or ""))


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from iter_strings(child)


def load_overlay(explicit: str | None) -> dict[str, Any]:
    candidates = [Path(explicit)] if explicit else list(DEFAULT_OVERLAY_CANDIDATES)
    for path in candidates:
        if path and path.exists():
            payload = read_json(path, {})
            if isinstance(payload, dict):
                payload["_loaded_from"] = str(path)
                return payload
    return {}


def quest_refs(text: Any) -> set[int]:
    return {int(match.group(1)) for match in QREF_RE.finditer(str(text or ""))}


def repeatability_kind(quest: Any, raw: dict[str, Any]) -> str:
    for key in ("isRepeatable", "repeatable", "is_repetable", "repetable"):
        if raw.get(key) is True:
            return "repeatable"
    text = norm(" ".join([
        str(getattr(quest, "category", "") or ""),
        str(getattr(quest, "start_criterion", "") or ""),
        *[str(v) for v in (getattr(quest, "info", ()) or ())],
    ]))
    if any(token in text for token in ("hebdomadaire", "weekly", "chaque_semaine")):
        return "weekly"
    if any(token in text for token in ("journaliere", "journalier", "daily", "chaque_jour")):
        return "daily"
    if any(token in text for token in ("repetable", "repeatable")):
        return "repeatable"
    return "normal"


def build_name_index(catalog: Any) -> dict[str, set[int]]:
    result: dict[str, set[int]] = defaultdict(set)
    for quest in catalog.quests:
        result[norm(quest.name)].add(int(quest.id))
    mapping = read_json(DATA_DIR / "encyclopedia" / "quests" / "source_mapping.json", {})
    rows = mapping.get("quests", {}) if isinstance(mapping, dict) else {}
    if isinstance(rows, dict):
        for raw_id, row in rows.items():
            if not isinstance(row, dict):
                continue
            qid = safe_int(row.get("quest_id"), safe_int(raw_id))
            name = norm(row.get("name"))
            if qid is not None and name and qid in catalog.by_id:
                result[name].add(qid)
    return result


def named_refs(text: str, name_index: dict[str, set[int]]) -> set[int]:
    value = norm(text)
    if not value:
        return set()
    direct = set(name_index.get(value, ()))
    if direct:
        return direct
    padded = f"_{value}_"
    for name, ids in sorted(name_index.items(), key=lambda row: len(row[0]), reverse=True):
        if len(name) < 8:
            continue
        if f"_{name}_" in padded or value.endswith(name):
            return set(ids)
    return set()


def enriched_prerequisites(catalog: Any, name_index: dict[str, set[int]]) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    payload = read_json(DATA_DIR / "encyclopedia" / "quests" / "quests_enriched.json", {})
    rows = payload.get("quests", {}) if isinstance(payload, dict) else {}
    if isinstance(rows, list):
        rows = {str(row.get("id")): row for row in rows if isinstance(row, dict)}
    if isinstance(rows, dict):
        for raw_id, row in rows.items():
            qid = safe_int(row.get("id") if isinstance(row, dict) else None, safe_int(raw_id))
            if qid is None or qid not in catalog.by_id or not isinstance(row, dict):
                continue
            for value in row.get("prerequisites", []) or []:
                result[qid].update(named_refs(str(value or ""), name_index))
    return result


def direct_prerequisites(quest: Any, enriched: dict[int, set[int]], name_index: dict[str, set[int]]) -> set[int]:
    # V5.1 hard graph source: only Qf IDs present in EVERY boolean branch.
    # Never flatten Qf=A|Qf=B into two mandatory prerequisites.
    qid = int(quest.id)
    result = set(mandatory_qf_ids(str(getattr(quest, "start_criterion", "") or "")))
    result.discard(qid)
    return result


def alternative_prerequisites(quest: Any) -> tuple[frozenset[int], ...]:
    qid = int(quest.id)
    rows = []
    for group in residual_qf_alternatives(str(getattr(quest, "start_criterion", "") or "")):
        cleaned = frozenset(int(value) for value in group if int(value) != qid)
        if cleaned:
            rows.append(cleaned)
    return tuple(rows)


def event_like(quest: Any, raw: dict[str, Any]) -> bool:
    category = norm(getattr(quest, "category", ""))
    text = norm(f"{getattr(quest, 'category', '')} {getattr(quest, 'name', '')} {' '.join(iter_strings(raw))}")
    if any(norm(token) in text for token in EVENT_TOKENS):
        return True
    return any(norm(token) in category for token in EVENT_CATEGORY_TOKENS)


def almanax_like(quest: Any, raw: dict[str, Any]) -> bool:
    text = norm(f"{getattr(quest, 'category', '')} {getattr(quest, 'name', '')} {' '.join(iter_strings(raw))}")
    return any(norm(token) in text for token in ALMANAX_TOKENS)


def order_lookup() -> dict[int, tuple[str, str, int]]:
    result: dict[int, tuple[str, str, int]] = {}
    for side, orders in ORDER_QUEST_IDS.items():
        for order_name, ids in orders.items():
            for rank, qid in enumerate(ids, 1):
                result[int(qid)] = (side, order_name, rank)
    return result


def criterion_alignment_side(criterion: str) -> str:
    """Return the explicit Bonta/Brâkmar side encoded by Ps=1/Ps=2."""
    match = SIDE_RE.search(str(criterion or ""))
    if not match:
        return ""
    value = safe_int(match.group(1))
    if value == 1:
        return "bonta"
    if value == 2:
        return "brakmar"
    return ""


def alignment_rows(
    catalog: Any,
    raw_quests: dict[int, dict[str, Any]],
) -> tuple[dict[int, tuple[str, int]], dict[int, tuple[str, int]]]:
    # Values keep the raw Pa prerequisite as well as the alignment side.
    # Example: Pa=19 is the quest that advances the character to alignment 20.
    # Keeping this metadata lets the GPS builder gate Order rank 1 behind the
    # real alignment-20 quest instead of pretending the character starts at 100.
    main: dict[int, tuple[str, int]] = {}
    variants: dict[int, tuple[str, int]] = {}
    for category_id, ps_value, side in ((9, 1, "bonta"), (10, 2, "brakmar")):
        by_rank: dict[int, list[int]] = defaultdict(list)
        for qid, raw in raw_quests.items():
            if safe_int(raw.get("categoryId")) != category_id:
                continue
            criterion = str(raw.get("startCriterion") or "")
            rm = RANK_RE.search(criterion)
            sm = SIDE_RE.search(criterion)
            if not rm or not sm or safe_int(sm.group(1)) != ps_value or qid not in catalog.by_id:
                continue
            by_rank[int(rm.group(1))].append(qid)
        for rank, ids in by_rank.items():
            ids.sort(key=lambda qid: (
                int(getattr(catalog.by_id[qid], "level_min", 0) or 0),
                norm(catalog.by_id[qid].name), qid,
            ))
            if ids:
                main[ids[0]] = (side, int(rank))
                for qid in ids[1:]:
                    variants[qid] = (side, int(rank))
    return main, variants


def achievement_sets(provider: AchievementProvider) -> tuple[set[int], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return quest-linked quests plus FULL-SUCCESS Monster and Dungeon targets."""
    quest_success_quests: set[int] = set()
    monster_successes: list[dict[str, Any]] = []
    dungeon_successes: list[dict[str, Any]] = []
    for achievement in provider.load_all():
        category = norm(getattr(achievement, "category_name", ""))
        subcategory = norm(getattr(achievement, "subcategory_name", ""))
        labels = f"{category} {subcategory}"
        if "quete" in labels:
            for ref in getattr(achievement, "linked_quests", ()) or ():
                quest_success_quests.add(int(ref.entity_id))
        if "monstre" in labels:
            monster_successes.append({
                "achievement_id": int(achievement.id),
                "name": str(achievement.name),
                "level": safe_int(getattr(achievement, "level", None)),
                "monster_ids": [int(ref.entity_id) for ref in getattr(achievement, "linked_monsters", ()) or ()],
                "quest_ids": [int(ref.entity_id) for ref in getattr(achievement, "linked_quests", ()) or ()],
            })
        if "donjon" in labels:
            dungeon_successes.append({
                "achievement_id": int(achievement.id),
                "name": str(achievement.name),
                "level": safe_int(getattr(achievement, "level", None)),
                "dungeons": [
                    {"dungeon_id": int(ref.entity_id), "name": str(getattr(ref, "label", "") or "")}
                    for ref in getattr(achievement, "linked_dungeons", ()) or ()
                ],
                "quest_ids": [int(ref.entity_id) for ref in getattr(achievement, "linked_quests", ()) or ()],
                "monster_ids": [int(ref.entity_id) for ref in getattr(achievement, "linked_monsters", ()) or ()],
            })
    return quest_success_quests, monster_successes, dungeon_successes


def guide_membership(guide_provider: GuideProvider) -> tuple[dict[int, set[str]], set[int], set[int]]:
    by_quest: dict[int, set[str]] = defaultdict(set)
    dofus: set[int] = set()
    curated: set[int] = set()
    for guide in guide_provider.load_all():
        # Avoid feeding a previously generated guide_ultime back into itself.
        if str(getattr(guide, "id", "")) == "guide_ultime":
            continue
        for qid in getattr(guide, "quest_ids", ()) or ():
            qid = int(qid)
            by_quest[qid].add(str(guide.id))
            curated.add(qid)
            if str(getattr(guide, "category", "")) == "dofus":
                dofus.add(qid)
    return by_quest, dofus, curated


def criterion_gate_codes(quest: Any) -> tuple[list[str], list[str]]:
    criterion = str(getattr(quest, "start_criterion", "") or "")
    extra = {
        norm(code)
        for code in CRITERION_CODE_RE.findall(criterion)
        if norm(code) not in KNOWN_CRITERION_CODES
    }
    return sorted(extra & RUNTIME_GATE_CODES), sorted(extra - RUNTIME_GATE_CODES)


def unknown_criterion_codes(quest: Any) -> list[str]:
    # Compatibility helper used by tests/callers: now means *truly unknown*,
    # not merely a runtime gate we cannot auto-evaluate.
    _runtime, unknown = criterion_gate_codes(quest)
    return unknown


def legacy_seed_map(overlay: dict[str, Any]) -> dict[int, int]:
    result: dict[int, int] = {}
    chapters = (((overlay.get("chapter_strategy") or {}).get("chapters")) or [])
    for row in chapters:
        order = safe_int(row.get("order"))
        if order is None:
            continue
        for qid in row.get("legacy_seed_quest_ids", []) or []:
            ident = safe_int(qid)
            if ident is not None:
                result.setdefault(ident, order)
    return result


def chapter_order_for_level(level: int) -> int:
    if level <= 20: return 1
    if level <= 30: return 2
    if level <= 40: return 3
    if level <= 50: return 4
    if level <= 60: return 5
    if level <= 70: return 6
    if level <= 80: return 7
    if level <= 90: return 8
    if level <= 100: return 9
    if level <= 110: return 10
    if level <= 120: return 11
    if level <= 130: return 12
    if level <= 140: return 13
    if level <= 150: return 14
    if level <= 160: return 15
    if level <= 170: return 16
    if level <= 180: return 17
    if level <= 190: return 18
    return 19


def chapter_templates(overlay: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in (((overlay.get("chapter_strategy") or {}).get("chapters")) or []):
        order = safe_int(row.get("order"))
        if order is not None:
            result[order] = dict(row)
    fallback_titles = {
        1: "Niv. 1–20 — Incarnam", 2: "Niv. 21–30 — Astrub & premiers donjons",
        3: "Niv. 31–40 — Alignement, Amakna & Tour du Monde", 4: "Niv. 41–50 — Bworks, Tofus & Cania",
        5: "Niv. 51–60 — Larves, Kwaks, Valonia & Otomaï", 6: "Niv. 61–70 — Moon, Wabbits & Cawotte",
        7: "Niv. 71–80 — Gelées, Saharach & Tour du Monde", 8: "Niv. 81–90 — Otomaï, Tourbières, Brumen & Koalaks",
        9: "Niv. 91–100 — Nyée, Abraknydes, Moon & Meulou", 10: "Niv. 101–110 — Rats, Rasboul & Pourpre",
        11: "Niv. 111–120 — Frigost, Pandala & Enutrosor", 12: "Niv. 121–130 — Dimensions, Pandala & Koalaks",
        13: "Niv. 131–140 — Srambad, Tanukouï & Frigost", 14: "Niv. 141–150 — Saharach, Pandala & Chêne Mou",
        15: "Niv. 151–160 — Minotot, Sphincter, Kimbo & Frigost", 16: "Niv. 161–170 — Obsidiantre, Tengu & Pandala",
        17: "Niv. 171–180 — Korriandre, Kolosso, Bworker & alignement", 18: "Niv. 181–190 — Ougah, Frigost II, Dimensions & Dofus",
        19: "Niv. 191–200 — Endgame, Eliocalypse & Sylvestre",
    }
    for order, title in fallback_titles.items():
        result.setdefault(order, {"order": order, "id": f"guide_ultime_{order:02d}", "title": title})
    return result


def objective_items(quest: Any) -> list[dict[str, Any]]:
    rows: dict[tuple[int | None, str], int] = Counter()
    labels: dict[tuple[int | None, str], str] = {}
    for step in getattr(quest, "steps", ()) or ():
        for obj in getattr(step, "objectives", ()) or ():
            item_id = safe_int(getattr(obj, "item_id", None))
            qty = max(1, safe_int(getattr(obj, "item_quantity", None), 1) or 1)
            if item_id is None:
                continue
            label = str(getattr(obj, "image_label", "") or getattr(obj, "text", "") or f"Objet {item_id}")
            key = (item_id, norm(label))
            rows[key] += qty
            labels[key] = label
    return [
        {"item_id": key[0], "name": labels[key], "quantity": int(qty), "source": "resolve_at_runtime"}
        for key, qty in sorted(rows.items(), key=lambda kv: (kv[0][1], kv[0][0] or 0))
    ]


def _objective_refs(objective: Any, entity_type: str) -> set[int]:
    result: set[int] = set()
    refs = list(getattr(objective, "entity_refs", ()) or ())
    singular = getattr(objective, "entity_ref", None)
    if singular is not None:
        refs.append(singular)
    for ref in refs:
        if str(getattr(ref, "entity_type", "") or "") == entity_type:
            ident = safe_int(getattr(ref, "entity_id", None))
            if ident is not None:
                result.add(ident)
    return result


def quest_achievement_requirements(provider: AchievementProvider) -> dict[str, Any]:
    """Expand Quest achievements into quest/meta/count requirements.

    V5.1 separates three things that the old audit mixed together:
    - quest dependencies/choices used by the content selector;
    - QQ global quest-count requirements;
    - non-quest success objectives (monster/object/progress state) that belong to
      route/gate coverage, not to the quest dependency graph.
    """
    all_achievements = {int(a.id): a for a in provider.load_all()}
    target_ids = {
        aid for aid, achievement in all_achievements.items()
        if "quete" in norm(f"{getattr(achievement, 'category_name', '')} {getattr(achievement, 'subcategory_name', '')}")
    }
    mandatory_quests: set[int] = set()
    choice_groups: list[dict[str, Any]] = []
    qq_criteria: list[str] = []
    visited: set[int] = set()
    unresolved: list[dict[str, Any]] = []
    route_side_objectives: list[dict[str, Any]] = []
    meta_edges: list[dict[str, Any]] = []

    def visit(aid: int, stack: tuple[int, ...] = ()) -> None:
        if aid in visited:
            return
        if aid in stack:
            unresolved.append({"achievement_id": aid, "type": "meta_cycle", "stack": list(stack)})
            return
        achievement = all_achievements.get(aid)
        if achievement is None:
            unresolved.append({"achievement_id": aid, "type": "missing_meta_achievement"})
            return
        visited.add(aid)
        linked_meta = {
            int(getattr(ref, "entity_id"))
            for ref in (getattr(achievement, "linked_achievements", ()) or ())
            if safe_int(getattr(ref, "entity_id", None)) is not None
        }
        for objective in getattr(achievement, "objectives", ()) or ():
            criterion = str(getattr(objective, "criterion", "") or "")
            objective_id = safe_int(getattr(objective, "id", None), 0) or 0
            entity_qids = _objective_refs(objective, "quest")
            hard_qids = set(mandatory_qf_ids(criterion)) | entity_qids
            residual_groups = residual_qf_alternatives(criterion)
            meta_ids = _objective_refs(objective, "achievement") | meta_achievement_ids(criterion)
            linked_meta.update(meta_ids)

            if hard_qids:
                mandatory_quests.update(hard_qids)
            if residual_groups:
                # Most DOFUS quest-success OR objectives are one quest from N.
                # Preserve the general set representation too so STRICT never
                # silently turns an AND-within-OR into a single quest choice.
                candidate_sets = [sorted(map(int, group)) for group in residual_groups]
                choice_groups.append({
                    "id": f"achievement_{aid}_objective_{objective_id}",
                    "achievement_id": aid,
                    "objective_id": objective_id,
                    "candidate_quest_id_sets": candidate_sets,
                    "candidate_quest_ids": sorted({qid for group in residual_groups for qid in group}),
                    "required_count": 1,
                })

            if re.search(r"\bQQ\s*(?:>=|<=|=|>|<)\s*\d+", criterion, re.IGNORECASE):
                qq_criteria.append(criterion)

            objective_type = norm(getattr(objective, "objective_type", ""))
            codes = {norm(code) for code in CRITERION_CODE_RE.findall(criterion)}
            recognized = bool(
                hard_qids
                or residual_groups
                or meta_ids
                or re.search(r"\b(?:QQ|Pa|Pr)\b", criterion, re.IGNORECASE)
            )
            ignored = objective_type in {"critere_pl", "critere_ea"} or (
                objective_type == "critere_bi"
                and "quete" in norm(getattr(achievement, "category_name", ""))
            )
            gate_only = bool(codes) and codes.issubset(KNOWN_CRITERION_CODES)

            # These are real success objectives but not hidden quest IDs. Keep
            # them for the GPS/gate audit instead of falsely failing content lock.
            side_codes = codes & {"po", "qo", "ei", "em"}
            is_monster_side = objective_type == "monstre" or "em" in codes
            if criterion and not recognized and not ignored and (side_codes or is_monster_side):
                route_side_objectives.append({
                    "achievement_id": aid,
                    "achievement_name": str(getattr(achievement, "name", "")),
                    "objective_id": objective_id,
                    "criterion": criterion,
                    "objective_type": str(getattr(objective, "objective_type", "")),
                    "codes": sorted(codes),
                    "route_kind": "monster_or_dungeon" if is_monster_side else "progress_or_object_gate",
                })
                recognized = True

            if criterion and not recognized and not ignored and not gate_only:
                unresolved.append({
                    "achievement_id": aid,
                    "achievement_name": str(getattr(achievement, "name", "")),
                    "objective_id": objective_id,
                    "criterion": criterion,
                    "objective_type": str(getattr(objective, "objective_type", "")),
                    "type": "unresolved_quest_achievement_objective",
                })
        for meta_id in sorted(linked_meta):
            meta_edges.append({"achievement_id": aid, "requires_achievement_id": meta_id})
            visit(meta_id, stack + (aid,))

    for aid in sorted(target_ids):
        visit(aid)

    return {
        "target_achievement_ids": sorted(target_ids),
        "expanded_achievement_ids": sorted(visited),
        "mandatory_quest_ids": sorted(mandatory_quests),
        "choice_groups": choice_groups,
        "qq_criteria": qq_criteria,
        "qq_required_count": max_qq_requirement(qq_criteria),
        "meta_edges": meta_edges,
        "route_side_objectives": route_side_objectives,
        "unresolved_objectives": unresolved,
    }


def _common_allowed(row: dict[str, Any], *, events: bool = False) -> bool:
    """True for content shared by every player of the single universal guide."""
    cond = row.get("condition") or {}
    side = norm(cond.get("alignment"))
    if side and side != "bonta":
        return False
    if cond.get("order") or cond.get("class"):
        return False
    policy = str(row.get("runtime_policy") or "")
    if policy in {"selected_class_only", "selected_alignment_and_order_only", "only_if_game_branch_selects_it"}:
        return False
    if policy == "only_while_event_available":
        return bool(events)
    if policy in {"skip", "tracked_side_thread_not_blocking", "skip_unless_proven_required"}:
        return False
    return True


def _dedupe_conflict_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _universal_scope(
    rows_by_id: dict[int, dict[str, Any]],
    direct_by_quest: dict[int, set[int]],
    alternative_by_quest: dict[int, tuple[frozenset[int], ...]],
    achievement_req: dict[str, Any],
    alignment_main: dict[int, tuple[str, int]],
    seed_map: dict[int, int],
    dofus_quests: set[int],
) -> dict[str, Any]:
    all_ids = set(rows_by_id)
    direct_targets = {int(v) for v in achievement_req["mandatory_quest_ids"] if int(v) in all_ids}
    darwin_ids = {qid for qid, row in rows_by_id.items() if norm(row["name"]) in DARWIN_CHOICE}
    achievement_choice_candidate_ids = {
        int(qid)
        for group in (achievement_req.get("choice_groups") or [])
        for qid in (group.get("candidate_quest_ids") or [])
        if int(qid) in all_ids
    }
    one_of_variant_ids = darwin_ids | achievement_choice_candidate_ids
    # A one-of objective contributes ONE logical quest completion, never every
    # candidate. Do not let linked_quests or the QQ filler phase re-add the
    # unselected alternatives. A variant can still enter through a genuine hard
    # prerequisite closure if another selected quest really requires it.
    direct_targets.difference_update(one_of_variant_ids)
    direct_targets = {qid for qid in direct_targets if _common_allowed(rows_by_id[qid], events=False)}
    bonta_alignment_ids = {qid for qid, (side, _rank) in alignment_main.items() if side == "bonta" and qid in all_ids}
    dofus_targets = {
        int(qid) for qid in dofus_quests
        if int(qid) in all_ids and _common_allowed(rows_by_id[int(qid)], events=False)
    }
    seeds = set(direct_targets) | bonta_alignment_ids | dofus_targets
    for qid, row in rows_by_id.items():
        if norm(row["name"]) in MANDATORY_REPEATABLES and _common_allowed(row, events=False):
            seeds.add(qid)

    exists = lambda qid: int(qid) in all_ids
    common_allowed = lambda qid: bool(
        rows_by_id.get(int(qid)) and _common_allowed(rows_by_id[int(qid)], events=False)
    )
    conditional_branch_id = lambda qid: bool(
        rows_by_id.get(int(qid))
        and (rows_by_id[int(qid)].get("is_class_quest") or rows_by_id[int(qid)].get("is_order_quest"))
    )

    common, prereq_added, conflicts = transitive_closure(
        seeds,
        direct_by_quest,
        allowed=common_allowed,
        exists=exists,
        alternatives=alternative_by_quest,
        defer_allowed=conditional_branch_id,
    )

    class_qids = {
        klass: next((qid for qid, row in rows_by_id.items() if norm(row["name"]) == norm(qname)), None)
        for klass, qname in CLASS_QUESTS.items()
    }
    class_qid_values = {int(qid) for qid in class_qids.values() if qid is not None}
    all_order_qids = {
        int(qid)
        for ids in ORDER_QUEST_IDS["bonta"].values()
        for qid in ids
        if int(qid) in all_ids
    }

    choices: dict[str, int] = {}
    conditional_choice_groups: list[str] = []
    for group in list(achievement_req.get("choice_groups") or []):
        candidates = [int(v) for v in group.get("candidate_quest_ids", []) if int(v) in all_ids]
        candidate_set = set(candidates)
        # A success saying "one class quest" or "one Order branch" is already
        # represented by the inline conditional card. It must never choose one
        # reference class globally for every player.
        if candidate_set and candidate_set.issubset(class_qid_values | all_order_qids):
            conditional_choice_groups.append(str(group["id"]))
            continue
        chosen, new_ids, local = choose_one_candidate(
            candidates,
            selected=common,
            prerequisites=direct_by_quest,
            allowed=common_allowed,
            exists=exists,
            alternatives=alternative_by_quest,
            defer_allowed=conditional_branch_id,
            rank_key=lambda qid: (
                0 if qid in seed_map else 1,
                rows_by_id[qid]["level_min"],
                seed_map.get(qid, 9999),
            ),
        )
        conflicts.extend(local)
        if chosen is not None:
            choices[str(group["id"])] = chosen
            common.update(new_ids | {chosen})
            prereq_added.update(new_ids - {chosen})

    if darwin_ids:
        chosen, new_ids, local = choose_one_candidate(
            darwin_ids,
            selected=common,
            prerequisites=direct_by_quest,
            allowed=common_allowed,
            exists=exists,
            alternatives=alternative_by_quest,
            defer_allowed=conditional_branch_id,
            rank_key=lambda qid: (rows_by_id[qid]["level_min"], seed_map.get(qid, 9999), qid),
        )
        conflicts.extend(local)
        if chosen is not None:
            choices["carnage_de_glace_one_of"] = chosen
            common.update(new_ids | {chosen})
            prereq_added.update(new_ids - {chosen})

    def compute_branch_deltas(base: set[int]) -> tuple[dict[str, set[int]], dict[str, set[int]], list[dict[str, Any]]]:
        branch_conflicts: list[dict[str, Any]] = []
        class_deltas: dict[str, set[int]] = {}
        for klass, maybe_qid in class_qids.items():
            if maybe_qid is None:
                branch_conflicts.append({"type": "missing_class_quest", "class": klass})
                class_deltas[klass] = set()
                continue
            qid = int(maybe_qid)
            allowed = lambda x, qid=qid: int(x) == qid or common_allowed(int(x))
            closure, _added, local = transitive_closure(
                {qid},
                direct_by_quest,
                allowed=allowed,
                exists=exists,
                alternatives=alternative_by_quest,
                defer_allowed=lambda x, qid=qid: int(x) == qid or rows_by_id[int(x)].get("is_order_quest", False),
                preselected=base,
            )
            branch_conflicts.extend({"branch": f"class:{klass}", **c} for c in local)
            class_deltas[klass] = closure - base

        order_deltas: dict[str, set[int]] = {}
        for order_name, ids in ORDER_QUEST_IDS["bonta"].items():
            branch_ids = {int(v) for v in ids if int(v) in all_ids}
            allowed = lambda x, branch_ids=branch_ids: int(x) in branch_ids or common_allowed(int(x))
            closure, _added, local = transitive_closure(
                branch_ids,
                direct_by_quest,
                allowed=allowed,
                exists=exists,
                alternatives=alternative_by_quest,
                defer_allowed=lambda x, branch_ids=branch_ids: int(x) in branch_ids or rows_by_id[int(x)].get("is_class_quest", False),
                preselected=base,
            )
            branch_conflicts.extend({"branch": f"order:{order_name}", **c} for c in local)
            order_deltas[order_name] = closure - base
        return class_deltas, order_deltas, _dedupe_conflict_rows(branch_conflicts)

    permanent_filler_ids: set[int] = set()
    temporal_filler_ids: set[int] = set()
    qq_required = int(achievement_req.get("qq_required_count") or 0)
    permanent_candidates = [
        qid for qid, row in rows_by_id.items()
        if qid not in common and row["repeatability"] == "normal"
        and not row["event_like"] and not row["almanax_like"]
        and not row.get("is_alignment_alternative")
        and not row.get("is_order_quest")
        and not row.get("is_class_quest")
        and qid not in one_of_variant_ids
        and common_allowed(qid)
    ]

    # Phase 1: exhaust useful permanent neutral quests first. This minimizes
    # calendar waiting while still meeting the global QQ achievement requirement.
    for _ in range(8):
        class_deltas, order_deltas, _branch_conflicts = compute_branch_deltas(common)
        counts = branch_combination_counts(common, class_deltas, order_deltas)
        minimum_count = min(counts, default=len(common))
        if minimum_count >= qq_required:
            break
        minimum_branch_delta = max(0, minimum_count - len(common))
        target_common = max(len(common), qq_required - minimum_branch_delta)
        filled, new_fillers, fill_conflicts = fill_to_qq_threshold(
            common,
            target_common,
            permanent_candidates,
            direct_by_quest,
            allowed=common_allowed,
            exists=exists,
            alternatives=alternative_by_quest,
            defer_allowed=conditional_branch_id,
            rank_key=lambda qid: (
                0 if qid in seed_map else 1,
                rows_by_id[qid]["level_min"],
                len(direct_by_quest.get(qid, set())),
                seed_map.get(qid, 9999),
                qid,
            ),
        )
        common = filled
        permanent_filler_ids.update(new_fillers)
        # QQ shortage here is not a structural failure yet: temporal content can
        # legally finish the 1600-count success.
        conflicts.extend(c for c in fill_conflicts if not str(c.get("type", "")).startswith("qq_"))
        if not new_fillers:
            break

    class_deltas, order_deltas, branch_conflicts = compute_branch_deltas(common)
    permanent_counts = branch_combination_counts(common, class_deltas, order_deltas)
    permanent_minimum_count = min(permanent_counts, default=len(common))
    permanent_maximum_count = max(permanent_counts, default=len(common))

    # Phase 2: if permanent content cannot mathematically reach QQ, add the
    # minimum distinct calendar quests. Prefer batchable seasonal event quests
    # over one-day Almanax offerings; both remain explicitly time-gated cards.
    temporal_allowed = lambda qid: bool(
        rows_by_id.get(int(qid))
        and not rows_by_id[int(qid)].get("is_alignment_alternative")
        and not rows_by_id[int(qid)].get("is_order_quest")
        and not rows_by_id[int(qid)].get("is_class_quest")
        and (
            common_allowed(int(qid))
            or rows_by_id[int(qid)].get("event_like")
            or rows_by_id[int(qid)].get("almanax_like")
        )
        and norm((rows_by_id[int(qid)].get("condition") or {}).get("alignment")) not in {"brakmar"}
    )
    temporal_candidates = [
        qid for qid, row in rows_by_id.items()
        if qid not in common
        and (row.get("event_like") or row.get("almanax_like"))
        and not row.get("is_alignment_alternative")
        and not row.get("is_order_quest")
        and not row.get("is_class_quest")
        and qid not in one_of_variant_ids
        and temporal_allowed(qid)
    ]

    if permanent_minimum_count < qq_required and temporal_candidates:
        minimum_branch_delta = max(0, permanent_minimum_count - len(common))
        target_common = max(len(common), qq_required - minimum_branch_delta)
        filled, new_temporal, temporal_conflicts = fill_to_qq_threshold(
            common,
            target_common,
            temporal_candidates,
            direct_by_quest,
            allowed=temporal_allowed,
            exists=exists,
            alternatives=alternative_by_quest,
            defer_allowed=conditional_branch_id,
            rank_key=lambda qid: (
                0 if rows_by_id[qid].get("event_like") and not rows_by_id[qid].get("almanax_like") else 1,
                rows_by_id[qid]["level_min"],
                len(direct_by_quest.get(qid, set())),
                seed_map.get(qid, 9999),
                qid,
            ),
        )
        common = filled
        temporal_filler_ids.update(new_temporal)
        conflicts.extend(c for c in temporal_conflicts if c.get("type") not in {"qq_shortfall", "qq_no_conflict_free_candidate"})

    class_deltas, order_deltas, branch_conflicts = compute_branch_deltas(common)
    conflicts.extend(branch_conflicts)
    counts = branch_combination_counts(common, class_deltas, order_deltas)
    minimum_count = min(counts, default=len(common))
    maximum_count = max(counts, default=len(common))
    filler_ids = permanent_filler_ids | temporal_filler_ids

    return {
        "id": "universal_bonta_full_success",
        "alignment": "Bonta",
        "common_selected_quest_ids": sorted(common),
        "routing_common_selected_quest_ids": sorted(set(common) - temporal_filler_ids),
        "seed_quest_ids": sorted(seeds),
        "dofus_seed_quest_ids": sorted(dofus_targets),
        "prerequisite_quest_ids_added": sorted(prereq_added),
        "qq_required_count": qq_required,
        "qq_filler_quest_ids": sorted(filler_ids),
        "qq_permanent_filler_quest_ids": sorted(permanent_filler_ids),
        "qq_temporal_filler_quest_ids": sorted(temporal_filler_ids),
        "qq_temporal_required_count": len(temporal_filler_ids),
        "qq_shortfall": max(0, qq_required - minimum_count),
        "choice_selections": choices,
        "conditional_choice_groups": sorted(set(conditional_choice_groups)),
        "class_branches": {k: sorted(v) for k, v in class_deltas.items()},
        "order_branches": {k: sorted(v) for k, v in order_deltas.items()},
        "class_branch_slot_count": 1,
        "order_branch_slot_count": 5,
        "permanent_execution_count_min": permanent_minimum_count,
        "permanent_execution_count_max": permanent_maximum_count,
        "execution_count_min": minimum_count,
        "execution_count_max": maximum_count,
        "execution_count_invariant": minimum_count == maximum_count,
        "conflicts": _dedupe_conflict_rows(conflicts),
    }


def classify_all(overlay: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    quest_provider = QuestProvider(data_dir=RAW_QUEST_DATA_DIR)
    catalog = quest_provider.get_catalog()
    achievement_provider = AchievementProvider(data_dir=RAW_QUEST_DATA_DIR, quest_provider=quest_provider)
    guide_provider = GuideProvider(quest_provider=quest_provider, achievement_provider=achievement_provider, include_drafts=True)

    raw_quests = doduda_rows(RAW_QUEST_DATA_DIR / "quests.json")
    name_index = build_name_index(catalog)
    enriched = enriched_prerequisites(catalog, name_index)
    alignment_main, alignment_variants = alignment_rows(catalog, raw_quests)
    orders = order_lookup()
    _legacy_quest_success_quests, monster_successes, dungeon_successes = achievement_sets(achievement_provider)
    guide_map, dofus_quests, curated_quests = guide_membership(guide_provider)
    achievement_req = quest_achievement_requirements(achievement_provider)

    direct_by_quest: dict[int, set[int]] = {}
    alternative_by_quest: dict[int, tuple[frozenset[int], ...]] = {}
    required_by: dict[int, set[int]] = defaultdict(set)
    for quest in catalog.quests:
        refs = direct_prerequisites(quest, enriched, name_index)
        alternatives = alternative_prerequisites(quest)
        direct_by_quest[int(quest.id)] = refs
        if alternatives:
            alternative_by_quest[int(quest.id)] = alternatives
        for previous in refs:
            if previous in catalog.by_id:
                required_by[previous].add(int(quest.id))

    seed_map = legacy_seed_map(overlay)
    order_templates = chapter_templates(overlay)
    rows_by_id: dict[int, dict[str, Any]] = {}
    unresolved_criteria: list[dict[str, Any]] = []
    runtime_gate_criteria: list[dict[str, Any]] = []
    missing_prereqs: list[dict[str, Any]] = []

    # First classify every catalogue quest, but include NONE by default. Runtime
    # V5 classifies the whole catalogue first; one universal scope is built below.
    for quest in sorted(catalog.quests, key=lambda q: (int(q.level_min or 0), norm(q.name), int(q.id))):
        qid = int(quest.id)
        qname = str(quest.name)
        nname = norm(qname)
        raw = raw_quests.get(qid, {}) if isinstance(raw_quests.get(qid, {}), dict) else {}
        repeat_kind = repeatability_kind(quest, raw)
        condition: dict[str, Any] = {}
        runtime_policy = "always_when_unlocked"
        base_status = "excluded_not_needed_for_target"
        repeat_target: dict[str, Any] | None = None
        choice_group: dict[str, Any] | None = None
        reasons: list[str] = []
        is_order = qid in orders
        is_class = nname in CLASS_BY_NAME
        is_alignment_alt = qid in alignment_variants

        if is_order:
            side, order_name, rank = orders[qid]
            base_status = "included_order_branch"
            condition = {"alignment": side, "order": order_name, "order_rank": rank, "min_alignment_level": ORDER_LEVELS[rank - 1]}
            runtime_policy = "selected_alignment_and_order_only"
            reasons.append("one_of_three_orders")
        elif qid in alignment_main:
            side, raw_pa = alignment_main[qid]
            base_status = "included_alignment_branch"
            condition = {"alignment": side, "alignment_raw_pa": int(raw_pa), "target_alignment_level": int(raw_pa) + 1}
            runtime_policy = "selected_alignment_only"
            reasons.append("canonical_alignment_rank")
        elif is_alignment_alt:
            side, raw_pa = alignment_variants[qid]
            base_status = "included_alignment_alternative"
            condition = {"alignment": side, "alignment_raw_pa": int(raw_pa), "target_alignment_level": int(raw_pa) + 1, "alternative_same_rank": True}
            runtime_policy = "only_if_game_branch_selects_it"
            reasons.append("same_rank_alternative")
        elif is_class:
            base_status = "included_class_branch"
            condition = {"class": CLASS_BY_NAME[nname]}
            runtime_policy = "selected_class_only"
            reasons.append("class_specific")
        elif event_like(quest, raw):
            base_status = "included_event_branch"
            condition = {"event_required": True}
            runtime_policy = "only_while_event_available"
            reasons.append("calendar_branch")

        if nname in DARWIN_CHOICE:
            base_status = "included_choice_repeatable"
            runtime_policy = "one_of_choice_group_until_success"
            choice_group = {"id": "carnage_de_glace_one_of", "required_count": 1}
            reasons.append("Carnage_de_glace_one_of_five")
        elif nname in MANDATORY_REPEATABLES:
            meta = MANDATORY_REPEATABLES[nname]
            base_status = "included_required_repeatable"
            runtime_policy = str(meta["runtime_policy"])
            repeat_target = dict(meta["counter"]) if isinstance(meta.get("counter"), dict) else None
            reasons.append(str(meta["reason"]))
        elif repeat_kind != "normal":
            if almanax_like(quest, raw):
                base_status = "deferred_daily"
                runtime_policy = "tracked_side_thread_not_blocking"
            elif base_status != "included_event_branch":
                base_status = "excluded_useless_repeatable"
                runtime_policy = "skip_unless_proven_required"

        if qid in dofus_quests: reasons.append("dofus_guide_context")
        if qid in curated_quests: reasons.append("curated_existing_guide_context")
        if qid in set(achievement_req["mandatory_quest_ids"]): reasons.append("quest_achievement_direct_target")

        raw_criterion = str(getattr(quest, "start_criterion", "") or "")
        criterion_side = criterion_alignment_side(raw_criterion)
        if criterion_side and not (condition.get("alignment") if isinstance(condition, dict) else None):
            # Generic Ps=1/Ps=2 gates exist outside the canonical alignment
            # rank chains too. They must participate in universal-scope
            # filtering, otherwise Brâkmar-only filler quests can leak into the
            # Bonta route and disappear later inside the GPS profile filter.
            condition = {**condition, "alignment": criterion_side}

        runtime_codes, unknown_codes = criterion_gate_codes(quest)
        if runtime_codes:
            runtime_gate_criteria.append({
                "quest_id": qid, "name": qname, "codes": runtime_codes,
                "criterion": raw_criterion,
                "policy": "surface_exact_gate_on_route_card_no_fake_validation",
            })
        if unknown_codes:
            unresolved_criteria.append({
                "quest_id": qid, "name": qname, "codes": unknown_codes,
                "criterion": raw_criterion,
            })
        prereqs = sorted(q for q in direct_by_quest[qid] if q in catalog.by_id)
        missing = sorted(q for q in direct_by_quest[qid] if q not in catalog.by_id)
        if missing:
            missing_prereqs.append({"quest_id": qid, "name": qname, "missing_prerequisite_ids": missing})

        rows_by_id[qid] = {
            "quest_id": qid,
            "name": qname,
            "level_min": int(getattr(quest, "level_min", 0) or 0),
            "level_max": int(getattr(quest, "level_max", 0) or 0),
            "category": str(getattr(quest, "category", "") or ""),
            "base_status": base_status,
            "status": base_status,
            "include_in_global_scope": False,
            "runtime_policy": runtime_policy,
            "condition": condition,
            "repeatability": repeat_kind,
            "repeat_target": repeat_target,
            "choice_group": choice_group,
            "prerequisite_quest_ids": prereqs,
            "prerequisite_quest_alternatives": [sorted(map(int, group)) for group in alternative_by_quest.get(qid, ())],
            "required_by_quest_ids": sorted(required_by.get(qid, set())),
            "achievement_names": list(getattr(quest, "achievements", ()) or ()),
            "guide_ids": sorted(guide_map.get(qid, set())),
            "objective_items": objective_items(quest),
            "chapter_seed_order": seed_map.get(qid, chapter_order_for_level(int(getattr(quest, "level_min", 0) or 0))),
            "reasons": sorted(set(reasons)),
            "event_like": event_like(quest, raw),
            "almanax_like": almanax_like(quest, raw),
            "is_order_quest": is_order,
            "is_class_quest": is_class,
            "is_alignment_alternative": is_alignment_alt,
        }

    universal = _universal_scope(rows_by_id, direct_by_quest, alternative_by_quest, achievement_req, alignment_main, seed_map, dofus_quests)
    common_ids = {int(v) for v in universal["common_selected_quest_ids"]}
    prerequisite_ids = {int(v) for v in universal["prerequisite_quest_ids_added"]}
    filler_ids = {int(v) for v in universal["qq_filler_quest_ids"]}
    permanent_filler_ids = {int(v) for v in universal.get("qq_permanent_filler_quest_ids", [])}
    temporal_filler_ids = {int(v) for v in universal.get("qq_temporal_filler_quest_ids", [])}
    conditional_choice_groups = set(str(v) for v in universal.get("conditional_choice_groups", []))
    class_branch_union = {int(v) for values in universal["class_branches"].values() for v in values}
    order_branch_union = {int(v) for values in universal["order_branches"].values() for v in values}

    # Keep all legal alternatives in the single content lock, but they are
    # conditional cards inside ONE guide, never separate generated profiles.
    choice_variant_ids = {qid for qid, row in rows_by_id.items() if norm(row["name"]) in DARWIN_CHOICE}
    for group in achievement_req.get("choice_groups", []):
        group_id = str(group["id"])
        gids = [int(v) for v in group.get("candidate_quest_ids", []) if int(v) in rows_by_id]
        if group_id in conditional_choice_groups:
            # Class/Order alternatives already live in their dedicated inline cards.
            continue
        choice_variant_ids.update(gids)
        for qid in gids:
            if rows_by_id[qid].get("choice_group") is None:
                rows_by_id[qid]["choice_group"] = {"id": group_id, "required_count": 1}
                rows_by_id[qid]["runtime_policy"] = "one_of_choice_group_until_success"
                rows_by_id[qid]["base_status"] = "included_choice_repeatable"

    global_ids = common_ids | class_branch_union | order_branch_union | choice_variant_ids
    direct_targets = set(int(v) for v in achievement_req["mandatory_quest_ids"])
    for qid, row in rows_by_id.items():
        include = qid in global_ids
        row["include_in_global_scope"] = include
        row["include_in_universal_common_route"] = qid in common_ids
        if qid in class_branch_union:
            row["status"] = "included_class_branch"
            row["runtime_policy"] = "conditional_class_card"
        elif qid in order_branch_union:
            row["status"] = "included_order_branch"
            row["runtime_policy"] = "conditional_order_card"
        elif include:
            if row["base_status"] not in {"excluded_not_needed_for_target", "excluded_useless_repeatable", "deferred_daily"}:
                row["status"] = row["base_status"]
            elif qid in temporal_filler_ids:
                row["status"] = "included_qq_temporal_filler"
                row["runtime_policy"] = "qq_calendar_filler_when_available"
                row["condition"] = {**(row.get("condition") or {}), "calendar_required": True}
                row["reasons"] = sorted(set(row["reasons"] + ["minimum_quest_count_for_QQ_success", "calendar_filler_for_QQ_1600"]))
            elif qid in permanent_filler_ids:
                row["status"] = "included_qq_filler"
                row["runtime_policy"] = "universal_qq_filler"
                row["reasons"] = sorted(set(row["reasons"] + ["minimum_quest_count_for_QQ_success"]))
            elif qid in prerequisite_ids and qid not in direct_targets:
                row["status"] = "included_prerequisite"
                row["runtime_policy"] = "required_by_Qf_dependency"
                row["reasons"] = sorted(set(row["reasons"] + ["transitive_Qf_prerequisite"]))
            else:
                row["status"] = "included_main"
                row["runtime_policy"] = "target_quest_success_or_required_chain"
        elif row["base_status"] in {"included_alignment_branch", "included_alignment_alternative"}:
            row["status"] = row["base_status"]
        elif row["event_like"]:
            row["status"] = "included_event_branch"
        elif row["repeatability"] != "normal":
            row["status"] = "excluded_useless_repeatable" if not row["almanax_like"] else "deferred_daily"
        else:
            row["status"] = "excluded_not_needed_for_target"

    rows = [rows_by_id[qid] for qid in sorted(rows_by_id, key=lambda q: (rows_by_id[q]["level_min"], norm(rows_by_id[q]["name"]), q))]
    status_counts = Counter(row["status"] for row in rows)

    chapter_quests: dict[int, list[int]] = defaultdict(list)
    for qid in sorted(global_ids):
        chapter_quests[rows_by_id[qid]["chapter_seed_order"]].append(qid)
    sections: list[dict[str, Any]] = []
    for order in range(1, 20):
        template = order_templates[order]
        qids = sorted(set(chapter_quests.get(order, [])), key=lambda qid: (
            0 if qid in seed_map else 1, seed_map.get(qid, 9999), rows_by_id[qid]["level_min"], norm(rows_by_id[qid]["name"]), qid,
        ))
        sections.append({
            "id": str(template.get("id") or f"guide_ultime_{order:02d}"),
            "title": str(template.get("title") or f"Chapitre {order}"),
            "description": "Route maître universelle. Les quêtes de classe et d'Ordre sont des cartes conditionnelles dans ce même guide.",
            "steps": [{
                "id": f"guide_ultime_quest_{qid}", "type": "quest", "entity_id": qid, "optional": False,
                "notes": " | ".join(rows_by_id[qid]["reasons"]),
                "prerequisites": [{"type": "quest", "entity_id": previous} for previous in rows_by_id[qid]["prerequisite_quest_ids"]],
                "prerequisite_alternatives": rows_by_id[qid].get("prerequisite_quest_alternatives", []),
                "status": rows_by_id[qid]["status"], "runtime_policy": rows_by_id[qid]["runtime_policy"],
                "condition": rows_by_id[qid]["condition"], "repeat_target": rows_by_id[qid]["repeat_target"],
                "choice_group": rows_by_id[qid]["choice_group"], "objective_items": rows_by_id[qid]["objective_items"],
            } for qid in qids],
        })

    universal_conflicts = list(universal.get("conflicts") or [])
    qq_shortfall = int(universal.get("qq_shortfall") or 0)
    target_monster_success_ids = sorted(int(row["achievement_id"]) for row in monster_successes)
    target_dungeon_success_ids = sorted(int(row["achievement_id"]) for row in dungeon_successes)
    target_quest_success_ids = list(achievement_req["target_achievement_ids"])

    guide = {
        "schema_version": 5,
        "id": "guide_ultime",
        "title": "Guide Ultime — FULL SUCCÈS universel 0→200",
        "category": "aventure",
        "description": (
            "Une seule route maître universelle: succès Quêtes permanents, succès Monstres intégrés, "
            "Dofus/Ocre/Sylvestre, Bonta 1→100, un Ordre au choix sous forme de cartes conditionnelles, "
            "une quête de classe conditionnelle, vrais prérequis Qf transitifs et minimum de quêtes QQ. "
            + DUNGEON_ACHIEVEMENT_POLICY_NOTE
        ),
        "recommended_level_min": 1,
        "recommended_level_max": 200,
        "reward_item_id": None, "illustration_item_id": None, "image": None,
        "linked_achievement_ids": sorted(set(target_quest_success_ids + target_monster_success_ids + target_dungeon_success_ids)),
        "completeness_status": "complete" if not (missing_prereqs or universal_conflicts or qq_shortfall or achievement_req["unresolved_objectives"]) else "partial",
        "verified_steps": len(global_ids), "total_steps": len(global_ids),
        "validation_warnings": [
            DUNGEON_ACHIEVEMENT_POLICY_NOTE,
            "V5 UNIVERSAL: aucun paramètre de classe ou d'Ordre pour générer le guide.",
            "Une seule branche de classe et un seul Ordre sont exécutés par le joueur via les cartes conditionnelles.",
            "QQ: toutes les quêtes permanentes compatibles sont prioritaires; si 1600 reste mathématiquement impossible, le minimum de quêtes calendrier est planifié explicitement.",
        ],
        "generation_source": "V5_universal_full_success+local_QuestCatalog+AchievementProvider",
        "guide_ultime_policy": {
            "overlay": overlay,
            "quest_manifest_count": len(rows),
            "included_global_union_count": len(global_ids),
            "target_quest_success_ids": target_quest_success_ids,
            "expanded_meta_achievement_ids": achievement_req["expanded_achievement_ids"],
            "quest_achievement_choice_groups": achievement_req["choice_groups"],
            "quest_achievement_route_side_objectives": achievement_req.get("route_side_objectives", []),
            "qq_required_count": achievement_req["qq_required_count"],
            "target_monster_successes": monster_successes,
            "target_dungeon_successes": dungeon_successes,
            "conditional_branches": {
                "class": {
                    "instruction": "Fais uniquement la quête correspondant à ta classe, puis reprends la route commune.",
                    "logical_slots": 1,
                    "branches": universal["class_branches"],
                },
                "bonta_order": {
                    "instruction": "Choisis un seul des 3 Ordres de Bonta au premier palier et garde le même jusqu'au rang 5.",
                    "logical_slots": 5,
                    "thresholds": list(ORDER_LEVELS),
                    "branches": universal["order_branches"],
                },
            },
            "universal_scope": universal,
        },
        "sections": sections,
    }

    all_ids = {int(q.id) for q in catalog.quests}
    fight_club_qids = {qid for qid, row in rows_by_id.items() if norm(row["name"]) == norm("Fight club")}
    audit = {
        "schema_version": 5,
        "as_of": "2026-08-22",
        "selection_model": "one_universal_guide_empty_seed_target_closure_conditional_class_order_minimum_QQ_fill",
        "catalog_total": len(all_ids), "raw_quests_total": len(raw_quests), "classified_total": len(rows),
        "unclassified_quest_ids": sorted(all_ids - set(rows_by_id)),
        "global_content_lock_quest_count": len(global_ids),
        "common_route_quest_count": len(universal.get("routing_common_selected_quest_ids", [])),
        "eventual_common_quest_count": len(common_ids),
        "universal_execution_count_min": int(universal["execution_count_min"]),
        "universal_execution_count_max": int(universal["execution_count_max"]),
        "universal_execution_count_invariant": bool(universal["execution_count_invariant"]),
        "class_branch_count": len(universal["class_branches"]),
        "order_branch_count": len(universal["order_branches"]),
        "class_branch_slot_count": 1,
        "order_branch_slot_count": 5,
        "qq_required_count": achievement_req["qq_required_count"],
        "qq_permanent_execution_count_min": int(universal.get("permanent_execution_count_min", 0)),
        "qq_permanent_execution_count_max": int(universal.get("permanent_execution_count_max", 0)),
        "qq_permanent_filler_count": len(universal.get("qq_permanent_filler_quest_ids", [])),
        "qq_temporal_filler_count": len(universal.get("qq_temporal_filler_quest_ids", [])),
        "qq_temporal_filler_quest_ids": list(universal.get("qq_temporal_filler_quest_ids", [])),
        "qq_shortfall": qq_shortfall,
        "universal_conflicts": universal_conflicts,
        "status_counts": dict(sorted(status_counts.items())),
        "target_quest_success_count": len(target_quest_success_ids),
        "expanded_meta_achievement_count": len(achievement_req["expanded_achievement_ids"]),
        "unresolved_quest_achievement_objectives": achievement_req["unresolved_objectives"],
        "quest_achievement_route_side_objectives": achievement_req.get("route_side_objectives", []),
        "monster_success_count": len(monster_successes),
        "dungeon_success_count": len(dungeon_successes),
        "dofus_guide_context_quest_count": len(dofus_quests),
        "missing_prerequisites": missing_prereqs,
        "runtime_gate_criteria": runtime_gate_criteria,
        "unresolved_hard_criteria": unresolved_criteria,
        "overlay_loaded_from": overlay.get("_loaded_from", ""),
        "critical_rules": {
            "starts_from_empty_scope": True,
            "single_universal_guide": True,
            "no_class_generator_parameter": True,
            "no_order_generator_parameter": True,
            "only_Qf_equals_is_hard_quest_dependency": True,
            "qf_or_is_any_of_not_all_of": True,
            "qa_is_not_completion_dependency": True,
            "bonta_one_order_as_conditional_branch": len(universal["order_branches"]) == 3 and int(universal["order_branch_slot_count"]) == 5,
            "one_class_branch_as_conditional_card": len(universal["class_branches"]) == len(CLASS_QUESTS) and int(universal["class_branch_slot_count"]) == 1,
            "darwin_exactly_one_reference_choice": bool(universal["choice_selections"].get("carnage_de_glace_one_of")),
            "qq_fill_prioritizes_permanent_then_minimum_calendar": True,
            "fight_club_once_retained": bool(fight_club_qids & common_ids),
            "dungeon_achievements_included": True,
            "full_success_categories_linked": bool(target_quest_success_ids and target_monster_success_ids and target_dungeon_success_ids),
        },
    }
    allowed_statuses = set(((overlay.get("completion_contract") or {}).get("allowed_statuses")) or [])
    audit["allowed_statuses"] = sorted(allowed_statuses)
    audit["unexpected_statuses"] = sorted(set(status_counts) - allowed_statuses) if allowed_statuses else []
    return guide, {"audit": audit, "rows": rows}


def write_outputs(guide: dict[str, Any], bundle: dict[str, Any], *, apply: bool) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    OUT_GUIDE.write_text(json.dumps(guide, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_AUDIT.write_text(json.dumps(bundle["audit"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([
            "quest_id", "name", "level_min", "category", "status", "include",
            "runtime_policy", "repeatability", "condition", "prerequisites", "reasons",
        ])
        for row in bundle["rows"]:
            writer.writerow([
                row["quest_id"], row["name"], row["level_min"], row["category"], row["status"],
                int(bool(row["include_in_global_scope"])), row["runtime_policy"], row["repeatability"],
                json.dumps(row["condition"], ensure_ascii=False, separators=(",", ":")),
                ",".join(map(str, row["prerequisite_quest_ids"])), " | ".join(row["reasons"]),
            ])

    audit = bundle["audit"]
    lines = [
        "DOFUS ATLAS — GUIDE ULTIME — CONTENT LOCK",
        "=" * 78,
        f"Catalogue local                    : {audit['catalog_total']}",
        f"Classifiées                        : {audit['classified_total']}",
        f"Contenu global (avec branches)      : {audit['global_content_lock_quest_count']}",
        f"Route commune                       : {audit['common_route_quest_count']}",
        f"Exécution universelle finale min→max: {audit['universal_execution_count_min']} → {audit['universal_execution_count_max']}",
        f"Route permanente avant calendrier   : {audit['qq_permanent_execution_count_min']} → {audit['qq_permanent_execution_count_max']}",
        f"Seuil QQ requis                     : {audit['qq_required_count']}",
        f"Fillers QQ permanents               : {audit['qq_permanent_filler_count']}",
        f"Fillers QQ calendrier               : {audit['qq_temporal_filler_count']}",
        f"Succès Monstres ciblés             : {audit['monster_success_count']}",
        f"Succès Donjons ciblés              : {audit['dungeon_success_count']}",
        f"Prérequis manquants                : {len(audit['missing_prerequisites'])}",
        f"Conflits universels/prérequis       : {len(audit['universal_conflicts'])}",
        f"Manque au seuil QQ                  : {audit['qq_shortfall']}",
        f"Objectifs succès Quêtes non résolus: {len(audit['unresolved_quest_achievement_objectives'])}",
        f"Objectifs succès routage/gates      : {len(audit.get('quest_achievement_route_side_objectives', []))}",
        f"Gates runtime explicites           : {len(audit.get('runtime_gate_criteria', []))}",
        f"Critères réellement inconnus       : {len(audit['unresolved_hard_criteria'])}",
        "",
        "STATUTS",
    ]
    for key, value in audit["status_counts"].items():
        lines.append(f"  {key:38} {value:>5}")
    lines.extend([
        "",
        f"Guide : {OUT_GUIDE}", f"Audit : {OUT_AUDIT}", f"CSV   : {OUT_CSV}",
    ])
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if apply:
        APPLY_PATH.parent.mkdir(parents=True, exist_ok=True)
        APPLY_PATH.write_text(json.dumps(guide, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def strict_errors(audit: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if audit["catalog_total"] != audit["classified_total"]:
        errors.append(f"{len(audit['unclassified_quest_ids'])} quête(s) non classée(s)")
    if audit["raw_quests_total"] and audit["raw_quests_total"] != audit["catalog_total"]:
        errors.append(f"raw quests={audit['raw_quests_total']} != QuestCatalog={audit['catalog_total']}")
    if audit["missing_prerequisites"]:
        errors.append(f"{len(audit['missing_prerequisites'])} prérequis Qf pointent hors catalogue")
    if audit.get("universal_conflicts"):
        errors.append(f"{len(audit['universal_conflicts'])} conflit(s) de prérequis/branche dans le guide universel")
    if int(audit.get("qq_shortfall") or 0):
        errors.append(f"seuil QQ non atteint: manque {int(audit['qq_shortfall'])} quête(s)")
    if audit.get("unresolved_quest_achievement_objectives"):
        errors.append(f"{len(audit['unresolved_quest_achievement_objectives'])} objectif(s) de succès Quêtes restent non résolus")
    if audit.get("unexpected_statuses"):
        errors.append("statuts hors contrat: " + ", ".join(audit["unexpected_statuses"]))
    if not audit["critical_rules"].get("starts_from_empty_scope"):
        errors.append("la sélection ne part pas d'un scope vide")
    if not audit["critical_rules"].get("fight_club_once_retained"):
        errors.append("Fight Club doit être retenu une fois dans la route universelle")
    if not audit["critical_rules"].get("dungeon_achievements_included"):
        errors.append("les succès Donjons doivent être inclus dans la cible FULL SUCCÈS")
    if not audit["critical_rules"].get("full_success_categories_linked"):
        errors.append("Quêtes/Monstres/Donjons ne sont pas tous reliés à la cible FULL SUCCÈS")
    return errors

def main() -> None:
    parser = argparse.ArgumentParser(description="Construit le Guide Ultime V5 UNIVERSAL à partir des données locales DOFUS Atlas.")
    parser.add_argument("--overlay", default=None, help="Chemin vers guide_ultime_master_2026-08-22.json")
    parser.add_argument("--strict", action="store_true", help="Échoue sur toute omission structurelle prouvée.")
    parser.add_argument("--apply", action="store_true", help="Écrit aussi data/encyclopedia/guides/guide_ultime.json après génération.")
    args = parser.parse_args()

    overlay = load_overlay(args.overlay)
    guide, bundle = classify_all(overlay)
    write_outputs(guide, bundle, apply=args.apply)
    audit = bundle["audit"]
    print(OUT_TXT.read_text(encoding="utf-8"))

    if args.strict:
        errors = strict_errors(audit)
        if errors:
            raise SystemExit("ECHEC STRICT — " + " ; ".join(errors))


if __name__ == "__main__":
    main()
