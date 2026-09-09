from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout

from app.modules.encyclopedia.services.guide_quest_view_model import (
    clean_requirement_line,
    clean_text,
    quest_solution_steps,
    quest_start_info,
)
from app.modules.encyclopedia.views.guide_ultime_generated_view import GuideUltimeCard
from app.quest_catalog import normalize_text


SENTINEL_COORD = -2147483648
COORD_RE = re.compile(r"\[(-?\d+)\s*,\s*(-?\d+)\]")


@dataclass(frozen=True, slots=True)
class ObjectiveWalkthrough:
    text: str = ""
    position: str = ""
    step_title: str = ""
    step_description: str = ""


class QuestWalkthroughIndex:
    """Read-only bridge between the GPS route and existing quest documentary data."""

    def __init__(self, quest_provider: Any = None, quest_graph: Any = None) -> None:
        self.quest_provider = quest_provider
        self.quest_graph = quest_graph

    @lru_cache(maxsize=512)
    def quest(self, quest_id: int) -> Any:
        if self.quest_provider is None:
            return None
        try:
            return self.quest_provider.get_quest(int(quest_id))
        except Exception:
            return None

    @lru_cache(maxsize=512)
    def start_details(self, quest_id: int) -> tuple[str, str, str]:
        quest = self.quest(int(quest_id))
        if quest is None:
            return "", "", ""
        info = quest_start_info(quest)
        npc = clean_text(info.npc)
        position = clean_text(info.position)
        zone = clean_text(info.zone)
        if not _valid_position_text(position):
            return npc, "", ""
        return npc, position, zone

    @lru_cache(maxsize=4096)
    def objective(self, quest_id: int, objective_id: int) -> ObjectiveWalkthrough:
        quest = self.quest(int(quest_id))
        if quest is None:
            return ObjectiveWalkthrough()
        for step in quest_solution_steps(quest):
            for objective in step.objectives:
                if objective.objective_id is None or int(objective.objective_id) != int(objective_id):
                    continue
                position = clean_text(objective.position)
                if not _valid_position_text(position):
                    position = ""
                return ObjectiveWalkthrough(
                    text=clean_text(objective.text),
                    position=position,
                    step_title=clean_text(step.title),
                    step_description=clean_text(step.description),
                )
        return ObjectiveWalkthrough()

    @lru_cache(maxsize=512)
    def quest_name(self, quest_id: int) -> str:
        quest = self.quest(int(quest_id))
        return clean_text(getattr(quest, "name", "")) if quest is not None else ""

    @lru_cache(maxsize=512)
    def useful_prerequisites(self, quest_id: int) -> tuple[str, ...]:
        quest = self.quest(int(quest_id))
        if quest is None:
            return ()
        previous_names: set[str] = set()
        if self.quest_graph is not None:
            try:
                previous_ids = self.quest_graph.previous_ids(int(quest_id))
            except Exception:
                previous_ids = ()
            for previous_id in previous_ids or ():
                name = self.quest_name(int(previous_id))
                if name:
                    previous_names.add(normalize_text(name))
        rows: list[str] = []
        seen: set[str] = set()
        for raw in getattr(quest, "prerequisites", ()) or ():
            text = clean_requirement_line(str(raw or ""))
            key = normalize_text(text)
            if not text or not key:
                continue
            if key in previous_names:
                continue
            if key in {"quete_precedente", "quete_precedente_de_la_serie", "suite_de_quetes"}:
                continue
            if key not in seen:
                seen.add(key)
                rows.append(text)
        return tuple(rows)


