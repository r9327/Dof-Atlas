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
        card = super()._stage_to_card(
            chapter_id,
            chapter_meta,
            chapter,
            stage,
            index,
            chapter_preparation=chapter_preparation,
        )
        card.update(
            {
                "manual_stage_data": copy.deepcopy(stage),
                "manual_chapter_preparation": copy.deepcopy(chapter_preparation or []),
            }
        )
        return card

    def _stage_lines(
        self,
        stage: dict[str, Any],
        quest_names: list[str],
        *,
        chapter_preparation: Any = None,
    ) -> list[dict[str, Any]]:
        lines = super()._stage_lines(
            stage,
            quest_names,
            chapter_preparation=chapter_preparation,
        )
        return apply_player_line_policy(lines)


def __getattr__(name: str) -> Any:
    """Preserve compatibility for historical imports without wildcard imports."""
    return getattr(_core, name)
