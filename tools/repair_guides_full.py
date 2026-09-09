from __future__ import annotations

import json
import re
import shutil
import sys

from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path


ROOT = Path.cwd()

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from app.constants import DATA_DIR

from app.modules.encyclopedia.providers import (
    AchievementProvider,
    GuideProvider,
    QuestProvider,
)

from app.quest_catalog import normalize_text


GUIDES = (
    DATA_DIR
    / "encyclopedia"
    / "guides"
)

ART = ROOT / "artifacts"


# ============================================================
# CRITERIA
#
# Qf = quête terminée
# Qa = quête active
# Sc = succès requis
# ============================================================

Q_RE = re.compile(
    r"\b(?:Qf|Qa)\s*[=><!]+\s*(\d+)",
    re.I,
)

SC_RE = re.compile(
    r"\bSc\s*[=><!]+\s*(\d+)",
    re.I,
)


# ============================================================
# KNOWN EXTERNAL CONTROL VALUES
#
# These are sanity checks.
# If the recursive local graph stays below one of these,
# the guide stays marked PARTIAL instead of lying.
# ============================================================

MINIMUMS = {
    "dofus_argente": 58,
    "dofoozbz": 13,
    "dofus_nebuleux": 101,
    "dofus_abyssal": 40,
    "dofus_des_glaces": 72,
    "dofus_vulbis": 8,

    # DPLN explicitly says > 400 with prerequisites.
    "dofus_sylvestre": 401,
}


# ============================================================
# KNOWN QUEST PREREQUISITES THAT MAY NOT APPEAR
# AS A SIMPLE Qf / Sc CRITERION.
# ============================================================