class GuideUltimeWalkthroughCard(GuideUltimeCard):
    """GPS card that tells the player exactly how to execute the quest action."""

    def __init__(self, *args, walkthrough: QuestWalkthroughIndex, **kwargs) -> None:
        self.walkthrough = walkthrough
        self._ordered_actions_rendered = False
        super().__init__(*args, **kwargs)

    @staticmethod
    def _location_text(card: dict[str, Any]) -> str:
        coords = _card_coords(card)
        zone = str(card.get("subzone") or card.get("zone") or "").strip()
        if coords and zone:
            return f"{zone}  •  {coords}"
        if zone:
            return zone
        if coords:
            return coords
        destination = _strip_sentinel_position(str(card.get("destination") or "").strip())
        return destination or "Destination"

    def _add_actions(self, root: QVBoxLayout, title: str, rows: Any, *, start_rows: bool) -> None:
        sequence = [str(value) for value in (self.card.get("action_sequence") or []) if str(value).strip()]
        if sequence:
            if self._ordered_actions_rendered:
                return
            self._ordered_actions_rendered = True
            self._add_actions_in_causal_order(root, sequence)
            return
        self._add_action_group(root, title, rows, start_rows=start_rows)

    def _add_actions_in_causal_order(self, root: QVBoxLayout, sequence: list[str]) -> None:
        by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        for section in ("a_prendre", "a_faire_ici"):
            for row in self.card.get(section, []) or []:
                if not isinstance(row, dict):
                    continue
                action_id = str(row.get("action_id") or "").strip()
                if action_id:
                    by_id[action_id] = (section, row)

        ordered: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for action_id in sequence:
            found = by_id.get(action_id)
            if found is None:
                continue
            ordered.append(found)
            seen.add(action_id)
        for action_id, found in by_id.items():
            if action_id not in seen:
                ordered.append(found)

        if not ordered:
            return
        body = self._section(root, "PARCOURS SUR CETTE CARTE")
        current_section = ""
        for section, row in ordered:
            if section != current_section:
                current_section = section
                label = QLabel("À PRENDRE" if section == "a_prendre" else "À FAIRE ICI")
                label.setObjectName("GuideUltimeInlineSectionTitle")
                body.addWidget(label)
            self._add_action_row(body, row, start_rows=(section == "a_prendre"))

    def _add_action_group(self, root: QVBoxLayout, title: str, rows: Any, *, start_rows: bool) -> None:
        values = [row for row in (rows or []) if isinstance(row, dict)]
        if not values:
            return
        body = self._section(root, title)
        for row in values:
            self._add_action_row(body, row, start_rows=start_rows)

    def _add_action_row(self, body: QVBoxLayout, row: dict[str, Any], *, start_rows: bool) -> None:
        qid = self._safe_int(row.get("quest_id"))
        oid = self._safe_int(row.get("objective_id"))
        quest_name = str(row.get("quest_name") or "").strip()
        if qid is not None:
            quest_name = self.walkthrough.quest_name(qid) or quest_name or f"Quête #{qid}"
        if start_rows:
            self._add_start_instruction(body, row, qid, quest_name)
            return

        checked = self.service.action_completed(self.character_key, row)
        detail = self.walkthrough.objective(qid, oid) if qid is not None and oid is not None else ObjectiveWalkthrough()
        instruction = detail.text or str(row.get("title") or "Action").strip()
        line_text = f"{quest_name} — {instruction}" if quest_name else instruction
        line = QCheckBox(line_text)
        line.setObjectName("GuideUltimeActionCheck")
        line.setChecked(checked)
        line.setProperty("state", "done" if checked else "todo")
        if qid is None or oid is None:
            line.setEnabled(False)
            line.setToolTip("Instruction de route sans objectif local validable automatiquement.")
        else:
            line.setToolTip("Objectif partagé avec la fiche Quête.")
            line.toggled.connect(
                lambda value, quest_id=qid, objective_id=oid: self._toggle_objective(quest_id, objective_id, value)
            )
        body.addWidget(line)
        position = detail.position or self._row_position(row)
        self._add_detail_label(body, self._position_label(position), checked)
        if detail.step_title:
            self._add_detail_label(body, f"Étape : {detail.step_title}", checked)
        if detail.step_description and self._different_text(detail.step_description, instruction):
            self._add_detail_label(body, detail.step_description, checked)

    def _add_progress_also(self, root: QVBoxLayout) -> None:
        progress = self.card.get("progresse_aussi") if isinstance(self.card.get("progresse_aussi"), dict) else {}
        primary_quests = {
            qid
            for section in ("a_prendre", "a_faire_ici")
            for row in self.card.get(section, []) or []
            if isinstance(row, dict) and (qid := self._safe_int(row.get("quest_id"))) is not None
        }
        quest_rows: list[tuple[int, str]] = []
        for raw in progress.get("quest_ids", []) or []:
            qid = self._safe_int(raw)
            if qid is None or qid in primary_quests:
                continue
            name = self.walkthrough.quest_name(qid)
            if name:
                quest_rows.append((qid, name))
        monster = [row for row in self.card.get("succes_monstres_a_faire", []) or [] if isinstance(row, dict) and str(row.get("name") or "").strip()]
        dungeon = [row for row in self.card.get("succes_donjon_a_faire", []) or [] if isinstance(row, dict) and str(row.get("name") or "").strip()]
        dungeon_context = self.card.get("dungeon_context") if isinstance(self.card.get("dungeon_context"), dict) else {}
        ocre = [row for row in dungeon_context.get("ocre_capture_targets", []) or [] if isinstance(row, dict) and (str(row.get("boss") or "").strip() or str(row.get("action") or "").strip())]
        if not quest_rows and not monster and not dungeon and not ocre:
            return
        body = self._section(root, "PROGRESSE AUSSI")
        for qid, name in quest_rows:
            done = self.service.quest_progress.is_quest_completed(self.character_key, qid)
            label = QLabel(f"{'✓' if done else '•'} {name}")
            label.setProperty("state", "done" if done else "todo")
            label.setObjectName("GuideUltimeInfoLine")
            label.setWordWrap(True)
            body.addWidget(label)
        for row in monster:
            self._add_success_line(body, row, "Monstres")
        for row in dungeon:
            self._add_success_line(body, row, "Donjon")
        for row in ocre:
            action = str(row.get("action") or "Capture Ocre").strip()
            boss = str(row.get("boss") or "").strip()
            label = QLabel(f"• Ocre : {action}{' — ' + boss if boss else ''}")
            label.setObjectName("GuideUltimeInfoLine")
            label.setWordWrap(True)
            body.addWidget(label)

    def _add_runtime(self, root: QVBoxLayout) -> None:
        rows: list[str] = []
        seen: set[str] = set()
        for qid in self.service.card_quest_ids(self.card):
            quest_name = self.walkthrough.quest_name(qid)
            for prerequisite in self.walkthrough.useful_prerequisites(qid):
                key = normalize_text(prerequisite)
                if not key or key in seen:
                    continue
                seen.add(key)
                rows.append(f"{prerequisite} — pour {quest_name}" if quest_name else prerequisite)
        for section in ("succes_monstres_a_faire", "succes_donjon_a_faire"):
            for success in self.card.get(section, []) or []:
                if not isinstance(success, dict):
                    continue
                success_name = str(success.get("name") or "").strip()
                for field in ("prerequisites", "requirements", "conditions"):
                    raw = success.get(field)
                    values = raw if isinstance(raw, list) else [raw] if raw else []
                    for value in values:
                        text = clean_text(value)
                        key = normalize_text(text)
                        if not text or not key or key in seen:
                            continue
                        seen.add(key)
                        rows.append(f"{text} — pour {success_name}" if success_name else text)
        if not rows:
            return
        body = self._section(root, "PRÉREQUIS UTILES")
        for text in rows:
            label = QLabel(f"• {text}")
            label.setObjectName("GuideUltimeInfoLine")
            label.setWordWrap(True)
            body.addWidget(label)

    def _add_start_instruction(self, body: QVBoxLayout, row: dict[str, Any], quest_id: int | None, quest_name: str) -> None:
        completed = bool(quest_id is not None and self.service.quest_progress.is_quest_completed(self.character_key, int(quest_id)))
        marker = "✓" if completed else "•"
        title = QLabel(f"{marker} {quest_name or str(row.get('title') or 'Prendre la quête')}")
        title.setObjectName("GuideUltimeQuestTakeTitle")
        title.setProperty("state", "done" if completed else "todo")
        title.setWordWrap(True)
        body.addWidget(title)
        npc = position = zone = ""
        if quest_id is not None:
            npc, position, zone = self.walkthrough.start_details(int(quest_id))
        if npc:
            self._add_detail_label(body, f"Parler à {npc} pour prendre « {quest_name} ».", completed, important=True)
        else:
            fallback = str(row.get("title") or "").strip()
            if fallback and fallback.casefold() not in {quest_name.casefold(), f"prendre — {quest_name}".casefold()}:
                self._add_detail_label(body, fallback, completed, important=True)
        if position:
            self._add_detail_label(body, f"Départ : {self._join_location(position, zone)}", completed)
        else:
            location = self._location_text(self.card)
            if location and location != "Destination":
                self._add_detail_label(body, f"Départ : {location}", completed)

    def _add_next(self, root: QVBoxLayout) -> None:
        nxt = self.card.get("ensuite") if isinstance(self.card.get("ensuite"), dict) else None
        candidate = nxt if nxt is not None and _card_coords(nxt) else None
        if candidate is None and self.index + 1 < len(self.service.cards):
            next_card = self.service.cards[self.index + 1]
            candidate = next_card if _card_coords(next_card) else None
        if candidate is None:
            return
        coords = _card_coords(candidate)
        if not coords:
            return
        zone = str(candidate.get("subzone") or candidate.get("zone") or "").strip()
        body = self._section(root, "ENSUITE")
        label = QLabel(f"→ {coords}{'  ' + zone if zone else ''}")
        label.setObjectName("GuideUltimeNextLine")
        body.addWidget(label)

    def _row_position(self, row: dict[str, Any]) -> str:
        value = str(row.get("position") or row.get("map_label") or "").strip()
        return value if _valid_position_text(value) else ""

    def _position_label(self, position: str) -> str:
        text = str(position or "").strip()
        if _valid_position_text(text):
            return f"Position : {text}"
        location = self._location_text(self.card)
        return f"Position : {location}" if location and location != "Destination" else ""

    @staticmethod
    def _join_location(position: str, zone: str) -> str:
        position = str(position or "").strip()
        zone = str(zone or "").strip()
        if position and zone:
            return f"{position} — {zone}"
        return position or zone

    @staticmethod
    def _different_text(left: str, right: str) -> bool:
        normalize = lambda value: " ".join(str(value or "").casefold().split()).strip(" .")
        a, b = normalize(left), normalize(right)
        return bool(a and a != b and a not in b and b not in a)

    @staticmethod
    def _add_detail_label(body: QVBoxLayout, text: str, completed: bool, *, important: bool = False) -> None:
        value = str(text or "").strip()
        if not value:
            return
        label = QLabel(value)
        label.setObjectName("GuideUltimeWalkthroughImportant" if important else "GuideUltimeWalkthroughDetail")
        label.setProperty("state", "done" if completed else "todo")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(label)


def _safe_coord(value: Any) -> int | None:
    try:
        coord = int(value)
    except (TypeError, ValueError):
        return None
    return None if coord == SENTINEL_COORD else coord


def _card_coords(card: dict[str, Any]) -> str:
    x = _safe_coord(card.get("x"))
    y = _safe_coord(card.get("y"))
    return f"[{x},{y}]" if x is not None and y is not None else ""


def _valid_position_text(value: str) -> bool:
    match = COORD_RE.search(str(value or ""))
    if not match:
        return False
    return _safe_coord(match.group(1)) is not None and _safe_coord(match.group(2)) is not None


def _strip_sentinel_position(value: str) -> str:
    text = str(value or "").strip()
    match = COORD_RE.search(text)
    if not match:
        return text
    if _safe_coord(match.group(1)) is not None and _safe_coord(match.group(2)) is not None:
        return text
    return (text[: match.start()] + text[match.end() :]).strip(" -—•,")
