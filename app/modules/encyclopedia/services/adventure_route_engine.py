from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from math import hypot
from typing import Iterable, Mapping, Sequence


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


@dataclass(frozen=True, slots=True)
class RouteLocation:
    """Stable geographical identity used by the optimizer.

    map_id is preferred when available. Coordinates are the next-best identity.
    zone/subzone remain useful when exact map information is missing.
    """

    map_id: int | None = None
    x: int | None = None
    y: int | None = None
    zone: str = ""
    subzone: str = ""
    label: str = ""

    @property
    def key(self) -> tuple[object, ...]:
        if self.map_id is not None:
            return ("map", int(self.map_id))
        if self.x is not None and self.y is not None:
            return ("coord", int(self.x), int(self.y), _norm(self.zone))
        if self.subzone:
            return ("subzone", _norm(self.zone), _norm(self.subzone))
        if self.zone:
            return ("zone", _norm(self.zone))
        return ("unknown", self.label)

    @property
    def zone_key(self) -> str:
        return _norm(self.zone)

    @property
    def subzone_key(self) -> tuple[str, str]:
        return (_norm(self.zone), _norm(self.subzone))

    def same_map(self, other: "RouteLocation | None") -> bool:
        if other is None:
            return False
        if self.map_id is not None and other.map_id is not None:
            return int(self.map_id) == int(other.map_id)
        if (
            self.x is not None
            and self.y is not None
            and other.x is not None
            and other.y is not None
        ):
            return (
                int(self.x),
                int(self.y),
                self.zone_key,
            ) == (
                int(other.x),
                int(other.y),
                other.zone_key,
            )
        return self.key == other.key and self.key[0] != "unknown"

    def display(self) -> str:
        if self.label:
            return self.label
        if self.x is not None and self.y is not None:
            suffix = f" — {self.subzone or self.zone}" if (self.subzone or self.zone) else ""
            return f"[{self.x},{self.y}]{suffix}"
        return self.subzone or self.zone or "Localisation à confirmer"


@dataclass(frozen=True, slots=True)
class RouteCondition:
    min_level: int | None = None
    max_level: int | None = None
    classes: frozenset[str] = frozenset()
    alignments: frozenset[str] = frozenset()
    orders: frozenset[str] = frozenset()
    min_alignment_level: int | None = None
    max_alignment_level: int | None = None
    required_flags: frozenset[str] = frozenset()

    def matches(self, profile: "RouteProfile") -> bool:
        if self.min_level is not None and profile.level < self.min_level:
            return False
        if self.max_level is not None and profile.level > self.max_level:
            return False
        if self.classes and _norm(profile.character_class) not in {_norm(v) for v in self.classes}:
            return False
        if self.alignments and _norm(profile.alignment) not in {_norm(v) for v in self.alignments}:
            return False
        if self.orders and _norm(profile.order) not in {_norm(v) for v in self.orders}:
            return False
        if self.min_alignment_level is not None and profile.alignment_level < self.min_alignment_level:
            return False
        if self.max_alignment_level is not None and profile.alignment_level > self.max_alignment_level:
            return False
        if self.required_flags and not self.required_flags.issubset(profile.flags):
            return False
        return True


@dataclass(frozen=True, slots=True)
class ItemRequirement:
    item_id: int | None
    name: str
    quantity: int = 1
    preparation: bool = False

    def normalized(self) -> "ItemRequirement":
        return replace(self, quantity=max(1, int(self.quantity or 1)))


@dataclass(frozen=True, slots=True)
class RouteAction:
    """One atomic game action.

    A quest may own many RouteAction objects. Dependencies are expressed with
    real quest IDs and action IDs, never by visual order.
    """

    action_id: str
    quest_id: int
    title: str
    kind: str
    location: RouteLocation = RouteLocation()
    quest_order: int = 0
    objective_order: int = 0
    objective_id: int | None = None
    prerequisites_quests: frozenset[int] = frozenset()
    prerequisite_quest_alternatives: tuple[frozenset[int], ...] = ()
    prerequisites_actions: frozenset[str] = frozenset()
    condition: RouteCondition = RouteCondition()
    requires_active_quest: bool = True
    activates_quest: bool = False
    completes_quest: bool = False
    completion_group: str = ""
    dungeon_id: int | str | None = None
    dungeon_name: str = ""
    monster_ids: frozenset[int] = frozenset()
    monster_names: tuple[str, ...] = ()
    item_requirements: tuple[ItemRequirement, ...] = ()
    success_ids: frozenset[int] = frozenset()
    before_leaving_area: bool = False
    mandatory: bool = True
    notes: str = ""

    @property
    def is_start(self) -> bool:
        return self.kind == "start" or self.activates_quest

    @property
    def is_dungeon(self) -> bool:
        return self.kind == "dungeon" or self.dungeon_id is not None

    @property
    def is_combat(self) -> bool:
        return self.kind == "combat" or bool(self.monster_ids)


