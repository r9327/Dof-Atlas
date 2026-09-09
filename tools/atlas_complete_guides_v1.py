from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
import traceback
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import DATA_DIR
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.quest_catalog import normalize_text

GUIDES_DIR = DATA_DIR / "encyclopedia" / "guides"
ARTIFACTS_DIR = ROOT / "artifacts"

GENERATED_PREREQ_ID = "atlas_complete_required_prerequisites"
GENERATED_ORDER_PREFIX = "atlas_complete_order_"

QUEST_CRITERION_RE = re.compile(r"\bQ(?:f|a)\s*[=><!]+\s*(\d+)", re.IGNORECASE)
ACHIEVEMENT_CRITERION_RE = re.compile(r"\b(?:Sc|Ac)\s*[=><!]+\s*(\d+)", re.IGNORECASE)

# Sanity checks only. These values never invent quest IDs: they only make an
# incomplete local closure visible in the before/after report.
KNOWN_MINIMUMS: dict[str, int] = {
    "dofus_argente": 58,
    "dofoozbz": 13,
    "dofus_des_glaces": 72,
    "dofus_nebuleux": 101,
    "dofus_abyssal": 40,
    "dofus_vulbis": 8,
    "dofus_sylvestre": 401,  # DPLN: more than 400 with mandatory prerequisites.
}

# Small list of blockers known to be mandatory but not always represented as a
# direct Qf/Sc criterion in exported data. Resolution is still against the
# user's LOCAL quest catalog; no fake quest ID is hard-coded here.
EXTRA_REQUIRED_QUEST_NAMES: dict[str, tuple[str, ...]] = {
    "dofus_pourpre": (
        "Comment perdre ses plumes",
    ),
    "dorigami": (
        "Sang d'encre",
        "Voir le Dark Vlad et mourir... ou pas",
    ),
    "dofus_vulbis": (
        "Ce sera mieux avant",
        "Le sens du sacrifice",
    ),
    "dofus_ebene": (
        "Mieux vaut ne pas se fier à la première impression",
        "Le fléau de Burin",
        "La colère des dieux",
        "Frappez, ami et entrez",
        "De Brikke et de Brokke",
        "Un pendule pour guider ses pas",
    ),
    "dofus_tachete": (
        "Requiem pour un Yokai",
        "L'épopée du moine pèlerin",
    ),
}

# Six Orders, 5 quests each. Group names are sorted alphabetically when written
# after the 100 main alignment quests.
ALIGNMENT_ORDERS: dict[str, dict[str, tuple[str, ...]]] = {
    "bonta": {
        "Ordre du Cœur Vaillant": (
            "Apprentissage : Disciple de Ménalt",
            "Apprentissage : Écuyer",
            "Apprentissage : Chevalier de l'Espoir",
            "Apprentissage : Champion Merveilleux",
            "Apprentissage : Héros Légendaire",
        ),
        "Ordre de l'Esprit Salvateur": (
            "Apprentissage : Disciple de Jiva",
            "Apprentissage : Apprenti Éclairé",
            "Apprentissage : Adepte des Écrits",
            "Apprentissage : Maître des Parchemins",
            "Apprentissage : Gardien du Savoir",
        ),
        "Ordre de l'Œil Attentif": (
            "Apprentissage : Disciple de Silvosse",
            "Apprentissage : Espion silencieux",
            "Apprentissage : Chasseur de Rénégats",
            "Apprentissage : Assassin Suprême",
            "Apprentissage : Maître des Illusions",
        ),
    },
    "brakmar": {
        "Ordre du Cœur Saignant": (
            "Apprentissage : Disciple de Djaul",
            "Apprentissage : Surineur",
            "Apprentissage : Chevalier du Désespoir",
            "Apprentissage : Champion du Chaos",
            "Apprentissage : Héros de l'Apocalypse",
        ),
        "Ordre de l'Esprit Malsain": (
            "Apprentissage : Disciple d'Hécate",
            "Apprentissage : Apprenti Sombre",
            "Apprentissage : Adepte des Douleurs",
            "Apprentissage : Maître des Sévices",
            "Apprentissage : Gardien des Tortures",
        ),
        "Ordre de l'Œil Putride": (
            "Apprentissage : Disciple de Brumaire",
            "Apprentissage : Espion Sombre",
            "Apprentissage : Chasseur d'Âmes",
            "Apprentissage : Psychopathe",
            "Apprentissage : Maître des Ombres",
        ),
    },
}

ORDER_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    normalize_text("Apprentissage : Champion du Chaos"): (
        "Apprentissage : Champion du Chaos",
        "Apprentissage : Champions du Chaos",
    ),
}


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON guide invalide: {path}")
    return value


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Parse before replacing a live guide.
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(path)


def normalized_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in normalize_text(value).split("_") if token)


