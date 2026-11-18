"""Qt proof of manual Ganymède source navigation, not a mock button shell."""
from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QProgressBar
from app.ui.components import AtlasGuideDisclosure, AtlasGuideParticipantButton

from app.modules.encyclopedia.services.guide_progress_service import (
    GuideProgressService,
)
from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256,
)
from app.modules.encyclopedia.views.guide_continuous_route_panel import (
    ContinuousGuideRoutePanel,
)
from app.modules.encyclopedia.views.guides_view import GuidesView
from tests.test_guide_continuous_navigation import _source_route


class ContinuousGuideRoutePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = GuideProgressService(Path(temp.name) / "guide_progress.json")
        self.panel = ContinuousGuideRoutePanel(
            _source_route(), self.store, ("character:1", "character:2"),
        )
        self.addCleanup(self.panel.deleteLater)

    def test_continuous_travel_falls_back_to_clipboard_on_explicit_refusal(self):
        from unittest.mock import Mock

        messages = []
        launch = Mock(return_value=False)
        view = SimpleNamespace(
            launch_travel_callback=launch,
            status_callback=messages.append,
        )
        keys = ("character:1",)
        command = "/travel 5,-18"
        GuidesView._dispatch_continuous_route_travel(view, command, keys)
        launch.assert_called_once_with(command, keys)
        self.assertEqual(QApplication.clipboard().text(), command)
        self.assertIn("copiée", messages[-1])

    def test_continuous_travel_preserves_legacy_none_acceptance(self):
        from unittest.mock import Mock

        QApplication.clipboard().setText("ancienne commande")
        messages = []
        view = SimpleNamespace(
            launch_travel_callback=Mock(return_value=None),
            status_callback=messages.append,
        )
        GuidesView._dispatch_continuous_route_travel(
            view, "/travel 5,-18", ("character:1",),
        )
        self.assertEqual(QApplication.clipboard().text(), "ancienne commande")
        self.assertEqual(messages, [])

    def test_continuous_travel_exception_copies_instruction(self):
        from unittest.mock import Mock, patch

        def failed_launch(_command, _keys):
            raise RuntimeError("macro rejected")

        messages = []
        view = SimpleNamespace(
            launch_travel_callback=failed_launch,
            status_callback=messages.append,
        )
        with patch("app.modules.encyclopedia.views.guides_view.logging.getLogger"):
            GuidesView._dispatch_continuous_route_travel(
                view, "/zaap 1,2 ; /travel 5,-18", ("character:1",),
            )
        self.assertEqual(
            QApplication.clipboard().text(), "/zaap 1,2 ; /travel 5,-18",
        )
        self.assertIn("copiée", messages[-1])

    def test_route_header_geometry_uses_dev_ui_tokens_at_four_sizes(self):
        from app.ui.unity_palette import (
            UNITY_CONTROL_SIZES_PX, UNITY_MODULE_GEOMETRY_PX,
            UNITY_WINDOW_PRESETS_PX,
        )
        geometry = UNITY_MODULE_GEOMETRY_PX["guide_route"]
        controls = UNITY_CONTROL_SIZES_PX
        self.assertEqual(self.panel.preparation_scroll.maximumHeight(),
                         geometry["detail_max_height"])
        self.assertEqual(self.panel.global_progress_bar.height(), controls["progress_primary"])
        self.assertEqual(self.panel.preparation_bar.height(), controls["progress_secondary"])
        self.assertFalse(hasattr(self.panel, "summary"))
        self.assertFalse(hasattr(self.panel, "summary_toggle"))
        self.assertFalse(hasattr(self.panel, "route_progress"))
        for preset, dimensions in UNITY_WINDOW_PRESETS_PX.items():
            with self.subTest(preset=preset):
                self.panel.resize(*dimensions)
                self.app.processEvents()
                self.assertEqual(self.panel.preparation_toggle.width(),
                                 controls["progress_toggle_width"])
                self.assertEqual(self.panel.preparation_toggle.height(),
                                 controls["progress_toggle_height"])
                self.assertEqual(self.panel.participants_button.width(),
                                 controls["guide_character_button"])


    def test_global_progress_tracks_both_lower_bars_across_all_four_presets(self):
        from app.ui.unity_palette import UNITY_WINDOW_PRESETS_PX
        self.panel.show()
        try:
            for preset, dimensions in UNITY_WINDOW_PRESETS_PX.items():
                with self.subTest(preset=preset):
                    self.panel.resize(*dimensions)
                    self.app.processEvents()
                    def edges(widget):
                        left = widget.mapTo(self.panel, widget.rect().topLeft()).x()
                        return left, left + widget.width()
                    global_span = edges(self.panel.global_progress_bar)
                    prep_span = edges(self.panel.preparation_bar)
                    self.assertLess(global_span[1], prep_span[0])
                    self.assertGreater(global_span[1] - global_span[0], 0)
                    self.assertGreater(prep_span[1] - prep_span[0], 0)
        finally:
            self.panel.hide()


    def test_disclosure_controls_keep_shared_unity_direction_and_panel_state(self):
        preparation = self.panel.preparation_toggle
        self.assertIsInstance(preparation, AtlasGuideDisclosure)
        self.assertEqual(preparation.objectName(), "GuideMetricDropdown")
        self.assertFalse(preparation.isChecked())
        self.assertFalse(hasattr(self.panel, "summary_toggle"))
        # This fixture has no certified preparation references.
        self.assertFalse(preparation.isEnabled())
        self.assertFalse(self.panel._preparation_open)
        self.assertEqual(preparation.accessibleName(), "Afficher Préparation")


    def test_preparation_references_are_plain_lines_without_added_bullets(self):
        from unittest.mock import patch

        reference = SimpleNamespace(
            label="Potion de rappel",
            optional_or_conditional=False,
            obtainable_on_route=False,
            needed_at_step=1,
        )
        with patch(
            "app.modules.encyclopedia.views.guide_continuous_route_panel.visible_object_references",
            return_value=(reference,),
        ):
            self.panel.refresh()
        self.assertIn("Potion de rappel", self.panel.preparation_label.text())
        self.assertNotIn("\n• ", self.panel.preparation_label.text())

    def test_actual_and_navigation_work_without_obsolete_summary(self):
        self.assertEqual(self.panel.navigation.position().viewed_step_id,
                         "ganymede_2205_step_0001")
        self.assertEqual(self.panel.title_label.text(), "Fiche 1")
        self.assertFalse(hasattr(self.panel, "summary"))
        self.panel.next_button.click()
        self.assertEqual(self.panel.navigation.position().viewed_step_id,
                         "ganymede_2205_step_0002")
        self.panel.actual_button.click()
        self.assertEqual(self.panel.navigation.position().viewed_step_id,
                         "ganymede_2205_step_0001")
        self.panel.previous_button.click()
        self.assertEqual(self.panel.navigation.position().viewed_step_id,
                         "ganymede_2205_step_0001")
        self.assertFalse(self.panel.preparation_toggle.isChecked())


    def test_all_trusted_continuous_routes_use_aligned_unity_shared_header(self):
        card = self.panel.title_label.parentWidget()
        self.assertEqual(card.objectName(), "GuideContinuousCard")
        header = self.panel.compact_header
        self.assertIsInstance(header, QFrame)
        self.assertEqual(header.objectName(), "GuideCompactHeader")
        self.assertIs(self.panel.position_label.parentWidget(), header)
        self.assertIs(self.panel.participants_button.parentWidget(), header)
        self.assertIs(self.panel.preparation_toggle.parentWidget(), header)
        self.assertEqual(self.panel.global_progress_bar.objectName(), "GuideGlobalProgress")
        self.assertEqual(self.panel.preparation_bar.objectName(), "GuideCompactPreparationProgress")
        self.assertIsInstance(self.panel.global_progress_bar, QProgressBar)
        self.assertIsInstance(self.panel._metric_grid, QGridLayout)
        self.assertIsInstance(self.panel.participants_button, AtlasGuideParticipantButton)
        self.assertIsNone(header.findChild(QProgressBar, "GuideContinuousRouteProgress"))
        self.assertFalse(hasattr(self.panel, "summary"))
        grid = self.panel._metric_grid
        self.assertIsNotNone(grid.itemAtPosition(0, 0).layout())
        self.assertIsNotNone(grid.itemAtPosition(0, 1).layout())
        self.assertIs(grid.itemAtPosition(1, 1).layout().itemAt(1).widget(),
                      self.panel.preparation_toggle)
        self.assertIs(grid.itemAtPosition(2, 1).widget(), self.panel.preparation_scroll)
        self.assertEqual((self.panel.preparation_bar.value(), self.panel.preparation_bar.maximum()), (0, 1))
        self.assertEqual(self.panel.position_label.text(), "FICHE 1")
        self.assertFalse(self.panel._characters_menu.isVisible())
        self.addCleanup(self.panel.hide)
        self.panel.show()
        for width in (900, 1200):
            with self.subTest(width=width):
                self.panel.resize(width, 600)
                self.app.processEvents()
                self.assertIs(self.panel.participants_button.parentWidget(), header)
                self.assertGreater(self.panel.global_progress_bar.width(), 0)


    def test_validation_checked_style_uses_only_unity_green_text_and_outline(self):
        from app.ui.theme import PALETTE, atlas_stylesheet

        style = atlas_stylesheet()
        checked_selector = "QToolButton#GuideContinuousValidate:checked {"
        self.assertIn(checked_selector, style)
        checked_rules = style.split(checked_selector, 1)[1].split("}", 1)[0]
        self.assertIn(f"color: {PALETTE['GREEN']}", checked_rules)
        self.assertIn(f"border-color: {PALETTE['GREEN_BORDER']}", checked_rules)
        self.assertNotIn("background:", checked_rules)

    def test_validation_is_real_and_per_character_only(self):
        self.assertEqual(self.panel.validate_button.text(), "Valider")
        self.assertTrue(self.panel.validate_button.isCheckable())
        self.assertFalse(self.panel.validate_button.isChecked())
        self.panel.validate_button.click()
        step = "ganymede_2205_step_0001"
        self.assertTrue(self.store.is_manual_step_completed("character:1", "dofus_cawotte", step))
        self.assertTrue(self.store.is_manual_step_completed("character:2", "dofus_cawotte", step))
        self.assertEqual(self.panel.navigation.position().actual_step_id,
                         "ganymede_2205_step_0002")
        self.panel.actual_button.click()
        self.assertEqual(self.panel.navigation.position().viewed_step_id,
                         "ganymede_2205_step_0002")
        self.panel.set_characters(["character:1"])
        self.panel.show_step(step)
        self.assertEqual(self.panel.validate_button.text(), "Valider")
        self.assertTrue(self.panel.validate_button.isChecked())
        self.panel.validate_button.click()
        self.assertEqual(self.panel.validate_button.text(), "Valider")
        self.assertFalse(self.panel.validate_button.isChecked())
        self.assertFalse(self.store.is_manual_step_completed("character:1", "dofus_cawotte", step))
        self.assertTrue(self.store.is_manual_step_completed("character:2", "dofus_cawotte", step))
        self.assertEqual(self.panel.navigation.position().actual_step_id, step)

    def test_character_picker_switches_real_keys_without_changing_manual_progress(self):
        characters = [
            SimpleNamespace(key="character:1", label="Alpha - Féca", connected=True),
            SimpleNamespace(key="character:2", label="Beta - Pandawa", connected=False),
            SimpleNamespace(key="slot:3", label="Unsafe slot", connected=True),
        ]
        extra = ContinuousGuideRoutePanel(
            _source_route(), self.store, ("character:1",),
            available_characters=characters,
        )
        self.addCleanup(extra.deleteLater)
        self.assertEqual(set(extra._character_actions), {"character:1", "character:2"})
        self.assertIn("hors ligne", extra._character_actions["character:2"].text())
        updates = []
        extra.selectedCharactersChanged.connect(updates.append)
        extra._character_actions["character:2"].trigger()
        self.assertEqual(
            extra.navigation.selected_character_keys,
            ("character:1", "character:2"),
        )
        self.assertEqual(updates[-1], ("character:1", "character:2"))
        self.assertEqual(extra.participants_button.text(), "Mes personnages (2)")
        self.assertEqual(extra.navigation.position().completed_by_character,
                         {"character:1": 0, "character:2": 0})
        extra._character_actions["character:1"].trigger()
        self.assertEqual(extra.navigation.selected_character_keys, ("character:2",))
        self.assertEqual(self.store.manual_steps("character:1", "dofus_cawotte"), set())

    def test_class_portraits_are_clickable_and_follow_stable_character_keys(self):
        characters = [
            SimpleNamespace(key="character:1", label="Alpha", connected=True, class_key="feca"),
            SimpleNamespace(key="character:2", label="Beta", connected=False, class_key=""),
        ]
        extra = ContinuousGuideRoutePanel(
            _source_route(), self.store, ("character:1",),
            available_characters=characters,
        )
        self.addCleanup(extra.deleteLater)
        self.assertEqual(len(extra.character_icon_buttons), 2)
        self.assertTrue(extra.character_icon_buttons["character:1"].isChecked())
        self.assertEqual(extra.character_icon_buttons["character:2"].toolTip(), "Beta")
        received = []
        extra.selectedCharactersChanged.connect(received.append)
        extra.character_icon_buttons["character:2"].click()
        self.assertEqual(received[-1], ("character:1", "character:2"))
        self.assertTrue(extra._character_actions["character:2"].isChecked())
        extra._character_actions["character:1"].trigger()
        self.assertFalse(extra.character_icon_buttons["character:1"].isChecked())
        self.assertEqual(extra.navigation.selected_character_keys, ("character:2",))

    def test_portrait_ring_tracks_manual_progress_even_when_deselected(self):
        characters = [
            SimpleNamespace(key="character:1", label="Alpha", connected=True, class_key=""),
            SimpleNamespace(key="character:2", label="Beta", connected=False, class_key=""),
        ]
        other_step = "ganymede_2205_step_0001"
        self.store.set_manual_step_completed(
            "character:2", "dofus_cawotte", other_step, True,
        )
        extra = ContinuousGuideRoutePanel(
            _source_route(), self.store, ("character:1",),
            available_characters=characters,
        )
        self.addCleanup(extra.deleteLater)
        one = extra.character_icon_buttons["character:1"]
        two = extra.character_icon_buttons["character:2"]
        self.assertEqual((one.progress_checked, one.progress_total), (0, 3))
        self.assertEqual((two.progress_checked, two.progress_total), (1, 3))
        extra.validate_button.click()
        self.assertEqual((one.progress_checked, one.progress_total), (1, 3))
        extra.set_characters(())
        self.assertEqual((one.progress_checked, one.progress_total), (1, 3))
        self.assertEqual((two.progress_checked, two.progress_total), (1, 3))
        self.assertIsNone(extra.navigation.position().actual_step_id)
        self.assertEqual(extra.global_progress_bar.value(), 0)

    def test_picker_selection_survives_reopening_through_organizer_store(self):
        from app.services.guide_participant_service import GuideParticipantService

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = root / "profiles.json"
            clients = root / "clients.json"
            bindings = root / "bindings.json"
            profile.write_text("{}", encoding="utf-8")
            clients.write_text('{"clients":[]}', encoding="utf-8")
            bindings.write_text(json.dumps({"characters": {
                "1": {"name": "Alpha", "source": "verified_network_identity"},
                "2": {"name": "Beta", "source": "verified_network_identity"},
            }}), encoding="utf-8")
            service = GuideParticipantService(profile, clients, bindings)
            panel = ContinuousGuideRoutePanel(
                _source_route(), self.store, (),
                available_characters=service.available_characters(),
            )
            self.addCleanup(panel.deleteLater)
            panel.selectedCharactersChanged.connect(service.save_selected_keys)
            panel._character_actions["character:2"].trigger()
            fresh = GuideParticipantService(profile, clients, bindings)
            self.assertEqual(fresh.selected_keys(), ("character:2",))
            reopened = ContinuousGuideRoutePanel(
                _source_route(), self.store, fresh.selected_keys(),
                available_characters=fresh.available_characters(),
            )
            self.addCleanup(reopened.deleteLater)
            self.assertTrue(reopened._character_actions["character:2"].isChecked())
            self.assertEqual(reopened.navigation.position().completed_by_character,
                             {"character:2": 0})

    def test_external_selection_updates_picker_without_false_signal(self):
        characters = [
            SimpleNamespace(key="character:1", label="Alpha", connected=True),
            SimpleNamespace(key="character:2", label="Beta", connected=True),
        ]
        extra = ContinuousGuideRoutePanel(
            _source_route(), self.store, (), available_characters=characters,
        )
        self.addCleanup(extra.deleteLater)
        received = []
        extra.selectedCharactersChanged.connect(received.append)
        extra.set_characters(("character:2",))
        self.assertTrue(extra._character_actions["character:2"].isChecked())
        self.assertFalse(extra._character_actions["character:1"].isChecked())
        self.assertEqual(received, [])
        self.assertEqual(extra.navigation.position().actual_step_id, "ganymede_2205_step_0001")

    def test_no_character_can_browse_source_without_checking_steps(self):
        self.panel.set_characters(())
        self.assertTrue(self.panel.next_button.isEnabled())
        self.panel.next_button.click()
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0002",
        )
        self.assertIsNone(self.panel.navigation.position().actual_step_id)
        self.assertFalse(self.panel.validate_button.isEnabled())
        self.assertEqual(self.store.manual_steps("character:1", "dofus_cawotte"), set())

    def test_preparation_is_compact_read_only_and_due_step_scoped(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        route["sections"][0]["steps"][0]["source_action_candidates"] = [
            {"kind": "optional_preparation", "object_id": 361,
             "label": "Cawottes facultatives", "needed_at_source_step": 3},
            {"kind": "prepare_object", "object_id": 969,
             "label": "Couronne du Wa"},
            {"kind": "quest_start", "quest_id": 123, "label": "Une quête"},
        ]
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
        )
        self.addCleanup(panel.deleteLater)
        self.assertEqual(panel.preparation_toggle.text(), "À préparer (2)")
        self.assertFalse(panel.preparation_scroll.isVisible())
        panel.preparation_toggle.click()
        self.assertTrue(panel.preparation_toggle.isChecked())
        self.assertTrue(panel._preparation_open)
        self.assertEqual(panel.preparation_toggle.accessibleName(), "Masquer Préparation")
        self.assertIn("Cawottes facultatives", panel.preparation_label.text())
        self.assertIn("étape 3", panel.preparation_label.text())
        self.assertIn("aucun achat présumé", panel.preparation_label.text())
        self.assertNotIn("Une quête", panel.preparation_label.text())
        self.assertEqual(self.store.manual_steps("character:1", "dofus_cawotte"), set())
        panel.next_step()
        self.assertEqual(panel.preparation_toggle.text(), "À préparer (1)")
        self.assertIn("Cawottes facultatives", panel.preparation_label.text())
        panel.next_step()
        self.assertEqual(panel.preparation_toggle.text(), "À préparer (1)")

    def test_global_progress_reports_only_manual_selected_checks(self):
        self.assertEqual(self.panel.global_progress_bar.value(), 0)
        self.panel.validate_button.click()
        self.assertEqual(self.panel.global_progress_bar.value(), 33)
        self.assertIn("1/3", self.panel.progress_label.text())
        self.panel.set_characters(("character:1",))
        self.assertEqual(self.panel.global_progress_bar.value(), 33)
        self.panel.set_characters(())
        self.assertEqual(self.panel.global_progress_bar.value(), 0)
        self.assertEqual(self.panel.global_progress_value.text(), "—")


    def test_travel_remains_disabled_for_unverified_source_coordinates(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        route["sections"][0]["steps"][0]["source_coordinates_mentioned"] = [[5, -18]]
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
        )
        self.addCleanup(panel.deleteLater)
        events = []
        panel.travelRequested.connect(lambda command, keys: events.append((command, keys)))
        self.assertFalse(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(events, [])

    def test_forged_source_travel_plan_never_enables_game_command(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        route["sections"][0]["steps"][0]["verified_travel_plan"] = {
            "mode": "direct", "participant_keys": ["character:1"],
            "destination": {"x": 5, "y": -18},
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": "ganymede_2205_step_0001",
            "evidence": "fake:source-metadata",
        }
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
        )
        self.addCleanup(panel.deleteLater)
        emitted = []
        panel.travelRequested.connect(lambda command, keys: emitted.append((command, keys)))
        self.assertFalse(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(emitted, [])

    def test_runtime_plan_rejects_foreign_guide_or_source_step(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        step_id = "ganymede_2205_step_0001"
        plan = {
            "mode": "direct", "participant_keys": ["character:1"],
            "destination": {"x": 5, "y": -18},
            "atlas_guide_id": "another_guide",
            "source_step_id": step_id,
            "evidence": "canonical:contract-test",
        }
        plan["source_payload_sha256"] = certified_payload_sha256(route)
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
            verified_travel_plans={step_id: plan},
        )
        self.addCleanup(panel.deleteLater)
        self.assertFalse(panel.travel_button.isEnabled())
        plan["atlas_guide_id"] = "dofus_cawotte"
        plan["source_step_id"] = "ganymede_2205_step_0002"
        panel.refresh()
        self.assertFalse(panel.travel_button.isEnabled())
        plan["source_step_id"] = step_id
        panel.refresh()
        self.assertTrue(panel.travel_button.isEnabled())
        panel.set_verified_travel_plans({})
        self.assertFalse(panel.travel_button.isEnabled())

    def test_verified_direct_travel_emits_only_selected_registered_character(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        route["sections"][0]["steps"][0]["verified_travel_plan"] = {
            "mode": "direct", "participant_keys": ["character:2"],
            "destination": {"x": 5, "y": -18},
            "evidence": "canonical:verified-coordinates",
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": "ganymede_2205_step_0001",
        }
        plan = route["sections"][0]["steps"][0].pop("verified_travel_plan")
        plan["source_payload_sha256"] = certified_payload_sha256(route)
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:2",),
            available_characters=[
                SimpleNamespace(key="character:1", connected=True),
                SimpleNamespace(key="character:2", connected=True),
            ],
            verified_travel_plans={"ganymede_2205_step_0001": plan},
        )
        self.addCleanup(panel.deleteLater)
        events = []
        panel.travelRequested.connect(lambda command, keys: events.append((command, keys)))
        self.assertTrue(panel.travel_button.isEnabled())
        panel.travel_button.click()
        self.assertEqual(events, [("/travel 5,-18", ("character:2",))])
        # A disconnected but still selected character retains progress,
        # not permission to receive another verified travel command.
        panel.available_characters[1].connected = False
        panel.refresh()
        self.assertFalse(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(len(events), 1)
        panel.set_characters(("character:1",))
        self.assertFalse(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(len(events), 1)

    def test_travel_rechecks_current_verified_connection_on_every_dispatch(self):
        route = _source_route()
        step_id = "ganymede_2205_step_0001"
        state = {"connected": True}
        checked = []

        def current_characters():
            checked.append(state["connected"])
            return (SimpleNamespace(key="character:1", connected=state["connected"]),)

        plan = {
            "mode": "direct",
            "participant_keys": ["character:1"],
            "destination": {"x": 5, "y": -18},
            "evidence": "atlas:verified-coordinate",
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": step_id,
            "source_payload_sha256": certified_payload_sha256(route),
        }
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
            available_characters_provider=current_characters,
            verified_travel_plans={step_id: plan},
        )
        self.addCleanup(panel.deleteLater)
        emitted = []
        panel.travelRequested.connect(lambda command, keys: emitted.append((command, keys)))
        self.assertTrue(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(emitted, [("/travel 5,-18", ("character:1",))])

        # The original UI snapshot is still "connected", but the canonical
        # identity provider now says otherwise. Neither the next click nor
        # the refreshed button may use the old evidence.
        state["connected"] = False
        panel.request_current_travel()
        self.assertEqual(len(emitted), 1)
        panel.refresh()
        self.assertFalse(panel.travel_button.isEnabled())
        state["connected"] = True
        panel.refresh()
        self.assertTrue(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(len(emitted), 2)
        self.assertIn(False, checked)
        self.assertTrue(checked[-1])

    def test_zaap_plan_requires_complete_verified_coordinates_and_exact_members(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        plan = {
            "mode": "zaap_then_travel",
            "participant_keys": ["character:1", "character:2"],
            "destination": {"x": 5, "y": -18},
            "zaap": {"x": -32, "y": -56},
            "world": "Monde des Douze",
            "evidence": "canonical:verified-route",
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": "ganymede_2205_step_0001",
        }
        plan["source_payload_sha256"] = certified_payload_sha256(route)
        participants = [
            SimpleNamespace(key="character:1", connected=True),
            SimpleNamespace(key="character:2", connected=False),
        ]
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1", "character:2"),
            available_characters=participants,
            verified_travel_plans={"ganymede_2205_step_0001": plan},
        )
        self.addCleanup(panel.deleteLater)
        events = []
        panel.travelRequested.connect(lambda command, keys: events.append((command, keys)))
        self.assertFalse(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(events, [])
        # The current participant inventory must attest both windows before
        # a full-team /zaap command is offered.
        participants[1].connected = True
        panel.refresh()
        self.assertTrue(panel.travel_button.isEnabled())
        panel.travel_button.click()
        self.assertEqual(events, [
            ("/zaap -32,-56 ; /travel 5,-18", ("character:1", "character:2")),
        ])
        for bad_coordinate in (-(2**31), -(2**31) - 1, 2**31):
            with self.subTest(destination=bad_coordinate):
                plan["destination"]["x"] = bad_coordinate
                panel.refresh()
                self.assertFalse(panel.travel_button.isEnabled())
                panel.request_current_travel()
                self.assertEqual(len(events), 1)
        plan["destination"]["x"] = 5
        for bad_coordinate in (-(2**31), -(2**31) - 1, 2**31):
            with self.subTest(zaap=bad_coordinate):
                plan["zaap"]["y"] = bad_coordinate
                panel.refresh()
                self.assertFalse(panel.travel_button.isEnabled())
                panel.request_current_travel()
                self.assertEqual(len(events), 1)

    def test_travel_refuses_unregistered_keys_even_with_matching_plan(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        route["sections"][0]["steps"][0]["verified_travel_plan"] = {
            "mode": "direct", "participant_keys": ["character:999"],
            "destination": {"x": 1, "y": 2},
            "evidence": "canonical:test",
        }
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:999",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
        )
        self.addCleanup(panel.deleteLater)
        self.assertFalse(panel.travel_button.isEnabled())

    def test_projected_planner_overlay_is_consumed_only_for_same_route_and_team(self):
        route = _source_route()
        step_id = "ganymede_2205_step_0001"
        payload_sha = certified_payload_sha256(route)
        plan = {
            "mode": "direct", "participant_keys": ["character:1"],
            "destination": {"x": 1, "y": 2},
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": step_id,
            "source_payload_sha256": payload_sha,
            "evidence": "atlas:verified-canonical-action",
        }
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
        )
        self.addCleanup(panel.deleteLater)
        projection = {
            "status": "TRUSTED_SOURCE_STEPS_MANUAL_ONLY",
            "atlas_guide_id": "dofus_cawotte",
            "source_payload_sha256": payload_sha,
            "selected_character_keys": ["character:1"],
            "runtime_verified_travel_plans": {step_id: plan},
        }
        self.assertTrue(panel.apply_projected_runtime_plan(projection))
        self.assertTrue(panel.travel_button.isEnabled())
        events = []
        panel.travelRequested.connect(lambda command, keys: events.append((command, keys)))
        panel.travel_button.click()
        self.assertEqual(events, [("/travel 1,2", ("character:1",))])
        panel.set_characters(())
        self.assertFalse(panel.travel_button.isEnabled())
        # A projection for the previous selection invalidates/clears the overlay.
        self.assertFalse(panel.apply_projected_runtime_plan(projection))
        panel.set_characters(("character:1",))
        self.assertFalse(panel.travel_button.isEnabled())

    def test_guides_view_receives_only_its_current_continuous_route_plan(self):
        route = _source_route()
        step_id = "ganymede_2205_step_0001"
        source_sha = certified_payload_sha256(route)
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
        )
        self.addCleanup(panel.deleteLater)
        view = SimpleNamespace(
            _continuous_route_panel=panel,
            current_guide=lambda: SimpleNamespace(id="dofus_cawotte"),
        )
        projection = {
            "status": "TRUSTED_SOURCE_STEPS_MANUAL_ONLY",
            "atlas_guide_id": "dofus_cawotte",
            "source_payload_sha256": source_sha,
            "selected_character_keys": ["character:1"],
            "runtime_verified_travel_plans": {
                step_id: {
                    "atlas_guide_id": "dofus_cawotte",
                    "source_step_id": step_id,
                    "source_payload_sha256": source_sha,
                    "participant_keys": ["character:1"],
                    "mode": "direct",
                    "destination": {"x": 5, "y": -18},
                    "evidence": "atlas:reviewed-start",
                },
            },
        }
        self.assertTrue(GuidesView.apply_continuous_travel_projection(view, projection))
        self.assertTrue(panel.travel_button.isEnabled())
        view.current_guide = lambda: SimpleNamespace(id="dofus_ocre")
        self.assertFalse(GuidesView.apply_continuous_travel_projection(view, projection))
        self.assertFalse(panel.travel_button.isEnabled())
        view.current_guide = lambda: SimpleNamespace(id="dofus_cawotte")
        self.assertFalse(panel.travel_button.isEnabled())
        view._continuous_route_panel = None
        self.assertFalse(GuidesView.apply_continuous_travel_projection(view, projection))

    def test_changing_team_invalidates_even_a_previously_matching_projection(self):
        route = _source_route()
        step_id = "ganymede_2205_step_0001"
        payload_sha = certified_payload_sha256(route)
        plan = {
            "mode": "direct",
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": step_id,
            "source_payload_sha256": payload_sha,
            "participant_keys": ["character:1"],
            "destination": {"x": 5, "y": -18},
            "evidence": "atlas:reviewed-start",
        }
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[
                SimpleNamespace(key="character:1", connected=True),
                SimpleNamespace(key="character:2", connected=True),
            ],
        )
        self.addCleanup(panel.deleteLater)
        projection = {
            "status": "TRUSTED_SOURCE_STEPS_MANUAL_ONLY",
            "atlas_guide_id": "dofus_cawotte",
            "source_payload_sha256": payload_sha,
            "selected_character_keys": ["character:1"],
            "runtime_verified_travel_plans": {step_id: plan},
        }
        self.assertTrue(panel.apply_projected_runtime_plan(projection))
        self.assertTrue(panel.travel_button.isEnabled())
        panel.set_characters(("character:2",))
        panel.set_characters(("character:1",))
        self.assertFalse(panel.travel_button.isEnabled())
        emitted = []
        panel.travelRequested.connect(lambda command, keys: emitted.append((command, keys)))
        panel.request_current_travel()
        self.assertEqual(emitted, [])
        self.assertTrue(panel.apply_projected_runtime_plan(projection))
        self.assertTrue(panel.travel_button.isEnabled())
        panel.set_characters(("character:1",))
        self.assertTrue(panel.travel_button.isEnabled())

    def test_projected_planner_rejects_changed_source_and_clears_old_commands(self):
        route = _source_route()
        step_id = "ganymede_2205_step_0001"
        payload_sha = certified_payload_sha256(route)
        plan = {
            "mode": "direct", "participant_keys": ["character:1"],
            "destination": {"x": 1, "y": 2},
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": step_id,
            "source_payload_sha256": payload_sha,
            "evidence": "atlas:verified-canonical-action",
        }
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
        )
        self.addCleanup(panel.deleteLater)
        projection = {
            "status": "TRUSTED_SOURCE_STEPS_MANUAL_ONLY",
            "atlas_guide_id": "dofus_cawotte",
            "source_payload_sha256": payload_sha,
            "selected_character_keys": ["character:1"],
            "runtime_verified_travel_plans": {step_id: plan},
        }
        self.assertTrue(panel.apply_projected_runtime_plan(projection))
        self.assertTrue(panel.travel_button.isEnabled())
        bad = dict(projection, source_payload_sha256="0" * 64)
        self.assertFalse(panel.apply_projected_runtime_plan(bad))
        self.assertFalse(panel.travel_button.isEnabled())
        self.assertFalse(panel.apply_projected_runtime_plan({"status": "invalid"}))

    def test_runtime_travel_rejects_plan_for_stale_signed_guide(self):
        from copy import deepcopy

        original = _source_route()
        route = deepcopy(original)
        route["sections"][0]["steps"][0]["title"] = "New source edition"
        step_id = "ganymede_2205_step_0001"
        plan = {
            "mode": "direct", "participant_keys": ["character:1"],
            "destination": {"x": 5, "y": -18},
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": step_id,
            "source_payload_sha256": certified_payload_sha256(original),
            "evidence": "atlas:verified-objective",
        }
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
            available_characters=[SimpleNamespace(key="character:1", connected=True)],
            verified_travel_plans={step_id: plan},
        )
        self.addCleanup(panel.deleteLater)
        emitted = []
        panel.travelRequested.connect(lambda command, keys: emitted.append((command, keys)))
        self.assertFalse(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(emitted, [])

    def test_manual_completion_invalidates_old_team_travel_immediately(self):
        route = _source_route()
        step_id = "ganymede_2205_step_0001"
        keys = ("character:1", "character:2")
        plan = {
            "mode": "direct",
            "participant_keys": list(keys),
            "destination": {"x": 5, "y": -18},
            "atlas_guide_id": "dofus_cawotte",
            "source_step_id": step_id,
            "source_payload_sha256": certified_payload_sha256(route),
            "evidence": "atlas:verified-canonical-action",
        }
        panel = ContinuousGuideRoutePanel(
            route, self.store, keys,
            available_characters=[
                SimpleNamespace(key="character:1", connected=True),
                SimpleNamespace(key="character:2", connected=True),
            ],
            verified_travel_plans={step_id: plan},
        )
        self.addCleanup(panel.deleteLater)
        events = []
        panel.travelRequested.connect(lambda command, characters: events.append((command, characters)))
        self.assertTrue(panel.travel_button.isEnabled())
        self.store.set_manual_step_completed(
            "character:1", "dofus_cawotte", step_id, True,
        )
        panel.refresh()
        self.assertFalse(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(events, [])
        # Undoing the manual mark returns the already-verified plan to its
        # original participant state; no synthetic quest completion is used.
        self.store.set_manual_step_completed(
            "character:1", "dofus_cawotte", step_id, False,
        )
        panel.refresh()
        self.assertTrue(panel.travel_button.isEnabled())

    def test_no_characters_block_manual_completion(self):
        self.panel.set_characters(())
        self.assertFalse(self.panel.actual_button.isEnabled())
        self.assertFalse(self.panel.validate_button.isEnabled())
        before = self.store.manual_steps("character:1", "dofus_cawotte")
        self.panel.validate_button.click()
        self.assertEqual(before, self.store.manual_steps("character:1", "dofus_cawotte"))


if __name__ == "__main__":
    unittest.main()
