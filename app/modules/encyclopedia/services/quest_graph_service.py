from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Iterable

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.providers.achievement_provider import safe_int
from app.quest_catalog import QuestRecord, normalize_text


_REFERENCE_RE = re.compile(r"\b(Qf|Qa|Sc|OA)\s*(?:==|=)\s*(\d+)\b", re.IGNORECASE)
_MAX_CRITERION_BRANCHES = 256


@dataclass(frozen=True, slots=True)
class CriterionBranch:
    """One valid boolean branch of a Dofus criterion."""

    hard_quests: frozenset[int] = frozenset()
    context_quests: frozenset[int] = frozenset()
    achievements: frozenset[int] = frozenset()

    @property
    def quest_ids(self) -> frozenset[int]:
        return self.hard_quests | self.context_quests

    def merged(self, other: "CriterionBranch") -> "CriterionBranch":
        return CriterionBranch(
            hard_quests=self.hard_quests | other.hard_quests,
            context_quests=self.context_quests | other.context_quests,
            achievements=self.achievements | other.achievements,
        )


@dataclass(frozen=True, slots=True)
class CriterionReferences:
    """Boolean-aware Qf/Qa/Sc references extracted from a criterion."""

    branches: tuple[CriterionBranch, ...] = (CriterionBranch(),)

    @property
    def mandatory_hard_quests(self) -> frozenset[int]:
        return _intersection(branch.hard_quests for branch in self.branches)

    @property
    def mandatory_context_quests(self) -> frozenset[int]:
        # If the same quest is Qf in one branch and Qa in another, it is useful
        # ordering context but completion is not mandatory in every branch.
        common = _intersection(branch.quest_ids for branch in self.branches)
        return common - self.mandatory_hard_quests

    @property
    def mandatory_achievements(self) -> frozenset[int]:
        return _intersection(branch.achievements for branch in self.branches)

    @property
    def alternative_branches(self) -> tuple[CriterionBranch, ...]:
        hard = self.mandatory_hard_quests
        context = self.mandatory_context_quests
        achievements = self.mandatory_achievements
        rows: list[CriterionBranch] = []
        for branch in self.branches:
            row = CriterionBranch(
                hard_quests=branch.hard_quests - hard - context,
                context_quests=branch.context_quests - hard - context,
                achievements=branch.achievements - achievements,
            )
            if row.hard_quests or row.context_quests or row.achievements:
                rows.append(row)
        return tuple(rows)


@dataclass(slots=True)
class QuestClosure:
    ordered_quest_ids: list[int] = field(default_factory=list)
    mandatory_quests: set[int] = field(default_factory=set)
    context_quests: set[int] = field(default_factory=set)
    optional_quests: set[int] = field(default_factory=set)
    hard_edges: set[tuple[int, int]] = field(default_factory=set)
    context_edges: set[tuple[int, int]] = field(default_factory=set)
    alternative_edges: set[tuple[int, int]] = field(default_factory=set)
    alternative_groups: dict[str, list[list[int]]] = field(default_factory=dict)
    quest_alternative_groups: dict[int, set[str]] = field(default_factory=dict)
    invalid_quest_ids: set[int] = field(default_factory=set)
    invalid_achievement_ids: set[int] = field(default_factory=set)
    cycles: list[list[int]] = field(default_factory=list)

    def hard_prerequisites(self, quest_id: int) -> list[int]:
        return sorted(previous for previous, following in self.hard_edges if following == int(quest_id))

    def context_predecessors(self, quest_id: int) -> list[int]:
        return sorted(previous for previous, following in self.context_edges if following == int(quest_id))


