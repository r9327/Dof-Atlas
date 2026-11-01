"""Qt proof of manual Ganymède source navigation, not a mock button shell."""
from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

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

    def test_progress_refresh_does_not_clear_current_summary_selection(self):
        changes = []
        selection = self.panel.summary.selectionModel()
        selection.selectionChanged.connect(lambda *_: changes.append(True))
        self.panel.refresh()
        self.panel.refresh()
        self.assertEqual(changes, [])
        self.panel.show_step("ganymede_2205_step_0002")
        self.assertEqual(self.panel.summary.currentIndex().row(), 1)
        changes.clear()
        self.panel.refresh()
        self.assertEqual(changes, [])
        self.assertEqual(self.panel.summary.currentIndex().row(), 1)

    def test_step_navigation_preserves_summary_model_and_updates_only_markers(self):
        resets = []
        changed = []
        self.panel.summary_model.modelReset.connect(lambda: resets.append(True))
        self.panel.summary_model.dataChanged.connect(lambda *_: changed.append(True))
        model = self.panel.summary_model
        old_first = model.data(model.index(0, 0))
        old_second = model.data(model.index(1, 0))
        # Simply browsing a different step does not alter the followed
        # marker. Validating the actual step does, and must avoid a full reset.
        self.panel.validate_button.click()
        self.assertEqual(resets, [])
        self.assertTrue(changed)
        self.assertNotEqual(model.data(model.index(0, 0)), old_first)
        self.assertNotEqual(model.data(model.index(1, 0)), old_second)
        self.assertTrue(model.data(model.index(1, 0)).startswith("→ "))
        self.panel.show_step("ganymede_2205_step_0001")
        self.panel.validate_button.click()  # Undo the first step for both characters.
        self.assertEqual(resets, [])
        self.assertEqual(model.data(model.index(0, 0)), old_first)
        self.assertEqual(model.data(model.index(1, 0)), old_second)

    def test_actual_summary_and_navigation_keep_popup_open(self):
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0001",
        )
        self.assertEqual(self.panel.title_label.text(), "Étape 1")
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

    def test_compact_header_keeps_step_navigation_and_source_card_separate(self):
        card = self.panel.title_label.parentWidget()
        self.assertEqual(card.objectName(), "GuideContinuousCard")
        header = self.panel.position_label.parentWidget()
        self.assertEqual(header.objectName(), "GuideCompactHeader")
        for control in (
            self.panel.participants_button, self.panel.summary_toggle,
            self.panel.preparation_toggle, self.panel.step_jump,
            self.panel.actual_button,
        ):
            self.assertIs(control.parentWidget(), header)
        self.assertEqual(self.panel.position_label.text(), "ÉTAPE 1 / 3")
        self.assertEqual(self.panel.step_jump.value(), 1)
        self.assertFalse(self.panel._characters_menu.isVisible())
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
                self.assertLess(header.geometry().bottom(), card.geometry().top())
                self.assertTrue(header.rect().contains(
                    self.panel.summary_toggle.geometry()
                ))
        self.panel.step_jump.setValue(3)
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0003",
        )
        self.assertEqual(self.panel.position_label.text(), "ÉTAPE 3 / 3")
        self.panel.actual_button.click()
        self.assertEqual(self.panel.step_jump.value(), 1)

    def test_source_actions_follow_guide_sections_not_flat_quest_names(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        route["sections"][0]["steps"][0]["source_action_candidates"] = [
            {"kind": "quest_prerequisite", "label": "Vérifier le prérequis"},
            {"kind": "talk", "label": "Parler au PNJ"},
            {"kind": "move", "label": "Aller sur la carte indiquée"},
            {"kind": "prepare_object", "label": "Objet nécessaire"},
        ]
        extra = ContinuousGuideRoutePanel(route, self.store, ("character:1",))
        self.addCleanup(extra.deleteLater)
        body = extra.body_label.text()
        self.assertLess(body.index("Avant de commencer"), body.index("À faire maintenant"))
        self.assertLess(body.index("À faire maintenant"), body.index("À préparer"))
        self.assertIn("Parler au PNJ", body)
        self.assertIn("Aller sur la carte indiquée", body)
        self.assertIn("références à vérifier", body)
        self.assertEqual(self.store.manual_steps("character:1", "dofus_cawotte"), set())

    def test_sommaire_marks_actual_checked_and_partially_checked_steps(self):
        idx = self.panel.summary_model.index
        label = lambda i: self.panel.summary_model.data(idx(i))
        self.assertTrue(label(0).startswith("→ "))
        self.assertFalse(label(1).startswith("✓ "))
        self.panel.validate_button.click()
        self.assertTrue(label(0).startswith("✓ "))
        self.assertTrue(label(1).startswith("→ "))
        self.panel.set_characters(("character:1",))
        self.panel.show_step("ganymede_2205_step_0001")
        self.panel.validate_button.click()
        self.panel.set_characters(("character:1", "character:2"))
        self.assertTrue(label(0).startswith("→◐ "))
        self.assertTrue(label(0).endswith("Fiche 1 — Étape 1"))
        self.assertEqual(self.panel.navigation.position().actual_step_id,
                         "ganymede_2205_step_0001")

    def test_validation_is_real_and_per_character_only(self):
        self.panel.validate_button.click()
        step = "ganymede_2205_step_0001"
        self.assertEqual(self.panel.navigation.position().viewed_step_id,
                         "ganymede_2205_step_0002")
        self.assertEqual(self.panel.step_jump.value(), 2)
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

    def test_reviewing_future_step_does_not_replace_actual_route_position(self):
        future = "ganymede_2205_step_0003"
        self.panel.show_step(future)
        self.panel.validate_button.click()
        self.assertEqual(self.panel.navigation.position().viewed_step_id, future)
        self.assertEqual(self.panel.position_label.text(), "ÉTAPE 3 / 3")
        self.assertEqual(self.panel.navigation.position().actual_step_id,
                         "ganymede_2205_step_0001")
        self.assertTrue(self.store.is_manual_step_completed(
            "character:1", "dofus_cawotte", future
        ))
        self.panel.actual_button.click()
        self.assertEqual(self.panel.step_jump.value(), 1)

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
        self.assertIn("Mes personnages (2)", extra.participants_button.toolTip())
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

    def test_empty_selection_can_browse_first_step_and_validation_opens_picker(self):
        from types import SimpleNamespace
        panel = ContinuousGuideRoutePanel(
            _source_route(), self.store, (),
            available_characters=(
                SimpleNamespace(key="character:1", label="Premier", class_key="iop"),
            ),
        )
        self.addCleanup(panel.deleteLater)
        self.assertEqual(panel.navigation.position().viewed_step_id,
                         "ganymede_2205_step_0001")
        self.assertIsNone(panel.navigation.position().actual_step_id)
        self.assertEqual(panel.step_jump.value(), 1)
        self.assertTrue(panel.validate_button.isEnabled())
        panel.validate_button.click()
        self.assertTrue(panel.participants_button.isChecked())
        self.assertTrue(panel.characters_panel.isVisibleTo(panel))
        self.assertEqual(self.store.manual_steps("character:1", "dofus_cawotte"), set())
        panel.character_icon_buttons["character:1"].click()
        self.assertEqual(panel.navigation.position().selected_character_keys,
                         ("character:1",))
        panel.validate_button.click()
        self.assertTrue(self.store.is_manual_step_completed(
            "character:1", "dofus_cawotte", "ganymede_2205_step_0001"
        ))

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

    def test_preparation_source_scan_is_cached_across_progress_refreshes(self):
        from unittest.mock import patch
        from app.modules.encyclopedia.services.guide_continuous_preparation import (
            visible_object_references,
        )

        with patch(
            "app.modules.encyclopedia.views.guide_continuous_route_panel.visible_object_references",
            wraps=visible_object_references,
        ) as scan:
            panel = ContinuousGuideRoutePanel(
                _source_route(), self.store, ("character:1",),
            )
            self.addCleanup(panel.deleteLater)
            self.assertEqual(scan.call_count, 1)
            for _ in range(5):
                panel.refresh()
            self.assertEqual(scan.call_count, 1)
            panel.next_step()
            self.assertEqual(scan.call_count, 2)
            panel.previous_step()
            self.assertEqual(scan.call_count, 2)
            # Manual progress affects selection and labels, never immutable
            # source preparation references for a previously visited step.
            panel.toggle_manual_current()
            self.assertEqual(scan.call_count, 2)

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

    def test_all_twenty_enabled_source_guides_open_with_inert_progress(self):
        guides_dir = (
            Path(__file__).resolve().parents[1] / "data" / "encyclopedia" / "guides"
        )
        catalog = json.loads((guides_dir / "catalog.json").read_text(encoding="utf-8"))
        rows = [
            row for row in catalog["guides"]
            if row.get("ganymede_manual_ui_ready") is True
        ]
        self.assertEqual(len(rows), 20)
        for row in rows:
            with self.subTest(guide=row["id"]):
                route_file = (
                    guides_dir / "replacement_drafts" / "cutovers"
                    / f"{row['id']}.json"
                )
                route = json.loads(route_file.read_text(encoding="utf-8"))
                panel = ContinuousGuideRoutePanel(
                    route, self.store, ("character:1",),
                )
                try:
                    total = route["expected_source_step_count"]
                    self.assertEqual(len(panel.navigation.step_ids), total)
                    self.assertIn(f"ÉTAPE 1 / {total}", panel.position_label.text())
                    self.assertTrue(panel.body_label.text().strip())
                    self.assertFalse(panel.travel_button.isEnabled())
                    panel.step_jump.setValue(total)
                    self.assertEqual(panel.step_jump.value(), total)
                    self.assertIn(
                        f"ÉTAPE {total} / {total}", panel.position_label.text()
                    )
                    panel.actual_button.click()
                    self.assertEqual(panel.step_jump.value(), 1)
                    self.assertEqual(
                        self.store.manual_steps("character:1", row["id"]), set()
                    )
                finally:
                    panel.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_thirty_reopens_keep_manual_progress_and_source_step_identity(self):
        route = _source_route()
        first_step = "ganymede_2205_step_0001"
        self.store.set_manual_step_completed(
            "character:1", "dofus_cawotte", first_step, True,
        )
        for cycle in range(30):
            with self.subTest(cycle=cycle):
                panel = ContinuousGuideRoutePanel(
                    route, self.store, ("character:1", "character:2"),
                )
                try:
                    panel.show()
                    self.app.processEvents()
                    self.assertEqual(
                        panel.navigation.position().actual_step_id, first_step
                    )
                    self.assertEqual(
                        panel.navigation.position().completed_by_character,
                        {"character:1": 1, "character:2": 0},
                    )
                    panel.next_button.click()
                    panel.actual_button.click()
                    self.assertEqual(
                        panel.navigation.position().viewed_step_id, first_step
                    )
                finally:
                    panel.hide()
                    panel.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(
            self.store.manual_steps("character:1", "dofus_cawotte"), {first_step}
        )
        self.assertEqual(
            self.store.manual_steps("character:2", "dofus_cawotte"), set()
        )

    def test_shipped_cawotte_and_argente_are_real_browsable_manual_routes(self):
        source_dir = (
            Path(__file__).resolve().parents[1] / "data" / "encyclopedia"
            / "guides" / "replacement_drafts" / "cutovers"
        )
        for guide_id, expected_count, source_id in (
            ("dofus_cawotte", 64, 2205),
            ("dofus_argente", 237, 2203),
        ):
            with self.subTest(guide_id=guide_id):
                route = json.loads(
                    (source_dir / f"{guide_id}.json").read_text(encoding="utf-8")
                )
                panel = ContinuousGuideRoutePanel(
                    route, self.store, ("character:1",),
                )
                self.addCleanup(panel.deleteLater)
                self.assertEqual(len(panel.navigation.step_ids), expected_count)
                self.assertEqual(
                    panel.navigation.position().viewed_step_id,
                    f"ganymede_{source_id}_step_0001",
                )
                self.assertNotIn(
                    "Actions de cette étape non renseignées.",
                    panel.body_label.text(),
                )
                panel.step_jump.setValue(expected_count)
                self.assertEqual(
                    panel.navigation.position().viewed_step_id,
                    f"ganymede_{source_id}_step_{expected_count:04d}",
                )
                panel.actual_button.click()
                self.assertEqual(
                    panel.navigation.position().viewed_step_id,
                    f"ganymede_{source_id}_step_0001",
                )
                self.assertEqual(self.store.manual_steps("character:1", guide_id), set())

    def test_copyable_source_items_and_coordinates_never_trigger_travel(self):
        from copy import deepcopy

        route = deepcopy(_source_route())
        route["sections"][0]["steps"][0]["source_action_candidates"] = [
            {"kind": "prepare_object", "object_id": 969,
             "label": 'Cape du "Wa" <Wabbit>'},
        ]
        route["sections"][0]["steps"][0]["source_coordinates_mentioned"] = [
            [25, -4], [24, -3],
        ]
        panel = ContinuousGuideRoutePanel(
            route, self.store, ("character:1",),
        )
        self.addCleanup(panel.deleteLater)
        emitted = []
        panel.travelRequested.connect(lambda *args: emitted.append(args))
        self.assertIn("&lt;Wabbit&gt;", panel.preparation_label.text())
        self.assertFalse(panel.preparation_label.openExternalLinks())
        self.assertFalse(panel.coordinates_label.openExternalLinks())

        clipboard = QApplication.clipboard()
        clipboard.clear()
        panel.preparation_label.linkActivated.emit("item:0")
        self.assertEqual(clipboard.text(), 'Cape du "Wa" <Wabbit>')
        panel.coordinates_label.linkActivated.emit("coordinate:1")
        self.assertEqual(clipboard.text(), "[24, -3]")
        for invalid in (
            "item:1000", "item:-1", "item:0/other", "https://bad.test",
            "item:" + "9" * 6000, "coordinate:" + "9" * 6000,
        ):
            panel._copy_source_link(invalid)
            self.assertEqual(clipboard.text(), "[24, -3]")

        self.assertEqual(emitted, [])
        self.assertEqual(self.store.manual_steps("character:1", "dofus_cawotte"), set())

    def test_runtime_travel_rejects_unbounded_and_boolean_coordinates(self):
        for bad in (
            {"x": 2**64, "y": 0},
            {"x": -(2**31), "y": 0},
            {"x": 0, "y": -(2**31)},
            {"x": 0, "y": 2**80},
            {"x": True, "y": 1},
            {"x": 0, "y": 1.5},
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(self.panel._exact_coordinates(bad))
        self.assertEqual(
            self.panel._exact_coordinates({"x": 25, "y": -4}), (25, -4)
        )

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
