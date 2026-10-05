from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/modules/encyclopedia/views/shared_manual_guide_view.py"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_progress_strip_is_built_before_scroll_and_bottom_navigation() -> None:
    source = _source()
    progress = source.index("self._build_progress_strip(root)")
    scroll = source.index("self.scroll = QScrollArea()")
    navigation = source.index("nav = QFrame()")
    assert progress < scroll < navigation


def test_detached_combat_fallback_is_gone() -> None:
    source = _source()
    assert "_add_unmatched_combats(root)" not in source
    assert "def _add_unmatched_combats" not in source


def test_lanyel_position_deduplication_is_part_of_shared_renderer() -> None:
    source = _source()
    assert "def _display_position" in source
    assert "self._last_route_position_key" in source
    assert 'position = self._display_position(str(row.get("position") or ""))' in source


def test_combat_rows_use_neutral_translucent_shared_style() -> None:
    source = _source()
    assert "GuideManualCombatInlineText" in source
    assert "GuideManualCombatInlineRow" in source
    assert "rgba(174, 183, 177" in source
    assert '"GuideManualDungeonSection"' not in source
