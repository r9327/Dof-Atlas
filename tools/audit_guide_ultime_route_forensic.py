from __future__ import annotations

"""Forensic audit for Guide Ultime V5.

This is intentionally stricter than the historical STRICT PASS.  It verifies the
actual player-facing route: quest/action order, prerequisite order, raw map IDs,
coordinates, next-card links, temporal/class/order leaks, and documentary conflicts.

Safe repair mode only fixes facts that can be derived without changing route scope:
- strips/replaces Dofus sentinel coordinates;
- recovers coordinates from the exact raw map or a single unambiguous documentary
  coordinate when the raw map has no world coordinate;
- writes an action_sequence preserving causal order inside each GPS card;
- rebuilds ENSUITE from the actual next card.

It NEVER reorders GPS cards, changes selected quests, or invents coordinates.
"""

import argparse
import copy
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services.adventure_route_adapter import AdventureRouteAdapter
from app.modules.encyclopedia.services.guide_quest_view_model import (
    quest_solution_steps,
    quest_start_info,
)
from app.quest_catalog import doduda_rows
from tools.guide_ultime_scope_v5 import mandatory_qf_ids, residual_qf_alternatives


ARTIFACTS = ROOT / "artifacts"
ROUTE_PATH = ARTIFACTS / "guide_ultime_gps_route.json"
FINAL_PATH = ARTIFACTS / "guide_ultime_final.json"
OUT_PATH = ARTIFACTS / "guide_ultime_route_forensic_audit.json"
SENTINEL_COORD = -2147483648
COORD_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")
TEMPORAL_POLICIES = {
    "only_while_event_available",
    "qq_calendar_filler_when_available",
    "tracked_side_thread_not_blocking",
    "skip",
}
CONDITIONAL_POLICIES = {
    "conditional_class_card",
    "conditional_order_card",
    "selected_class_only",
    "selected_alignment_and_order_only",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z0-9]+", " ", text.casefold()).strip()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_coord(value: Any) -> int | None:
    coord = _safe_int(value)
    if coord is None or coord == SENTINEL_COORD:
        return None
    # Dofus world coordinates are small. This broad bound only catches corrupted
    # integer sentinels/garbage without asserting a narrow map-world range.
    if abs(coord) > 10000:
        return None
    return coord


def _coord_from_text(value: Any) -> tuple[int, int] | None:
    match = COORD_RE.search(str(value or ""))
    if not match:
        return None
    x, y = _safe_coord(match.group(1)), _safe_coord(match.group(2))
    return (x, y) if x is not None and y is not None else None


def _explicit_coord(row: dict[str, Any]) -> tuple[int, int] | None:
    x, y = _safe_coord(row.get("x")), _safe_coord(row.get("y"))
    return (x, y) if x is not None and y is not None else None


def _array(value: Any) -> list[Any]:
    if isinstance(value, dict):
        inner = value.get("Array", [])
        return inner if isinstance(inner, list) else []
    return value if isinstance(value, list) else []


