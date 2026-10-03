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


_COORD_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")


class GuideCatalogManualRuntimeService(GuideUltimeManualRuntimeService):
    """Project one canonical Guide catalogue route into the shared manual road-book UI.

    The Guide model remains the source of truth for ordering/completion. Quest source
    data supplies the visible route instructions, positions, explicit preparation and
    combat objectives. Nothing is scraped or guessed at render time.
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
        cards: list[dict[str, Any]] = []
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
            cards.append(self._quest_card(step, quest, len(cards)))

        if not cards:
            raise ValueError(f"Aucune fiche route exploitable pour {self.guide_id}")

        self._link_next_cards(cards)
        self.route = {
            "schema_version": 5,
            "id": f"catalog_manual_{self.guide_id}",
            "source": f"data/encyclopedia/guides/{self.guide_id}.json",
            "manual_preview": False,
            "manual_manifest": False,
            "manual_chapters": [self.guide_id],
            "universal_route": {
                "common_route_quest_count": len(cards),
                "qq_required_count": 0,
            },
            "conditional_branches": {},
            "full_success_cards": {},
            "steps": cards,
        }
        self.cards = cards
        self._common_quest_ids = tuple(
            quest_id
            for card in cards
            for quest_id in card.get("manual_quest_ids", ())
        )
        self._full_success_ids = ()
        self.manual_audit_data = {
            "source": self.route["source"],
            "guide_id": self.guide_id,
            "card_count": len(cards),
            "quest_count": len(seen_quests),
        }
        self.manual_preview_active = True
        self.manual_preview_chapters = (self.guide_id,)
        self.manual_manifest_active = False
        self.manual_chapters = (self.guide_id,)
        self.manual_preview_error = ""

    def _quest_card(self, guide_step, quest, index: int) -> dict[str, Any]:
        quest_id = int(quest.id)
        start = quest_start_info(quest)
        position = str(start.position or first_position_from_quest(quest) or "").strip()
        zone = str(start.zone or (quest.zones[0] if getattr(quest, "zones", ()) else "") or "").strip()
        coords = self._coords(position)

        prepare: list[dict[str, Any]] = []
        now: list[dict[str, Any]] = []
        boss: list[dict[str, Any]] = []
        resource_names: list[str] = []
        structured_preparation: list[dict[str, Any]] = []

        for prerequisite in getattr(quest, "prerequisites", ()) or ():
            text = clean_requirement_line(str(prerequisite or ""))
            if text:
                prepare.append(self._line("warning", "", f"Prérequis : {text}"))

        all_items = quest_items_from_objectives(quest)
        for item in all_items:
            name = str(getattr(item, "name", "") or "").strip()
            if name and name.casefold() not in {value.casefold() for value in resource_names}:
                resource_names.append(name)
            if not bool(getattr(item, "preparable", False)) or not name:
                continue
            quantity = int(getattr(item, "quantity", 0) or 0) or 1
            prepare.append(self._line("warning", "", f"Prépare {quantity} × {name}."))
            structured_preparation.append(
                {
                    "item_id": getattr(item, "item_id", None),
                    "name": name,
                    "quantity": quantity,
                    "_source_field": "quest_required_items",
                }
            )

        if start.npc:
            location = " — ".join(value for value in (position, zone) if value)
            text = f"Prends la quête « {quest.name} » auprès de {start.npc}."
            if location:
                text += f" {location}"
            now.append(self._line("action", position, text))

        for solution_step in quest_solution_steps(quest):
            if solution_step.title:
                now.append(self._line("action", "", solution_step.title))
            if solution_step.description:
                now.append(self._line("action", "", solution_step.description))
            for objective in solution_step.objectives:
                text = str(objective.text or "").strip()
                if not text:
                    continue
                row = self._line(
                    "action",
                    str(objective.position or "").strip(),
                    text,
                )
                if bool(objective.combat):
                    boss.append(row)
                else:
                    now.append(row)

        if not now:
            now.append(self._line("action", position, f"Faire la quête « {quest.name} »."))

        sections = {
            "prepare": self._dedupe_rows(prepare),
            "now": self._dedupe_rows(now),
            "opportunity": [],
            "keep": [],
            "boss": self._dedupe_rows(boss),
            "before_leave": [],
        }
        manual_lines = [
            copy.deepcopy(row)
            for key in ("prepare", "now", "boss")
            for row in sections[key]
        ]
        destination = " — ".join(value for value in (position, zone) if value) or str(quest.name)
        stage_id = str(getattr(guide_step, "id", "") or f"quest-{quest_id}")

        return {
            "index": index + 1,
            "manual_source": True,
            "_manual_route_cacheable": True,
            "manual_chapter_id": self.guide_id,
            "manual_chapter_label": self.guide_title,
            "manual_stage_id": stage_id,
            "manual_title": str(quest.name),
            "expected_level": str(getattr(quest, "level_min", "") or ""),
            "x": coords[0] if coords is not None else None,
            "y": coords[1] if coords is not None else None,
            "zone": zone,
            "subzone": zone,
            "destination": destination,
            "manual_lines": manual_lines,
            "manual_sections": sections,
            "structured_runtime_lines": [],
            "manual_quest_ids": [quest_id],
            "manual_quest_names": [str(quest.name)],
            "manual_resource_names": resource_names,
            "manual_success_names": [],
            "manual_temporal_hooks": [],
            "manual_runtime_metadata": {},
            "a_prendre": [],
            "a_faire_ici": [],
            "progresse_aussi": {"quest_ids": [quest_id], "success_ids": []},
            "a_preparer": structured_preparation,
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
        return [copy.deepcopy(row) for row in card.get("manual_lines", ()) if isinstance(row, dict)]

    def manual_sections_for_card(
        self,
        character_key: str,
        card: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        del character_key
        source = card.get("manual_sections") if isinstance(card.get("manual_sections"), dict) else {}
        return {
            key: [copy.deepcopy(row) for row in source.get(key, ()) if isinstance(row, dict)]
            for key in ("prepare", "now", "opportunity", "keep", "boss", "before_leave")
        }

    def manual_checked(self, character_key: str, key: str) -> bool:
        return self.guide_progress.is_manual_step_completed(
            character_key,
            self.progress_id,
            key,
        )

    def set_manual_checked(self, character_key: str, key: str, checked: bool) -> None:
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


__all__ = ["GuideCatalogManualRuntimeService"]