@dataclass(frozen=True, slots=True)
class RouteProfile:
    level: int = 1
    character_class: str = ""
    alignment: str = "neutre"
    alignment_level: int = 0
    order: str = ""
    flags: frozenset[str] = frozenset()


@dataclass(slots=True)
class RouteProgress:
    completed_quest_ids: set[int] = field(default_factory=set)
    active_quest_ids: set[int] = field(default_factory=set)
    completed_action_ids: set[str] = field(default_factory=set)
    owned_items: dict[int, int] = field(default_factory=dict)

    def clone(self) -> "RouteProgress":
        return RouteProgress(
            completed_quest_ids=set(self.completed_quest_ids),
            active_quest_ids=set(self.active_quest_ids),
            completed_action_ids=set(self.completed_action_ids),
            owned_items=dict(self.owned_items),
        )


@dataclass(frozen=True, slots=True)
class OptimizationWeights:
    same_subzone: float = 2.0
    same_zone: float = 7.0
    zone_change: float = 22.0
    unknown_location: float = 12.0
    zone_return: float = 26.0
    map_return: float = 4.0
    dungeon_repeat: float = 90.0
    parallel_action_bonus: float = 2.0
    parallel_quest_bonus: float = 8.0
    dungeon_bundle_bonus: float = 35.0
    before_leaving_bonus: float = 10.0


@dataclass(frozen=True, slots=True)
class RouteStep:
    index: int
    location: RouteLocation
    actions: tuple[RouteAction, ...]
    quest_ids: tuple[int, ...]
    success_ids: tuple[int, ...] = ()
    items_to_prepare: tuple[ItemRequirement, ...] = ()
    before_leaving: tuple[str, ...] = ()
    next_location: RouteLocation | None = None

    @property
    def parallel(self) -> bool:
        return len(self.quest_ids) > 1

    @property
    def dungeon_ids(self) -> tuple[int | str, ...]:
        return tuple(
            dict.fromkeys(
                action.dungeon_id
                for action in self.actions
                if action.dungeon_id is not None
            )
        )


@dataclass(frozen=True, slots=True)
class OptimizationMetrics:
    steps: int = 0
    map_changes: int = 0
    zone_changes: int = 0
    zone_returns: int = 0
    long_travels: int = 0
    dungeon_visits: int = 0
    repeated_dungeons: int = 0
    repeated_combat_targets: int = 0
    parallel_groups: int = 0
    individually_handled_steps: int = 0
    optimization_score: float = 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "steps": self.steps,
            "map_changes": self.map_changes,
            "zone_changes": self.zone_changes,
            "zone_returns": self.zone_returns,
            "long_travels": self.long_travels,
            "dungeon_visits": self.dungeon_visits,
            "repeated_dungeons": self.repeated_dungeons,
            "repeated_combat_targets": self.repeated_combat_targets,
            "parallel_groups": self.parallel_groups,
            "individually_handled_steps": self.individually_handled_steps,
            "optimization_score": round(self.optimization_score, 2),
        }


@dataclass(frozen=True, slots=True)
class RoutePlan:
    steps: tuple[RouteStep, ...]
    blocked: Mapping[str, str]
    metrics: OptimizationMetrics
    final_progress: RouteProgress