def canonical_guide_key(payload: dict[str, Any], path: Path) -> str:
    identity = normalize_text(
        " ".join(
            (
                str(payload.get("id") or path.stem),
                str(payload.get("title") or ""),
                path.stem,
            )
        )
    )
    aliases = (
        ("dofoozbz", "dofoozbz"),
        ("argente_scintillant", "dofus_argente_scintillant"),
        ("argente", "dofus_argente"),
        ("des_glaces", "dofus_des_glaces"),
        ("nebuleux", "dofus_nebuleux"),
        ("abyssal", "dofus_abyssal"),
        ("vulbis", "dofus_vulbis"),
        ("sylvestre", "dofus_sylvestre"),
        ("pourpre", "dofus_pourpre"),
        ("ebene", "dofus_ebene"),
        ("tachete", "dofus_tachete"),
        ("dorigami", "dorigami"),
        ("domakuro", "domakuro"),
        ("veilleur", "dofus_des_veilleurs"),
        ("cawotte", "dofus_cawotte"),
        ("emeraude", "dofus_emeraude"),
        ("turquoise", "dofus_turquoise"),
        ("ivoire", "dofus_ivoire"),
        ("ocre", "dofus_ocre"),
        ("cauchemar", "dofus_du_cauchemar"),
        ("dokoko", "dokoko"),
        ("dokille", "dokille"),
        ("dolmanax", "dolmanax"),
    )
    for token, key in aliases:
        if token in identity:
            return key
    return normalize_text(str(payload.get("id") or path.stem))


def collect_quest_ids(value: Any) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            kind = normalize_text(str(node.get("type") or node.get("step_type") or ""))
            if kind == "quest":
                qid = safe_int(node.get("entity_id"))
                if qid is not None and qid not in seen:
                    seen.add(qid)
                    result.append(qid)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return result


def collect_linked_achievement_ids(value: Any) -> set[int]:
    result: set[int] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            rows = node.get("linked_achievement_ids")
            if isinstance(rows, list):
                for raw in rows:
                    aid = safe_int(raw)
                    if aid is not None:
                        result.add(aid)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return result


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from iter_strings(child)