class QuestGraphService:
    def __init__(
        self,
        quest_provider: QuestProvider,
        guide_provider: GuideProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
    ) -> None:
        self.quest_provider = quest_provider
        self.guide_provider = guide_provider
        self.achievement_provider = achievement_provider
        self.catalog = quest_provider.get_catalog()
        self.previous_by_quest: dict[int, set[int]] = defaultdict(set)
        self.next_by_quest: dict[int, set[int]] = defaultdict(set)
        self.criterion_previous_by_quest: dict[int, set[int]] = defaultdict(set)
        self.criterion_next_by_quest: dict[int, set[int]] = defaultdict(set)
        self.context_previous_by_quest: dict[int, set[int]] = defaultdict(set)
        self.context_next_by_quest: dict[int, set[int]] = defaultdict(set)
        self.alternative_previous_by_quest: dict[int, set[int]] = defaultdict(set)
        self.guide_ids_by_quest: dict[int, set[str]] = defaultdict(set)
        self.achievement_names_by_quest: dict[int, set[str]] = defaultdict(set)
        self._build()

    def previous_ids(self, quest_id: int) -> list[int]:
        return sorted(self.previous_by_quest.get(int(quest_id), set()))

    def next_ids(self, quest_id: int) -> list[int]:
        return sorted(self.next_by_quest.get(int(quest_id), set()))

    def context_previous_ids(self, quest_id: int) -> list[int]:
        return sorted(self.context_previous_by_quest.get(int(quest_id), set()))

    def reliable_neighbors(self, quest_id: int, guide_id: str = "") -> tuple[int | None, int | None]:
        """Return navigation only when its provenance is explicit.

        Guide display order is valid for previous/next navigation, but it is not
        inserted into the dependency graph.
        """

        quest_id = int(quest_id)
        if guide_id and self.guide_provider is not None:
            guide = self.guide_provider.get_by_id(str(guide_id))
            if guide is not None:
                ordered = list(guide.quest_ids)
                try:
                    index = ordered.index(quest_id)
                except ValueError:
                    pass
                else:
                    previous = ordered[index - 1] if index > 0 else None
                    following = ordered[index + 1] if index + 1 < len(ordered) else None
                    return previous, following

        previous_rows = self.criterion_previous_by_quest.get(quest_id, set())
        next_rows = self.criterion_next_by_quest.get(quest_id, set())
        previous = next(iter(previous_rows)) if len(previous_rows) == 1 else None
        following = next(iter(next_rows)) if len(next_rows) == 1 else None
        return previous, following

    def logical_order(self, quest_ids: Iterable[int]) -> list[int]:
        """Order a known group from explicit Qf dependencies, then stable local data."""

        ids = {int(quest_id) for quest_id in quest_ids if int(quest_id) in self.catalog.by_id}
        edges = {
            (previous, quest_id)
            for quest_id in ids
            for previous in self.criterion_previous_by_quest.get(quest_id, set())
            if previous in ids
        }
        ordered, _cycles = self._topological_order(ids, edges)
        return ordered

    def guide_ids(self, quest_id: int) -> list[str]:
        return sorted(self.guide_ids_by_quest.get(int(quest_id), set()))

    def achievement_names(self, quest_id: int) -> list[str]:
        return sorted(self.achievement_names_by_quest.get(int(quest_id), set()), key=normalize_text)

    def is_repeatable(self, quest: QuestRecord) -> bool:
        text = normalize_text(" ".join([quest.category, quest.start_criterion, *quest.info]))
        return any(token in text for token in ("journaliere", "hebdomadaire", "repetable", "repeatable"))

    @classmethod
    def criterion_references(cls, criterion: str) -> CriterionReferences:
        branches = _criterion_branches(str(criterion or ""))
        return CriterionReferences(tuple(branches or [CriterionBranch()]))

    def prerequisite_closure(
        self,
        seed_quests: Iterable[int] = (),
        seed_achievements: Iterable[int] = (),
        *,
        seed_context_quests: Iterable[int] = (),
        seed_optional_quests: Iterable[int] = (),
    ) -> QuestClosure:
        """Resolve recursive Qf/Qa/Sc/OA relations without flattening OR.

        Qf creates a completion edge, Qa only an ordering/context edge, and
        Sc/OA expands to the quests of the referenced achievement. References
        found only in OR branches remain optional alternatives.
        """

        achievements = {
            int(row.id): row
            for row in (self.achievement_provider.load_all() if self.achievement_provider is not None else ())
        }
        quest_mode: dict[int, int] = {}  # 2 mandatory, 1 context, 0 optional
        achievement_mode: dict[int, int] = {}
        quest_queue: deque[tuple[int, int]] = deque()
        achievement_queue: deque[tuple[int, int]] = deque()
        processed_quest_mode: dict[int, int] = {}
        processed_achievement_mode: dict[int, int] = {}
        hard_edges: set[tuple[int, int]] = set()
        context_edges: set[tuple[int, int]] = set()
        alternative_edges: set[tuple[int, int]] = set()
        invalid_quests: set[int] = set()
        invalid_achievements: set[int] = set()
        alternative_groups: dict[str, list[list[int]]] = {}
        quest_groups: dict[int, set[str]] = defaultdict(set)
        achievement_groups: dict[int, set[str]] = defaultdict(set)

        def add_quest(raw_id: int, mode: int, groups: Iterable[str] = ()) -> None:
            quest_id = int(raw_id)
            if quest_id not in self.catalog.by_id:
                invalid_quests.add(quest_id)
                return
            for group in groups:
                if group:
                    quest_groups[quest_id].add(str(group))
            previous = quest_mode.get(quest_id, -1)
            if mode > previous:
                quest_mode[quest_id] = mode
                quest_queue.append((quest_id, mode))

        def add_achievement(raw_id: int, mode: int, groups: Iterable[str] = ()) -> None:
            achievement_id = int(raw_id)
            if achievement_id not in achievements:
                invalid_achievements.add(achievement_id)
                return
            for group in groups:
                if group:
                    achievement_groups[achievement_id].add(str(group))
            previous = achievement_mode.get(achievement_id, -1)
            if mode > previous:
                achievement_mode[achievement_id] = mode
                achievement_queue.append((achievement_id, mode))

        def add_references(
            refs: CriterionReferences,
            *,
            mode: int,
            owner: str,
            following_quest: int | None = None,
            inherited_groups: Iterable[str] = (),
        ) -> set[int]:
            inherited = set(str(value) for value in inherited_groups if value)
            covered_quests: set[int] = set()
            # A Qf prerequisite of a Qa context quest still has to be
            # completed to reach that context. Only optional OR branches keep
            # their recursively discovered Qf references optional.
            hard_mode = 2 if mode >= 1 else 0
            context_mode = 0 if mode == 0 else 1
            for quest_id in refs.mandatory_hard_quests:
                add_quest(quest_id, hard_mode, inherited)
                covered_quests.add(quest_id)
                if following_quest is not None:
                    hard_edges.add((quest_id, following_quest))
            for quest_id in refs.mandatory_context_quests:
                add_quest(quest_id, context_mode, inherited)
                covered_quests.add(quest_id)
                if following_quest is not None:
                    context_edges.add((quest_id, following_quest))
            for achievement_id in refs.mandatory_achievements:
                add_achievement(achievement_id, mode, inherited)

            alternatives = refs.alternative_branches
            if alternatives:
                group_id = f"{owner}:or"
                group_rows: list[list[int]] = []
                for branch_index, branch in enumerate(alternatives, 1):
                    branch_group = f"{group_id}:{branch_index}"
                    groups = inherited | {branch_group}
                    branch_ids = sorted(branch.quest_ids)
                    group_rows.append(branch_ids)
                    for quest_id in branch.hard_quests | branch.context_quests:
                        add_quest(quest_id, 0, groups)
                        covered_quests.add(quest_id)
                        if following_quest is not None:
                            alternative_edges.add((quest_id, following_quest))
                    for achievement_id in branch.achievements:
                        add_achievement(achievement_id, 0, groups)
                alternative_groups[group_id] = group_rows
            return covered_quests

        for quest_id in seed_quests:
            add_quest(int(quest_id), 2)
        for quest_id in seed_context_quests:
            add_quest(int(quest_id), 1)
        for quest_id in seed_optional_quests:
            add_quest(int(quest_id), 0)
        for achievement_id in seed_achievements:
            add_achievement(int(achievement_id), 2)

        while quest_queue or achievement_queue:
            while quest_queue:
                quest_id, mode = quest_queue.popleft()
                if processed_quest_mode.get(quest_id, -1) >= mode:
                    continue
                processed_quest_mode[quest_id] = mode
                quest = self.catalog.by_id[quest_id]
                add_references(
                    self.criterion_references(quest.start_criterion),
                    mode=mode,
                    owner=f"quest:{quest_id}",
                    following_quest=quest_id,
                    inherited_groups=quest_groups.get(quest_id, ()),
                )

            while achievement_queue:
                achievement_id, mode = achievement_queue.popleft()
                if processed_achievement_mode.get(achievement_id, -1) >= mode:
                    continue
                processed_achievement_mode[achievement_id] = mode
                achievement = achievements[achievement_id]
                covered: set[int] = set()
                inherited = achievement_groups.get(achievement_id, ())
                for objective in getattr(achievement, "objectives", ()) or ():
                    refs = self.criterion_references(str(getattr(objective, "criterion", "") or ""))
                    objective_covered = add_references(
                        refs,
                        mode=mode,
                        owner=f"achievement:{achievement_id}:objective:{getattr(objective, 'id', 0)}",
                        inherited_groups=inherited,
                    )
                    covered.update(objective_covered)
                    ref = getattr(objective, "entity_ref", None)
                    if not objective_covered and ref is not None and getattr(ref, "entity_type", "") == "quest":
                        quest_id = safe_int(getattr(ref, "entity_id", None))
                        if quest_id is not None:
                            add_quest(quest_id, mode, inherited)
                            covered.add(quest_id)
                for ref in getattr(achievement, "linked_quests", ()) or ():
                    quest_id = safe_int(getattr(ref, "entity_id", None))
                    if quest_id is not None and int(quest_id) not in covered:
                        add_quest(int(quest_id), mode, inherited)

            if len(quest_mode) > 1500:
                raise RuntimeError("fermeture de prérequis >1500 quêtes, refus de contamination")

        all_ids = set(quest_mode)

        def achievement_quest_ids(achievement_id: int, visited: set[int] | None = None) -> set[int]:
            seen = set() if visited is None else set(visited)
            if achievement_id in seen or achievement_id not in achievements:
                return set()
            seen.add(achievement_id)
            achievement = achievements[achievement_id]
            result: set[int] = set()
            child_achievements: set[int] = set()
            for objective in getattr(achievement, "objectives", ()) or ():
                refs = self.criterion_references(str(getattr(objective, "criterion", "") or ""))
                for branch in refs.branches:
                    result.update(branch.quest_ids)
                    child_achievements.update(branch.achievements)
            for ref in getattr(achievement, "linked_quests", ()) or ():
                quest_id = safe_int(getattr(ref, "entity_id", None))
                if quest_id is not None:
                    result.add(int(quest_id))
            for child_id in child_achievements:
                result.update(achievement_quest_ids(child_id, seen))
            return result & all_ids

        # A Sc/OA condition is ordered after the quests that make up that
        # achievement, while the quest steps keep only Qf in prerequisites.
        for following in all_ids:
            refs = self.criterion_references(self.catalog.by_id[following].start_criterion)
            for achievement_id in refs.mandatory_achievements:
                for previous in achievement_quest_ids(achievement_id):
                    if previous != following:
                        hard_edges.add((previous, following))
            for branch in refs.alternative_branches:
                for achievement_id in branch.achievements:
                    for previous in achievement_quest_ids(achievement_id):
                        if previous != following:
                            alternative_edges.add((previous, following))

        ordering_edges = {
            edge
            for edge in hard_edges | context_edges | alternative_edges
            if edge[0] in all_ids and edge[1] in all_ids and edge[0] != edge[1]
        }
        ordered, cycles = self._topological_order(all_ids, ordering_edges)
        return QuestClosure(
            ordered_quest_ids=ordered,
            mandatory_quests={quest_id for quest_id, mode in quest_mode.items() if mode == 2},
            context_quests={quest_id for quest_id, mode in quest_mode.items() if mode == 1},
            optional_quests={quest_id for quest_id, mode in quest_mode.items() if mode == 0},
            hard_edges={edge for edge in hard_edges if edge[0] in all_ids and edge[1] in all_ids},
            context_edges={edge for edge in context_edges if edge[0] in all_ids and edge[1] in all_ids},
            alternative_edges={edge for edge in alternative_edges if edge[0] in all_ids and edge[1] in all_ids},
            alternative_groups=alternative_groups,
            quest_alternative_groups={quest_id: set(groups) for quest_id, groups in quest_groups.items()},
            invalid_quest_ids=invalid_quests,
            invalid_achievement_ids=invalid_achievements,
            cycles=cycles,
        )

    def _build(self) -> None:
        for quest in self.catalog.quests:
            refs = self.criterion_references(quest.start_criterion)
            for previous in refs.mandatory_hard_quests:
                if previous in self.catalog.by_id and previous != quest.id:
                    self.criterion_previous_by_quest[quest.id].add(previous)
                    self.criterion_next_by_quest[previous].add(quest.id)
                    self.previous_by_quest[quest.id].add(previous)
                    self.next_by_quest[previous].add(quest.id)
            for previous in refs.mandatory_context_quests:
                if previous in self.catalog.by_id and previous != quest.id:
                    self.context_previous_by_quest[quest.id].add(previous)
                    self.context_next_by_quest[previous].add(quest.id)
            for branch in refs.alternative_branches:
                for previous in branch.quest_ids:
                    if previous in self.catalog.by_id and previous != quest.id:
                        self.alternative_previous_by_quest[quest.id].add(previous)
            for name in quest.achievements:
                self.achievement_names_by_quest[quest.id].add(name)
        if self.guide_provider is not None:
            for guide in self.guide_provider.load_all():
                for quest_id in guide.quest_ids:
                    self.guide_ids_by_quest[quest_id].add(guide.id)

    def _topological_order(
        self,
        quest_ids: set[int],
        edges: set[tuple[int, int]],
    ) -> tuple[list[int], list[list[int]]]:
        ids = {int(quest_id) for quest_id in quest_ids if int(quest_id) in self.catalog.by_id}
        incoming = {quest_id: 0 for quest_id in ids}
        children: dict[int, set[int]] = defaultdict(set)
        for previous, following in edges:
            if previous not in ids or following not in ids or following in children[previous]:
                continue
            children[previous].add(following)
            incoming[following] += 1

        def key(quest_id: int) -> tuple[int, str, int]:
            quest = self.catalog.by_id[quest_id]
            return int(getattr(quest, "level_min", 0) or 0), normalize_text(quest.name), quest_id

        ready = sorted((quest_id for quest_id, count in incoming.items() if count == 0), key=key)
        result: list[int] = []
        while ready:
            quest_id = ready.pop(0)
            result.append(quest_id)
            for child in sorted(children.get(quest_id, ()), key=key):
                incoming[child] -= 1
                if incoming[child] == 0:
                    ready.append(child)
                    ready.sort(key=key)

        remaining = ids - set(result)
        cycles = _cycle_components(remaining, children)
        result.extend(sorted(remaining, key=key))
        return result, cycles

    @classmethod
    def _criterion_quest_ids(cls, criterion: str) -> list[int]:
        """Compatibility helper: only true, mandatory Qf dependencies."""

        return sorted(cls.criterion_references(criterion).mandatory_hard_quests)


