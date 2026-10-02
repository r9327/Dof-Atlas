from __future__ import annotations

from typing import Any

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import *  # noqa: F401,F403
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
    GuideUltimeManualRuntimeService as _GuideUltimeManualRuntimeCore,
)
from app.modules.encyclopedia.services.guide_ultime_player_policy import apply_player_line_policy


class GuideUltimeManualRuntimeService(_GuideUltimeManualRuntimeCore):
    """Canonical manual runtime with the Phase 7E player-facing policy applied once."""

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
