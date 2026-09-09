from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.modules.encyclopedia.services.adventure_route_engine import (
    ItemRequirement,
    RouteAction,
    RouteCondition,
    RouteLocation,
)
from tools.guide_ultime_scope_v5 import mandatory_qf_ids, residual_qf_alternatives


QF_RE = re.compile(r"\bQf\s*=\s*(\d+)", re.IGNORECASE)
PL_RE = re.compile(r"\bPL\s*>\s*(\d+)", re.IGNORECASE)
PS_RE = re.compile(r"\bPs\s*=\s*(\d+)", re.IGNORECASE)
PA_RE = re.compile(r"\bPa\s*=\s*(\d+)", re.IGNORECASE)
CRITERION_CODE_RE = re.compile(
    r"\b([A-Za-z]{1,5})\s*(?:!=|>=|<=|=|>|<)\s*(?:-?\d+|[A-Za-z_]+)",
    re.IGNORECASE,
)
COORD_RE = re.compile(r"\[(-?\d+)\s*,\s*(-?\d+)\]")

KNOWN_CRITERION_CODES = {
    "bt", "pl", "qf", "qa", "sc", "ps", "pa", "pr", "qq", "bi", "ea",
}

# These codes are real game gates/state checks. V5 does not pretend to
# auto-validate them; it surfaces the exact raw criterion on the route card.
# Only a code outside BOTH sets remains an unresolved hard criterion.
RUNTIME_GATE_CODES = {
    "ad", "qo", "po", "pz", "qc", "pg", "pj", "pm", "st",
    "dd", "oa", "we", "dh", "dm", "sv", "ha", "sh", "ei", "em",
}

COMBAT_OBJECTIVE_TYPES = {6, 7}
NPC_OBJECTIVE_TYPES = {1, 2, 3, 9, 10}
ITEM_OBJECTIVE_TYPES = {2, 3, 8, 17}

CLASS_QUESTS = {
    "cra": "C'est pour ta pomme",
    "ecaflip": "Au petit malheur la chance",
    "eliotrope": "Un rayon de soleil",
    "eniripsa": "Piques de solution",
    "enutrof": "La fête de la chocopépite",
    "feca": "Tournée d'inspection",
    "forgelance": "La routine anodine du chevalier citadin",
    "huppermage": "Les paroles s'envolent, les aigris restent",
    "iop": "Iop et hop",
    "ouginak": "Une vie de milichien",
    "osamodas": "Série animalière",
    "pandawa": "Trempette dans un verre d'eau",
    "roublard": "Braquage à la Roublard",
    "sacrieur": "Souffre-douleur",
    "sadida": "C'est pourtant naturel",
    "sram": "Crime et châtiment",
    "steamer": "L'étrange créature de l'étang bleu",
    "xelor": "Tarot, t'es très fort",
    "zobal": "Zobal Hibaba et les 40 Roublards",
}

ORDER_QUESTS: dict[str, dict[str, tuple[str, ...]]] = {
    "bonta": {
        "coeur vaillant": (
            "Disciple de Ménalt",
            "Écuyer",
            "Chevalier de l'Espoir",
            "Champion Merveilleux",
            "Héros Légendaire",
        ),
        "oeil attentif": (
            "Disciple de Silvosse",
            "Espion silencieux",
            "Chasseur de Renégats",
            "Assassin Suprême",
            "Maître des Illusions",
        ),
        "esprit salvateur": (
            "Disciple de Jiva",
            "Apprenti Éclairé",
            "Adepte des Écrits",
            "Maître des Parchemins",
            "Gardien du Savoir",
        ),
    },
    "brakmar": {
        "coeur saignant": (
            "Disciple de Djaul",
            "Surineur",
            "Chevalier du Désespoir",
            "Champion du Chaos",
            "Héros de l'Apocalypse",
        ),
        "oeil putride": (
            "Disciple de Brumaire",
            "Espion Sombre",
            "Chasseur d'Âmes",
            "Psychopathe",
            "Maître des Ombres",
        ),
        "esprit malsain": (
            "Disciple d'Hécate",
            "Apprenti Sombre",
            "Adepte des Douleurs",
            "Maître des Sévices",
            "Gardien des Tortures",
        ),
    },
}
ORDER_LEVELS = (20, 40, 60, 80, 100)


def _norm(value: object) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z0-9]+", " ", text.casefold()).strip()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _array(value: Any) -> list[Any]:
    if isinstance(value, dict):
        inner = value.get("Array", [])
        return inner if isinstance(inner, list) else []
    return value if isinstance(value, list) else []