def make_quest_step(
    prefix: str,
    quest_id: int,
    prerequisites: Iterable[int] = (),
    *,
    optional: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    refs = [
        {"type": "quest", "entity_id": int(qid)}
        for qid in dict.fromkeys(int(value) for value in prerequisites)
        if int(qid) != int(quest_id)
    ]
    return {
        "id": f"{prefix}_quest_{int(quest_id)}",
        "type": "quest",
        "entity_id": int(quest_id),
        "optional": bool(optional),
        "notes": notes,
        "prerequisites": refs,
    }


def discover_guides() -> tuple[
    dict[str, tuple[Path, dict[str, Any]]],
    dict[str, tuple[Path, dict[str, Any]]],
]:
    dofus: dict[str, tuple[Path, dict[str, Any]]] = {}
    alignments: dict[str, tuple[Path, dict[str, Any]]] = {}

    if not GUIDES_DIR.exists():
        raise RuntimeError(f"Dossier guides introuvable: {GUIDES_DIR}")

    for path in sorted(GUIDES_DIR.glob("*.json")):
        if path.name in {
            "catalog.json",
            "manifest.json",
            "dofus_guide_overrides.json",
        }:
            continue
        try:
            payload = read_json(path)
        except Exception:
            continue
        category = normalize_text(str(payload.get("category") or ""))
        identity = normalize_text(
            f"{payload.get('id', '')} {payload.get('title', '')} {path.stem}"
        )
        if category == "dofus":
            dofus[canonical_guide_key(payload, path)] = (path, payload)
        elif category in {"alignement", "alignements"}:
            if "bonta" in identity:
                alignments["bonta"] = (path, payload)
            elif "brakmar" in identity:
                alignments["brakmar"] = (path, payload)

    if not dofus:
        raise RuntimeError("Aucun guide Dofus actif trouvé.")
    missing_sides = {"bonta", "brakmar"} - set(alignments)
    if missing_sides:
        raise RuntimeError(f"Guide(s) Alignement introuvable(s): {sorted(missing_sides)}")
    return dofus, alignments


class LocalResolver:
    def __init__(self, dofus_guides: dict[str, tuple[Path, dict[str, Any]]]) -> None:
        self.quest_provider = QuestProvider()
        self.quest_catalog = self.quest_provider.get_catalog()
        self.quests = list(self.quest_catalog.quests)
        self.quest_by_id = dict(self.quest_catalog.by_id)
        self.quest_by_name: dict[str, list[Any]] = defaultdict(list)
        for quest in self.quests:
            self.quest_by_name[normalize_text(str(quest.name))].append(quest)

        self.achievement_provider = AchievementProvider(quest_provider=self.quest_provider)
        self.achievements = self.achievement_provider.load_all()
        self.achievement_by_id = {int(item.id): item for item in self.achievements}
        self.achievement_by_name: dict[str, list[Any]] = defaultdict(list)
        for achievement in self.achievements:
            self.achievement_by_name[normalize_text(str(achievement.name))].append(achievement)

        self.quest_name_index = sorted(
            (
                (name, tuple(rows))
                for name, rows in self.quest_by_name.items()
                if len(name) >= 9
            ),
            key=lambda row: len(row[0]),
            reverse=True,
        )
        self.achievement_name_index = sorted(
            (
                (name, tuple(rows))
                for name, rows in self.achievement_by_name.items()
                if len(name) >= 8
            ),
            key=lambda row: len(row[0]),
            reverse=True,
        )

        self.dofus_guides = dofus_guides
        self.guide_name_index: list[tuple[str, str, dict[str, Any]]] = []
        for key, (_path, payload) in dofus_guides.items():
            title = normalize_text(str(payload.get("title") or ""))
            ident = normalize_text(str(payload.get("id") or key))
            for candidate in dict.fromkeys((title, ident)):
                if len(candidate) >= 6:
                    self.guide_name_index.append((candidate, key, payload))
        self.guide_name_index.sort(key=lambda row: len(row[0]), reverse=True)

        self.reasons: dict[int, set[str]] = defaultdict(set)

    def resolve_quest_name(self, name: str, *, strict: bool = True) -> Any | None:
        keys = [normalize_text(name)]
        for alias in ORDER_NAME_ALIASES.get(normalize_text(name), ()):
            keys.append(normalize_text(alias))
        found: dict[int, Any] = {}
        for key in dict.fromkeys(keys):
            for quest in self.quest_by_name.get(key, ()):
                found[int(quest.id)] = quest
        if len(found) == 1:
            return next(iter(found.values()))

        # Conservative fuzzy fallback for punctuation/singular-plural drift.
        target = normalize_text(name)
        candidates = difflib.get_close_matches(
            target,
            list(self.quest_by_name),
            n=4,
            cutoff=0.88,
        )
        fuzzy: dict[int, Any] = {}
        for key in candidates:
            for quest in self.quest_by_name[key]:
                fuzzy[int(quest.id)] = quest
        if len(fuzzy) == 1:
            return next(iter(fuzzy.values()))
        if strict:
            suggestions = [
                (int(q.id), str(q.name))
                for key in candidates
                for q in self.quest_by_name.get(key, ())
            ]
            raise RuntimeError(
                f"Quête locale introuvable/ambiguë: {name!r}. Suggestions: {suggestions[:8]}"
            )
        return None

    def quest_refs_in_criterion(self, text: str) -> set[int]:
        return {
            int(match.group(1))
            for match in QUEST_CRITERION_RE.finditer(str(text or ""))
            if int(match.group(1)) in self.quest_by_id
        }

    def achievement_refs_in_criterion(self, text: str) -> set[int]:
        return {
            int(match.group(1))
            for match in ACHIEVEMENT_CRITERION_RE.finditer(str(text or ""))
            if int(match.group(1)) in self.achievement_by_id
        }

    def quest_names_in_text(self, text: str) -> set[int]:
        normalized = normalize_text(str(text or ""))
        if not normalized:
            return set()
        result: set[int] = set()
        for name, rows in self.quest_name_index:
            if name in normalized:
                result.update(int(quest.id) for quest in rows)
        return result

    def achievement_names_in_text(self, text: str) -> set[int]:
        normalized = normalize_text(str(text or ""))
        if not normalized:
            return set()
        result: set[int] = set()
        for name, rows in self.achievement_name_index:
            if name in normalized:
                result.update(int(achievement.id) for achievement in rows)
        return result

    def referenced_dofus_guides(self, text: str) -> list[tuple[str, dict[str, Any]]]:
        normalized = normalize_text(str(text or ""))
        if not normalized:
            return []
        # Only interpret another Dofus name as a hard prerequisite in a text that
        # clearly expresses possession/obtention/requirement.
        trigger_tokens = (
            "obtenir",
            "posseder",
            "possession",
            "avoir",
            "requis",
            "prerequis",
            "necessaire",
        )
        if not any(token in normalized for token in trigger_tokens):
            return []
        result: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for guide_name, key, payload in self.guide_name_index:
            if guide_name in normalized and key not in seen:
                seen.add(key)
                result.append((key, payload))
        return result

    def achievement_linked_quests(self, achievement: Any) -> set[int]:
        result: set[int] = set()
        for ref in getattr(achievement, "linked_quests", ()) or ():
            qid = safe_int(getattr(ref, "entity_id", None))
            if qid is not None and qid in self.quest_by_id:
                result.add(qid)
        return result

    def root_achievement_ids(self, payload: dict[str, Any]) -> set[int]:
        roots = {
            aid
            for aid in collect_linked_achievement_ids(payload)
            if aid in self.achievement_by_id
        }
        reward_item_id = safe_int(payload.get("reward_item_id"))
        if reward_item_id is not None:
            for achievement in self.achievements:
                for reward in getattr(achievement, "rewards", ()) or ():
                    entity_id = safe_int(getattr(reward, "entity_id", None))
                    if (
                        str(getattr(reward, "kind", "") or "") == "item"
                        and entity_id == reward_item_id
                    ):
                        roots.add(int(achievement.id))
        return roots

    def direct_quest_dependencies(self, quest_id: int) -> set[int]:
        quest = self.quest_by_id.get(int(quest_id))
        if quest is None:
            return set()
        return self.quest_refs_in_criterion(str(getattr(quest, "start_criterion", "") or ""))

    def closure(self, guide_key: str, payload: dict[str, Any]) -> tuple[list[int], dict[int, list[str]]]:
        quest_seen: set[int] = set()
        achievement_seen: set[int] = set()
        quest_queue: deque[int] = deque()
        achievement_queue: deque[int] = deque()

        self.reasons = defaultdict(set)

        def add_quest(qid: int, reason: str) -> None:
            qid = int(qid)
            if qid not in self.quest_by_id:
                return
            self.reasons[qid].add(reason)
            if qid in quest_seen:
                return
            quest_seen.add(qid)
            quest_queue.append(qid)
            if len(quest_seen) > 900:
                raise RuntimeError(
                    f"Fermeture de prérequis anormalement large pour {guide_key}: "
                    f"> 900 quêtes. Écriture refusée pour éviter une contamination du guide."
                )

        def add_achievement(aid: int, reason: str) -> None:
            aid = int(aid)
            if aid not in self.achievement_by_id or aid in achievement_seen:
                return
            achievement_seen.add(aid)
            achievement_queue.append(aid)

        for qid in collect_quest_ids(payload):
            add_quest(qid, "déjà_dans_guide")

        for aid in self.root_achievement_ids(payload):
            add_achievement(aid, "succès_racine")

        # If a legacy guide only contains a direct quest and no linked success,
        # its own achievements are useful roots.
        for qid in list(quest_seen):
            for achievement in self.achievement_provider.get_by_quest(qid):
                add_achievement(int(achievement.id), f"succès_de_quête_{qid}")

        for required_name in EXTRA_REQUIRED_QUEST_NAMES.get(guide_key, ()):
            quest = self.resolve_quest_name(required_name, strict=False)
            if quest is not None:
                add_quest(int(quest.id), f"prérequis_spécial:{normalize_text(required_name)}")

        while quest_queue or achievement_queue:
            while achievement_queue:
                aid = achievement_queue.popleft()
                achievement = self.achievement_by_id[aid]

                for qid in self.achievement_linked_quests(achievement):
                    add_quest(qid, f"succès:{normalize_text(str(achievement.name))}")

                # Parse every exported criterion/raw string for Qf/Qa and Sc/Ac.
                for text in (
                    [str(getattr(obj, "criterion", "") or "") for obj in getattr(achievement, "objectives", ()) or ()]
                    + list(iter_strings(getattr(achievement, "raw", {}) or {}))
                ):
                    for qid in self.quest_refs_in_criterion(text):
                        add_quest(qid, f"critère_succès_{aid}")
                    for child_aid in self.achievement_refs_in_criterion(text):
                        add_achievement(child_aid, f"critère_succès_{aid}")

                # Some meta-success exports carry readable objective labels rather
                # than an explicit Sc criterion. Resolve exact local success names.
                for objective in getattr(achievement, "objectives", ()) or ():
                    text = str(getattr(objective, "text", "") or "")
                    normalized = normalize_text(text)
                    if "succes" in normalized:
                        for child_aid in self.achievement_names_in_text(text):
                            if child_aid != aid:
                                add_achievement(child_aid, f"objectif_succès_{aid}")
                    if "quete" in normalized:
                        for qid in self.quest_names_in_text(text):
                            add_quest(qid, f"objectif_succès_{aid}")
                    for _other_key, other_payload in self.referenced_dofus_guides(text):
                        for qid in collect_quest_ids(other_payload):
                            add_quest(qid, f"dofus_prérequis_succès_{aid}")
                        for child_aid in self.root_achievement_ids(other_payload):
                            add_achievement(child_aid, f"dofus_prérequis_succès_{aid}")

            if quest_queue:
                qid = quest_queue.popleft()
                quest = self.quest_by_id[qid]
                criterion = str(getattr(quest, "start_criterion", "") or "")

                for previous in self.quest_refs_in_criterion(criterion):
                    if previous != qid:
                        add_quest(previous, f"prérequis_Qf/Qa_de_{qid}")
                for aid in self.achievement_refs_in_criterion(criterion):
                    add_achievement(aid, f"prérequis_succès_de_{qid}")

                # Enriched prerequisite labels in the local quest catalog.
                for text in getattr(quest, "prerequisites", ()) or ():
                    text = str(text)
                    for previous in self.quest_refs_in_criterion(text):
                        if previous != qid:
                            add_quest(previous, f"prérequis_texte_de_{qid}")
                    for previous in self.quest_names_in_text(text):
                        if previous != qid:
                            add_quest(previous, f"prérequis_texte_de_{qid}")
                    for aid in self.achievement_refs_in_criterion(text):
                        add_achievement(aid, f"prérequis_texte_de_{qid}")
                    for aid in self.achievement_names_in_text(text):
                        add_achievement(aid, f"prérequis_texte_de_{qid}")
                    for _other_key, other_payload in self.referenced_dofus_guides(text):
                        for other_qid in collect_quest_ids(other_payload):
                            add_quest(other_qid, f"dofus_prérequis_de_{qid}")
                        for aid in self.root_achievement_ids(other_payload):
                            add_achievement(aid, f"dofus_prérequis_de_{qid}")

        ordered = self.dependency_order(quest_seen)
        return ordered, {qid: sorted(self.reasons[qid]) for qid in ordered}

    def dependency_order(self, quest_ids: Iterable[int]) -> list[int]:
        ids = {int(qid) for qid in quest_ids if int(qid) in self.quest_by_id}
        incoming = {qid: 0 for qid in ids}
        children: dict[int, set[int]] = defaultdict(set)

        for qid in ids:
            for previous in self.direct_quest_dependencies(qid):
                if previous not in ids or qid in children[previous]:
                    continue
                children[previous].add(qid)
                incoming[qid] += 1

        def sort_key(qid: int) -> tuple[int, str, int]:
            quest = self.quest_by_id[qid]
            level = safe_int(getattr(quest, "level_min", None)) or 9999
            return level, normalize_text(str(quest.name)), qid

        ready = sorted((qid for qid, count in incoming.items() if count == 0), key=sort_key)
        result: list[int] = []
        while ready:
            qid = ready.pop(0)
            result.append(qid)
            for child in sorted(children.get(qid, ()), key=sort_key):
                incoming[child] -= 1
                if incoming[child] == 0:
                    ready.append(child)
                    ready.sort(key=sort_key)

        remaining = ids - set(result)
        result.extend(sorted(remaining, key=sort_key))
        return result

    def resolve_order_quests(self) -> dict[str, dict[str, list[int]]]:
        result: dict[str, dict[str, list[int]]] = {"bonta": {}, "brakmar": {}}
        all_ids: list[int] = []
        for side in ("bonta", "brakmar"):
            for order_name in sorted(ALIGNMENT_ORDERS[side], key=normalize_text):
                ids: list[int] = []
                for quest_name in ALIGNMENT_ORDERS[side][order_name]:
                    quest = self.resolve_quest_name(quest_name, strict=True)
                    assert quest is not None
                    ids.append(int(quest.id))
                if len(ids) != 5 or len(set(ids)) != 5:
                    raise RuntimeError(f"{side}/{order_name}: 5 IDs uniques attendus, obtenu {ids}")
                result[side][order_name] = ids
                all_ids.extend(ids)
        if len(all_ids) != 30 or len(set(all_ids)) != 30:
            raise RuntimeError("Les 30 quêtes d'Ordre ne sont pas toutes résolues de façon unique.")
        return result


def remove_generated_parts(payload: dict[str, Any], prefix: str) -> None:
    parts = payload.get("parts")
    if isinstance(parts, list):
        parts[:] = [
            part
            for part in parts
            if not (
                isinstance(part, dict)
                and str(part.get("id") or "").startswith(prefix)
            )
        ]


def remove_generated_sections(payload: dict[str, Any], prefix: str) -> None:
    sections = payload.get("sections")
    if isinstance(sections, list):
        sections[:] = [
            section
            for section in sections
            if not (
                isinstance(section, dict)
                and str(section.get("id") or "").startswith(prefix)
            )
        ]


def add_alignment_orders(
    payload: dict[str, Any],
    side: str,
    resolved: dict[str, list[int]],
) -> None:
    remove_generated_parts(payload, GENERATED_ORDER_PREFIX)
    remove_generated_sections(payload, GENERATED_ORDER_PREFIX)

    parts = payload.get("parts")
    use_parts = isinstance(parts, list) and bool(parts)

    if use_parts:
        assert isinstance(parts, list)
        max_order = max(
            (safe_int(part.get("order")) or 0 for part in parts if isinstance(part, dict)),
            default=0,
        )
        for index, order_name in enumerate(sorted(resolved, key=normalize_text), 1):
            quest_ids = resolved[order_name]
            steps: list[dict[str, Any]] = []
            previous: int | None = None
            for rank, qid in enumerate(quest_ids, 1):
                deps = [previous] if previous is not None else []
                steps.append(
                    make_quest_step(
                        f"{GENERATED_ORDER_PREFIX}{side}_{index}",
                        qid,
                        deps,
                        optional=True,
                        notes=f"{order_name} · Rang {rank} · palier alignement {rank * 20}.",
                    )
                )
                previous = qid
            block_id = f"{GENERATED_ORDER_PREFIX}{side}_{index}"
            parts.append(
                {
                    "id": block_id,
                    "title": order_name,
                    "order": max_order + index,
                    "type": "quest_category",
                    "progress_mode": "quests",
                    "optional_branch": True,
                    "exclusive_group": f"alignement_{side}_ordres",
                    "chapters": [
                        {
                            "id": f"{block_id}_chapter",
                            "title": order_name,
                            "order": 1,
                            "series": [
                                {
                                    "id": f"{block_id}_series",
                                    "title": order_name,
                                    "order": 1,
                                    "quest_ids": quest_ids,
                                    "steps": steps,
                                }
                            ],
                        }
                    ],
                }
            )
        return

    sections = payload.setdefault("sections", [])
    if not isinstance(sections, list):
        raise RuntimeError(f"{payload.get('id')}: sections invalide")
    for index, order_name in enumerate(sorted(resolved, key=normalize_text), 1):
        quest_ids = resolved[order_name]
        previous: int | None = None
        steps = []
        for rank, qid in enumerate(quest_ids, 1):
            deps = [previous] if previous is not None else []
            steps.append(
                make_quest_step(
                    f"{GENERATED_ORDER_PREFIX}{side}_{index}",
                    qid,
                    deps,
                    optional=True,
                    notes=f"{order_name} · Rang {rank} · palier alignement {rank * 20}.",
                )
            )
            previous = qid
        sections.append(
            {
                "id": f"{GENERATED_ORDER_PREFIX}{side}_{index}",
                "title": order_name,
                "description": "",
                "optional_branch": True,
                "exclusive_group": f"alignement_{side}_ordres",
                "steps": steps,
            }
        )


def group_missing_quests(resolver: LocalResolver, quest_ids: list[int]) -> list[tuple[str, list[int]]]:
    groups: dict[str, list[int]] = defaultdict(list)
    group_first_index: dict[str, int] = {}
    for index, qid in enumerate(quest_ids):
        quest = resolver.quest_by_id[qid]
        achievements = list(getattr(quest, "achievements", ()) or ())
        label = str(achievements[0]).strip() if achievements else str(getattr(quest, "category", "") or "").strip()
        if not label:
            label = "Prérequis obligatoires"
        group_first_index.setdefault(label, index)
        groups[label].append(qid)
    return sorted(groups.items(), key=lambda row: (group_first_index[row[0]], normalize_text(row[0])))


def add_dofus_prerequisites(
    payload: dict[str, Any],
    resolver: LocalResolver,
    required_ids: list[int],
) -> list[int]:
    # Idempotent: remove only blocks created by this tool, then recompute against
    # all original/current guide content.
    remove_generated_parts(payload, GENERATED_PREREQ_ID)
    remove_generated_sections(payload, GENERATED_PREREQ_ID)

    current = set(collect_quest_ids(payload))
    missing = [qid for qid in required_ids if qid not in current]
    if not missing:
        return []

    groups = group_missing_quests(resolver, missing)
    parts = payload.get("parts")
    use_parts = isinstance(parts, list) and bool(parts)

    if use_parts:
        assert isinstance(parts, list)
        existing_orders = [
            safe_int(part.get("order")) or index
            for index, part in enumerate(parts, 1)
            if isinstance(part, dict)
        ]
        first_order = min(existing_orders, default=1)
        chapters: list[dict[str, Any]] = []
        for group_index, (label, ids) in enumerate(groups, 1):
            steps = [
                make_quest_step(
                    f"{GENERATED_PREREQ_ID}_{group_index}",
                    qid,
                    resolver.direct_quest_dependencies(qid) & set(required_ids),
                )
                for qid in ids
            ]
            chapter_id = f"{GENERATED_PREREQ_ID}_chapter_{group_index}"
            chapters.append(
                {
                    "id": chapter_id,
                    "title": label,
                    "order": group_index,
                    "series": [
                        {
                            "id": f"{chapter_id}_series",
                            "title": label,
                            "order": 1,
                            "quest_ids": ids,
                            "steps": steps,
                        }
                    ],
                }
            )
        parts.insert(
            0,
            {
                "id": GENERATED_PREREQ_ID,
                "title": "Prérequis obligatoires",
                "order": first_order - 1000,
                "type": "quest_category",
                "progress_mode": "quests",
                "chapters": chapters,
            },
        )
        return missing

    sections = payload.setdefault("sections", [])
    if not isinstance(sections, list):
        raise RuntimeError(f"{payload.get('id')}: sections invalide")
    steps = [
        make_quest_step(
            GENERATED_PREREQ_ID,
            qid,
            resolver.direct_quest_dependencies(qid) & set(required_ids),
        )
        for qid in missing
    ]
    sections.insert(
        0,
        {
            "id": GENERATED_PREREQ_ID,
            "title": "Prérequis obligatoires",
            "description": "",
            "steps": steps,
        },
    )
    return missing


def clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False))