EXTRA = {
    "dofus_cawotte": (
        "Un sage parmi les sages",
    ),

    "dofus_pourpre": (
        "Comment perdre ses plumes",
    ),

    "dorigami": (
        "Sang d'encre",
        "Voir le Dark Vlad et mourir... ou pas",
    ),

    "dofoozbz": (
        "Ça barde là-haut",
        "Un problème de taille",
        "Le vol des bourdons",
        "Des petites bêtes qui font bzzzbz",
        "Têtes de ponte",
        "Dérive insectaire",
        "La proie des vérités",
        "Quand on la cherche, on finit par tomber dessus",
        "Devoir de réserve",
        "Trois cœurs, un roi",
        "Un hôte de marque",
        "L'union sacrée",
        "Destructeur de mondes",
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


# ============================================================
# ALIGNMENT ORDERS
# ============================================================

ORDERS = {
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


# DPLN itself has used both forms.
ALIASES = {
    normalize_text(
        "Apprentissage : Champion du Chaos"
    ): (
        "Apprentissage : Champion du Chaos",
        "Apprentissage : Champions du Chaos",
    ),
}


# ============================================================
# JSON
# ============================================================

def read(path):
    payload = json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            f"JSON invalide: {path}"
        )

    return payload


def write(path, payload):
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Check JSON before replacing live file.
    json.loads(
        tmp.read_text(
            encoding="utf-8",
        )
    )

    tmp.replace(
        path
    )


# ============================================================
# READ QUEST IDs FROM ANY GUIDE STRUCTURE
# ============================================================

def ids_in(payload):
    out = []
    seen = set()

    def walk(value):
        if isinstance(
            value,
            dict,
        ):
            kind = normalize_text(
                value.get("type")
                or value.get("step_type")
                or ""
            )

            if kind == "quest":
                try:
                    quest_id = int(
                        value.get(
                            "entity_id"
                        )
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    quest_id = None

                if (
                    quest_id is not None
                    and quest_id not in seen
                ):
                    seen.add(
                        quest_id
                    )

                    out.append(
                        quest_id
                    )

            for child in value.values():
                walk(child)

        elif isinstance(
            value,
            list,
        ):
            for child in value:
                walk(child)

    walk(payload)

    return out


def achievement_ids_in(
    payload,
):
    result = set()

    def walk(value):
        if isinstance(
            value,
            dict,
        ):
            ids = value.get(
                "linked_achievement_ids"
            )

            if isinstance(
                ids,
                list,
            ):
                for raw in ids:
                    try:
                        result.add(
                            int(raw)
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        pass

            for child in value.values():
                walk(child)

        elif isinstance(
            value,
            list,
        ):
            for child in value:
                walk(child)

    walk(payload)

    return result


# ============================================================
# LOCAL DATA
# ============================================================

QUEST_PROVIDER = QuestProvider()

QUEST_CATALOG = (
    QUEST_PROVIDER
    .get_catalog()
)

QUESTS = list(
    QUEST_CATALOG.quests
)

QUEST_BY_ID = dict(
    QUEST_CATALOG.by_id
)


ACHIEVEMENT_PROVIDER = (
    AchievementProvider(
        quest_provider=QUEST_PROVIDER,
    )
)

ACHIEVEMENTS = (
    ACHIEVEMENT_PROVIDER
    .load_all()
)

ACHIEVEMENT_BY_ID = {
    int(achievement.id):
    achievement

    for achievement
    in ACHIEVEMENTS
}


QUESTS_BY_NAME = defaultdict(
    list
)

for quest in QUESTS:
    QUESTS_BY_NAME[
        normalize_text(
            quest.name
        )
    ].append(
        quest
    )


ACHIEVEMENTS_BY_NAME = (
    defaultdict(list)
)

for achievement in ACHIEVEMENTS:
    ACHIEVEMENTS_BY_NAME[
        normalize_text(
            achievement.name
        )
    ].append(
        achievement
    )


QUEST_NAME_INDEX = sorted(
    (
        (
            key,
            values,
        )

        for key, values
        in QUESTS_BY_NAME.items()

        if len(key) >= 8
    ),

    key=lambda row:
    -len(row[0]),
)


ACHIEVEMENT_NAME_INDEX = sorted(
    (
        (
            key,
            values,
        )

        for key, values
        in ACHIEVEMENTS_BY_NAME.items()

        if len(key) >= 8
    ),

    key=lambda row:
    -len(row[0]),
)


# ============================================================
# STRICT QUEST NAME RESOLUTION
# ============================================================

def resolve_quest(
    name,
):
    matches = {}

    candidates = (
        name,
        *ALIASES.get(
            normalize_text(name),
            (),
        ),
    )

    for candidate in candidates:
        key = normalize_text(
            candidate
        )

        for quest in (
            QUESTS_BY_NAME.get(
                key,
                (),
            )
        ):
            matches[
                int(quest.id)
            ] = quest

    if len(matches) == 1:
        return next(
            iter(
                matches.values()
            )
        )

    # Strict fallback without punctuation separators.
    target = (
        normalize_text(name)
        .replace(
            "_",
            "",
        )
    )

    for quest in QUESTS:
        current = (
            normalize_text(
                quest.name
            )
            .replace(
                "_",
                "",
            )
        )

        if current == target:
            matches[
                int(quest.id)
            ] = quest

    if len(matches) == 1:
        return next(
            iter(
                matches.values()
            )
        )

    raise RuntimeError(
        "Quête introuvable ou ambiguë : "
        f"{name!r} -> "
        f"{[(qid, q.name) for qid, q in matches.items()]}"
    )


# ============================================================
# CRITERIA PARSING
# ============================================================

def criterion_quest_ids(
    text,
):
    return {
        int(match.group(1))

        for match
        in Q_RE.finditer(
            str(
                text
                or ""
            )
        )

        if int(match.group(1))
        in QUEST_BY_ID
    }


def criterion_success_ids(
    text,
):
    return {
        int(match.group(1))

        for match
        in SC_RE.finditer(
            str(
                text
                or ""
            )
        )

        if int(match.group(1))
        in ACHIEVEMENT_BY_ID
    }


# ============================================================
# EXACT NAMES INSIDE PREREQUISITE TEXTS
# ============================================================

def named_quest_ids(
    text,
):
    normalized = normalize_text(
        text
    )

    result = set()

    for key, rows in (
        QUEST_NAME_INDEX
    ):
        if key in normalized:
            result.update(
                int(quest.id)
                for quest in rows
            )

    return result


def named_success_ids(
    text,
):
    normalized = normalize_text(
        text
    )

    result = set()

    for key, rows in (
        ACHIEVEMENT_NAME_INDEX
    ):
        if key in normalized:
            result.update(
                int(achievement.id)
                for achievement
                in rows
            )

    return result


def prerequisite_texts(
    quest,
):
    result = [
        str(value)

        for value
        in (
            getattr(
                quest,
                "prerequisites",
                [],
            )
            or []
        )
    ]

    trigger_tokens = (
        "prerequis",
        "requis",
        "necess",
        "termin",
        "quete",
        "succes",
        "debloqu",
        "avoir_fait",
    )

    weak = [
        str(value)

        for value
        in (
            getattr(
                quest,
                "info",
                [],
            )
            or []
        )
    ]

    for quest_step in (
        getattr(
            quest,
            "steps",
            [],
        )
        or []
    ):
        weak.append(
            str(
                getattr(
                    quest_step,
                    "name",
                    "",
                )
                or ""
            )
        )

        weak.append(
            str(
                getattr(
                    quest_step,
                    "description",
                    "",
                )
                or ""
            )
        )

        for objective in (
            getattr(
                quest_step,
                "objectives",
                [],
            )
            or []
        ):
            weak.append(
                str(
                    getattr(
                        objective,
                        "text",
                        "",
                    )
                    or ""
                )
            )

    for text in weak:
        normalized = normalize_text(
            text
        )

        if any(
            token in normalized
            for token
            in trigger_tokens
        ):
            result.append(
                text
            )

    return result


# ============================================================
# ORDER QUESTS BY REAL Qf DEPENDENCIES
# ============================================================

def quest_sort_key(
    quest_id,
):
    quest = QUEST_BY_ID[
        quest_id
    ]

    try:
        level = int(
            getattr(
                quest,
                "level_min",
                None,
            )
            or 9999
        )

    except Exception:
        level = 9999

    return (
        level,
        normalize_text(
            quest.name
        ),
        quest_id,
    )


def dependency_order(
    all_ids,
):
    all_ids = {
        int(value)

        for value
        in all_ids

        if int(value)
        in QUEST_BY_ID
    }

    incoming = {
        quest_id: 0

        for quest_id
        in all_ids
    }

    children = defaultdict(
        set
    )

    for quest_id in all_ids:
        quest = QUEST_BY_ID[
            quest_id
        ]

        previous_ids = (
            criterion_quest_ids(
                getattr(
                    quest,
                    "start_criterion",
                    "",
                )
            )
        )

        for previous_id in previous_ids:
            if (
                previous_id
                not in all_ids
            ):
                continue

            if (
                quest_id
                in children[
                    previous_id
                ]
            ):
                continue

            children[
                previous_id
            ].add(
                quest_id
            )

            incoming[
                quest_id
            ] += 1

    ready = sorted(
        (
            quest_id

            for quest_id, count
            in incoming.items()

            if count == 0
        ),

        key=quest_sort_key,
    )

    result = []

    while ready:
        quest_id = ready.pop(
            0
        )

        result.append(
            quest_id
        )

        for child in sorted(
            children[
                quest_id
            ],
            key=quest_sort_key,
        ):
            incoming[
                child
            ] -= 1

            if (
                incoming[
                    child
                ]
                == 0
            ):
                ready.append(
                    child
                )

                ready.sort(
                    key=quest_sort_key
                )

    remaining = (
        all_ids
        - set(result)
    )

    result.extend(
        sorted(
            remaining,
            key=quest_sort_key,
        )
    )

    return result


# ============================================================
# FIND SUCCESS THAT ACTUALLY REWARDS THE DOFUS
# ============================================================

def reward_roots(
    payload,
):
    try:
        item_id = int(
            payload.get(
                "reward_item_id"
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return set()

    result = set()

    for achievement in (
        ACHIEVEMENTS
    ):
        for reward in (
            getattr(
                achievement,
                "rewards",
                (),
            )
            or ()
        ):
            try:
                reward_id = int(
                    getattr(
                        reward,
                        "entity_id",
                        0,
                    )
                    or 0
                )

            except Exception:
                continue

            if (
                str(
                    getattr(
                        reward,
                        "kind",
                        "",
                    )
                    or ""
                )
                == "item"
                and reward_id
                == item_id
            ):
                result.add(
                    int(
                        achievement.id
                    )
                )

    return result


# ============================================================
# RECURSIVE DOFUS RESOLVER
#
# success
#   -> linked quests
#   -> Sc sub-successes
#   -> Qf / Qa quest requirements
#
# quest
#   -> Qf / Qa prerequisites
#   -> Sc required successes
#   -> local prerequisite text
#
# repeat until stable
# ============================================================

def resolve_closure(
    payload,
    guide_key,
):
    quest_seen = set(
        ids_in(
            payload
        )
    )

    success_seen = set()

    quest_queue = deque(
        quest_seen
    )

    success_queue = deque()

    root_successes = (
        achievement_ids_in(
            payload
        )
        | reward_roots(
            payload
        )
    )

    for success_id in (
        root_successes
    ):
        if (
            success_id
            in ACHIEVEMENT_BY_ID
            and success_id
            not in success_seen
        ):
            success_seen.add(
                success_id
            )

            success_queue.append(
                success_id
            )

    # Add externally verified blockers.
    for name in EXTRA.get(
        guide_key,
        (),
    ):
        quest_id = int(
            resolve_quest(
                name
            ).id
        )

        if (
            quest_id
            not in quest_seen
        ):
            quest_seen.add(
                quest_id
            )

            quest_queue.append(
                quest_id
            )

    while (
        success_queue
        or quest_queue
    ):

        # --------------------------------------------
        # ACHIEVEMENTS
        # --------------------------------------------

        while success_queue:
            success_id = (
                success_queue
                .popleft()
            )

            achievement = (
                ACHIEVEMENT_BY_ID[
                    success_id
                ]
            )

            # Direct quests of success.
            for ref in (
                getattr(
                    achievement,
                    "linked_quests",
                    (),
                )
                or ()
            ):
                try:
                    quest_id = int(
                        ref.entity_id
                    )

                except Exception:
                    continue

                if (
                    quest_id
                    in QUEST_BY_ID
                    and quest_id
                    not in quest_seen
                ):
                    quest_seen.add(
                        quest_id
                    )

                    quest_queue.append(
                        quest_id
                    )

            # Meta-success relations are stored
            # in achievement objective criteria.
            for objective in (
                getattr(
                    achievement,
                    "objectives",
                    (),
                )
                or ()
            ):
                criterion = str(
                    getattr(
                        objective,
                        "criterion",
                        "",
                    )
                    or ""
                )

                for quest_id in (
                    criterion_quest_ids(
                        criterion
                    )
                ):
                    if (
                        quest_id
                        not in quest_seen
                    ):
                        quest_seen.add(
                            quest_id
                        )

                        quest_queue.append(
                            quest_id
                        )

                for child_success in (
                    criterion_success_ids(
                        criterion
                    )
                ):
                    if (
                        child_success
                        not in success_seen
                    ):
                        success_seen.add(
                            child_success
                        )

                        success_queue.append(
                            child_success
                        )

                text = str(
                    getattr(
                        objective,
                        "text",
                        "",
                    )
                    or ""
                )

                if (
                    "succes"
                    in normalize_text(
                        text
                    )
                ):
                    for child_success in (
                        named_success_ids(
                            text
                        )
                    ):
                        if (
                            child_success
                            != success_id
                            and child_success
                            not in success_seen
                        ):
                            success_seen.add(
                                child_success
                            )

                            success_queue.append(
                                child_success
                            )

        # --------------------------------------------
        # QUESTS
        # --------------------------------------------

        if quest_queue:
            quest_id = (
                quest_queue
                .popleft()
            )

            quest = QUEST_BY_ID[
                quest_id
            ]

            criterion = str(
                getattr(
                    quest,
                    "start_criterion",
                    "",
                )
                or ""
            )

            for previous_id in (
                criterion_quest_ids(
                    criterion
                )
            ):
                if (
                    previous_id
                    not in quest_seen
                ):
                    quest_seen.add(
                        previous_id
                    )

                    quest_queue.append(
                        previous_id
                    )

            for success_id in (
                criterion_success_ids(
                    criterion
                )
            ):
                if (
                    success_id
                    not in success_seen
                ):
                    success_seen.add(
                        success_id
                    )

                    success_queue.append(
                        success_id
                    )

            # Also use enriched Dofus Atlas prerequisite text.
            for text in (
                prerequisite_texts(
                    quest
                )
            ):
                for previous_id in (
                    named_quest_ids(
                        text
                    )
                ):
                    if (
                        previous_id
                        != quest_id
                        and previous_id
                        not in quest_seen
                    ):
                        quest_seen.add(
                            previous_id
                        )

                        quest_queue.append(
                            previous_id
                        )

                for success_id in (
                    named_success_ids(
                        text
                    )
                ):
                    if (
                        success_id
                        not in success_seen
                    ):
                        success_seen.add(
                            success_id
                        )

                        success_queue.append(
                            success_id
                        )

    return dependency_order(
        quest_seen
    )


# ============================================================
# GUIDE STEP FACTORIES
# ============================================================

def make_step(
    prefix,
    quest_id,
    previous=None,
    optional=False,
):
    return {
        "id": (
            f"{prefix}"
            f"_quest_"
            f"{quest_id}"
        ),

        "type": "quest",

        "entity_id": int(
            quest_id
        ),

        "optional": bool(
            optional
        ),

        "notes": "",

        "prerequisites": (
            [
                {
                    "type": "quest",
                    "entity_id": int(
                        previous
                    ),
                }
            ]
            if previous
            is not None
            else []
        ),
    }


def make_series(
    block_id,
    title,
    quest_ids,
    order=1,
    optional=False,
):
    rows = []

    previous = None

    for quest_id in (
        quest_ids
    ):
        rows.append(
            make_step(
                block_id,
                quest_id,
                previous,
                optional,
            )
        )

        previous = (
            quest_id
        )

    return {
        "id": block_id,
        "title": title,
        "order": order,
        "quest_ids": [
            int(value)
            for value
            in quest_ids
        ],
        "steps": rows,
    }


# ============================================================
# ALIGNMENTS
#
# IMPORTANT:
# if "parts" exist, WRITE TO PARTS.
# This is what makes them visible in task column.
# ============================================================

def add_orders(
    payload,
    side,
    resolved,
):
    parts = payload.get(
        "parts"
    )

    if (
        isinstance(
            parts,
            list,
        )
        and parts
    ):
        # Remove only previous auto-generated Order parts.
        parts[:] = [
            part

            for part in parts

            if not (
                isinstance(
                    part,
                    dict,
                )
                and str(
                    part.get(
                        "id",
                        "",
                    )
                ).startswith(
                    f"atlas_order_{side}_"
                )
            )
        ]

        max_order = max(
            [
                int(
                    part.get(
                        "order"
                    )
                    or 0
                )

                for part in parts

                if isinstance(
                    part,
                    dict,
                )
            ]
            or [0]
        )

        # Sorted by ORDER NAME.
        for index, order_name in enumerate(
            sorted(
                resolved,
                key=normalize_text,
            ),
            1,
        ):
            part_id = (
                f"atlas_order_"
                f"{side}_"
                f"{index}"
            )

            quest_ids = (
                resolved[
                    order_name
                ]
            )

            parts.append(
                {
                    "id": part_id,
                    "title": order_name,

                    # AFTER everything already present,
                    # therefore after alignment 100.
                    "order": (
                        max_order
                        + index
                    ),

                    "type": "quest_category",

                    "progress_mode": "quests",

                    "optional_branch": True,

                    "exclusive_group": (
                        f"alignement_"
                        f"{side}_ordres"
                    ),

                    "chapters": [
                        {
                            "id": (
                                part_id
                                + "_chapter"
                            ),

                            "title": order_name,

                            "order": 1,

                            "series": [
                                make_series(
                                    part_id
                                    + "_series",

                                    order_name,

                                    quest_ids,

                                    1,

                                    True,
                                )
                            ],
                        }
                    ],
                }
            )

        return

    # Legacy guide without parts.
    sections = payload.setdefault(
        "sections",
        [],
    )

    if not isinstance(
        sections,
        list,
    ):
        raise RuntimeError(
            f"{payload.get('id')}: "
            "structure invalide"
        )

    sections[:] = [
        section

        for section
        in sections

        if not (
            isinstance(
                section,
                dict,
            )
            and str(
                section.get(
                    "id",
                    "",
                )
            ).startswith(
                f"atlas_order_{side}_"
            )
        )
    ]

    for index, order_name in enumerate(
        sorted(
            resolved,
            key=normalize_text,
        ),
        1,
    ):
        previous = None
        rows = []

        for quest_id in (
            resolved[
                order_name
            ]
        ):
            rows.append(
                make_step(
                    (
                        f"atlas_order_"
                        f"{side}_"
                        f"{index}"
                    ),
                    quest_id,
                    previous,
                    True,
                )
            )

            previous = (
                quest_id
            )

        sections.append(
            {
                "id": (
                    f"atlas_order_"
                    f"{side}_"
                    f"{index}"
                ),

                "title": order_name,

                "description": "",

                "optional_branch": True,

                "exclusive_group": (
                    f"alignement_"
                    f"{side}_ordres"
                ),

                "steps": rows,
            }
        )


# ============================================================
# DOFUS - ADD MISSING REQUIRED QUESTS
# ============================================================

def add_missing_dofus_quests(
    payload,
    required,
):
    parts = payload.get(
        "parts"
    )

    sections = payload.get(
        "sections"
    )

    # Idempotent:
    # remove only the part generated by THIS script.
    if isinstance(
        parts,
        list,
    ):
        parts[:] = [
            part

            for part
            in parts

            if not (
                isinstance(
                    part,
                    dict,
                )
                and part.get(
                    "id"
                )
                == "atlas_required_prerequisites"
            )
        ]

    if isinstance(
        sections,
        list,
    ):
        sections[:] = [
            section

            for section
            in sections

            if not (
                isinstance(
                    section,
                    dict,
                )
                and section.get(
                    "id"
                )
                == "atlas_required_prerequisites"
            )
        ]

    current = set(
        ids_in(
            payload
        )
    )

    missing = [
        quest_id

        for quest_id
        in required

        if quest_id
        not in current
    ]

    if not missing:
        return 0

    # --------------------------------------------------------
    # MODERN STRUCTURE -> parts
    # --------------------------------------------------------

    if (
        isinstance(
            parts,
            list,
        )
        and parts
    ):
        minimum_order = min(
            [
                int(
                    part.get(
                        "order"
                    )
                    or 0
                )

                for part in parts

                if isinstance(
                    part,
                    dict,
                )
            ]
            or [1]
        )

        # Put required prerequisites BEFORE main Dofus series.
        parts.insert(
            0,
            {
                "id": (
                    "atlas_required_prerequisites"
                ),

                "title": (
                    "Prérequis obligatoires"
                ),

                "order": (
                    minimum_order
                    - 1000
                ),

                "type": "quest_category",

                "progress_mode": "quests",

                "chapters": [
                    {
                        "id": (
                            "atlas_required_chapter"
                        ),

                        "title": (
                            "Prérequis obligatoires"
                        ),

                        "order": 1,

                        "series": [
                            make_series(
                                "atlas_required_series",
                                "Prérequis obligatoires",
                                missing,
                            )
                        ],
                    }
                ],
            },
        )

    # --------------------------------------------------------
    # LEGACY STRUCTURE -> sections
    # --------------------------------------------------------

    else:
        if not isinstance(
            sections,
            list,
        ):
            sections = []

            payload[
                "sections"
            ] = sections

        previous = None
        rows = []

        for quest_id in (
            missing
        ):
            rows.append(
                make_step(
                    "atlas_required",
                    quest_id,
                    previous,
                )
            )

            previous = (
                quest_id
            )

        sections.insert(
            0,
            {
                "id": (
                    "atlas_required_prerequisites"
                ),

                "title": (
                    "Prérequis obligatoires"
                ),

                "description": "",

                "steps": rows,
            },
        )

    return len(
        missing
    )


# ============================================================
# DISCOVER LIVE GUIDES
# ============================================================

def find_files():
    dofus = {}
    alignment = {}

    for path in sorted(
        GUIDES.glob(
            "*.json"
        )
    ):
        if path.name in {
            "catalog.json",
            "manifest.json",
        }:
            continue

        try:
            payload = read(
                path
            )

        except Exception:
            continue

        category = normalize_text(
            payload.get(
                "category"
            )
            or ""
        )

        identity = normalize_text(
            f"{payload.get('id', '')} "
            f"{payload.get('title', '')} "
            f"{path.stem}"
        )

        if category == "dofus":
            key = normalize_text(
                payload.get(
                    "id"
                )
                or path.stem
            )

            dofus[
                key
            ] = (
                path,
                payload,
            )

        elif category in {
            "alignement",
            "alignements",
        }:
            if (
                "bonta"
                in identity
            ):
                alignment[
                    "bonta"
                ] = (
                    path,
                    payload,
                )

            elif (
                "brakmar"
                in identity
            ):
                alignment[
                    "brakmar"
                ] = (
                    path,
                    payload,
                )

    return (
        dofus,
        alignment,
    )


# ============================================================
# MAIN
# ============================================================

def main():
    dofus_guides, alignment_guides = (
        find_files()
    )

    if not dofus_guides:
        raise SystemExit(
            "Aucun guide Dofus trouvé."
        )

    if set(
        alignment_guides
    ) != {
        "bonta",
        "brakmar",
    }:
        raise SystemExit(
            "Guides d'alignement incomplets : "
            f"{sorted(alignment_guides)}"
        )


    # ========================================================
    # 1. RESOLVE ALL 30 ORDER QUESTS
    # BEFORE WRITING ANYTHING
    # ========================================================

    resolved = {
        "bonta": {},
        "brakmar": {},
    }

    for side in (
        "bonta",
        "brakmar",
    ):
        for order_name in sorted(
            ORDERS[
                side
            ],
            key=normalize_text,
        ):
            quest_ids = [
                int(
                    resolve_quest(
                        quest_name
                    ).id
                )

                for quest_name
                in ORDERS[
                    side
                ][
                    order_name
                ]
            ]

            if (
                len(
                    quest_ids
                )
                != 5
                or len(
                    set(
                        quest_ids
                    )
                )
                != 5
            ):
                raise RuntimeError(
                    f"{side} / "
                    f"{order_name}: "
                    f"{quest_ids}"
                )

            resolved[
                side
            ][
                order_name
            ] = quest_ids


    all_order_ids = [
        quest_id

        for side_rows
        in resolved.values()

        for quest_ids
        in side_rows.values()

        for quest_id
        in quest_ids
    ]

    if (
        len(all_order_ids)
        != 30
        or len(
            set(
                all_order_ids
            )
        )
        != 30
    ):
        raise RuntimeError(
            "Les 30 quêtes d'Ordre "
            "ne sont pas uniques."
        )


    # ========================================================
    # 2. BUILD EVERYTHING IN MEMORY
    # ========================================================

    planned = {}

    report = {
        "orders": {},
        "dofus": {},
    }


    # --------------------------------------------------------
    # ALIGNMENTS
    # --------------------------------------------------------

    for side, (
        path,
        original,
    ) in (
        alignment_guides.items()
    ):
        payload = json.loads(
            json.dumps(
                original,
                ensure_ascii=False,
            )
        )

        before = len(
            set(
                ids_in(
                    payload
                )
            )
        )

        add_orders(
            payload,
            side,
            resolved[
                side
            ],
        )

        after_ids = set(
            ids_in(
                payload
            )
        )

        expected = {
            quest_id

            for quest_ids
            in resolved[
                side
            ].values()

            for quest_id
            in quest_ids
        }

        if not expected.issubset(
            after_ids
        ):
            raise RuntimeError(
                f"{side}: "
                "quêtes Ordre absentes : "
                f"{sorted(expected - after_ids)}"
            )

        planned[
            path
        ] = payload

        report[
            "orders"
        ][
            side
        ] = {
            "before": before,
            "after": len(
                after_ids
            ),
            "ids": sorted(
                expected
            ),
        }


    # --------------------------------------------------------
    # ALL DOFUS GUIDES
    # --------------------------------------------------------

    for key, (
        path,
        original,
    ) in sorted(
        dofus_guides.items()
    ):
        payload = json.loads(
            json.dumps(
                original,
                ensure_ascii=False,
            )
        )

        before = len(
            set(
                ids_in(
                    payload
                )
            )
        )

        required = (
            resolve_closure(
                payload,
                key,
            )
        )

        detected_total = len(
            set(required)
            | set(
                ids_in(
                    payload
                )
            )
        )

        added = (
            add_missing_dofus_quests(
                payload,
                required,
            )
        )

        after = len(
            set(
                ids_in(
                    payload
                )
            )
        )

        minimum = (
            MINIMUMS.get(
                key
            )
        )

        control_ok = (
            minimum is None
            or detected_total
            >= minimum
        )


        # Remove old audit warning.
        warnings = payload.get(
            "validation_warnings"
        )

        if not isinstance(
            warnings,
            list,
        ):
            warnings = []

        warnings = [
            warning

            for warning
            in warnings

            if not str(
                warning
            ).startswith(
                "AUDIT PREREQUIS:"
            )
        ]


        if not control_ok:
            warnings.append(
                "AUDIT PREREQUIS: "
                f"{detected_total} détectées, "
                f"minimum de contrôle {minimum}; "
                "guide encore partiel."
            )

            payload[
                "completeness_status"
            ] = "partial"

        elif minimum is not None:
            payload[
                "completeness_status"
            ] = "complete"


        payload[
            "validation_warnings"
        ] = warnings

        payload[
            "verified_steps"
        ] = after

        payload[
            "total_steps"
        ] = after


        planned[
            path
        ] = payload


        report[
            "dofus"
        ][
            key
        ] = {
            "title": payload.get(
                "title"
            ),

            "before": before,

            "added": added,

            "after": after,

            "detected": (
                detected_total
            ),

            "minimum": (
                minimum
            ),

            "status": (
                "OK"
                if control_ok
                else "PARTIEL"
            ),
        }


    # ========================================================
    # 3. BACKUP EVERYTHING
    # ========================================================

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = (
        ART
        / (
            "guide_content_backup_"
            + stamp
        )
    )

    backup.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in planned:
        shutil.copy2(
            path,
            backup
            / path.name,
        )


    # ========================================================
    # 4. WRITE
    # ========================================================

    try:
        for path, payload in (
            planned.items()
        ):
            write(
                path,
                payload,
            )


        # ====================================================
        # 5. VALIDATE THROUGH REAL APP PROVIDER
        # ====================================================

        live_guides = (
            GuideProvider()
            .load_all()
        )

        live_by_id = {
            str(
                guide.id
            ):
            guide

            for guide
            in live_guides
        }


        # ----------------------------------------------------
        # ORDERS MUST REALLY EXIST IN guide.parts
        # ----------------------------------------------------

        for side, (
            path,
            original,
        ) in (
            alignment_guides.items()
        ):
            guide_id = str(
                original.get(
                    "id"
                )
                or path.stem
            )

            guide = (
                live_by_id.get(
                    guide_id
                )
            )

            if guide is None:
                raise RuntimeError(
                    f"{guide_id}: "
                    "guide non chargé"
                )


            expected = {
                quest_id

                for quest_ids
                in resolved[
                    side
                ].values()

                for quest_id
                in quest_ids
            }


            visible_ids = set(
                map(
                    int,
                    guide.quest_ids,
                )
            )


            if not expected.issubset(
                visible_ids
            ):
                raise RuntimeError(
                    f"{guide_id}: "
                    "IDs d'Ordre invisibles : "
                    f"{sorted(expected - visible_ids)}"
                )


            # THIS is the important visual check.
            # The current guide UI iterates guide.parts.
            titles = {
                normalize_text(
                    part.title
                )

                for part
                in guide.parts
            }


            for order_name in (
                resolved[
                    side
                ]
            ):
                if (
                    normalize_text(
                        order_name
                    )
                    not in titles
                ):
                    raise RuntimeError(
                        f"{guide_id}: "
                        "tâche d'Ordre invisible : "
                        f"{order_name}"
                    )


        # ----------------------------------------------------
        # DOFUS ADDED QUESTS MUST REALLY BE IN guide.quest_ids
        # ----------------------------------------------------

        for key, (
            path,
            original,
        ) in (
            dofus_guides.items()
        ):
            guide_id = str(
                original.get(
                    "id"
                )
                or path.stem
            )

            guide = (
                live_by_id.get(
                    guide_id
                )
            )

            if guide is None:
                raise RuntimeError(
                    f"{guide_id}: "
                    "guide non chargé"
                )


            expected = set(
                ids_in(
                    planned[
                        path
                    ]
                )
            )


            visible = set(
                map(
                    int,
                    guide.quest_ids,
                )
            )


            missing = (
                expected
                - visible
            )


            if missing:
                raise RuntimeError(
                    f"{guide_id}: "
                    f"{len(missing)} "
                    "quêtes ajoutées sont "
                    "invisibles dans GuideProvider"
                )


    # ========================================================
    # ANY PROBLEM => RESTORE ALL GUIDES
    # ========================================================

    except Exception:
        for path in planned:
            saved = (
                backup
                / path.name
            )

            if saved.exists():
                shutil.copy2(
                    saved,
                    path,
                )

        print()
        print(
            "ERREUR -> "
            "ROLLBACK COMPLET EFFECTUÉ."
        )

        raise


    # ========================================================
    # 6. REPORT
    # ========================================================

    ART.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = (
        ART
        / (
            "guide_content_repair_"
            + stamp
            + ".json"
        )
    )

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    # ========================================================
    # RESULT
    # ========================================================

    print()

    print(
        "=" * 94
    )

    print(
        "GUIDES REPARÉS - "
        "VALIDATION VIA LE VRAI GuideProvider"
    )

    print(
        "=" * 94
    )


    for side in (
        "bonta",
        "brakmar",
    ):
        row = report[
            "orders"
        ][
            side
        ]

        print(
            f"{side.upper():10} "
            f"{row['before']:>4} "
            f"-> "
            f"{row['after']:>4} "
            "| +15 quêtes d'Ordre "
            "| TÂCHES VISIBLES: OK"
        )


    print(
        "-" * 94
    )


    print(
        f"{'GUIDE':32} "
        f"{'AVANT':>7} "
        f"{'AJOUT':>7} "
        f"{'APRES':>7} "
        f"{'MIN':>7}  "
        "ETAT"
    )


    for key, row in sorted(
        report[
            "dofus"
        ].items()
    ):
        title = str(
            row[
                "title"
            ]
            or key
        )[:31]

        minimum = (
            row[
                "minimum"
            ]
            if row[
                "minimum"
            ]
            is not None
            else "-"
        )

        print(
            f"{title:32} "
            f"{row['before']:>7} "
            f"{row['added']:>7} "
            f"{row['after']:>7} "
            f"{str(minimum):>7}  "
            f"{row['status']}"
        )


    print(
        "=" * 94
    )

    print(
        "Backup :",
        backup,
    )

    print(
        "Rapport:",
        report_path,
    )

    print(
        "=" * 94
    )


if __name__ == "__main__":
    main()