def _doduda_rows(path: Path) -> dict[int, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    refs = payload.get("references", {}).get("RefIds", []) if isinstance(payload, dict) else []
    result: dict[int, dict[str, Any]] = {}
    for ref in refs:
        data = ref.get("data") if isinstance(ref, dict) else None
        if not isinstance(data, dict):
            continue
        ident = _safe_int(data.get("id"))
        if ident is not None:
            result[ident] = data
    return result


@dataclass(frozen=True, slots=True)
class AdapterWarning:
    quest_id: int
    code: str
    message: str
    criterion: str = ""
    criterion_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AdventureRouteAdapterResult:
    actions: tuple[RouteAction, ...]
    warnings: tuple[AdapterWarning, ...]
    quest_ids: tuple[int, ...]


class AdventureRouteAdapter:
    """Normalize the existing guide + local quest catalog into RouteAction rows.

    Important: this adapter deliberately ignores visual prerequisites injected by
    GuideCatalogBuilder. Hard quest dependencies come from startCriterion Qf only.
    """

    def __init__(
        self,
        quest_catalog: Any,
        guide: Any,
        *,
        achievement_provider: Any = None,
        raw_data_dir: Path | None = None,
        preparation_overrides: Mapping[int, Iterable[ItemRequirement]] | None = None,
        before_leaving_objective_ids: Iterable[int] = (),
    ) -> None:
        self.catalog = quest_catalog
        self.guide = guide
        self.achievement_provider = achievement_provider
        loaded_from = getattr(quest_catalog, "loaded_from", None)
        self.raw_data_dir = Path(raw_data_dir or loaded_from) if (raw_data_dir or loaded_from) else None
        self.preparation_overrides = {
            int(quest_id): tuple(items)
            for quest_id, items in (preparation_overrides or {}).items()
        }
        self.before_leaving_objective_ids = {
            int(value) for value in before_leaving_objective_ids
        }
        self.raw_quests: dict[int, dict[str, Any]] = {}
        self.raw_objectives: dict[int, dict[str, Any]] = {}
        self.raw_maps: dict[int, dict[str, Any]] = {}
        self._load_raw()

    def _load_raw(self) -> None:
        if self.raw_data_dir is None:
            return
        self.raw_quests = _doduda_rows(self.raw_data_dir / "quests.json")
        self.raw_objectives = _doduda_rows(self.raw_data_dir / "quest_objectives.json")
        self.raw_maps = _doduda_rows(self.raw_data_dir / "maps_information.json")

    def build(self) -> AdventureRouteAdapterResult:
        warnings: list[AdapterWarning] = []
        actions: list[RouteAction] = []
        quest_ids = tuple(dict.fromkeys(int(value) for value in getattr(self.guide, "quest_ids", ())))

        for quest_order, quest_id in enumerate(quest_ids):
            quest = self.catalog.by_id.get(quest_id)
            if quest is None:
                warnings.append(AdapterWarning(
                    quest_id, "missing_quest", "Quête absente du catalogue local."
                ))
                continue

            condition, condition_warnings = self._condition_for_quest(quest)
            warnings.extend(condition_warnings)
            criterion = str(getattr(quest, "start_criterion", "") or "")
            real_prerequisites = frozenset(int(value) for value in mandatory_qf_ids(criterion))
            alternative_prerequisites = tuple(
                frozenset(int(value) for value in group)
                for group in residual_qf_alternatives(criterion)
                if group
            )

            start_location = self._start_location(quest_id)
            if start_location.key[0] == "unknown":
                warnings.append(AdapterWarning(
                    quest_id,
                    "unknown_start_location",
                    "Départ de quête non localisable de façon unique ; aucune optimisation de prise ne sera inventée.",
                ))

            start_id = f"quest:{quest_id}:start"
            actions.append(RouteAction(
                action_id=start_id,
                quest_id=quest_id,
                title=f"Prendre — {quest.name}",
                kind="start",
                location=start_location,
                quest_order=quest_order,
                objective_order=-1,
                prerequisites_quests=real_prerequisites,
                prerequisite_quest_alternatives=alternative_prerequisites,
                condition=condition,
                requires_active_quest=False,
                activates_quest=True,
                success_ids=self._success_ids(quest_id),
            ))

            previous_layer = frozenset({start_id})
            quest_steps = list(getattr(quest, "steps", ()) or ())
            last_layer: frozenset[str] = frozenset()
            for step_index, quest_step in enumerate(quest_steps):
                layer: list[str] = []
                for objective_index, objective in enumerate(
                    list(getattr(quest_step, "objectives", ()) or ())
                ):
                    action = self._objective_action(
                        quest=quest,
                        quest_id=quest_id,
                        quest_order=quest_order,
                        step_index=step_index,
                        objective_index=objective_index,
                        objective=objective,
                        prerequisites_actions=previous_layer,
                        condition=condition,
                    )
                    actions.append(action)
                    layer.append(action.action_id)
                if layer:
                    previous_layer = frozenset(layer)
                    last_layer = previous_layer

            # Quest completion is represented by a group barrier on the last real
            # objective layer. It does not impose an artificial order between
            # objectives of the same quest step.
            if last_layer:
                group = f"quest:{quest_id}:completion"
                actions = [
                    action if action.action_id not in last_layer
                    else RouteAction(
                        **{
                            field_name: getattr(action, field_name)
                            for field_name in action.__dataclass_fields__
                            if field_name != "completion_group"
                        },
                        completion_group=group,
                    )
                    for action in actions
                ]
            else:
                # A quest with no locally exposed objective cannot safely be
                # auto-completed from the route model.
                warnings.append(AdapterWarning(
                    quest_id,
                    "no_objectives",
                    "Aucun objectif local ; la quête reste pilotée par la progression partagée.",
                ))

        return AdventureRouteAdapterResult(
            actions=tuple(actions),
            warnings=tuple(warnings),
            quest_ids=quest_ids,
        )

    def _condition_for_quest(self, quest: Any) -> tuple[RouteCondition, list[AdapterWarning]]:
        warnings: list[AdapterWarning] = []
        criterion = str(getattr(quest, "start_criterion", "") or "")
        classes: set[str] = set()
        alignments: set[str] = set()
        orders: set[str] = set()
        required_flags: set[str] = set()

        quest_name = _norm(getattr(quest, "name", ""))
        for class_name, class_quest_name in CLASS_QUESTS.items():
            if quest_name == _norm(class_quest_name):
                classes.add(class_name)
                break

        order_level: int | None = None
        for side, side_orders in ORDER_QUESTS.items():
            for order_name, names in side_orders.items():
                for rank_index, name in enumerate(names):
                    if quest_name == _norm(name):
                        alignments.add(side)
                        orders.add(order_name)
                        order_level = ORDER_LEVELS[rank_index]
                        break

        ps_match = PS_RE.search(criterion)
        if ps_match:
            value = int(ps_match.group(1))
            if value == 1:
                alignments.add("bonta")
            elif value == 2:
                alignments.add("brakmar")

        level = int(getattr(quest, "level_min", 0) or 0)
        pl_match = PL_RE.search(criterion)
        if pl_match:
            level = max(level, int(pl_match.group(1)) + 1)

        # Pa is preserved as a hard alignment progression threshold when present.
        # Values in the local alignment chain are zero-based before the next rank.
        pa_match = PA_RE.search(criterion)
        pa_level = int(pa_match.group(1)) + 1 if pa_match else None
        min_alignment_level = max(
            [value for value in (order_level, pa_level) if value is not None],
            default=None,
        )

        all_extra_codes = {
            _norm(code)
            for code in CRITERION_CODE_RE.findall(criterion)
            if _norm(code) not in KNOWN_CRITERION_CODES
        }
        runtime_codes = sorted(all_extra_codes & RUNTIME_GATE_CODES)
        unknown_codes = sorted(all_extra_codes - RUNTIME_GATE_CODES)

        if runtime_codes:
            warnings.append(AdapterWarning(
                int(quest.id),
                "runtime_gate_criterion",
                "Gate de jeu à respecter sur la carte; V5 conserve le critère brut et ne le valide pas artificiellement: "
                + ", ".join(runtime_codes),
                criterion=criterion,
                criterion_codes=tuple(runtime_codes),
            ))

        if unknown_codes:
            flag = f"criterion-verified:{int(quest.id)}"
            required_flags.add(flag)
            warnings.append(AdapterWarning(
                int(quest.id),
                "unresolved_hard_criterion",
                "Critère(s) réellement inconnu(s) "
                + ", ".join(unknown_codes)
                + f" ; action bloquée tant que le flag {flag!r} n'est pas validé.",
                criterion=criterion,
                criterion_codes=tuple(unknown_codes),
            ))

        return RouteCondition(
            min_level=level or None,
            classes=frozenset(classes),
            alignments=frozenset(alignments),
            orders=frozenset(orders),
            min_alignment_level=min_alignment_level,
            required_flags=frozenset(required_flags),
        ), warnings

    def _success_ids(self, quest_id: int) -> frozenset[int]:
        if self.achievement_provider is None:
            return frozenset()
        values = set()
        try:
            achievements = self.achievement_provider.get_by_quest(int(quest_id))
        except Exception:
            achievements = ()
        for achievement in achievements or ():
            ident = _safe_int(getattr(achievement, "id", None))
            if ident is not None:
                values.add(ident)
        return frozenset(values)

    def _start_location(self, quest_id: int) -> RouteLocation:
        raw = self.raw_quests.get(int(quest_id), {})
        map_ids = []
        for row in _array(raw.get("startPosition")):
            if not isinstance(row, dict):
                continue
            ident = _safe_int(row.get("mapId"))
            if ident is not None and ident not in map_ids:
                map_ids.append(ident)
        if len(map_ids) == 1:
            return self._location_from_map(map_ids[0], None, zone="")
        return RouteLocation(label="Départ de quête à confirmer")

    def _location_from_map(
        self,
        map_id: int | None,
        coords: Mapping[str, Any] | None,
        *,
        zone: str,
        fallback_label: str = "",
    ) -> RouteLocation:
        x = _safe_int(coords.get("x")) if isinstance(coords, Mapping) else None
        y = _safe_int(coords.get("y")) if isinstance(coords, Mapping) else None
        row = self.raw_maps.get(int(map_id), {}) if map_id is not None else {}
        if x is None:
            x = _safe_int(row.get("posX"))
        if y is None:
            y = _safe_int(row.get("posY"))
        label = f"[{x},{y}]" if x is not None and y is not None else fallback_label
        return RouteLocation(
            map_id=map_id,
            x=x,
            y=y,
            zone=zone,
            label=label,
        )

    def _objective_action(
        self,
        *,
        quest: Any,
        quest_id: int,
        quest_order: int,
        step_index: int,
        objective_index: int,
        objective: Any,
        prerequisites_actions: frozenset[str],
        condition: RouteCondition,
    ) -> RouteAction:
        objective_id = int(getattr(objective, "id", 0) or 0)
        raw = self.raw_objectives.get(objective_id, {})
        type_id = int(getattr(objective, "type_id", 0) or 0)
        params = raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {}
        values = tuple(params.get(f"parameter{index}", 0) for index in range(5))
        raw_map_id = _safe_int(raw.get("mapId"))
        map_id = raw_map_id

        zone = str(getattr(objective, "zone", "") or "")
        fallback_label = str(getattr(objective, "map_label", "") or "")
        coords = raw.get("coords") if isinstance(raw.get("coords"), dict) else None
        if map_id is not None:
            location = self._location_from_map(
                map_id, coords, zone=zone, fallback_label=fallback_label
            )
        else:
            match = COORD_RE.search(fallback_label)
            location = RouteLocation(
                x=int(match.group(1)) if match else None,
                y=int(match.group(2)) if match else None,
                zone=zone,
                label=fallback_label,
            )

        if type_id in COMBAT_OBJECTIVE_TYPES:
            kind = "combat"
        elif type_id in NPC_OBJECTIVE_TYPES:
            kind = "dialogue"
        elif type_id in ITEM_OBJECTIVE_TYPES or type_id == 5:
            kind = "interaction"
        else:
            kind = "interaction"

        monster_ids = frozenset(
            {value}
            if type_id in COMBAT_OBJECTIVE_TYPES
            and (value := _safe_int(values[0])) is not None
            else set()
        )
        monster_names = ()
        image_label = str(getattr(objective, "image_label", "") or "")
        if monster_ids and image_label:
            monster_names = (image_label,)

        item_requirements: list[ItemRequirement] = []
        item_id = _safe_int(getattr(objective, "item_id", None))
        if item_id is not None:
            item_requirements.append(ItemRequirement(
                item_id=item_id,
                name=image_label or str(getattr(objective, "text", "") or f"Objet {item_id}"),
                quantity=max(1, int(getattr(objective, "item_quantity", 0) or 1)),
                preparation=False,
            ))
        item_requirements.extend(self.preparation_overrides.get(quest_id, ()))

        action_id = f"quest:{quest_id}:objective:{objective_id or step_index * 1000 + objective_index}"
        return RouteAction(
            action_id=action_id,
            quest_id=quest_id,
            title=str(getattr(objective, "text", "") or f"Objectif {objective_id}"),
            kind=kind,
            location=location,
            quest_order=quest_order,
            objective_order=step_index * 1000 + objective_index,
            objective_id=objective_id or None,
            prerequisites_actions=prerequisites_actions,
            condition=condition,
            requires_active_quest=True,
            monster_ids=monster_ids,
            monster_names=monster_names,
            item_requirements=tuple(item_requirements),
            success_ids=self._success_ids(quest_id),
            before_leaving_area=objective_id in self.before_leaving_objective_ids,
        )