def build_plan() -> tuple[
    dict[Path, dict[str, Any]],
    dict[str, Any],
    dict[str, dict[str, list[int]]],
    dict[str, tuple[Path, dict[str, Any]]],
    dict[str, tuple[Path, dict[str, Any]]],
]:
    dofus_guides, alignment_guides = discover_guides()
    resolver = LocalResolver(dofus_guides)
    order_ids = resolver.resolve_order_quests()

    planned: dict[Path, dict[str, Any]] = {}
    report: dict[str, Any] = {
        "orders": {},
        "dofus": {},
    }

    # Alignments: preserve all current content, append 3 named Order groups after
    # the existing 100 alignment quests.
    for side in ("bonta", "brakmar"):
        path, original = alignment_guides[side]
        payload = clone_payload(original)
        before_ids = set(collect_quest_ids(payload))
        if len(before_ids) < 100:
            raise RuntimeError(
                f"{payload.get('title') or path.stem}: seulement {len(before_ids)} quêtes avant Ordres; "
                "les 100 quêtes d'alignement doivent déjà être présentes."
            )
        add_alignment_orders(payload, side, order_ids[side])
        after_ids = set(collect_quest_ids(payload))
        expected_order_ids = {
            qid for ids in order_ids[side].values() for qid in ids
        }
        if not expected_order_ids.issubset(after_ids):
            raise RuntimeError(f"{side}: certaines quêtes d'Ordre n'ont pas été ajoutées.")
        planned[path] = payload
        report["orders"][side] = {
            "title": payload.get("title"),
            "before": len(before_ids),
            "added": len(expected_order_ids - before_ids),
            "after": len(after_ids),
            "order_groups": {
                name: ids for name, ids in sorted(order_ids[side].items(), key=lambda row: normalize_text(row[0]))
            },
        }

    # Dofus: recursively resolve all local mandatory prerequisites, including
    # success trees, quest criteria and explicit prerequisite labels.
    for guide_key, (path, original) in sorted(dofus_guides.items()):
        payload = clone_payload(original)
        # Remove previous generated block before counting the true current guide.
        remove_generated_parts(payload, GENERATED_PREREQ_ID)
        remove_generated_sections(payload, GENERATED_PREREQ_ID)
        before_ids = set(collect_quest_ids(payload))
        required_ids, reasons = resolver.closure(guide_key, payload)
        added_ids = add_dofus_prerequisites(payload, resolver, required_ids)
        after_ids = set(collect_quest_ids(payload))
        missing_after = set(required_ids) - after_ids
        if missing_after:
            raise RuntimeError(
                f"{payload.get('title') or guide_key}: {len(missing_after)} quêtes résolues restent absentes du JSON."
            )

        minimum = KNOWN_MINIMUMS.get(guide_key)
        status = "OK"
        if minimum is not None and len(after_ids) < minimum:
            status = "PARTIEL"

        warnings = payload.get("validation_warnings")
        if not isinstance(warnings, list):
            warnings = []
        warnings = [
            str(value)
            for value in warnings
            if not str(value).startswith("AUDIT COMPLET PREREQUIS:")
        ]
        if status == "PARTIEL":
            warnings.append(
                f"AUDIT COMPLET PREREQUIS: {len(after_ids)} quêtes visibles; "
                f"minimum externe de contrôle {minimum}. Vérification manuelle requise."
            )
            payload["completeness_status"] = "partial"
        payload["validation_warnings"] = warnings
        payload["verified_steps"] = len(after_ids)
        payload["total_steps"] = len(after_ids)

        planned[path] = payload
        report["dofus"][guide_key] = {
            "title": payload.get("title"),
            "before": len(before_ids),
            "detected_required": len(required_ids),
            "added": len(added_ids),
            "after": len(after_ids),
            "minimum_control": minimum,
            "status": status,
            "added_quests": [
                {
                    "id": qid,
                    "name": str(resolver.quest_by_id[qid].name),
                    "reasons": reasons.get(qid, []),
                }
                for qid in added_ids
            ],
        }

    return planned, report, order_ids, dofus_guides, alignment_guides


