"""Qt proof of manual Ganymède source navigation, not a mock button shell."""
from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QMenu

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

    def test_actual_summary_and_navigation_keep_popup_open(self):
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0001",
        )
        self.assertEqual(self.panel.title_label.text(), "Fiche 1")
        self.assertFalse(self.panel.summary.isVisible())
        self.panel.summary_toggle.click()
        self.assertTrue(self.panel.summary.isVisibleTo(self.panel))
        self.panel.next_button.click()
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0002",
        )
        self.assertTrue(self.panel.summary.isVisibleTo(self.panel))
        self.panel.actual_button.click()
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0001",
        )
        self.assertTrue(self.panel.summary.isVisibleTo(self.panel))
        self.panel.summary_toggle.click()
        self.assertFalse(self.panel.summary.isVisible())
        self.panel.next_button.click()
        self.assertFalse(self.panel.summary.isVisible())
        self.panel.summary_toggle.click()
        self.assertTrue(self.panel.summary.isVisibleTo(self.panel))

    def test_character_and_summary_controls_belong_to_the_active_card_header(self):
        card = self.panel.title_label.parentWidget()
        self.assertEqual(card.objectName(), "GuideContinuousCard")
        for control in (
            self.panel.position_label, self.panel.participants_button,
            self.panel.summary_toggle,
        ):
            self.assertIs(control.parentWidget(), card)
        self.assertEqual(self.panel.position_label.text(), "FICHE 1")
        self.assertFalse(self.panel.characters_panel.isVisible())
        self.assertEqual(self.panel.findChildren(QMenu), [])
        self.assertEqual(self.panel.findChildren(QComboBox), [])
        self.addCleanup(self.panel.hide)
        self.panel.show()
        for width in (900, 1200):
            with self.subTest(width=width):
                self.panel.resize(width, 600)
                self.panel.summary.setVisible(True)
                self.app.processEvents()
                self.assertFalse(self.panel.participants_button.geometry().intersects(
                    self.panel.summary_toggle.geometry(),
                ))
                self.assertLess(
                    self.panel.participants_button.geometry().bottom(),
                    self.panel.title_label.geometry().top(),
                )
                self.assertTrue(card.rect().contains(self.panel.summary_toggle.geometry()))
                self.panel.participants_button.click()
                self.assertTrue(self.panel.characters_panel.isVisibleTo(card))
                self.assertTrue(card.rect().contains(self.panel.characters_panel.geometry()))
                self.panel.participants_button.click()
                self.assertFalse(self.panel.characters_panel.isVisible())

    def test_current_step_displays_source_provenance_not_false_certification(self):
        route = _source_route()
        route["sections"][0]["steps"][0]["source_page"] = 4
        route["sections"][0]["steps"][1]["source_page"] = True
        panel = ContinuousGuideRoutePanel(route, self.store, ("character:1",))
        self.addCleanup(panel.deleteLater)
        self.assertIn("Ganymède #2205", panel.source_evidence_label.text())
        self.assertIn("fiche 1/3", panel.source_evidence_label.text())
        self.assertIn("page source 4", panel.source_evidence_label.text())
        self.assertIn("non certifiées", panel.source_evidence_label.text())
        panel.next_button.click()
        self.assertIn("fiche 2/3", panel.source_evidence_label.text())
        self.assertNotIn("page source", panel.source_evidence_label.text())

    def test_manual_sheet_status_keeps_two_characters_independent(self):
        first = "ganymede_2205_step_0001"
        self.assertEqual(
            self.panel.current_manual_label.text(),
            "Cette fiche : 0/2 personnages cochés manuellement."
        )
        self.store.set_manual_step_completed("character:2", "dofus_cawotte", first, True)
        self.panel.refresh()
        self.assertIn("1/2", self.panel.current_manual_label.text())
        self.assertEqual(self.panel.validate_button.text(), "Valider manuellement")
        self.panel.validate_button.click()
        self.assertTrue(self.store.is_manual_step_completed("character:1", "dofus_cawotte", first))
        self.assertTrue(self.store.is_manual_step_completed("character:2", "dofus_cawotte", first))
        self.assertIn("2/2", self.panel.current_manual_label.text())
        self.assertEqual(self.panel.validate_button.text(), "Décocher manuellement")
        self.panel.next_button.click()
        self.assertIn("0/2", self.panel.current_manual_label.text())
        self.assertNotIn("0 %", self.panel.current_manual_label.text())
        self.panel.set_characters(())
        self.assertIn("sélectionnez un personnage", self.panel.current_manual_label.text())
        self.assertFalse(self.panel.validate_button.isEnabled())
        # No automatic quest or achievement completion is created by the view.
        self.assertTrue(self.store.is_manual_step_completed("character:2", "dofus_cawotte", first))

    def test_validation_is_real_and_per_character_only(self):
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
        self.panel.validate_button.click()
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
        self.assertEqual(set(extra._character_checks), {"character:1", "character:2"})
        self.assertIn("hors ligne", extra._character_checks["character:2"].text())
        updates = []
        extra.selectedCharactersChanged.connect(updates.append)
        extra._character_checks["character:2"].click()
        self.assertEqual(
            extra.navigation.selected_character_keys,
            ("character:1", "character:2"),
        )
        self.assertEqual(updates[-1], ("character:1", "character:2"))
        self.assertEqual(extra.participants_button.text(), "Mes personnages (2)")
        self.assertEqual(extra.navigation.position().completed_by_character,
                         {"character:1": 0, "character:2": 0})
        extra._character_checks["character:1"].click()
        self.assertEqual(extra.navigation.selected_character_keys, ("character:2",))
        self.assertEqual(self.store.manual_steps("character:1", "dofus_cawotte"), set())

    def test_character_panel_stays_open_during_manual_navigation(self):
        characters = [SimpleNamespace(key="character:1", label="Alpha", connected=True)]
        extra = ContinuousGuideRoutePanel(
            _source_route(), self.store, ("character:1",), available_characters=characters,
        )
        self.addCleanup(extra.deleteLater)
        extra.show()
        self.addCleanup(extra.hide)
        extra.participants_button.click()
        self.assertTrue(extra.characters_panel.isVisible())
        extra.next_button.click()
        self.assertTrue(extra.characters_panel.isVisible())
        extra.show_actual()
        self.assertTrue(extra.characters_panel.isVisible())
        extra.participants_button.click()
        self.assertFalse(extra.characters_panel.isVisible())

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
        self.assertTrue(extra._character_checks["character:2"].isChecked())
        extra._character_checks["character:1"].click()
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
        self.assertEqual(extra.route_progress.value(), 0)

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
            panel._character_checks["character:2"].click()
            fresh = GuideParticipantService(profile, clients, bindings)
            self.assertEqual(fresh.selected_keys(), ("character:2",))
            reopened = ContinuousGuideRoutePanel(
                _source_route(), self.store, fresh.selected_keys(),
                available_characters=fresh.available_characters(),
            )
            self.addCleanup(reopened.deleteLater)
            self.assertTrue(reopened._character_checks["character:2"].isChecked())
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
        self.assertTrue(extra._character_checks["character:2"].isChecked())
        self.assertFalse(extra._character_checks["character:1"].isChecked())
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

    def test_route_progress_reports_only_manual_selected_checks(self):
        self.assertEqual(self.panel.route_progress.value(), 0)
        self.assertIn("0/6", self.panel.route_progress.format())
        self.panel.validate_button.click()
        self.assertEqual(self.panel.route_progress.value(), 33)
        self.assertIn("2/6", self.panel.route_progress.format())
        self.panel.set_characters(("character:1",))
        self.assertEqual(self.panel.route_progress.value(), 33)
        self.assertIn("1/3", self.panel.route_progress.format())
        self.panel.set_characters(())
        self.assertEqual(self.panel.route_progress.value(), 0)
        self.assertIn("aucun personnage", self.panel.route_progress.format())

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
        panel.set_characters(("character:1",))
        self.assertFalse(panel.travel_button.isEnabled())
        panel.request_current_travel()
        self.assertEqual(len(events), 1)

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
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1", "character:2"),
            available_characters=[
                SimpleNamespace(key="character:1", connected=True),
                SimpleNamespace(key="character:2", connected=False),
            ],
            verified_travel_plans={"ganymede_2205_step_0001": plan},
        )
        self.addCleanup(panel.deleteLater)
        events = []
        panel.travelRequested.connect(lambda command, keys: events.append((command, keys)))
        self.assertTrue(panel.travel_button.isEnabled())
        panel.travel_button.click()
        self.assertEqual(events, [
            ("/zaap -32,-56 ; /travel 5,-18", ("character:1", "character:2")),
        ])
        plan["destination"]["x"] = -(2**31)
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
