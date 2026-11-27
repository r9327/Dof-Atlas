from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/modules/encyclopedia/views/shared_manual_guide_view.py"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")



class SharedGuideVisualFlowContractTests(unittest.TestCase):
    def test_compact_progress_header_is_built_before_scroll_and_bottom_navigation(self) -> None:
        source = _source()
        progress = source.index("self._build_compact_header(root)")
        scroll = source.index("self.scroll = configure_unity_scroll_area(")
        navigation = source.index("nav = AtlasGuideReadingNav()")
        assert progress < scroll < navigation
        assert "header = AtlasGuideReadingHeader(" in source


    def test_detached_combat_fallback_is_gone(self) -> None:
        source = _source()
        assert "_add_unmatched_combats(root)" not in source
        assert "def _add_unmatched_combats" not in source


    def test_lanyel_position_deduplication_is_part_of_shared_renderer(self) -> None:
        source = _source()
        assert "def _display_position" in source
        assert "self._last_route_position_key" in source
        assert 'position = self._display_position(str(row.get("position") or ""))' in source


    def test_combat_rows_use_neutral_translucent_shared_style(self) -> None:
        source = _source()
        assert "GuideManualCombatInlineText" in source
        assert "GuideManualCombatInlineRow" in source
        theme = (ROOT / "app/ui/theme.py").read_text(encoding="utf-8")
        combat_style = theme.split("QFrame#GuideManualCombatInlineRow {", 1)[1].split("}", 1)[0]
        assert "background: @GLASS_SUBTLE_SURFACE;" in combat_style
        assert '"GuideManualDungeonSection"' not in source
