from __future__ import annotations

import copy
import re
from typing import Any

from app.modules.encyclopedia.services.guide_quest_view_model import (
    clean_requirement_line,
    first_position_from_quest,
    quest_items_from_objectives,
    quest_solution_steps,
    quest_start_info,
)
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from app.quest_catalog import normalize_text


_COORD_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")


class GuideCatalogManualRuntimeService(GuideUltimeManualRuntimeService):
    """Project a Guide catalogue route into the shared manual road-book UI.

    The Guide model remains authoritative for quest order and completion. Quest
    source data supplies route positions, walkthrough actions, preparation and
    combat objectives. A rendered sheet represents a route position, not a quest:
    one quest may span several maps and consecutive work on the same map is merged.
    """

    def __init__(
        self,
        *args,
        guide,
        quest_provider,
        **kwargs,
    ) -> None:
        self.catalog_guide = guide
        self.guide_id = str(getattr(guide, "id", "") or "")
        self.guide_title = str(getattr(guide, "title", "") or self.guide_id)
        self.progress_id = f"catalog_manual:{self.guide_id}"
        kwargs["autoload"] = False
        super().__init__(*args, quest_provider=quest_provider, **kwargs)

    def _load_manual_preview(self) -> None:
        quest_count = 0
        raw_segments: list[dict[str, Any]] = []
        seen_quests: set[int] = set()

        for step in sorted(
            getattr(self.catalog_guide, "required_steps", ()) or (),
            key=lambda row: int(getattr(row, "order", 0) or 0),
        ):
            if str(getattr(step, "step_type", "")) != "quest":
                continue
            raw_id = getattr(step, "entity_id", None)
            try:
                quest_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if quest_id in seen_quests:
                continue
            quest = self.quest_provider.get_quest(quest_id)
            if quest is None:
                continue
            seen_quests.add(quest_id)
            quest_count += 1
            raw_segments.extend(self._quest_segments(step, quest))

        segments = self._merge_consecutive_positions(raw_segments)
        cards = [
            self._segment_to_card(segment, index)
            for index, segment in enumerate(segments)
        ]
        if not cards:
            raise ValueError(f"Aucune fiche route exploitable pour {self.guide_id}")

        self._link_next_cards(cards)
        self.route = {
            "schema_version": 5,
            "id": f"catalog_manual_{self.guide_id}",
            "source": f"data/encyclopedia/guides/{self.guide_id}.json+quest_catalog",
            "manual_preview": False,
            "manual_manifest": False,
            "manual_chapters": [self.guide_id],
            "route_model": "map_segments",
            "universal_route": {
                "common_route_quest_count": quest_count,
                "qq_required_count": 0,
            },
            "conditional_branches": {},
            "full_success_cards": {},
            "steps": cards,
        }
        self.cards = cards
        self._common_quest_ids = tuple(sorted(seen_quests))
        self._full_success_ids = ()
        self.manual_audit_data = {
            "source": self.route["source"],
            "guide_id": self.guide_id,
            "route_model": "map_segments",
            "card_count": len(cards),
            "raw_segment_count": len(raw_segments),
            "quest_count": quest_count,
            "merged_segment_count": max(0, len(raw_segments) - len(cards)),
        }
        self.manual_preview_active = True
        self.manual_preview_chapters = (self.guide_id,)
        self.manual_manifest_active = False
        self.manual_chapters = (self.guide_id,)
        self.manual_preview_error = ""

    def _quest_segments(self, guide_step, quest) -> list[dict[str, Any]]:
        quest_id = int(quest.id)
        quest_name = str(getattr(quest, "name", "") or f"Quête #{quest_id}")
        start = quest_start_info(quest)
        start_position = str(
            start.position
            or first_position_from_quest(quest)
            or ""
        ).strip()
        zone = str(
            start.zone
            or (quest.zones[0] if getattr(quest, "zones", ()) else "")
            or ""
        ).strip()

        first = self._new_segment(
            position=start_position,
            zone=zone,
            quest_id=quest_id,
            quest_name=quest_name,
            guide_step_id=str(getattr(guide_step, "id", "") or f"quest-{quest_id}"),
        )

        for prerequisite in getattr(quest, "prerequisites", ()) or ():
            text = clean_requirement_line(str(prerequisite or ""))
            if text:
                first["sections"]["prepare"].append(
                    self._line("warning", start_position, f"Prérequis : {text}")
                )

        for item in quest_items_from_objectives(quest):
            name = str(getattr(item, "name", "") or "").strip()
            if name and name.casefold() not in {
                value.casefold() for value in first["resource_names"]
            }:
                first["resource_names"].append(name)
            if not bool(getattr(item, "preparable", False)) or not name:
                continue
            quantity = int(getattr(item, "quantity", 0) or 0) or 1
            first["sections"]["prepare"].append(
                self._line("warning", start_position, f"Prépare {quantity} × {name}.")
            )
            first["structured_preparation"].append(
                {
                    "item_id": getattr(item, "item_id", None),
                    "name": name,
                    "quantity": quantity,
                    "_source_field": "quest_required_items",
                }
            )

        location = " — ".join(value for value in (start_position, zone) if value)
        if start.npc:
            text = f"Prends la quête « {quest_name} » auprès de {start.npc}."
            if location:
                text += f" {location}"
        else:
            text = f"Commence / poursuis la quête « {quest_name} »."
        first["sections"]["now"].append(
            self._line("action", start_position, text)
        )

        segments: list[dict[str, Any]] = []
        current = first
        for solution_step in quest_solution_steps(quest):
            if solution_step.title:
                current["sections"]["now"].append(
                    self._line("action", current["position"], solution_step.title)
                )
            if solution_step.description:
                current["sections"]["now"].append(
                    self._line("action", current["position"], solution_step.description)
                )

            for objective in solution_step.objectives:
                text = str(objective.text or "").strip()
                if not text:
                    continue
                objective_position = str(
                    objective.position
                    or current["position"]
                    or start_position
                    or ""
                ).strip()
                if (
                    self._position_key(objective_position)
                    and self._position_key(current["position"])
                    and self._position_key(objective_position)
                    != self._position_key(current["position"])
                ):
                    self._finalize_segment(current)
                    if self._segment_has_content(current):
                        segments.append(current)
                    current = self._new_segment(
                        position=objective_position,
                        zone=zone,
                        quest_id=quest_id,
                        quest_name=quest_name,
                        guide_step_id=str(
                            getattr(guide_step, "id", "") or f"quest-{quest_id}"
                        ),
                    )

                row = self._line(
                    "combat" if bool(objective.combat) else "action",
                    objective_position,
                    text,
                )
                if bool(objective.combat):
                    current["sections"]["boss"].append(row)
                else:
                    current["sections"]["now"].append(row)

        self._finalize_segment(current)
        if self._segment_has_content(current):
            segments.append(current)
        return segments

    @staticmethod
    def _new_segment(
        *,
        position: str,
        zone: str,
        quest_id: int,
        quest_name: str,
        guide_step_id: str,
    ) -> dict[str, Any]:
        return {
            "position": str(position or "").strip(),
            "zone": str(zone or "").strip(),
            "guide_step_ids": [str(guide_step_id)],
            "quest_ids": [int(quest_id)],
            "quest_names": [str(quest_name)],
            "resource_names": [],
            "structured_preparation": [],
            "sections": {
                "prepare": [],
                "now": [],
                "opportunity": [],
                "keep": [],
                "boss": [],
                "before_leave": [],
            },
            "manual_lines": [],
        }

    def _finalize_segment(self, segment: dict[str, Any]) -> None:
        sections = segment["sections"]
        for key in sections:
            sections[key] = self._dedupe_rows(sections[key])
        segment["manual_lines"] = [
            copy.deepcopy(row)
            for key in ("prepare", "now", "boss", "before_leave")
            for row in sections[key]
        ]

    @staticmethod
    def _segment_has_content(segment: dict[str, Any]) -> bool:
        return bool(
            segment.get("manual_lines")
            or any(segment.get("sections", {}).values())
        )

    def _merge_consecutive_positions(
        self,
        segments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        for raw in segments:
            segment = copy.deepcopy(raw)
            key = self._position_key(segment.get("position"))
            previous_key = (
                self._position_key(merged[-1].get("position"))
                if merged
                else ""
            )
            if merged and key and key == previous_key:
                self._merge_segment(merged[-1], segment)
                continue
            merged.append(segment)
        return merged

    def _merge_segment(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
    ) -> None:
        for field in ("guide_step_ids", "quest_ids", "quest_names", "resource_names"):
            for value in source.get(field, ()) or ():
                if value not in target[field]:
                    target[field].append(value)
        target["structured_preparation"].extend(
            copy.deepcopy(source.get("structured_preparation", ()))
        )
        for key, rows in source.get("sections", {}).items():
            target["sections"].setdefault(key, [])
            target["sections"][key].extend(copy.deepcopy(rows))
        self._finalize_segment(target)

    def _segment_to_card(
        self,
        segment: dict[str, Any],
        index: int,
    ) -> dict[str, Any]:
        position = str(segment.get("position") or "").strip()
        zone = str(segment.get("zone") or "").strip()
        coords = self._coords(position)
        quest_names = list(segment.get("quest_names", ()))
        quest_ids = [int(value) for value in segment.get("quest_ids", ())]
        stage_ids = [str(value) for value in segment.get("guide_step_ids", ())]
        route_label = " — ".join(value for value in (position, zone) if value)
        title = f"Étape GPS — {route_label}" if route_label else (
            quest_names[0]
            if len(quest_names) == 1
            else f"Étape GPS — {len(quest_names)} quêtes"
        )
        stage_key = "+".join(stage_ids[:3]) or f"map-{index + 1}"
        if len(stage_ids) > 3:
            stage_key += f"+{len(stage_ids) - 3}"

        waypoint: dict[str, Any] = {
            "label": position or zone,
            "quests": quest_names,
        }
        if coords is not None:
            waypoint["x"], waypoint["y"] = coords

        return {
            "index": index + 1,
            "manual_source": True,
            "_manual_route_cacheable": True,
            "manual_chapter_id": self.guide_id,
            "manual_chapter_label": self.guide_title,
            "manual_stage_id": f"{self.guide_id}:gps:{stage_key}:{index + 1}",
            "manual_title": title,
            "manual_route_position": position,
            "expected_level": "",
            "x": coords[0] if coords is not None else None,
            "y": coords[1] if coords is not None else None,
            "zone": zone,
            "subzone": zone,
            "destination": route_label or title,
            "manual_lines": copy.deepcopy(segment.get("manual_lines", ())),
            "manual_sections": copy.deepcopy(segment.get("sections", {})),
            "structured_runtime_lines": [],
            "manual_quest_ids": quest_ids,
            "manual_quest_names": quest_names,
            "manual_resource_names": list(segment.get("resource_names", ())),
            "manual_success_names": [],
            "manual_temporal_hooks": [],
            "manual_runtime_metadata": {},
            "manual_stage_data": {"waypoints": [waypoint]},
            "a_prendre": [],
            "a_faire_ici": [],
            "progresse_aussi": {"quest_ids": quest_ids, "success_ids": []},
            "a_preparer": self._dedupe_structured_preparation(
                segment.get("structured_preparation", ())
            ),
            "hard_runtime_gates": [],
            "profession_gates": [],
            "avant_de_partir": [],
            "succes_monstres_a_faire": [],
            "succes_donjon_a_faire": [],
            "ensuite": None,
        }

    def manual_lines_for_card(
        self,
        character_key: str,
        card: dict[str, Any],
    ) -> list[dict[str, Any]]:
        del character_key
        return [
            copy.deepcopy(row)
            for row in card.get("manual_lines", ())
            if isinstance(row, dict)
        ]

    def manual_sections_for_card(
        self,
        character_key: str,
        card: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        del character_key
        source = (
            card.get("manual_sections")
            if isinstance(card.get("manual_sections"), dict)
            else {}
        )
        return {
            key: [
                copy.deepcopy(row)
                for row in source.get(key, ())
                if isinstance(row, dict)
            ]
            for key in (
                "prepare",
                "now",
                "opportunity",
                "keep",
                "boss",
                "before_leave",
            )
        }

    def manual_checked(self, character_key: str, key: str) -> bool:
        return self.guide_progress.is_manual_step_completed(
            character_key,
            self.progress_id,
            key,
        )

    def set_manual_checked(
        self,
        character_key: str,
        key: str,
        checked: bool,
    ) -> None:
        self.guide_progress.set_manual_step_completed(
            character_key,
            self.progress_id,
            key,
            bool(checked),
        )

    @staticmethod
    def _line(kind: str, position: str, text: str) -> dict[str, Any]:
        return {
            "kind": str(kind),
            "position": str(position or "").strip(),
            "text": " ".join(str(text or "").split()).strip(),
        }

    @staticmethod
    def _coords(position: str) -> tuple[int, int] | None:
        match = _COORD_RE.search(str(position or ""))
        if match is None:
            return None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _position_key(value: Any) -> str:
        text = " ".join(str(value or "").split()).strip()
        match = _COORD_RE.search(text)
        if match is not None:
            return f"{int(match.group(1))},{int(match.group(2))}"
        return normalize_text(text)

    @staticmethod
    def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            text = " ".join(str(row.get("text") or "").split()).strip()
            position = " ".join(str(row.get("position") or "").split()).strip()
            key = (position.casefold(), text.casefold())
            if text and key not in seen:
                seen.add(key)
                result.append(row)
        return result

    @staticmethod
    def _dedupe_structured_preparation(rows) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[Any, str, int]] = set()
        for raw in rows or ():
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            quantity = int(raw.get("quantity") or 0)
            key = (raw.get("item_id"), name.casefold(), quantity)
            if name and key not in seen:
                seen.add(key)
                result.append(copy.deepcopy(raw))
        return result


__all__ = ["GuideCatalogManualRuntimeService"]