def _iter_final_steps(final: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for section in final.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        for step in section.get("steps", []) or []:
            if isinstance(step, dict) and step.get("type") == "quest":
                yield step


def _iter_action_rows(step: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for section in ("a_prendre", "a_faire_ici"):
        for row in step.get(section, []) or []:
            if isinstance(row, dict):
                yield section, row


def _recursive_sentinel_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(_recursive_sentinel_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_recursive_sentinel_paths(child, f"{path}[{index}]"))
    elif value == SENTINEL_COORD or str(value).strip() == str(SENTINEL_COORD):
        found.append(path)
    return found


@dataclass(frozen=True, slots=True)
class Occurrence:
    action_id: str
    quest_id: int
    step_pos: int
    card_index: int
    section: str
    row: dict[str, Any]


class DocumentaryIndex:
    def __init__(self, catalog: Any) -> None:
        self.catalog = catalog

    @lru_cache(maxsize=4096)
    def start(self, quest_id: int) -> tuple[str, tuple[int, int] | None, str]:
        quest = self.catalog.by_id.get(int(quest_id))
        if quest is None:
            return "", None, ""
        info = quest_start_info(quest)
        return str(info.npc or "").strip(), _coord_from_text(info.position), str(info.zone or "").strip()

    @lru_cache(maxsize=16384)
    def objective_coord(self, quest_id: int, objective_id: int) -> tuple[int, int] | None:
        quest = self.catalog.by_id.get(int(quest_id))
        if quest is None:
            return None
        for step in quest_solution_steps(quest):
            for objective in step.objectives:
                if objective.objective_id is not None and int(objective.objective_id) == int(objective_id):
                    return _coord_from_text(objective.position)
        return None


class ForensicAudit:
    def __init__(self, route: dict[str, Any], final: dict[str, Any]) -> None:
        self.route = route
        self.final = final
        self.hard: list[dict[str, Any]] = []
        self.warn: list[dict[str, Any]] = []
        self.repairs: list[dict[str, Any]] = []
        self.catalog = QuestProvider(data_dir=RAW_QUEST_DATA_DIR).get_catalog()
        self.docs = DocumentaryIndex(self.catalog)
        self.raw_quests = doduda_rows(RAW_QUEST_DATA_DIR / "quests.json")
        self.raw_objectives = doduda_rows(RAW_QUEST_DATA_DIR / "quest_objectives.json")
        self.raw_maps = doduda_rows(RAW_QUEST_DATA_DIR / "maps_information.json")
        self.steps = [row for row in route.get("steps", []) or [] if isinstance(row, dict)]
        self.final_by_qid = {
            int(row.get("entity_id")): row
            for row in _iter_final_steps(final)
            if _safe_int(row.get("entity_id")) is not None
        }
        self.occurrences: dict[str, Occurrence] = {}
        self.occurrences_by_qid: dict[int, list[Occurrence]] = defaultdict(list)
        self._collect_occurrences()
        self.route_qids = tuple(
            dict.fromkeys(
                occ.quest_id
                for step in self.steps
                for _section, row in _iter_action_rows(step)
                if (aid := str(row.get("action_id") or ""))
                and (occ := self.occurrences.get(aid)) is not None
            )
        )
        pseudo = SimpleNamespace(quest_ids=self.route_qids)
        self.adapter_result = AdventureRouteAdapter(
            self.catalog,
            pseudo,
            raw_data_dir=RAW_QUEST_DATA_DIR,
        ).build()
        self.expected = {action.action_id: action for action in self.adapter_result.actions}
        self.completion_actions = self._completion_action_ids()

    def error(self, code: str, **data: Any) -> None:
        self.hard.append({"code": code, **data})

    def warning(self, code: str, **data: Any) -> None:
        self.warn.append({"code": code, **data})

    def repair(self, code: str, **data: Any) -> None:
        self.repairs.append({"code": code, **data})

    def _collect_occurrences(self) -> None:
        for step_pos, step in enumerate(self.steps):
            card_index = _safe_int(step.get("index")) or step_pos + 1
            for section, row in _iter_action_rows(step):
                aid = str(row.get("action_id") or "").strip()
                qid = _safe_int(row.get("quest_id"))
                if not aid or qid is None:
                    self.error("action_row_missing_identity", card_index=card_index, section=section, row=row)
                    continue
                occurrence = Occurrence(aid, qid, step_pos, card_index, section, row)
                if aid in self.occurrences:
                    self.error(
                        "duplicate_action_id",
                        action_id=aid,
                        first_card=self.occurrences[aid].card_index,
                        second_card=card_index,
                    )
                    continue
                self.occurrences[aid] = occurrence
                self.occurrences_by_qid[qid].append(occurrence)

    def _completion_action_ids(self) -> dict[int, tuple[str, ...]]:
        by_group: dict[str, list[str]] = defaultdict(list)
        group_qid: dict[str, int] = {}
        for action in self.adapter_result.actions:
            if action.completion_group:
                by_group[action.completion_group].append(action.action_id)
                group_qid[action.completion_group] = int(action.quest_id)
        result: dict[int, tuple[str, ...]] = {}
        for group, ids in by_group.items():
            result[group_qid[group]] = tuple(ids)
        return result

    def map_coord(self, map_id: int | None) -> tuple[int, int] | None:
        if map_id is None:
            return None
        row = self.raw_maps.get(int(map_id), {})
        x, y = _safe_coord(row.get("posX")), _safe_coord(row.get("posY"))
        return (x, y) if x is not None and y is not None else None

    def raw_start_map_ids(self, quest_id: int) -> tuple[int, ...]:
        raw = self.raw_quests.get(int(quest_id), {})
        ids: list[int] = []
        for row in _array(raw.get("startPosition")):
            if not isinstance(row, dict):
                continue
            ident = _safe_int(row.get("mapId"))
            if ident is not None and ident not in ids:
                ids.append(ident)
        return tuple(ids)

    def raw_objective_map_id(self, objective_id: int | None) -> int | None:
        if objective_id is None:
            return None
        return _safe_int(self.raw_objectives.get(int(objective_id), {}).get("mapId"))

    def _documentary_candidates_for_card(self, step: dict[str, Any]) -> set[tuple[int, int]]:
        values: set[tuple[int, int]] = set()
        for section, row in _iter_action_rows(step):
            qid = _safe_int(row.get("quest_id"))
            if qid is None:
                continue
            if section == "a_prendre":
                _npc, coord, _zone = self.docs.start(qid)
            else:
                oid = _safe_int(row.get("objective_id"))
                coord = self.docs.objective_coord(qid, oid) if oid is not None else None
            if coord is not None:
                values.add(coord)
        return values

    def _best_coord_for_card(self, step: dict[str, Any]) -> tuple[tuple[int, int] | None, str]:
        current = _explicit_coord(step)
        if current is not None:
            return current, "route"
        destination = _coord_from_text(step.get("destination"))
        if destination is not None:
            return destination, "destination"
        map_coord = self.map_coord(_safe_int(step.get("map_id")))
        if map_coord is not None:
            return map_coord, "raw_map"
        docs = self._documentary_candidates_for_card(step)
        if len(docs) == 1:
            return next(iter(docs)), "documentary_unique"
        return None, ""

    def safe_repair(self) -> None:
        # First normalize every card without touching global card order.
        for step_pos, step in enumerate(self.steps):
            card_index = _safe_int(step.get("index")) or step_pos + 1
            before = _explicit_coord(step)
            recovered, source = self._best_coord_for_card(step)
            if before is None and recovered is not None:
                step["x"], step["y"] = recovered
                self.repair("coordinate_recovered", card_index=card_index, coordinate=list(recovered), source=source)
            elif before is None:
                if step.get("x") is not None or step.get("y") is not None:
                    step["x"], step["y"] = None, None
                    self.repair("invalid_coordinate_cleared", card_index=card_index)

            coord = _explicit_coord(step)
            destination = str(step.get("destination") or "").strip()
            if str(SENTINEL_COORD) in destination:
                zone = str(step.get("subzone") or step.get("zone") or "").strip()
                step["destination"] = f"[{coord[0]},{coord[1]}] — {zone}" if coord and zone else f"[{coord[0]},{coord[1]}]" if coord else zone or "Localisation à confirmer"
                self.repair("sentinel_destination_rebuilt", card_index=card_index)

            sequence = self._topological_sequence_for_card(step)
            if sequence and step.get("action_sequence") != sequence:
                step["action_sequence"] = sequence
                self.repair("action_sequence_written", card_index=card_index, action_count=len(sequence))

        # ENSUITE is derived from the actual next card, never from stale payload.
        for step_pos, step in enumerate(self.steps):
            card_index = _safe_int(step.get("index")) or step_pos + 1
            if step_pos + 1 >= len(self.steps):
                if step.get("ensuite") is not None:
                    step["ensuite"] = None
                    self.repair("final_next_cleared", card_index=card_index)
                continue
            nxt = self.steps[step_pos + 1]
            coord = _explicit_coord(nxt)
            expected = {
                "destination": str(nxt.get("destination") or ""),
                "map_id": nxt.get("map_id"),
                "x": coord[0] if coord else None,
                "y": coord[1] if coord else None,
                "zone": str(nxt.get("zone") or ""),
                "subzone": str(nxt.get("subzone") or ""),
            }
            if step.get("ensuite") != expected:
                step["ensuite"] = expected
                self.repair("next_rebuilt", card_index=card_index, next_card=_safe_int(nxt.get("index")) or step_pos + 2)

    def _topological_sequence_for_card(self, step: dict[str, Any]) -> list[str]:
        rows = [row for _section, row in _iter_action_rows(step)]
        ids = [str(row.get("action_id") or "") for row in rows if row.get("action_id")]
        present = set(ids)
        if not ids:
            return []
        deps: dict[str, set[str]] = {aid: set() for aid in ids}
        for aid in ids:
            action = self.expected.get(aid)
            if action is None:
                continue
            deps[aid].update(dep for dep in action.prerequisites_actions if dep in present)
            if action.is_start:
                for qid in action.prerequisites_quests:
                    deps[aid].update(dep for dep in self.completion_actions.get(int(qid), ()) if dep in present)
                for group in action.prerequisite_quest_alternatives:
                    for qid in group:
                        deps[aid].update(dep for dep in self.completion_actions.get(int(qid), ()) if dep in present)

        output: list[str] = []
        remaining = set(ids)
        while remaining:
            ready = [aid for aid in remaining if not (deps.get(aid, set()) & remaining)]
            if not ready:
                self.error(
                    "same_card_dependency_cycle",
                    card_index=_safe_int(step.get("index")),
                    action_ids=sorted(remaining),
                )
                return ids
            ready.sort(key=self._action_sort_key)
            for aid in ready:
                output.append(aid)
                remaining.remove(aid)
        return output

    def _action_sort_key(self, aid: str) -> tuple[int, int, int, str]:
        action = self.expected.get(aid)
        if action is None:
            return (10**9, 10**9, 10**9, aid)
        return (int(action.quest_order), int(action.objective_order), int(action.quest_id), aid)

    def run_checks(self) -> None:
        self._check_sentinels()
        self._check_scope_leaks()
        self._check_action_contract()
        self._check_locations()
        self._check_order()
        self._check_next_links()
        self._check_branch_contract()

    def _check_sentinels(self) -> None:
        for path in _recursive_sentinel_paths(self.route):
            self.error("sentinel_value_present", path=path)

    def _check_scope_leaks(self) -> None:
        route_set = set(self.route_qids)
        temporal_branch = self.route.get("conditional_branches") if isinstance(self.route.get("conditional_branches"), dict) else {}
        temporal_ids = {
            int(v) for v in ((temporal_branch.get("qq_calendar_card") or {}).get("quest_ids") or [])
            if _safe_int(v) is not None
        }
        for qid in sorted(route_set & temporal_ids):
            self.error("temporal_quest_leaked_into_permanent_route", quest_id=qid, quest_name=getattr(self.catalog.by_id.get(qid), "name", ""))

        for qid in self.route_qids:
            row = self.final_by_qid.get(int(qid), {})
            policy = str(row.get("runtime_policy") or "always_when_unlocked")
            cond = row.get("condition") if isinstance(row.get("condition"), dict) else {}
            alignment = _norm(cond.get("alignment"))
            if policy in TEMPORAL_POLICIES:
                self.error("non_permanent_policy_in_common_route", quest_id=qid, policy=policy, quest_name=getattr(self.catalog.by_id.get(qid), "name", ""))
            if policy in CONDITIONAL_POLICIES or cond.get("class") or cond.get("order"):
                self.error("conditional_branch_quest_in_common_route", quest_id=qid, policy=policy, condition=cond)
            if alignment and alignment != "bonta":
                self.error("non_bonta_quest_in_common_route", quest_id=qid, alignment=alignment)

    def _check_action_contract(self) -> None:
        expected_ids = set(self.expected)
        actual_ids = set(self.occurrences)
        for aid in sorted(actual_ids - expected_ids):
            self.error("unexpected_route_action", action_id=aid)
        for aid in sorted(expected_ids - actual_ids):
            self.error("expected_action_missing_from_route", action_id=aid, quest_id=int(self.expected[aid].quest_id))
        for aid in sorted(actual_ids & expected_ids):
            occ = self.occurrences[aid]
            action = self.expected[aid]
            if int(action.quest_id) != occ.quest_id:
                self.error("action_quest_id_mismatch", action_id=aid, route_quest_id=occ.quest_id, expected_quest_id=int(action.quest_id))
            route_name = str(occ.row.get("quest_name") or "").strip()
            quest = self.catalog.by_id.get(occ.quest_id)
            if route_name and quest is not None and _norm(route_name) != _norm(quest.name):
                self.error("quest_name_mismatch", action_id=aid, route_name=route_name, catalog_name=quest.name)

    def _check_locations(self) -> None:
        for step_pos, step in enumerate(self.steps):
            card_index = _safe_int(step.get("index")) or step_pos + 1
            route_coord = _explicit_coord(step)
            map_id = _safe_int(step.get("map_id"))
            raw_map_coord = self.map_coord(map_id)
            destination_coord = _coord_from_text(step.get("destination"))

            if (step.get("x") is None) != (step.get("y") is None):
                self.error("partial_coordinate_pair", card_index=card_index, x=step.get("x"), y=step.get("y"))
            if raw_map_coord is not None and route_coord is not None and raw_map_coord != route_coord:
                self.error("card_coordinate_disagrees_with_raw_map", card_index=card_index, map_id=map_id, route=list(route_coord), raw_map=list(raw_map_coord))
            if destination_coord is not None and route_coord is not None and destination_coord != route_coord:
                self.error("destination_coordinate_mismatch", card_index=card_index, route=list(route_coord), destination=list(destination_coord))

            expected_map_ids: set[int] = set()
            documentary_coords = self._documentary_candidates_for_card(step)
            for section, row in _iter_action_rows(step):
                aid = str(row.get("action_id") or "")
                action = self.expected.get(aid)
                if action is not None and action.location.map_id is not None:
                    expected_map_ids.add(int(action.location.map_id))
                qid = _safe_int(row.get("quest_id"))
                oid = _safe_int(row.get("objective_id"))
                if qid is None:
                    continue
                if section == "a_prendre":
                    raw_start_ids = self.raw_start_map_ids(qid)
                    if len(raw_start_ids) == 1:
                        expected_map_ids.add(raw_start_ids[0])
                        if map_id is not None and map_id != raw_start_ids[0]:
                            self.error("quest_start_map_mismatch", card_index=card_index, quest_id=qid, route_map_id=map_id, raw_start_map_id=raw_start_ids[0])
                    npc, doc_coord, _doc_zone = self.docs.start(qid)
                    if not npc:
                        self.warning("quest_start_npc_not_documented", card_index=card_index, quest_id=qid, quest_name=getattr(self.catalog.by_id.get(qid), "name", ""))
                    if doc_coord and route_coord and raw_map_coord and doc_coord != route_coord:
                        self.warning("documentary_start_position_conflicts_with_game_map", card_index=card_index, quest_id=qid, documentary=list(doc_coord), game_route=list(route_coord))
                else:
                    raw_oid_map = self.raw_objective_map_id(oid)
                    if raw_oid_map is not None:
                        expected_map_ids.add(raw_oid_map)
                        if map_id is not None and map_id != raw_oid_map:
                            self.error("objective_map_mismatch", card_index=card_index, quest_id=qid, objective_id=oid, route_map_id=map_id, raw_objective_map_id=raw_oid_map)
                    doc_coord = self.docs.objective_coord(qid, oid) if oid is not None else None
                    if doc_coord and route_coord and raw_map_coord and doc_coord != route_coord:
                        self.warning("documentary_objective_position_conflicts_with_game_map", card_index=card_index, quest_id=qid, objective_id=oid, documentary=list(doc_coord), game_route=list(route_coord))

            if len(expected_map_ids) > 1:
                self.error("multiple_raw_maps_grouped_in_one_card", card_index=card_index, raw_map_ids=sorted(expected_map_ids))
            if len(expected_map_ids) == 1 and map_id is not None and map_id not in expected_map_ids:
                self.error("card_map_id_mismatch", card_index=card_index, route_map_id=map_id, expected_map_id=next(iter(expected_map_ids)))

            should_have_coord = raw_map_coord is not None or destination_coord is not None or len(documentary_coords) == 1
            if should_have_coord and route_coord is None:
                self.error("recoverable_card_missing_coordinate", card_index=card_index, map_id=map_id, documentary_candidates=[list(v) for v in sorted(documentary_coords)])
            elif route_coord is None:
                self.warning("card_has_no_travel_coordinate", card_index=card_index, map_id=map_id, destination=step.get("destination"))

    def _sequence_positions(self) -> dict[str, tuple[int, int]]:
        result: dict[str, tuple[int, int]] = {}
        for step_pos, step in enumerate(self.steps):
            sequence = [str(v) for v in (step.get("action_sequence") or []) if str(v)]
            if not sequence:
                sequence = self._topological_sequence_for_card(step)
            for local_pos, aid in enumerate(sequence):
                result[aid] = (step_pos, local_pos)
        return result

    def _quest_completion_position(self, qid: int, positions: dict[str, tuple[int, int]]) -> tuple[int, int] | None:
        ids = self.completion_actions.get(int(qid), ())
        values = [positions[aid] for aid in ids if aid in positions]
        return max(values) if values and len(values) == len(ids) else None

    def _check_order(self) -> None:
        positions = self._sequence_positions()
        for aid, action in self.expected.items():
            current = positions.get(aid)
            if current is None:
                continue
            for dep in action.prerequisites_actions:
                dep_pos = positions.get(dep)
                if dep_pos is None:
                    self.error("action_dependency_missing", action_id=aid, dependency_action_id=dep)
                elif dep_pos >= current:
                    self.error("action_dependency_order_violation", action_id=aid, dependency_action_id=dep, dependency_position=list(dep_pos), action_position=list(current))
            if action.is_start:
                for qid in action.prerequisites_quests:
                    dep_pos = self._quest_completion_position(int(qid), positions)
                    if dep_pos is None:
                        if int(qid) in self.route_qids:
                            self.error("quest_prerequisite_completion_unverifiable", quest_id=int(action.quest_id), prerequisite_quest_id=int(qid), action_id=aid)
                        continue
                    if dep_pos >= current:
                        self.error("quest_prerequisite_order_violation", quest_id=int(action.quest_id), prerequisite_quest_id=int(qid), prerequisite_position=list(dep_pos), start_position=list(current))

                if action.prerequisite_quest_alternatives:
                    satisfied = False
                    represented = False
                    for group in action.prerequisite_quest_alternatives:
                        dep_positions = [self._quest_completion_position(int(qid), positions) for qid in group]
                        if any(int(qid) in self.route_qids for qid in group):
                            represented = True
                        if dep_positions and all(value is not None and value < current for value in dep_positions):
                            satisfied = True
                            break
                    if represented and not satisfied:
                        self.error("alternative_quest_prerequisite_order_violation", quest_id=int(action.quest_id), action_id=aid, alternatives=[sorted(map(int, group)) for group in action.prerequisite_quest_alternatives])

            level = _safe_int(self.steps[current[0]].get("planned_at_level")) or 0
            min_level = _safe_int(action.condition.min_level) or 0
            if level < min_level:
                self.error("planned_level_below_action_requirement", action_id=aid, quest_id=int(action.quest_id), planned_level=level, required_level=min_level)

        levels = [_safe_int(step.get("planned_at_level")) or 0 for step in self.steps]
        for index in range(1, len(levels)):
            if levels[index] < levels[index - 1]:
                self.error("planned_level_regression", previous_card=index, previous_level=levels[index - 1], card=index + 1, level=levels[index])

    def _check_next_links(self) -> None:
        for step_pos, step in enumerate(self.steps):
            card_index = _safe_int(step.get("index")) or step_pos + 1
            nxt = step.get("ensuite") if isinstance(step.get("ensuite"), dict) else None
            if step_pos + 1 >= len(self.steps):
                if nxt:
                    self.error("final_card_has_next", card_index=card_index, next=nxt)
                continue
            actual_next = self.steps[step_pos + 1]
            if not nxt:
                self.error("missing_next_link", card_index=card_index, expected_next=_safe_int(actual_next.get("index")) or step_pos + 2)
                continue
            for field in ("map_id", "x", "y"):
                expected = actual_next.get(field)
                got = nxt.get(field)
                if field in {"x", "y"}:
                    expected = _safe_coord(expected)
                    got = _safe_coord(got)
                if got != expected:
                    self.error("next_link_mismatch", card_index=card_index, field=field, got=got, expected=expected)

    def _check_branch_contract(self) -> None:
        branches = self.route.get("conditional_branches") if isinstance(self.route.get("conditional_branches"), dict) else {}
        class_card = branches.get("class_card") if isinstance(branches.get("class_card"), dict) else {}
        class_options = [row for row in class_card.get("options", []) or [] if isinstance(row, dict)]
        class_qids = [_safe_int(row.get("quest_id")) for row in class_options]
        class_qids = [qid for qid in class_qids if qid is not None]
        if len(class_qids) != len(set(class_qids)):
            self.error("duplicate_class_branch_quest_ids")
        if set(class_qids) & set(self.route_qids):
            self.error("class_branch_quest_leaked_into_common_route", quest_ids=sorted(set(class_qids) & set(self.route_qids)))

        order_cards = [row for row in branches.get("order_cards", []) or [] if isinstance(row, dict)]
        bonta_by_order: dict[str, dict[int, int]] = defaultdict(dict)
        for card in order_cards:
            rank = _safe_int(card.get("rank"))
            if rank is None:
                continue
            for option in card.get("options", []) or []:
                if not isinstance(option, dict):
                    continue
                name = str(option.get("order") or "").strip()
                key = _norm(name)
                if key in {"coeur vaillant", "oeil attentif", "esprit salvateur"}:
                    qid = _safe_int(option.get("quest_id"))
                    if qid is not None:
                        bonta_by_order[key][rank] = qid
        expected_ranks = {20, 40, 60, 80, 100}
        for order in ("coeur vaillant", "oeil attentif", "esprit salvateur"):
            got = set(bonta_by_order.get(order, {}))
            if got != expected_ranks:
                self.error("bonta_order_ranks_incomplete", order=order, ranks=sorted(got), expected=sorted(expected_ranks))
            leaked = set(bonta_by_order.get(order, {}).values()) & set(self.route_qids)
            if leaked:
                self.error("bonta_order_quest_leaked_into_common_route", order=order, quest_ids=sorted(leaked))

    def result(self) -> dict[str, Any]:
        sentinel_paths = _recursive_sentinel_paths(self.route)
        missing_coords = [
            _safe_int(step.get("index")) or index + 1
            for index, step in enumerate(self.steps)
            if _explicit_coord(step) is None
        ]
        policy_counts: dict[str, int] = defaultdict(int)
        for qid in self.route_qids:
            policy_counts[str(self.final_by_qid.get(qid, {}).get("runtime_policy") or "always_when_unlocked")] += 1
        return {
            "schema_version": 1,
            "route_schema_version": self.route.get("schema_version"),
            "summary": {
                "route_card_count": len(self.steps),
                "route_quest_count": len(set(self.route_qids)),
                "route_action_count": len(self.occurrences),
                "expected_action_count": len(self.expected),
                "hard_error_count": len(self.hard),
                "warning_count": len(self.warn),
                "safe_repair_count": len(self.repairs),
                "cards_without_travel_coordinate": len(missing_coords),
                "sentinel_value_count": len(sentinel_paths),
            },
            "policy_counts": dict(sorted(policy_counts.items())),
            "hard_checks": {
                "no_hard_errors": not self.hard,
                "no_sentinel_coordinates": not sentinel_paths,
                "all_expected_actions_present": not any(row["code"] == "expected_action_missing_from_route" for row in self.hard),
                "all_action_dependencies_ordered": not any("order_violation" in row["code"] for row in self.hard),
                "no_temporal_quest_in_permanent_route": not any("temporal" in row["code"] or "non_permanent_policy" in row["code"] for row in self.hard),
                "no_conditional_branch_in_common_route": not any("conditional_branch" in row["code"] or "branch_quest_leaked" in row["code"] for row in self.hard),
                "raw_map_ids_match_cards": not any("map_mismatch" in row["code"] or "multiple_raw_maps" in row["code"] for row in self.hard),
                "next_links_match_actual_route": not any(row["code"] in {"next_link_mismatch", "missing_next_link", "final_card_has_next"} for row in self.hard),
            },
            "cards_without_travel_coordinate": missing_coords,
            "repairs": self.repairs,
            "hard_errors": self.hard,
            "warnings": self.warn,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--repair-safe", action="store_true")
    args = parser.parse_args()

    if not ROUTE_PATH.exists() or not FINAL_PATH.exists():
        print("Artefacts V5 absents. Lance d'abord tools/run_guide_ultime_v5.ps1", file=sys.stderr)
        return 2

    route = _read_json(ROUTE_PATH)
    final = _read_json(FINAL_PATH)
    audit = ForensicAudit(route, final)
    if args.repair_safe:
        audit.safe_repair()
        _write_json(ROUTE_PATH, route)
        # Rebuild occurrence indexes after safe route enrichment.
        audit = ForensicAudit(route, final)
        # Keep repair log from the first pass.
        repair_log = list(ForensicAudit(_read_json(ROUTE_PATH), final).repairs)
        # The constructor above has no repairs; preserve the actual prior log.
        # It is attached below from the pre-recheck pass through a local copy.
        audit.repairs = []
        # Re-run safe repair idempotently only to capture no-op semantics.
        audit.safe_repair()
        # The second pass should be idempotent. Report only any unexpected changes.
        if audit.repairs:
            audit.warning("safe_repair_not_idempotent", repairs=copy.deepcopy(audit.repairs))
        # Read back and perform checks on final persisted form.
        route = _read_json(ROUTE_PATH)
        audit = ForensicAudit(route, final)
        audit.repairs = repair_log

    audit.run_checks()
    result = audit.result()
    _write_json(OUT_PATH, result)

    summary = result["summary"]
    print(
        "FORENSIC "
        f"cards={summary['route_card_count']} quests={summary['route_quest_count']} "
        f"actions={summary['route_action_count']} hard={summary['hard_error_count']} "
        f"warnings={summary['warning_count']} no_coord={summary['cards_without_travel_coordinate']} "
        f"sentinel={summary['sentinel_value_count']}"
    )
    print(f"Audit: {OUT_PATH}")
    if args.strict and result["hard_errors"]:
        print("FORENSIC STRICT FAIL", file=sys.stderr)
        for row in result["hard_errors"][:30]:
            print(json.dumps(row, ensure_ascii=False), file=sys.stderr)
        if len(result["hard_errors"]) > 30:
            print(f"... +{len(result['hard_errors']) - 30} erreurs dans l'audit JSON", file=sys.stderr)
        return 1
    print("FORENSIC STRICT PASS" if args.strict else "FORENSIC AUDIT DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
