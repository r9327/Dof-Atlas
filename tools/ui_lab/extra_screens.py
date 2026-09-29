from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from tools.ui_lab.screens import PreviewContext

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


def create_crafts_preview(context: PreviewContext) -> "QWidget":
    """Instantiate the real CraftPage in its canonical deferred-loading skeleton state."""

    import app.pages.craft_page as craft_module

    scratch = context.sandbox_root / "crafts"
    scratch.mkdir(parents=True, exist_ok=True)
    selection_path = scratch / "craft_selection.json"

    with patch.object(craft_module, "CRAFT_SELECTION_FILE", selection_path):
        page = craft_module.CraftPage(
            context.report_status,
            preload={},
            defer_runtime=True,
        )
    return page


def create_world_map_preview(context: PreviewContext) -> "QWidget":
    """Instantiate the real WorldScanPanel; its normal product worker may hydrate local data."""

    from app.ui.world_scan_panel import WorldScanPanel

    page = WorldScanPanel(context.report_status)
    return page