class AdventureRouteEngine:
    """Dependency-safe geographical optimizer for Aventure de zéro.

    The engine is intentionally data-agnostic: local quest IDs remain the source
    of truth. It only consumes normalized RouteAction objects.
    """

    def __init__(
        self,
        actions: Iterable[RouteAction],
        *,
        weights: OptimizationWeights | None = None,
    ) -> None:
        rows = tuple(actions)
        duplicates = [
            action_id
            for action_id, count in Counter(action.action_id for action in rows).items()
            if count > 1
        ]
        if duplicates:
            raise ValueError(f"action_id dupliqué(s): {', '.join(sorted(duplicates))}")
        self.actions = rows
        self.by_id = {action.action_id: action for action in rows}
        self.completion_groups: dict[str, frozenset[str]] = {}
        grouped_completion: dict[str, set[str]] = defaultdict(set)
        for action in rows:
            if action.completion_group:
                grouped_completion[action.completion_group].add(action.action_id)
        self.completion_groups = {
            key: frozenset(values) for key, values in grouped_completion.items()
        }

        # Read-only indexes used by the optimizer. They preserve route semantics
        # while avoiding repeated full scans of every action for map-local work.
        grouped_location_actions: dict[tuple[object, ...], list[str]] = defaultdict(list)
        preparation_action_ids: list[str] = []
        for action in rows:
            grouped_location_actions[action.location.key].append(action.action_id)
            if any(item.preparation for item in action.item_requirements):
                preparation_action_ids.append(action.action_id)
        self.action_ids_by_location = {
            key: tuple(values) for key, values in grouped_location_actions.items()
        }
        self.preparation_action_ids = tuple(preparation_action_ids)

        self.weights = weights or OptimizationWeights()
        self._validate_graph()

    def _validate_graph(self) -> None:
        missing = []
        for action in self.actions:
            for dep in action.prerequisites_actions:
                if dep not in self.by_id:
                    missing.append(f"{action.action_id}->{dep}")
        if missing:
            raise ValueError("dépendance d'action introuvable: " + ", ".join(sorted(missing)))

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(action_id: str) -> None:
            if action_id in visited:
                return
            if action_id in visiting:
                raise ValueError(f"cycle de dépendances autour de {action_id}")
            visiting.add(action_id)
            for dep in self.by_id[action_id].prerequisites_actions:
                visit(dep)
            visiting.remove(action_id)
            visited.add(action_id)

        for action_id in self.by_id:
            visit(action_id)

    def _availability_reason(
        self,
        action: RouteAction,
        profile: RouteProfile,
        progress: RouteProgress,
    ) -> str:
        if action.quest_id in progress.completed_quest_ids:
            return "quête déjà terminée"
        if action.action_id in progress.completed_action_ids:
            return "action déjà terminée"
        if not action.condition.matches(profile):
            return "condition personnage non satisfaite"
        missing_quests = action.prerequisites_quests - progress.completed_quest_ids
        if missing_quests:
            return "prérequis quête manquant: " + ",".join(map(str, sorted(missing_quests)))
        if action.prerequisite_quest_alternatives:
            if not any(set(group).issubset(progress.completed_quest_ids) for group in action.prerequisite_quest_alternatives):
                rendered = " | ".join("+".join(map(str, sorted(group))) for group in action.prerequisite_quest_alternatives)
                return "prérequis quête alternatif manquant: " + rendered
        missing_actions = action.prerequisites_actions - progress.completed_action_ids
        if missing_actions:
            return "prérequis action manquant: " + ",".join(sorted(missing_actions))
        if (
            action.requires_active_quest
            and not action.is_start
            and action.quest_id not in progress.active_quest_ids
        ):
            return "quête non active"
        return ""

    def _available(
        self,
        action: RouteAction,
        profile: RouteProfile,
        progress: RouteProgress,
    ) -> bool:
        return not self._availability_reason(action, profile, progress)

    def _apply(self, action: RouteAction, progress: RouteProgress) -> None:
        progress.completed_action_ids.add(action.action_id)
        if action.activates_quest or action.kind == "start":
            progress.active_quest_ids.add(action.quest_id)
        completed = bool(action.completes_quest)
        if action.completion_group:
            members = self.completion_groups.get(action.completion_group, frozenset())
            completed = bool(members) and members.issubset(progress.completed_action_ids)
        if completed:
            progress.completed_quest_ids.add(action.quest_id)
            progress.active_quest_ids.discard(action.quest_id)

    @staticmethod
    def _same_location(a: RouteLocation, b: RouteLocation) -> bool:
        return a.key == b.key

    def _movement_cost(
        self,
        current: RouteLocation | None,
        candidate: RouteLocation,
        *,
        visited_zones: set[str],
        visited_maps: set[tuple[object, ...]],
    ) -> float:
        w = self.weights
        if current is None:
            base = 0.0
        elif current.same_map(candidate):
            base = 0.0
        elif current.subzone and candidate.subzone and current.subzone_key == candidate.subzone_key:
            base = w.same_subzone
        elif current.zone_key and current.zone_key == candidate.zone_key:
            if (
                current.x is not None
                and current.y is not None
                and candidate.x is not None
                and candidate.y is not None
            ):
                base = min(
                    w.same_zone,
                    max(1.0, hypot(candidate.x - current.x, candidate.y - current.y) / 4.0),
                )
            else:
                base = w.same_zone
        elif current.zone_key and candidate.zone_key:
            base = w.zone_change
        else:
            base = w.unknown_location

        if (
            candidate.zone_key
            and current is not None
            and candidate.zone_key != current.zone_key
            and candidate.zone_key in visited_zones
        ):
            base += w.zone_return
        if current is not None and candidate.key != current.key and candidate.key in visited_maps:
            base += w.map_return
        return base

    def _candidate_score(
        self,
        location: RouteLocation,
        local: Sequence[RouteAction],
        *,
        current: RouteLocation | None,
        visited_zones: set[str],
        visited_maps: set[tuple[object, ...]],
        dungeon_visits: Counter,
    ) -> float:
        # ``local`` is already grouped by _choose_location. The previous code
        # rescanned the entire ready list for every candidate map, making this
        # quadratic on large guides.
        score = self._movement_cost(
            current,
            location,
            visited_zones=visited_zones,
            visited_maps=visited_maps,
        )
        score -= self.weights.parallel_action_bonus * max(0, len(local) - 1)
        quest_count = len({action.quest_id for action in local})
        score -= self.weights.parallel_quest_bonus * max(0, quest_count - 1)

        by_dungeon = Counter(
            action.dungeon_id for action in local if action.dungeon_id is not None
        )
        if by_dungeon:
            score -= self.weights.dungeon_bundle_bonus * max(max(by_dungeon.values()) - 1, 0)
            for dungeon_id in by_dungeon:
                if dungeon_visits[dungeon_id]:
                    score += self.weights.dungeon_repeat

        if any(action.before_leaving_area for action in local):
            score -= self.weights.before_leaving_bonus
        return score

    def _choose_location(
        self,
        ready: Sequence[RouteAction],
        *,
        current: RouteLocation | None,
        visited_zones: set[str],
        visited_maps: set[tuple[object, ...]],
        dungeon_visits: Counter,
    ) -> RouteLocation:
        locations: dict[tuple[object, ...], RouteLocation] = {}
        actions_by_location: dict[tuple[object, ...], list[RouteAction]] = defaultdict(list)
        for action in ready:
            key = action.location.key
            locations.setdefault(key, action.location)
            actions_by_location[key].append(action)
        return min(
            locations.values(),
            key=lambda location: (
                self._candidate_score(
                    location,
                    actions_by_location[location.key],
                    current=current,
                    visited_zones=visited_zones,
                    visited_maps=visited_maps,
                    dungeon_visits=dungeon_visits,
                ),
                location.display(),
            ),
        )

    def _closure_at_location(
        self,
        location: RouteLocation,
        pending: dict[str, RouteAction],
        profile: RouteProfile,
        progress: RouteProgress,
    ) -> list[RouteAction]:
        """Consume every action that becomes possible before leaving this place."""

        selected: list[RouteAction] = []
        local_action_ids = self.action_ids_by_location.get(location.key, ())
        while True:
            ready_here = [
                action
                for action_id in local_action_ids
                if (action := pending.get(action_id)) is not None
                and self._available(action, profile, progress)
            ]
            if not ready_here:
                break
            ready_here.sort(
                key=lambda action: (
                    0 if action.before_leaving_area else 1,
                    action.quest_order,
                    action.objective_order,
                    action.quest_id,
                    action.action_id,
                )
            )
            # All currently available actions on the map can be completed before
            # leaving. Applying them in topological order can unlock more actions
            # at the same location, which the next loop iteration consumes too.
            for action in ready_here:
                if action.action_id not in pending:
                    continue
                if not self._available(action, profile, progress):
                    continue
                selected.append(action)
                self._apply(action, progress)
                pending.pop(action.action_id, None)
        return selected

    @staticmethod
    def _merge_items(items: Iterable[ItemRequirement]) -> tuple[ItemRequirement, ...]:
        merged: dict[tuple[int | None, str], ItemRequirement] = {}
        quantities: Counter = Counter()
        preparation: dict[tuple[int | None, str], bool] = {}
        for raw in items:
            item = raw.normalized()
            key = (item.item_id, _norm(item.name))
            quantities[key] += item.quantity
            preparation[key] = preparation.get(key, False) or item.preparation
            merged[key] = item
        result = [
            ItemRequirement(
                item_id=key[0],
                name=merged[key].name,
                quantity=int(quantities[key]),
                preparation=preparation[key],
            )
            for key in merged
        ]
        return tuple(sorted(result, key=lambda item: (_norm(item.name), item.item_id or 0)))

    def _items_to_prepare(
        self,
        selected: Sequence[RouteAction],
        pending: Mapping[str, RouteAction],
        profile: RouteProfile,
        progress: RouteProgress,
        location: RouteLocation,
    ) -> tuple[ItemRequirement, ...]:
        items: list[ItemRequirement] = [
            item
            for action in selected
            for item in action.item_requirements
            if item.preparation
        ]
        # Short look-ahead only: a pending action must already have its hard quest
        # prerequisites satisfied and be in the same zone (or have no location).
        # Iterate only actions that can actually contribute preparation items.
        for action_id in self.preparation_action_ids:
            action = pending.get(action_id)
            if action is None:
                continue
            if not action.condition.matches(profile):
                continue
            if not action.prerequisites_quests.issubset(progress.completed_quest_ids):
                continue
            if action.prerequisite_quest_alternatives and not any(
                set(group).issubset(progress.completed_quest_ids)
                for group in action.prerequisite_quest_alternatives
            ):
                continue
            if not action.prerequisites_actions.issubset(progress.completed_action_ids):
                continue
            same_zone = (
                bool(location.zone_key)
                and action.location.zone_key == location.zone_key
            )
            unknown_location = action.location.key[0] == "unknown"
            if not (same_zone or unknown_location):
                continue
            for item in action.item_requirements:
                if item.preparation:
                    items.append(item)
        return self._merge_items(items)

    def plan(
        self,
        profile: RouteProfile,
        progress: RouteProgress | None = None,
        *,
        start_location: RouteLocation | None = None,
    ) -> RoutePlan:
        working = (progress or RouteProgress()).clone()
        pending = {
            action.action_id: action
            for action in self.actions
            if action.action_id not in working.completed_action_ids
            and action.quest_id not in working.completed_quest_ids
            and action.condition.matches(profile)
        }

        current = start_location
        visited_zones: set[str] = set()
        visited_maps: set[tuple[object, ...]] = set()
        if current is not None:
            if current.zone_key:
                visited_zones.add(current.zone_key)
            visited_maps.add(current.key)

        dungeon_visits: Counter = Counter()
        raw_steps: list[RouteStep] = []

        while pending:
            ready = [
                action
                for action in pending.values()
                if self._available(action, profile, working)
            ]
            if not ready:
                break

            location = self._choose_location(
                ready,
                current=current,
                visited_zones=visited_zones,
                visited_maps=visited_maps,
                dungeon_visits=dungeon_visits,
            )
            selected = self._closure_at_location(
                location,
                pending,
                profile,
                working,
            )
            if not selected:
                # Defensive guard against an impossible optimizer state.
                break

            items = self._items_to_prepare(
                selected,
                pending,
                profile,
                working,
                location,
            )
            quest_ids = tuple(dict.fromkeys(action.quest_id for action in selected))
            success_ids = tuple(
                sorted({sid for action in selected for sid in action.success_ids})
            )
            before_leaving = tuple(
                action.title
                for action in selected
                if action.before_leaving_area
            )

            raw_steps.append(
                RouteStep(
                    index=len(raw_steps) + 1,
                    location=location,
                    actions=tuple(selected),
                    quest_ids=quest_ids,
                    success_ids=success_ids,
                    items_to_prepare=items,
                    before_leaving=before_leaving,
                )
            )

            for dungeon_id in {
                action.dungeon_id
                for action in selected
                if action.dungeon_id is not None
            }:
                dungeon_visits[dungeon_id] += 1

            current = location
            visited_maps.add(location.key)
            if location.zone_key:
                visited_zones.add(location.zone_key)

        blocked: dict[str, str] = {}
        for action_id, action in pending.items():
            reason = self._availability_reason(action, profile, working)
            blocked[action_id] = reason or "action non planifiable"

        steps: list[RouteStep] = []
        for index, step in enumerate(raw_steps, 1):
            next_location = raw_steps[index].location if index < len(raw_steps) else None
            steps.append(replace(step, index=index, next_location=next_location))

        metrics = self.metrics_for_steps(steps)
        return RoutePlan(
            steps=tuple(steps),
            blocked=blocked,
            metrics=metrics,
            final_progress=working,
        )

    def metrics_for_steps(
        self,
        steps: Sequence[RouteStep],
    ) -> OptimizationMetrics:
        if not steps:
            return OptimizationMetrics()

        map_changes = 0
        zone_changes = 0
        zone_returns = 0
        long_travels = 0
        seen_zones: set[str] = set()
        dungeon_visits: Counter = Counter()
        monster_visits: Counter = Counter()

        previous: RouteLocation | None = None
        for step in steps:
            location = step.location
            if previous is not None:
                if location.key != previous.key:
                    map_changes += 1
                if (
                    location.zone_key
                    and previous.zone_key
                    and location.zone_key != previous.zone_key
                ):
                    zone_changes += 1
                    long_travels += 1
                    if location.zone_key in seen_zones:
                        zone_returns += 1
            if previous is not None and previous.zone_key:
                seen_zones.add(previous.zone_key)
            if location.zone_key:
                seen_zones.add(location.zone_key)

            for dungeon_id in step.dungeon_ids:
                dungeon_visits[dungeon_id] += 1
            for monster_id in {
                monster_id
                for action in step.actions
                for monster_id in action.monster_ids
            }:
                monster_visits[monster_id] += 1
            previous = location

        repeated_dungeons = sum(max(0, count - 1) for count in dungeon_visits.values())
        repeated_monsters = sum(max(0, count - 1) for count in monster_visits.values())
        parallel_groups = sum(1 for step in steps if step.parallel)
        individual = sum(1 for step in steps if len(step.quest_ids) == 1)

        score = (
            map_changes
            + zone_changes * self.weights.zone_change
            + zone_returns * self.weights.zone_return
            + long_travels * self.weights.zone_change
            + repeated_dungeons * self.weights.dungeon_repeat
            + repeated_monsters * 8.0
            - parallel_groups * self.weights.parallel_quest_bonus
        )
        return OptimizationMetrics(
            steps=len(steps),
            map_changes=map_changes,
            zone_changes=zone_changes,
            zone_returns=zone_returns,
            long_travels=long_travels,
            dungeon_visits=sum(dungeon_visits.values()),
            repeated_dungeons=repeated_dungeons,
            repeated_combat_targets=repeated_monsters,
            parallel_groups=parallel_groups,
            individually_handled_steps=individual,
            optimization_score=score,
        )

    def metrics_for_naive_sequence(
        self,
        actions: Iterable[RouteAction] | None = None,
    ) -> OptimizationMetrics:
        rows = list(actions if actions is not None else self.actions)
        rows.sort(
            key=lambda action: (
                action.quest_order,
                action.objective_order,
                action.quest_id,
                action.action_id,
            )
        )
        steps = [
            RouteStep(
                index=index,
                location=action.location,
                actions=(action,),
                quest_ids=(action.quest_id,),
            )
            for index, action in enumerate(rows, 1)
        ]
        return self.metrics_for_steps(steps)


