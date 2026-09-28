from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.views import guides_view


class QuestDetailGuideUiContractTests(unittest.TestCase):
    def test_modern_guides_view_explicitly_exports_quest_detail_primitives(self) -> None:
        required = {
            "GuidesView",
            "SolutionImageLabel",
            "CollapsibleInfoSection",
            "clear_layout",
            "text_label",
            "_display_quest_level_text",
            "_progress_count",
            "_progress_state",
            "quest_solution_document_widgets",
            "quest_navigation_footer",
            "hidden_label",
            "info_section",
            "activity_chip_grid",
            "reward_row",
            "prerequisite_row",
        }
        missing = sorted(name for name in required if not hasattr(guides_view, name))
        self.assertEqual([], missing, f"Primitives manquantes pour QuestDetailView: {missing}")

    def test_compatibility_surface_uses_explicit_imports_not_wildcards(self) -> None:
        source = Path(guides_view.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import *", source)
        self.assertIn("quest_solution_document_widgets", source)
        self.assertIn("quest_navigation_footer", source)

    def test_encyclopedia_routes_guide_gps_quest_to_canonical_quest_sheet(self) -> None:
        source = Path(
            "app/modules/encyclopedia/views/encyclopedia_page.py"
        ).read_text(encoding="utf-8")
        self.assertIn('source == "guide_gps"', source)
        self.assertIn("QuestViewContext(", source)
        self.assertIn('host="guide_gps"', source)
        self.assertIn("guide_stage_id=", source)
        self.assertIn("guide_index=", source)
        self.assertIn("self.quest_page.select_quest(quest_id)", source)

    def test_shared_item_copy_shows_short_confirmation(self) -> None:
        source = Path(
            "app/modules/encyclopedia/widgets/quest_item_row.py"
        ).read_text(encoding="utf-8")
        self.assertIn("QApplication.clipboard().setText(value)", source)
        self.assertIn("QToolTip.showText", source)
        self.assertIn("1200", source)


if __name__ == "__main__":
    unittest.main()
