from __future__ import annotations

import inspect
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QLabel

from app.modules.encyclopedia.services.guide_ultime_generated_service import GuideUltimeGeneratedService
from app.modules.encyclopedia.views.guide_ultime_universal_view import (
    GuideUltimeRouteCard,
    GuideUltimeUniversalView,
)
from app.ui.styles.guide import guide_universal_stylesheet


class GuideUltimeRouteSheetUITests(unittest.TestCase):
    def test_spaced_coordinate_is_copyable_without_inventing_a_zaap(self):
        app = QApplication.instance() or QApplication([])

        class Filter(QObject):
            travel_callback = None

            @staticmethod
            def _safe_int(value):
                return int(value)

        listener = Filter()
        label = QLabel("Position [ 003, -06 ]")
        try:
            # Exercise the real QLabel decorator, without hydrating routes.
            GuideUltimeUniversalView._make_positions_copyable(listener, label)
            self.assertTrue(label.property("travelCopyEnabled"))
            self.assertEqual(label.property("travelCommand"), "/travel 3,-6")
            self.assertIn("copier", label.toolTip().lower())
        finally:
            label.deleteLater()
            listener.deleteLater()
            app.processEvents()

    def test_missing_coordinate_never_dispatches_travel_to_game(self):
        app = QApplication.instance() or QApplication([])
        calls = []
        view = SimpleNamespace(
            participant_service=SimpleNamespace(
                available_characters=lambda: (
                    SimpleNamespace(key="character:1", connected=True),
                ),
            ),
            selected_participant_keys=lambda: ("character:1",),
            travel_callback=lambda command, keys: calls.append((command, keys)),
        )
        command = "/travel -2147483648,3"
        self.assertFalse(GuideUltimeUniversalView._launch_travel_command(view, command))
        self.assertEqual(calls, [])
        self.assertEqual(app.clipboard().text(), command)
        self.assertTrue(
            GuideUltimeUniversalView._launch_travel_command(view, "/travel 3,-6")
        )
        self.assertEqual(calls, [("/travel 3,-6", ("character:1",))])

    def test_travel_dispatch_error_is_logged_and_copied(self):
        app = QApplication.instance() or QApplication([])

        def failed_send(command, keys):
            raise RuntimeError("capture lost")

        view = SimpleNamespace(
            participant_service=SimpleNamespace(
                available_characters=lambda: (
                    SimpleNamespace(key="character:1", connected=True),
                ),
            ),
            selected_participant_keys=lambda: ("character:1",),
            travel_callback=failed_send,
        )
        with patch(
            "app.modules.encyclopedia.views.guide_ultime_universal_view._LOGGER.exception"
        ) as logger:
            self.assertFalse(
                GuideUltimeUniversalView._launch_travel_command(view, "/travel 3,-6")
            )
            self.assertEqual(app.clipboard().text(), "/travel 3,-6")
            logger.assert_called_once()

    def test_explicitly_refused_travel_is_copied_not_reported_sent(self):
        app = QApplication.instance() or QApplication([])
        calls = []
        view = SimpleNamespace(
            participant_service=SimpleNamespace(
                available_characters=lambda: (
                    SimpleNamespace(key="character:1", connected=True),
                ),
            ),
            selected_participant_keys=lambda: ("character:1",),
            travel_callback=lambda command, keys: (
                calls.append((command, keys)) or False
            ),
        )
        self.assertFalse(
            GuideUltimeUniversalView._launch_travel_command(view, "/travel 3,-6")
        )
        self.assertEqual(calls, [("/travel 3,-6", ("character:1",))])
        self.assertEqual(app.clipboard().text(), "/travel 3,-6")

    def test_identity_lookup_exception_fails_closed_with_clipboard(self):
        app = QApplication.instance() or QApplication([])
        calls = []

        def missing_registry():
            raise OSError("verified participant registry unreadable")

        view = SimpleNamespace(
            participant_service=SimpleNamespace(
                available_characters=missing_registry,
            ),
            selected_participant_keys=lambda: ("character:1",),
            travel_callback=lambda command, keys: calls.append((command, keys)),
        )
        with patch(
            "app.modules.encyclopedia.views.guide_ultime_universal_view._LOGGER.exception"
        ) as logger:
            self.assertFalse(
                GuideUltimeUniversalView._launch_travel_command(view, "/travel 3,-6")
            )
            logger.assert_called_once()
        self.assertEqual(calls, [])
        self.assertEqual(app.clipboard().text(), "/travel 3,-6")

    def test_unreasonably_long_coordinate_is_not_dispatched(self):
        app = QApplication.instance() or QApplication([])
        calls = []
        view = SimpleNamespace(
            participant_service=SimpleNamespace(
                available_characters=lambda: (
                    SimpleNamespace(key="character:1", connected=True),
                ),
            ),
            selected_participant_keys=lambda: ("character:1",),
            travel_callback=lambda command, keys: calls.append((command, keys)),
        )
        for command in (
            "/travel 2147483648,2",
            "/travel -2147483649,2",
            "/travel " + "9" * 5000 + ",2",
        ):
            with self.subTest(command_length=len(command)):
                self.assertFalse(
                    GuideUltimeUniversalView._launch_travel_command(view, command)
                )
                self.assertEqual(calls, [])
                self.assertEqual(app.clipboard().text(), command)

    def test_single_route_sheet_is_rendered(self):
        source = inspect.getsource(GuideUltimeUniversalView._render_window)
        self.assertIn("GuideUltimeRouteCard", source)
        self.assertIn("self.rendered_card_count = 1", source)
        self.assertNotIn("_visible_indices", source)

    def test_navigation_reuses_shared_x_x_counter(self):
        build = inspect.getsource(GuideUltimeUniversalView._build_ui)
        render = inspect.getsource(GuideUltimeUniversalView._render_window)
        self.assertIn("self.page_navigator = AtlasPageNavigator()", build)
        self.assertIn("self.page_navigator.pageRequested.connect(", build)
        self.assertIn("self.page_navigator.set_page(index + 1,", render)
        self.assertNotIn('AtlasButton("← Précédent")', build)
        self.assertNotIn('AtlasButton("Suivant →")', build)

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
        self.assertIn("self.breadcrumb = AtlasBreadcrumb()", source)
        self.assertIn('home = AtlasButton("Guides", variant="guide_breadcrumb")', source)
        self.assertIn("self.breadcrumb.add_separator()", source)
        self.assertIn('self.breadcrumb.add_current("Guide Ultime")', source)

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