def format_route_step(step: RouteStep) -> str:
    """Compact text representation usable in logs/audits and as UI fallback."""

    groups: dict[str, list[str]] = defaultdict(list)
    labels = {
        "start": "À prendre",
        "turn_in": "À rendre",
        "dialogue": "À faire",
        "interaction": "À faire",
        "combat": "Combat",
        "dungeon": "Donjon",
        "prepare": "Objet à prévoir",
        "choice": "Choix",
    }
    for action in step.actions:
        groups[labels.get(action.kind, "À faire")].append(action.title)

    lines = [f"{step.index} — {step.location.display()}"]
    for label in (
        "À prendre",
        "À rendre",
        "À faire",
        "Combat",
        "Donjon",
        "Objet à prévoir",
        "Choix",
    ):
        rows = groups.get(label, [])
        if rows:
            lines.append(label.upper())
            lines.extend(f"- {row}" for row in rows)
    if step.parallel:
        lines.append("PROGRESSION PARALLÈLE")
        lines.append("- Quêtes : " + ", ".join(map(str, step.quest_ids)))
    if step.items_to_prepare:
        lines.append("À PRÉPARER")
        lines.extend(
            f"- {item.quantity} × {item.name}"
            for item in step.items_to_prepare
        )
    if step.before_leaving:
        lines.append("IMPORTANT AVANT DE PARTIR")
        lines.extend(f"- {row}" for row in step.before_leaving)
    if step.next_location is not None:
        lines.append("ENSUITE")
        lines.append("→ " + step.next_location.display())
    return "\n".join(lines)
