from __future__ import annotations

import copy
from typing import Any

from app.modules.encyclopedia.services import guide_ultime_manual_runtime_core as _core
from app.modules.encyclopedia.services.guide_ultime_player_policy import apply_player_line_policy


ROOT = _core.ROOT
MANUAL_DIR = _core.MANUAL_DIR
MANIFEST_PATH = _core.MANIFEST_PATH
clear_manual_bundle_cache = _core.clear_manual_bundle_cache


class GuideUltimeManualRuntimeService(_core.GuideUltimeManualRuntimeService):
    """Canonical manual runtime with the Phase 7E player-facing policy applied once."""

    @classmethod
    def _structured_rows_from_fields(
        cls,
        stage: dict[str, Any],
        fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        return super()._structured_rows_from_fields(stage, fields)

    @staticmethod
    def _link_next_cards(cards) -> None:
        for index, card in enumerate(cards):
            if index + 1 >= len(cards):
                card["ensuite"] = None
                continue
            nxt = cards[index + 1]
            card["ensuite"] = {
                "destination": str(nxt.get("destination") or ""),
                "x": nxt.get("x"),
                "y": nxt.get("y"),
                "zone": str(nxt.get("zone") or ""),
                "subzone": str(nxt.get("subzone") or ""),
                "manual_stage_id": str(nxt.get("manual_stage_id") or ""),
            }

    def _stage_to_card(
        self,
        chapter_id: str,
        chapter_meta: dict[str, Any],
        chapter: dict[str, Any],
        stage: dict[str, Any],
        index: int,
        *,
        chapter_preparation: Any = None,
    ) -> dict[str, Any]:
        # The core already owns the canonical stage/preparation snapshots.
        # Copying them again here briefly doubles the heaviest per-card payload.
        return super()._stage_to_card(
            chapter_id,
            chapter_meta,
            chapter,
            stage,
            index,
            chapter_preparation=chapter_preparation,
        )

    def _raw_stage_lines(
        self,
        stage: dict[str, Any],
        quest_names: list[str],
        *,
        chapter_preparation: Any = None,
    ) -> list[dict[str, Any]]:
        """Render authored lines before the Phase 7E presentation policy mutates them."""
        return _core.GuideUltimeManualRuntimeService._stage_lines(
            self,
            stage,
            quest_names,
            chapter_preparation=chapter_preparation,
        )

    def _stage_lines(
        self,
        stage: dict[str, Any],
        quest_names: list[str],
        *,
        chapter_preparation: Any = None,
    ) -> list[dict[str, Any]]:
        return apply_player_line_policy(
            self._raw_stage_lines(
                stage,
                quest_names,
                chapter_preparation=chapter_preparation,
            )
        )

    def manual_sections_for_card(
        self,
        character_key: str,
        card: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """Classify authored intent first, then apply the player policy across all sections.

        Action splitting changes line fingerprints. Classifying already-split lines can
        therefore move a dungeon/boss instruction into the generic ``now`` bucket.
        Rebuild only the source card's authored lines without presentation transforms,
        let the canonical core classify those stable fingerprints, then run the Phase
        7E policy once across the tagged section rows so preparation dedupe still sees
        acquisitions from every section.
        """
        stage = card.get("manual_stage_data")
        if not isinstance(stage, dict):
            return super().manual_sections_for_card(character_key, card)

        source_card = copy.deepcopy(card)
        source_card["manual_lines"] = self._raw_stage_lines(
            stage,
            [
                str(value)
                for value in source_card.get("manual_quest_names", []) or []
                if str(value).strip()
            ],
            chapter_preparation=source_card.get("manual_chapter_preparation"),
        )
        sections = super().manual_sections_for_card(character_key, source_card)

        tagged: list[dict[str, Any]] = []
        for section_name, rows in sections.items():
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                row = copy.deepcopy(raw)
                row["_phase7e_section"] = section_name
                tagged.append(row)

        result = {key: [] for key in sections}
        for row in apply_player_line_policy(tagged):
            section_name = str(row.pop("_phase7e_section", "now") or "now")
            result.setdefault(section_name, []).append(row)
        return result


def __getattr__(name: str) -> Any:
    """Preserve compatibility for historical imports without wildcard imports."""
    return getattr(_core, name)