def print_report(report: dict[str, Any]) -> None:
    print()
    print("=" * 106)
    print("GUIDES DOFUS ATLAS — AVANT / AJOUT / APRÈS")
    print("=" * 106)
    for side in ("bonta", "brakmar"):
        row = report["orders"][side]
        print(
            f"{str(row['title'])[:34]:34}  {row['before']:>5} -> {row['after']:>5}  "
            f"(+{row['added']})  |  3 Ordres x 5 quêtes"
        )
    print("-" * 106)
    print(f"{'GUIDE DOFUS':38} {'AVANT':>7} {'AJOUT':>7} {'APRÈS':>7} {'MIN':>7}  ETAT")
    for _key, row in sorted(report["dofus"].items(), key=lambda item: normalize_text(str(item[1].get("title") or item[0]))):
        title = str(row.get("title") or _key)[:37]
        minimum = row.get("minimum_control")
        minimum_text = str(minimum) if minimum is not None else "-"
        print(
            f"{title:38} {row['before']:>7} {row['added']:>7} {row['after']:>7} "
            f"{minimum_text:>7}  {row['status']}"
        )
    print("=" * 106)


def save_report(report: dict[str, Any], stamp: str) -> tuple[Path, Path]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = ARTIFACTS_DIR / f"guides_complete_before_after_{stamp}.json"
    txt_path = ARTIFACTS_DIR / f"guides_complete_before_after_{stamp}.txt"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "GUIDES DOFUS ATLAS — AVANT / AJOUT / APRÈS",
        "",
    ]
    for side in ("bonta", "brakmar"):
        row = report["orders"][side]
        lines.append(
            f"{row['title']}: {row['before']} -> {row['after']} (+{row['added']}) ; "
            "3 Ordres x 5 quêtes"
        )
    lines.extend(("", "GUIDES DOFUS"))
    for key, row in sorted(report["dofus"].items(), key=lambda item: normalize_text(str(item[1].get("title") or item[0]))):
        lines.append(
            f"{row.get('title') or key}: {row['before']} -> {row['after']} "
            f"(+{row['added']}) ; min={row.get('minimum_control') or '-'} ; {row['status']}"
        )
        for quest in row.get("added_quests", []):
            lines.append(f"  + [{quest['id']}] {quest['name']}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, txt_path


def validate_live_guides(
    report: dict[str, Any],
    order_ids: dict[str, dict[str, list[int]]],
    dofus_guides: dict[str, tuple[Path, dict[str, Any]]],
    alignment_guides: dict[str, tuple[Path, dict[str, Any]]],
) -> None:
    provider = GuideProvider()
    loaded = provider.load_all()
    by_id = {str(guide.id): guide for guide in loaded}

    # Alignment Orders must be present in the actual structure consumed by the UI.
    for side in ("bonta", "brakmar"):
        path, original = alignment_guides[side]
        guide_id = str(original.get("id") or path.stem)
        guide = by_id.get(guide_id)
        if guide is None:
            raise RuntimeError(f"Validation: guide {guide_id} non chargé par GuideProvider.")
        visible_ids = {int(qid) for qid in guide.quest_ids}
        expected_ids = {qid for ids in order_ids[side].values() for qid in ids}
        if not expected_ids.issubset(visible_ids):
            raise RuntimeError(
                f"Validation {guide_id}: {len(expected_ids - visible_ids)} IDs d'Ordre invisibles."
            )
        part_titles = {normalize_text(str(part.title)) for part in guide.parts}
        for order_name in order_ids[side]:
            if normalize_text(order_name) not in part_titles:
                raise RuntimeError(
                    f"Validation {guide_id}: groupe d'Ordre invisible dans guide.parts: {order_name}"
                )

    # Every quest written to a Dofus JSON must be visible through GuideProvider.
    for key, (path, original) in dofus_guides.items():
        guide_id = str(original.get("id") or path.stem)
        guide = by_id.get(guide_id)
        if guide is None:
            raise RuntimeError(f"Validation: guide Dofus {guide_id} non chargé.")
        expected_count = int(report["dofus"][key]["after"])
        visible_ids = {int(qid) for qid in guide.quest_ids}
        if len(visible_ids) < expected_count:
            raise RuntimeError(
                f"Validation {guide_id}: GuideProvider voit {len(visible_ids)} quêtes, "
                f"{expected_count} attendues."
            )


def apply_plan(
    planned: dict[Path, dict[str, Any]],
    report: dict[str, Any],
    order_ids: dict[str, dict[str, list[int]]],
    dofus_guides: dict[str, tuple[Path, dict[str, Any]]],
    alignment_guides: dict[str, tuple[Path, dict[str, Any]]],
    stamp: str,
) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    backup_dir = ARTIFACTS_DIR / f"guides_complete_backup_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for path in planned:
        shutil.copy2(path, backup_dir / path.name)

    try:
        for path, payload in planned.items():
            write_json_atomic(path, payload)
        validate_live_guides(report, order_ids, dofus_guides, alignment_guides)
    except BaseException:
        print("\nERREUR PENDANT L'APPLICATION. Restauration des guides...", file=sys.stderr)
        traceback.print_exc()
        for path in planned:
            saved = backup_dir / path.name
            if saved.exists():
                shutil.copy2(saved, path)
        print(f"Rollback terminé. Backup conservé: {backup_dir}", file=sys.stderr)
        raise

    return backup_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Complète les guides Dofus et ajoute les quêtes d'Ordre aux Alignements."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Écrit réellement les guides après l'audit et les validations.",
    )
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    planned, report, order_ids, dofus_guides, alignment_guides = build_plan()
    print_report(report)
    json_report, txt_report = save_report(report, stamp)

    print(f"\nRapport JSON : {json_report}")
    print(f"Rapport texte: {txt_report}")

    partial = [
        str(row.get("title") or key)
        for key, row in report["dofus"].items()
        if row.get("status") == "PARTIEL"
    ]
    if partial:
        print("\nATTENTION — minimum externe non atteint pour:")
        for title in partial:
            print(f"  - {title}")
        print(
            "Le script ajoute quand même toutes les dépendances obligatoires qu'il peut "
            "résoudre dans les données locales, mais ne marque pas ces guides comme complets."
        )

    if not args.apply:
        print("\nAUDIT UNIQUEMENT — aucun guide modifié.")
        print(r"Pour appliquer: py -3.13 .\tools\atlas_complete_guides_v1.py --apply")
        return

    backup_dir = apply_plan(
        planned,
        report,
        order_ids,
        dofus_guides,
        alignment_guides,
        stamp,
    )
    print("\nAPPLICATION TERMINÉE ET VALIDÉE PAR GuideProvider.")
    print(f"Backup: {backup_dir}")
    print("Bonta: 3 Ordres x 5 quêtes ajoutés après les quêtes d'alignement.")
    print("Brâkmar: 3 Ordres x 5 quêtes ajoutés après les quêtes d'alignement.")


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        # Never swallow the real error. No sys.exit()/PowerShell exit here.
        traceback.print_exc()
