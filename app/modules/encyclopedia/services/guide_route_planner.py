from __future__ import annotations

"""Multi-character orchestration for the canonical adventure route engine.

The planner keeps one :class:`RouteProgress` per stable character identity,
then groups only the actions that each participant still needs.  Travel and
capture metadata are deliberately explicit: no Zaap eligibility or capture
rule is guessed from labels, notes, or coordinates.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping

from app.core.character_identity import require_character_key
from app.modules.encyclopedia.services.adventure_route_engine import (
    AdventureRouteEngine,
    RouteAction,
    RouteLocation,
    RoutePlan,
    RouteProfile,
    RouteProgress,
    RouteStep,
)
from app.modules.encyclopedia.services.guide_route_naming import title_for_route_step
from app.modules.encyclopedia.services.guide_team_route_order import order_team_actions


class TravelMode(StrEnum):
    DIRECT = "direct"
    ZAAP_THEN_TRAVEL = "zaap_then_travel"


class CaptureKind(StrEnum):
    SOUL_STONE = "soul_stone"
    ZONE_SPECIAL = "zone_special"
    DROP = "drop"


# Doduda uses INT32_MIN as an absent coordinate.  A manual Ganymede hint
# must not become a /travel command just because both fields are integers.
_MISSING_GAME_COORDINATE = -(2**31)


def _has_exact_game_coordinates(location: RouteLocation) -> bool:
    return (
        type(location.x) is int
        and type(location.y) is int
        and location.x != _MISSING_GAME_COORDINATE
        and location.y != _MISSING_GAME_COORDINATE
    )


@dataclass(frozen=True, slots=True)
class GuideParticipantState:
    character_key: str
    profile: RouteProfile = RouteProfile()
    progress: RouteProgress | None = None
    start_location: RouteLocation | None = None
    world: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "character_key", require_character_key(self.character_key))


@dataclass(frozen=True, slots=True)
class VerifiedZaapRoute:
    destination: RouteLocation
    zaap: RouteLocation
    world: str
    eligible_character_keys: frozenset[str]
    evidence: str

    def __post_init__(self) -> None:
        if not _has_exact_game_coordinates(self.destination):
            raise ValueError("verified Zaap destination requires exact coordinates")
        if not _has_exact_game_coordinates(self.zaap):
            raise ValueError("verified Zaap location requires exact coordinates")
        if not self.world.strip() or not self.evidence.strip():
            raise ValueError("verified Zaap route requires world and evidence")
        keys = frozenset(require_character_key(key) for key in self.eligible_character_keys)
        if not keys:
            raise ValueError("verified Zaap route requires explicit eligible characters")
        object.__setattr__(self, "eligible_character_keys", keys)


@dataclass(frozen=True, slots=True)
class GuideTravelPlan:
    mode: TravelMode
    destination: RouteLocation
    participant_keys: tuple[str, ...]
    world: str = ""
    zaap: RouteLocation | None = None
    evidence: str = "exact_destination_coordinates"

    def __post_init__(self) -> None:
        if not isinstance(self.mode, TravelMode):
            raise ValueError("travel mode must be explicitly verified")
        if not _has_exact_game_coordinates(self.destination):
            raise ValueError("travel destination requires exact coordinates")
        keys = tuple(require_character_key(key) for key in self.participant_keys)
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("travel plan requires unique explicit participant keys")
        object.__setattr__(self, "participant_keys", keys)
        if self.mode is TravelMode.ZAAP_THEN_TRAVEL:
            if self.zaap is None or not _has_exact_game_coordinates(self.zaap):
                raise ValueError("zaap_then_travel requires exact Zaap coordinates")
            if not self.world.strip() or not self.evidence.strip():
                raise ValueError("zaap_then_travel requires world and evidence")
        elif self.zaap is not None:
            raise ValueError("direct travel cannot carry a Zaap")

    def to_chat_command(self) -> str:
        """Explicit two-command protocol consumed by Organizer's TravelMacro.

        Creating a plan does not dispatch any macro. The caller must still
        enforce the exact participant_keys when the user clicks to travel.
        """
        destination = f"/travel {self.destination.x},{self.destination.y}"
        if self.mode is TravelMode.DIRECT:
            return destination
        assert self.zaap is not None  # Guaranteed by __post_init__
        return f"/zaap {self.zaap.x},{self.zaap.y} ; {destination}"

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mode": self.mode.value,
            "participant_keys": list(self.participant_keys),
            "destination": {
                "map_id": self.destination.map_id,
                "x": self.destination.x,
                "y": self.destination.y,
                "zone": self.destination.zone,
                "subzone": self.destination.subzone,
            },
            "world": self.world,
            "evidence": self.evidence,
        }
        if self.zaap is not None:
            payload["zaap"] = {
                "map_id": self.zaap.map_id,
                "x": self.zaap.x,
                "y": self.zaap.y,
                "zone": self.zaap.zone,
                "subzone": self.zaap.subzone,
            }
        return payload


def unbound_direct_travel_payload(destination: RouteLocation) -> dict[str, object]:
    """Describe a static direct route without inventing runtime participants."""

    if not _has_exact_game_coordinates(destination):
        return {
            "status": "unavailable",
            "reason": "destination_without_exact_coordinates",
            "participant_keys": [],
            "requires_explicit_participants": True,
        }
    return {
        "status": "template",
        "mode": TravelMode.DIRECT.value,
        "participant_keys": [],
        "requires_explicit_participants": True,
        "destination": {
            "map_id": destination.map_id,
            "x": destination.x,
            "y": destination.y,
            "zone": destination.zone,
            "subzone": destination.subzone,
        },
        "evidence": "exact_destination_coordinates",
    }


@dataclass(frozen=True, slots=True)
class GuideCaptureRequirement:
    requirement_id: str
    action_id: str
    kind: CaptureKind
    quantity: int = 1
    consumable_item_id: int | None = None
    consumable_name: str = ""
    evidence: str = ""

    def __post_init__(self) -> None:
        if (not isinstance(self.requirement_id, str) or not self.requirement_id.strip()
                or not isinstance(self.action_id, str) or not self.action_id.strip()):
            raise ValueError("capture requirement requires stable ids")
        if not isinstance(self.kind, CaptureKind):
            raise ValueError("capture kind must be explicit and supported")
        if type(self.quantity) is not int or self.quantity < 1:
            raise ValueError("capture quantity must be a positive integer")
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            raise ValueError("capture requirement requires evidence")
        if self.kind is CaptureKind.SOUL_STONE:
            if (type(self.consumable_item_id) is not int
                    or self.consumable_item_id <= 0
                    or not isinstance(self.consumable_name, str)
                    or not self.consumable_name.strip()):
                raise ValueError(
                    "soul-stone capture requires a positive item id and name"
                )
        elif self.consumable_item_id is not None or self.consumable_name:
            raise ValueError("only soul-stone capture may require a soul stone")


@dataclass(frozen=True, slots=True)
class GuideStockNeed:
    item_id: int | None
    name: str
    required_by_character: Mapping[str, int]
    remaining_by_character: Mapping[str, int | None]

    @property
    def total_remaining(self) -> int | None:
        """A reliable total requires an explicit inventory for every participant."""
        if any(value is None for value in self.remaining_by_character.values()):
            return None
        return sum(value for value in self.remaining_by_character.values()
                   if value is not None)


@dataclass(frozen=True, slots=True)
class GuidePlanningIssue:
    code: str
    detail: str
    character_key: str = ""
    action_id: str = ""


@dataclass(frozen=True, slots=True)
class GroupedGuideActivity:
    action: RouteAction
    participant_keys: tuple[str, ...]
    title: str
    travel_plan: GuideTravelPlan | None
    captures: tuple[GuideCaptureRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class ParticipantRoutePlan:
    character_key: str
    route: RoutePlan


@dataclass(frozen=True, slots=True)
class GlobalGuidePlan:
    participants: tuple[ParticipantRoutePlan, ...]
    activities: tuple[GroupedGuideActivity, ...]
    stock: tuple[GuideStockNeed, ...]
    issues: tuple[GuidePlanningIssue, ...]


def schedule_success_passes(
    success_ids: Iterable[int],
    incompatible_pairs: Iterable[tuple[int, int]],
) -> tuple[tuple[int, ...], ...]:
    """Partition successes into deterministic compatible dungeon passes."""

    supplied_ids = tuple(success_ids)
    if any(type(value) is not int or value <= 0 for value in supplied_ids):
        raise ValueError("success IDs must be positive canonical integers")
    nodes = tuple(sorted(set(supplied_ids)))
    node_set = set(nodes)
    incompatible: dict[int, set[int]] = defaultdict(set)
    for left, right in incompatible_pairs:
        if (type(left) is not int or left <= 0
                or type(right) is not int or right <= 0):
            raise ValueError("incompatible success IDs must be positive canonical integers")
        if left == right or left not in node_set or right not in node_set:
            continue
        incompatible[left].add(right)
        incompatible[right].add(left)
    passes: list[list[int]] = []
    for success_id in sorted(nodes, key=lambda value: (-len(incompatible[value]), value)):
        for group in passes:
            if all(other not in incompatible[success_id] for other in group):
                group.append(success_id)
                break
        else:
            passes.append([success_id])
    return tuple(tuple(sorted(group)) for group in passes)


class GuideRoutePlanner:
    """Compose independent canonical routes into one explainable team plan."""

    def __init__(self, engine: AdventureRouteEngine) -> None:
        self.engine = engine

    @staticmethod
    def _shared_action_order(
        participant_plans: tuple[ParticipantRoutePlan, ...],
        memberships: Mapping[str, list[tuple[int, str]]],
        engine: AdventureRouteEngine,
        participant_starts: Mapping[str, RouteLocation | None],
    ) -> tuple[str, ...] | None:
        """Merge team actions subject to *real* prerequisites, not visual order.

        Independently optimized player itineraries may legitimately visit
        unrelated actions in opposite orders. Treating those preferences as
        hard edges invents conflicts. By contrast, a required quest start or
        prerequisite action cannot be visited after its dependent action
        when it is still needed by a selected participant.
        """
        successors: dict[str, set[str]] = {
            action_id: set() for action_id in memberships
        }
        incoming = {action_id: 0 for action_id in memberships}

        def connect(before: str, after: str) -> None:
            if (before != after and before in successors and after in successors
                    and after not in successors[before]):
                successors[before].add(after)
                incoming[after] += 1

        starts_by_quest: dict[int, set[str]] = defaultdict(set)
        completions_by_quest: dict[int, set[str]] = defaultdict(set)
        for action_id in memberships:
            action = engine.by_id[action_id]
            if action.is_start:
                starts_by_quest[action.quest_id].add(action_id)
            if action.completes_quest:
                completions_by_quest[action.quest_id].add(action_id)

        for participant in participant_plans:
            member_ids = {
                action.action_id
                for step in participant.route.steps
                for action in step.actions
            }
            for action_id in member_ids:
                action = engine.by_id[action_id]
                for prerequisite in action.prerequisites_actions:
                    if prerequisite in member_ids:
                        connect(prerequisite, action_id)
                if action.requires_active_quest and not action.is_start:
                    for start in starts_by_quest.get(action.quest_id, ()):
                        if start in member_ids:
                            connect(start, action_id)
                for quest_id in action.prerequisites_quests:
                    for completion in completions_by_quest.get(quest_id, ()):
                        if completion in member_ids:
                            connect(completion, action_id)

        # Source-step indices are tie-breakers, not hard prerequisites.
        # Pick among canonically available actions via movement heuristic.
        return order_team_actions(
            successors, incoming, memberships, engine, participant_starts,
        )

    def plan(
        self,
        participants: Iterable[GuideParticipantState],
        *,
        verified_zaap_routes: Iterable[VerifiedZaapRoute] = (),
        capture_requirements: Iterable[GuideCaptureRequirement] = (),
    ) -> GlobalGuidePlan:
        states = tuple(participants)
        if not states:
            # The guide remains visible with nobody selected, but planning
            # must never invent a participant, action or inventory requirement.
            return GlobalGuidePlan(
                participants=(),
                activities=(),
                stock=(),
                issues=(GuidePlanningIssue(
                    "no_selected_participants",
                    "Select at least one character to calculate a route",
                ),),
            )
        keys = tuple(state.character_key for state in states)
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate participant character_key")

        participant_plans = tuple(
            ParticipantRoutePlan(
                state.character_key,
                self.engine.plan(
                    state.profile,
                    state.progress,
                    start_location=state.start_location,
                ),
            )
            for state in states
        )
        worlds_by_character = {
            state.character_key: state.world.strip() for state in states
        }
        issues: list[GuidePlanningIssue] = []
        for participant in participant_plans:
            for action_id, reason in sorted(participant.route.blocked.items()):
                issues.append(
                    GuidePlanningIssue(
                        "action_blocked", reason, participant.character_key, action_id
                    )
                )

        capture_by_action: dict[str, list[GuideCaptureRequirement]] = defaultdict(list)
        seen_capture_requirements: set[str] = set()
        for requirement in capture_requirements:
            if requirement.requirement_id in seen_capture_requirements:
                raise ValueError("duplicate capture requirement_id")
            seen_capture_requirements.add(requirement.requirement_id)
            if requirement.action_id not in self.engine.by_id:
                issues.append(
                    GuidePlanningIssue(
                        "capture_action_unknown",
                        requirement.requirement_id,
                        action_id=requirement.action_id,
                    )
                )
                continue
            capture_by_action[requirement.action_id].append(requirement)

        memberships: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for participant_index, participant in enumerate(participant_plans):
            for step in participant.route.steps:
                for action in step.actions:
                    memberships[action.action_id].append(
                        (step.index, participant.character_key)
                    )

        ordered_ids = self._shared_action_order(
            participant_plans, memberships, self.engine,
            {state.character_key: state.start_location for state in states},
        )
        if ordered_ids is None:
            issues.append(GuidePlanningIssue(
                "shared_route_order_conflict",
                "Individual routes require incompatible action ordering; "
                "keep personal itineraries and do not fabricate a common route",
            ))
            return GlobalGuidePlan(
                participants=participant_plans,
                activities=(),
                stock=self._stock(participant_plans, states, capture_by_action),
                issues=tuple(issues),
            )

        zaap_routes = tuple(verified_zaap_routes)
        # This is a route *estimate*, not live player tracking.
        # Never move a player to another participant's inferred position.
        projected_locations = {
            state.character_key: state.start_location for state in states
        }
        activities: list[GroupedGuideActivity] = []
        for action_id in ordered_ids:
            rows = memberships[action_id]
            action = self.engine.by_id[action_id]
            participant_keys = tuple(
                key for key in keys if any(row_key == key for _index, row_key in rows)
            )
            travel = self._travel_plan(
                action,
                participant_keys,
                worlds_by_character,
                zaap_routes,
                issues,
                projected_locations,
            )
            if action.location.x is not None and action.location.y is not None:
                for character_key in participant_keys:
                    projected_locations[character_key] = action.location
            synthetic_step = RouteStep(
                index=len(activities) + 1,
                location=action.location,
                actions=(action,),
                quest_ids=(action.quest_id,),
            )
            activities.append(
                GroupedGuideActivity(
                    action=action,
                    participant_keys=participant_keys,
                    title=title_for_route_step(synthetic_step).text,
                    travel_plan=travel,
                    captures=tuple(
                        sorted(
                            capture_by_action.get(action_id, ()),
                            key=lambda requirement: requirement.requirement_id,
                        )
                    ),
                )
            )

        stock = self._stock(participant_plans, states, capture_by_action)
        return GlobalGuidePlan(
            participants=participant_plans,
            activities=tuple(activities),
            stock=stock,
            issues=tuple(issues),
        )

    def _travel_plan(
        self,
        action: RouteAction,
        participant_keys: tuple[str, ...],
        worlds_by_character: Mapping[str, str],
        zaap_routes: tuple[VerifiedZaapRoute, ...],
        issues: list[GuidePlanningIssue],
        projected_locations: Mapping[str, RouteLocation | None],
    ) -> GuideTravelPlan | None:
        destination = action.location
        if not _has_exact_game_coordinates(destination):
            issues.append(
                GuidePlanningIssue(
                    "transport_destination_unresolved",
                    destination.display(),
                    action_id=action.action_id,
                )
            )
            return None

        # A global command applies to the whole selected subset. If one
        # participant is already on the destination map, forcing a Zaap on
        # everybody adds a needless teleport and can split the group.
        if any(
            projected_locations.get(key) is not None
            and projected_locations[key].same_map(destination)
            for key in participant_keys
        ):
            return GuideTravelPlan(TravelMode.DIRECT, destination, participant_keys)

        candidates = sorted(
            (
                route
                for route in zaap_routes
                if route.destination.key == destination.key
                and set(participant_keys).issubset(route.eligible_character_keys)
                and all(
                    worlds_by_character.get(key) == route.world
                    for key in participant_keys
                )
            ),
            key=lambda route: (route.world.casefold(), route.zaap.display()),
        )
        if candidates:
            route = candidates[0]
            return GuideTravelPlan(
                TravelMode.ZAAP_THEN_TRAVEL,
                destination,
                participant_keys,
                world=route.world,
                zaap=route.zaap,
                evidence=route.evidence,
            )
        if any(route.destination.key == destination.key for route in zaap_routes):
            supplied_worlds = {
                worlds_by_character.get(key, "") for key in participant_keys
            }
            reason = (
                "world missing or inconsistent; safe direct fallback"
                if "" in supplied_worlds or len(supplied_worlds) != 1
                else "Zaap eligibility does not cover every participant; safe direct fallback"
            )
            issues.append(
                GuidePlanningIssue(
                    "zaap_ineligible_participant",
                    reason,
                    action_id=action.action_id,
                )
            )
        return GuideTravelPlan(TravelMode.DIRECT, destination, participant_keys)

    def _stock(
        self,
        participant_plans: tuple[ParticipantRoutePlan, ...],
        states: tuple[GuideParticipantState, ...],
        capture_by_action: Mapping[str, list[GuideCaptureRequirement]],
    ) -> tuple[GuideStockNeed, ...]:
        state_by_key = {state.character_key: state for state in states}
        required: dict[tuple[int | None, str], Counter[str]] = defaultdict(Counter)
        display_names: dict[tuple[int | None, str], str] = {}
        for participant in participant_plans:
            action_ids = {
                action.action_id
                for step in participant.route.steps
                for action in step.actions
            }
            for action_id in action_ids:
                for item in self.engine.by_id[action_id].item_requirements:
                    if not item.preparation:
                        continue
                    normalized = item.normalized()
                    item_key = (normalized.item_id, " ".join(normalized.name.casefold().split()))
                    required[item_key][participant.character_key] += normalized.quantity
                    display_names[item_key] = normalized.name
                for capture in capture_by_action.get(action_id, ()):
                    if capture.kind is not CaptureKind.SOUL_STONE:
                        continue
                    item_key = (
                        capture.consumable_item_id,
                        " ".join(capture.consumable_name.casefold().split()),
                    )
                    required[item_key][participant.character_key] += capture.quantity
                    display_names[item_key] = capture.consumable_name

        rows: list[GuideStockNeed] = []
        for item_key, per_character in required.items():
            item_id, _normalized_name = item_key
            remaining: dict[str, int | None] = {}
            for character_key, quantity in per_character.items():
                state = state_by_key[character_key]
                # A missing snapshot (or missing item in a partial snapshot)
                # is UNKNOWN, never proof that the character owns zero.
                owned: int | None = None
                if item_id is not None and state.progress is not None:
                    candidate = state.progress.owned_items.get(item_id)
                    if candidate is not None:
                        if type(candidate) is not int or candidate < 0:
                            raise ValueError("Invalid explicit inventory quantity")
                        owned = candidate
                remaining[character_key] = (
                    max(0, quantity - owned) if owned is not None else None
                )
            rows.append(
                GuideStockNeed(
                    item_id,
                    display_names[item_key],
                    dict(sorted(per_character.items())),
                    dict(sorted(remaining.items())),
                )
            )
        return tuple(
            sorted(rows, key=lambda row: (row.name.casefold(), row.item_id or 0))
        )


__all__ = [
    "CaptureKind",
    "GlobalGuidePlan",
    "GroupedGuideActivity",
    "GuideCaptureRequirement",
    "GuideParticipantState",
    "GuidePlanningIssue",
    "GuideRoutePlanner",
    "GuideStockNeed",
    "GuideTravelPlan",
    "ParticipantRoutePlan",
    "TravelMode",
    "VerifiedZaapRoute",
    "schedule_success_passes",
    "unbound_direct_travel_payload",
]
