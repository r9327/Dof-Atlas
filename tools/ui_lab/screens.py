from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


@dataclass(slots=True)
class PreviewContext:
    sandbox_root: Path
    report_status: Callable[[str], None]
    scenario: str = "default"


def create_guides_preview(context: PreviewContext) -> "QWidget":
    """Instantiate the real GuidesView while isolating mutable progress files."""

    from app.modules.encyclopedia.views.guides_view import GuidesView

    scratch = context.sandbox_root / "guides"
    scratch.mkdir(parents=True, exist_ok=True)

    return GuidesView(
        status_callback=context.report_status,
        quest_progress_path=scratch / "quest_progress.json",
        achievement_progress_path=scratch / "achievement_progress.json",
        guide_progress_path=scratch / "guide_progress.json",
        profile_path=scratch / "client_profiles.json",
        client_index_path=scratch / "client_index.json",
    )
