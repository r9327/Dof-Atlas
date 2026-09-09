from __future__ import annotations

import unittest

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
        source = __import__("pathlib").Path(guides_view.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import *", source)
        self.assertIn("quest_solution_document_widgets", source)
        self.assertIn("quest_navigation_footer", source)


if __name__ == "__main__":
    unittest.main()