def _intersection(values: Iterable[frozenset[int]]) -> frozenset[int]:
    rows = list(values)
    if not rows:
        return frozenset()
    result = set(rows[0])
    for row in rows[1:]:
        result.intersection_update(row)
    return frozenset(result)


def _strip_outer_parentheses(value: str) -> str:
    text = value.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        closes_at_end = False
        for index, char in enumerate(text):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    closes_at_end = index == len(text) - 1
                    break
        if not closes_at_end:
            break
        text = text[1:-1].strip()
    return text


def _split_top(value: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == separator and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    if not parts:
        return []
    parts.append(value[start:])
    return [part.strip() for part in parts if part.strip()]


def _criterion_branches(criterion: str) -> list[CriterionBranch]:
    text = str(criterion or "").replace("&&", "&").replace("||", "|").strip()

    def parse(value: str) -> list[CriterionBranch]:
        value = _strip_outer_parentheses(value)
        or_parts = _split_top(value, "|")
        if or_parts:
            rows = [branch for part in or_parts for branch in parse(part)]
            return _deduplicate_branches(rows[:_MAX_CRITERION_BRANCHES])

        and_parts = _split_top(value, "&")
        if and_parts:
            groups = [parse(part) for part in and_parts]
            rows: list[CriterionBranch] = []
            for combination in product(*groups):
                merged = CriterionBranch()
                for branch in combination:
                    merged = merged.merged(branch)
                rows.append(merged)
                if len(rows) >= _MAX_CRITERION_BRANCHES:
                    break
            return _deduplicate_branches(rows)

        hard: set[int] = set()
        context: set[int] = set()
        achievements: set[int] = set()
        for match in _REFERENCE_RE.finditer(value):
            code = match.group(1).casefold()
            entity_id = int(match.group(2))
            if code == "qf":
                hard.add(entity_id)
            elif code == "qa":
                context.add(entity_id)
            else:
                achievements.add(entity_id)
        return [CriterionBranch(frozenset(hard), frozenset(context), frozenset(achievements))]

    return parse(text) if text else [CriterionBranch()]


def _deduplicate_branches(branches: Iterable[CriterionBranch]) -> list[CriterionBranch]:
    seen: set[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = set()
    rows: list[CriterionBranch] = []
    for branch in branches:
        key = (
            tuple(sorted(branch.hard_quests)),
            tuple(sorted(branch.context_quests)),
            tuple(sorted(branch.achievements)),
        )
        if key not in seen:
            seen.add(key)
            rows.append(branch)
    return rows or [CriterionBranch()]


def _cycle_components(remaining: set[int], children: dict[int, set[int]]) -> list[list[int]]:
    """Return deterministic strongly connected components for unresolved cycles."""

    index = 0
    indices: dict[int, int] = {}
    lowlinks: dict[int, int] = {}
    stack: list[int] = []
    on_stack: set[int] = set()
    components: list[list[int]] = []

    def visit(node: int) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for child in sorted(children.get(node, ()) & remaining):
            if child not in indices:
                visit(child)
                lowlinks[node] = min(lowlinks[node], lowlinks[child])
            elif child in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[child])
        if lowlinks[node] != indices[node]:
            return
        component: list[int] = []
        while stack:
            child = stack.pop()
            on_stack.discard(child)
            component.append(child)
            if child == node:
                break
        if len(component) > 1 or node in children.get(node, set()):
            components.append(sorted(component))

    for quest_id in sorted(remaining):
        if quest_id not in indices:
            visit(quest_id)
    return sorted(components)
