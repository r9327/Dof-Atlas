from __future__ import annotations

import inspect
import unittest

from app.modules.encyclopedia.services.guide_ultime_generated_service import GuideUltimeGeneratedService
from app.modules.encyclopedia.views.guide_ultime_universal_view import (
    GuideUltimeRouteCard,
    GuideUltimeUniversalView,
)
from app.ui.styles.guide_universal import guide_universal_stylesheet


class GuideUltimeRouteSheetUITests(unittest.TestCase):
    def test_single_route_sheet_is_rendered(self):
        source = inspect.getsource(GuideUltimeUniversalView._render_window)
        self.assertIn("GuideUltimeRouteCard", source)
        self.assertIn("self.rendered_card_count = 1", source)
        self.assertNotIn("_visible_indices", source)

    def test_no_step_number_or_card_counter_in_route_sheet(self):
        source = inspect.getsource(GuideUltimeUniversalView._render_window)
        card_source = inspect.getsource(GuideUltimeRouteCard.__init__)
        self.assertNotIn("Carte {", source)
        self.assertNotIn("CARTE", card_source)
        self.assertNotIn("NIVEAU", card_source)

    def test_quest_name_is_only_used_when_taking_quest(self):
        objective_source = inspect.getsource(GuideUltimeRouteCard._add_action_row)
        take_source = inspect.getsource(GuideUltimeRouteCard._add_start_instruction)
        self.assertNotIn("quest_name", objective_source)
        self.assertIn("Prends la quête", take_source)

    def test_preparation_is_in_the_central_route_sheet(self):
        source = inspect.getsource(GuideUltimeRouteCard.__init__)
        self.assertIn("self._add_preparation(root)", source)
        self.assertLess(source.index("self._add_preparation(root)"), source.index("self._add_route_actions(root)"))

    def test_no_permanent_side_panel_or_level_slice_column(self):
        source = inspect.getsource(GuideUltimeUniversalView._build_ui)
        self.assertNotIn("GuideUltimeBranchPanel", source)
        self.assertNotIn("PROGRESSION PAR PALIERS", source)
        self.assertNotIn("Résumé global", source)

    def test_only_page_validation_is_a_checkbox(self):
        action_source = inspect.getsource(GuideUltimeRouteCard._add_action_row)
        preparation_source = inspect.getsource(GuideUltimeRouteCard._add_preparation)
        leaving_source = inspect.getsource(GuideUltimeRouteCard._add_before_leaving)
        page_source = inspect.getsource(GuideUltimeRouteCard._add_page_validation)
        self.assertNotIn("QCheckBox", action_source)
        self.assertNotIn("QCheckBox", preparation_source)
        self.assertNotIn("QCheckBox", leaving_source)
        self.assertIn("QCheckBox", page_source)
        self.assertIn("FICHE TERMINÉE", page_source)

    def test_before_continue_generic_gate_block_is_gone(self):
        card_source = inspect.getsource(GuideUltimeRouteCard)
        self.assertNotIn('self._section(root, "AVANT DE CONTINUER")', card_source)
        self.assertIn("_generic_gate", card_source)

    def test_page_override_is_separate_from_quest_progress(self):
        state_source = inspect.getsource(GuideUltimeGeneratedService.card_state)
        page_source = inspect.getsource(GuideUltimeGeneratedService.set_page_checked)
        self.assertIn("automatic_ok or page_done", state_source)
        self.assertNotIn("set_quest_completed", page_source)
        self.assertNotIn("set_objective_completed", page_source)

    def test_breadcrumb_uses_same_components_as_quests(self):
        source = inspect.getsource(GuideUltimeUniversalView._build_ui)
        self.assertIn('self.breadcrumb.setObjectName("GuideBreadcrumb")', source)
        self.assertIn('home = AtlasButton("Guides")', source)
        self.assertIn('home.setObjectName("GuideBreadcrumbButton")', source)
        self.assertIn('separator.setObjectName("GuideBreadcrumbSeparator")', source)
        self.assertIn('current.setObjectName("GuideBreadcrumbCurrent")', source)

    def test_order_choice_is_not_permanent_and_only_appears_on_first_order_card(self):
        build_source = inspect.getsource(GuideUltimeUniversalView._build_ui)
        render_source = inspect.getsource(GuideUltimeUniversalView._render_window)
        gate_source = inspect.getsource(GuideUltimeUniversalView._card_requires_first_order_choice)
        self.assertNotIn("Choisis ton Ordre Bonta une seule fois", build_source)
        self.assertIn("_add_inline_order_choice(card)", render_source)
        self.assertIn("selected_order_name", gate_source)
        self.assertIn("_first_order_card", gate_source)

    def test_route_has_no_fais_ca_ici_or_ensuite_section_titles(self):
        action_source = inspect.getsource(GuideUltimeRouteCard._add_route_actions)
        next_source = inspect.getsource(GuideUltimeRouteCard._add_next)
        self.assertNotIn("FAIS ÇA ICI", action_source)
        self.assertNotIn("ENSUITE", next_source)
        self.assertNotIn("_section", next_source)

    def test_active_sheet_keeps_neutral_panel_background(self):
        source = guide_universal_stylesheet()
        self.assertIn('#GuideUltimeRouteSheet[state="active"]', source)
        self.assertIn("background:", source)
        self.assertNotIn("PANEL_ACTIVE", source)


if __name__ == "__main__":
    unittest.main()
