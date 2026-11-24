"""Qt regression for the shared Quêtes / Guide quest information rail."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.quest_catalog import QuestObjective, QuestRecord, QuestStep

from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView
from app.ui.components import AtlasPanelToggle
from app.ui.theme import THEME_TOKENS, atlas_stylesheet


class QuestDetailViewColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_related_achievement_uses_shared_progress_and_manual_complete(self) -> None:
        from app.pages._quests_page_impl import achievement_context_section

        def objective(ident):
            return SimpleNamespace(
                id=ident, text=f"Objectif {ident}", objective_type="",
            )

        achievement = SimpleNamespace(
            id=17, name="Succès test", description="",
            objectives=[objective(1), objective(2), objective(3)], rewards=[],
        )
        progress = SimpleNamespace(
            is_achievement_completed=lambda ident: False,
            is_objective_completed=lambda aid, oid: oid in {1, 2},
        )
        html = achievement_context_section([achievement], progress, [])
        self.assertIn("2 / 3 objectif(s) • 67 %", html)
        progress.is_achievement_completed = lambda ident: True
        self.assertIn(
            "2 / 3 objectif(s) • 100 %",
            achievement_context_section([achievement], progress, []),
        )
        achievement.objectives = []
        self.assertIn(
            "0 / 0 objectif(s) • 100 %",
            achievement_context_section([achievement], progress, []),
        )

    def test_quest_list_cleanup_preserves_parent_until_deferred_delete(self) -> None:
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        from app.pages._quests_page_impl import clear_layout

        host = QWidget()
        layout = QVBoxLayout(host)
        label = QLabel("Ancienne quête")
        layout.addWidget(label)
        try:
            clear_layout(layout)
            self.assertEqual(layout.count(), 0)
            self.assertIs(label.parent(), host)
        finally:
            host.deleteLater()

    def test_shared_quest_detail_cleanup_removes_nested_rows(self) -> None:
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

        host = QWidget()
        layout = QVBoxLayout(host)
        inner = QHBoxLayout()
        label = QLabel("previous quest")
        inner.addWidget(label)
        layout.addLayout(inner)
        try:
            QuestDetailView._clear_layout(layout)
            self.assertEqual(layout.count(), 0)
            self.assertEqual(inner.count(), 0)
            self.assertIsNone(label.parent())
        finally:
            host.deleteLater()

    def test_encyclopedia_detail_panel_keeps_horizontal_scroll_policy(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFrame
        from app.modules.encyclopedia.widgets.detail_panel import DetailPanel

        panel = DetailPanel()
        try:
            self.assertTrue(panel.widgetResizable())
            self.assertEqual(panel.frameShape(), QFrame.NoFrame)
            self.assertEqual(panel.horizontalScrollBarPolicy(), Qt.ScrollBarAsNeeded)
            self.assertEqual(panel.objectName(), "EncyclopediaDetailPanel")
        finally:
            panel.deleteLater()

    def test_quest_columns_share_unity_scroll_policy(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFrame

        panel, scroll, layout = QuestDetailView._build_column("TestQuestPanel")
        try:
            self.assertTrue(scroll.widgetResizable())
            self.assertEqual(scroll.frameShape(), QFrame.NoFrame)
            self.assertEqual(scroll.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
            self.assertEqual(scroll.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded)
            self.assertEqual(scroll.objectName(), "TestQuestPanelScroll")
            self.assertIsNotNone(layout)
        finally:
            panel.deleteLater()

    def test_detail_geometry_is_shared_with_dev_ui(self) -> None:
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        geom = UNITY_MODULE_GEOMETRY_PX["quest_detail"]
        sheet = QuestDetailView(object(), object(), object())
        try:
            self.assertEqual(sheet._right_panel_saved_width,
                             geom["saved_right_width"])
            self.assertEqual(sheet.center_panel.minimumWidth(),
                             geom["center_min_width"])
            self.assertEqual(sheet.right_panel.minimumWidth(),
                             geom["right_min_width"])
            self.assertEqual(sheet.right_panel.maximumWidth(),
                             geom["right_max_width"])
            self.assertEqual(sheet.header.layout().getContentsMargins(),
                             geom["header_margins"])
            prerequisite = sheet._prerequisite_row("Quête précédente", False, 42)
            try:
                layout = prerequisite.layout()
                self.assertEqual(layout.spacing(), geom["prerequisite_row_spacing"])
                self.assertEqual(
                    layout.itemAt(0).widget().width(), geom["prerequisite_marker_width"]
                )
            finally:
                prerequisite.deleteLater()
        finally:
            sheet.deleteLater()

    def test_start_coordinate_is_not_falsely_certified_from_an_objective(self) -> None:
        quest = QuestRecord(
            id=42, name="Quête de test", category="Quêtes",
            level_min=1, level_max=1, start_criterion="",
            zones=["Zone locale"],
            steps=[QuestStep(
                id=1, name="Objectif", description="",
                objectives=[QuestObjective(
                    id=101, text="Rejoindre la zone", type_id=0,
                    map_label="[11,12]",
                )],
            )],
        )
        # Quest objective coordinates are valid objective hints, but not
        # independent evidence of where to launch the quest.
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[11,12]"),
            "Position d'objectif (départ non confirmé)",
        )
        quest.source_info = {"launch_position": {"position": "[3,4]"}}
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[3,4]"),
            "Position de lancement (source locale)",
        )
        # The source declares [3,4]; [11,12] is a different objective, not
        # automatically an independently verified start position.
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[11,12]"),
            "Position d'objectif (départ non confirmé)",
        )
        quest.source_info = {"source_meta": {"startCoords": "[3, 4]"}}
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[3,4]"),
            "Position de lancement (source locale)",
        )
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, ""),
            "Zone de quête",
        )

    def test_legacy_quest_links_share_strict_bold_coordinate_contract(self) -> None:
        from PySide6.QtCore import QUrl
        from app.pages._quests_page_impl import linkify_travel_coordinates, travel_command_from_url
        from app.core.map_coordinates import declared_quest_start

        self.assertIn('<b><a class="coord" href="atlas-travel:3,-6">[3,-6]</a></b>',
                      linkify_travel_coordinates("Aller [ 003, -06 ]"))
        for invalid in ("[-2147483648,2]", "[2147483648,2]", "[" + "9" * 5000 + ",2]"):
            self.assertNotIn("atlas-travel:", linkify_travel_coordinates(invalid))
        for invalid in ("atlas-travel:-2147483648,2", "atlas-travel:3,4?other=5,6"):
            self.assertEqual(travel_command_from_url(QUrl(invalid)), "")
        self.assertEqual(travel_command_from_url(QUrl("atlas-travel:3,-6")), "/travel 3,-6")
        self.assertEqual(declared_quest_start({
            "launch_position": {"position": "[03,4]"},
            "source_meta": {"startCoords": "[3, 4]"},
        })[:2], ("[3,4]", "LOCAL_START_DECLARED"))
        self.assertEqual(declared_quest_start({
            "launch_position": {"position": "Position inconnue"},
            "source_meta": {"startCoords": "[3, 4]"},
        })[:2], ("[3,4]", "INVALID_START_COORDINATES"))

    def test_invalid_or_conflicting_local_starts_are_not_verified(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_start_info,
        )

        quest = QuestRecord(
            id=43, name="Départ incertain", category="Quêtes",
            level_min=1, level_max=1, start_criterion="",
            zones=["Zone locale"],
            steps=[QuestStep(
                id=1, name="Objectif", description="",
                objectives=[QuestObjective(
                    id=101, text="Rejoindre la zone", type_id=0,
                    map_label="[11,12]",
                )],
            )],
        )
        # An invalid source must not block the objective fallback.
        quest.source_info = {"launch_position": {"position": "inconnue"}}
        self.assertEqual(
            quest_start_info(quest, include_map_images=False).position, "[11,12]"
        )
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[11,12]"),
            "Position d'objectif (départ non confirmé)",
        )
        # The second source can provide a coordinate, but a malformed first
        # source must be surfaced as inconsistent, not certified.
        quest.source_info = {
            "launch_position": {"position": "inconnue"},
            "source_meta": {"startCoords": "[3, 4]"},
        }
        self.assertEqual(
            quest_start_info(quest, include_map_images=False).position, "[3,4]"
        )
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[3, 4]"),
            "Départ à vérifier (sources incohérentes)",
        )
        quest.source_info = {
            "launch_position": {"position": "[3,4]"},
            "source_meta": {"startCoords": "[5,6]"},
        }
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[3,4]"),
            "Départ à vérifier (sources incohérentes)",
        )
        # Padded/zero-prefixed source coordinates are normalized for the
        # same [x,y] clickable travel contract used by the Guide.
        quest.source_info = {
            "launch_position": {"position": "[ 003, -06 ]"},
        }
        self.assertEqual(
            quest_start_info(quest, include_map_images=False).position,
            "[3,-6]",
        )
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[3,-6]"),
            "Position de lancement (source locale)",
        )
        # Doduda's numeric missing-location sentinel must not become a
        # clickable "start" or suppress a valid objective fallback.
        quest.source_info = {
            "launch_position": {"position": "[-2147483648,3]"},
        }
        self.assertEqual(
            quest_start_info(quest, include_map_images=False).position,
            "[11,12]",
        )
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[11,12]"),
            "Position d'objectif (départ non confirmé)",
        )
        # Equivalent numbers with formatting changes remain the same source.
        quest.source_info = {
            "launch_position": {"position": "[03,4]"},
            "source_meta": {"startCoords": "[3, 4]"},
        }
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[3,4]"),
            "Position de lancement (source locale)",
        )

    def test_shared_quest_travel_contract_rejects_invalid_coordinates(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            _canonical_source_coordinate,
            travel_command,
            quest_start_info,
        )

        for raw in (
            "[-2147483648,3]",
            "[-2147483649,3]",
            "[2147483648,3]",
            "[" + "9" * 5000 + ",3]",
            "[inconnue,3]",
        ):
            with self.subTest(raw_length=len(raw)):
                self.assertEqual(_canonical_source_coordinate(raw), "")
                self.assertEqual(travel_command(f"Position {raw}"), "")
        self.assertEqual(_canonical_source_coordinate("[ 003, -06 ]"), "[3,-6]")
        self.assertEqual(travel_command("Rejoindre [ 003, -06 ]"), "/travel 3,-6")

        quest = QuestRecord(
            id=45, name="Départ non validé", category="Quêtes",
            level_min=1, level_max=1, start_criterion="",
            zones=["Zone locale"],
            steps=[QuestStep(
                id=1, name="Objectif", description="",
                objectives=[QuestObjective(
                    id=101, text="Rejoindre la zone", type_id=0,
                    map_label="[11,12]",
                )],
            )],
        )
        for invalid_start in ("[2147483648,3]", "[" + "9" * 5000 + ",3]"):
            with self.subTest(source_length=len(invalid_start)):
                quest.source_info = {
                    "launch_position": {"position": invalid_start},
                }
                self.assertEqual(
                    quest_start_info(quest, include_map_images=False).position,
                    "[11,12]",
                )
                self.assertEqual(
                    QuestDetailView._start_position_heading(quest, "[11,12]"),
                    "Position d'objectif (départ non confirmé)",
                )

    def test_imported_walkthrough_objective_position_appears_in_quest_sheet(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            first_position_from_quest, quest_start_info,
        )

        quest = QuestRecord(
            id=47, name="Walkthrough source", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            source_solution_steps=[QuestStep(
                id=2, name="Source", description="Rejoindre le PNJ",
                objectives=[QuestObjective(
                    id=201, text="Parler au PNJ", type_id=0,
                    map_label="[ 003, -06 ]",
                )],
            )],
        )
        info = quest_start_info(quest, include_map_images=False)
        self.assertEqual(info.position, "[3,-6]")
        self.assertEqual(first_position_from_quest(quest), "[3,-6]")
        # Source objective coordinates do not certify where the quest starts.
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, info.position),
            "Position d'objectif (départ non confirmé)",
        )

        # A separately sourced actual start keeps precedence.
        quest.source_info = {"source_meta": {"startCoords": "[9,10]"}}
        self.assertEqual(
            quest_start_info(quest, include_map_images=False).position,
            "[9,10]",
        )

    def test_imported_source_block_position_is_visible_without_local_objectives(self) -> None:
        from app.quest_catalog import QuestSolutionBlock
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            first_position_from_quest, quest_start_info,
        )

        quest = QuestRecord(
            id=48, name="Étape documentaire", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            solution_blocks=[
                QuestSolutionBlock(
                    order=1, block_type="text",
                    content="Rejoignez le temple.",
                    position="[12,-3]",
                ),
            ],
        )
        self.assertEqual(
            quest_start_info(quest, include_map_images=False).position,
            "[12,-3]",
        )
        self.assertEqual(first_position_from_quest(quest), "[12,-3]")

        # Never turn documentary prose or a placeholder into a position.
        quest.solution_blocks[0].position = "carte inconnue"
        self.assertEqual(
            quest_start_info(quest, include_map_images=False).position, "",
        )
        self.assertEqual(first_position_from_quest(quest), "")

    def test_quest_objective_coordinates_are_normalized_not_fabricated(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            first_position_from_quest,
            quest_start_info,
        )

        quest = QuestRecord(
            id=46, name="Objectif sans départ confirmé", category="Quêtes",
            level_min=1, level_max=1, start_criterion="",
            zones=["Zone locale"],
            steps=[QuestStep(
                id=1, name="Visiter", description="",
                objectives=[
                    QuestObjective(id=1, text="Coordonnée hors carte", type_id=0,
                                   map_label="[2147483648,3]"),
                    QuestObjective(id=2, text="Coordonnée inconnue", type_id=0,
                                   map_label="[-2147483648,3]"),
                    QuestObjective(id=3, text="Coordonnée utile", type_id=0,
                                   map_label="[ 003, -06 ]"),
                ],
            )],
        )
        info = quest_start_info(quest, include_map_images=False)
        self.assertEqual(info.position, "[3,-6]")
        self.assertEqual(first_position_from_quest(quest, start_info=info), "[3,-6]")
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, info.position),
            "Position d'objectif (départ non confirmé)",
        )

        # No valid objective coordinate means the UI must show the zone only.
        quest.steps[0].objectives[2].map_label = "coordonnées indisponibles"
        info = quest_start_info(quest, include_map_images=False)
        self.assertEqual(info.position, "")
        self.assertEqual(first_position_from_quest(quest, start_info=info), "")
        self.assertEqual(QuestDetailView._start_position_heading(quest, ""), "Zone de quête")

        # A stale caller-supplied start does not bypass objective validation.
        from dataclasses import replace
        quest.steps[0].objectives[2].map_label = "[1,2]"
        self.assertEqual(
            first_position_from_quest(
                quest, start_info=replace(info, position="[2147483648,3]")
            ),
            "[1,2]",
        )

    def test_solution_objective_uses_only_valid_copyable_coordinates(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            solution_objective,
        )

        discover = QuestObjective(
            id=108, text="Découvrir la carte : 1234", type_id=0,
            map_label="[ 003, -06 ]",
        )
        row = solution_objective(discover)
        self.assertIsNotNone(row)
        self.assertEqual(row.text, "Rendez-vous en [3,-6].")
        self.assertEqual(row.position, "[3,-6]")

        discover.map_label = "[2147483648,3]"
        # A missing map is not permission to erase the documentary objective.
        # The ID remains trackable, but cannot become a travel action.
        unresolved = solution_objective(discover)
        self.assertIsNotNone(unresolved)
        self.assertEqual(unresolved.objective_id, 108)
        self.assertEqual(unresolved.text, "Découvrir la carte : 1234")
        self.assertEqual(unresolved.position, "")
        discover.map_label = ""
        self.assertEqual(solution_objective(discover).text, unresolved.text)

        combat = QuestObjective(
            id=109, text="Combat contre le monstre", type_id=6,
            image_label="Bouftou Royal", map_label="[-2147483648,3]",
        )
        combat_row = solution_objective(combat)
        self.assertIsNotNone(combat_row)
        self.assertEqual(combat_row.text, "Lancez le combat contre Bouftou Royal.")
        self.assertEqual(combat_row.position, "")
        combat.map_label = "[2,3]"
        combat_row = solution_objective(combat)
        self.assertEqual(combat_row.position, "[2,3]")
        self.assertIn("en [2,3]", combat_row.text)

    def test_discover_map_without_location_stays_in_quest_steps(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_steps,
        )
        from app.modules.encyclopedia.views.guides_view import linkify_travel_text

        quest = QuestRecord(
            id=900, name="Quête avec carte inconnue", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            steps=[
                QuestStep(id=7, name="Visiter", description="", objectives=[
                    QuestObjective(
                        id=17, text="Découvrir la carte : 9999",
                        type_id=0, map_label="[-2147483648,0]",
                    ),
                    QuestObjective(
                        id=18, text="Parler au garde", type_id=1,
                        map_label="[2,3]",
                    ),
                ]),
            ],
        )
        steps = quest_solution_steps(quest)
        self.assertEqual(len(steps), 1)
        self.assertEqual([objective.objective_id for objective in steps[0].objectives],
                         [17, 18])
        self.assertEqual(steps[0].objectives[0].text, "Découvrir la carte : 9999")
        self.assertEqual(steps[0].objectives[0].position, "")
        self.assertNotIn(
            "atlas-travel",
            linkify_travel_text(steps[0].objectives[0].text),
        )
        self.assertEqual(steps[0].objectives[1].position, "[2,3]")

    def test_source_solution_steps_preserve_local_progress_objective_alignment(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_steps,
        )

        quest = QuestRecord(
            id=901, name="Carte et progression", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            steps=[QuestStep(
                id=3, name="Étape locale", description="",
                objectives=[
                    QuestObjective(
                        id=17, text="Découvrir la carte : 9999",
                        type_id=0, map_label="",
                    ),
                    QuestObjective(
                        id=18, text="Parler au garde", type_id=1, map_label="[2,3]",
                    ),
                ],
            )],
            source_solution_steps=[QuestStep(
                id=4, name="Source importée", description="",
                objectives=[
                    QuestObjective(
                        id=1001, text="Découvrir la carte : 9999",
                        type_id=0, map_label="[-2147483648,0]",
                    ),
                    QuestObjective(
                        id=1002, text="Parler au garde", type_id=1, map_label="[2,3]",
                    ),
                ],
            )],
        )
        steps = quest_solution_steps(quest)
        self.assertEqual(len(steps), 1)
        self.assertEqual(
            [objective.objective_id for objective in steps[0].objectives],
            [17, 18],
        )
        self.assertEqual(
            [objective.text for objective in steps[0].objectives],
            ["Découvrir la carte : 9999", "Parler au garde"],
        )
        self.assertEqual(
            [objective.position for objective in steps[0].objectives],
            ["", "[2,3]"],
        )

    def test_source_blocks_share_audit_instruction_filter(self) -> None:
        from app.quest_catalog import QuestSolutionBlock
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_blocks,
        )

        quest = QuestRecord(
            id=902, name="Sources non vérifiées", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            solution_blocks=[
                QuestSolutionBlock(1, "text", "Qf>=20"),
                QuestSolutionBlock(
                    2, "text",
                    "Mini-carte L’aperçu de la carte sera affiché ici sur le site.",
                ),
                QuestSolutionBlock(3, "text", "Découvrir la carte : 9999"),
                QuestSolutionBlock(4, "image", image_path="image_locale.webp"),
            ],
        )
        blocks = quest_solution_blocks(quest)
        self.assertEqual(
            [(block.block_type, block.content) for block in blocks],
            [("text", "Découvrir la carte : 9999"), ("image", "")],
        )
        self.assertEqual(blocks[1].image_path, "image_locale.webp")

    def test_source_progress_matching_survives_insertion_and_reordering(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_steps,
        )

        quest = QuestRecord(
            id=910, name="Étapes importées", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            steps=[QuestStep(1, "Locale", "", [
                QuestObjective(17, "Parler au garde", 1, map_label="[2,3]"),
                QuestObjective(18, "Découvrir la carte : 991", 0, map_label="[4,5]"),
            ])],
            source_solution_steps=[QuestStep(2, "Documentation", "", [
                QuestObjective(-1, "Lire la note du PNJ", 0),
                QuestObjective(-2, "Découvrir la carte : 991", 0, map_label="[4,5]"),
                QuestObjective(-3, "Parler au garde", 0, map_label="[2,3]"),
            ])],
        )
        objectives = quest_solution_steps(quest)[0].objectives
        self.assertEqual([row.objective_id for row in objectives], [None, 18, 17])
        self.assertEqual(objectives[0].text, "Lire la note du PNJ")

    def test_source_progress_matching_rejects_conflicting_coordinates(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_steps,
        )

        quest = QuestRecord(
            id=911, name="Coordonnées opposées", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            steps=[QuestStep(1, "Locale", "", [
                QuestObjective(17, "Parler au garde", 1, map_label="[2,3]"),
            ])],
            source_solution_steps=[QuestStep(2, "Documentation", "", [
                QuestObjective(-1, "Parler au garde", 0, map_label="[9,9]"),
            ])],
        )
        objective = quest_solution_steps(quest)[0].objectives[0]
        self.assertIsNone(objective.objective_id)
        self.assertEqual(objective.position, "[9,9]")

    def test_source_progress_matching_rejects_ambiguous_duplicate_objectives(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_steps,
        )

        quest = QuestRecord(
            id=912, name="Doublons", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            steps=[QuestStep(1, "Locale", "", [
                QuestObjective(17, "Parler au garde", 1),
            ])],
            source_solution_steps=[QuestStep(2, "Documentation", "", [
                QuestObjective(-1, "Parler au garde", 0),
                QuestObjective(-2, "Parler au garde", 0),
            ])],
        )
        rows = quest_solution_steps(quest)[0].objectives
        self.assertEqual([row.objective_id for row in rows], [None, None])

        # Even one source row cannot choose between two local objectives
        # with the same text and no valid position differentiating them.
        quest.source_solution_steps[0].objectives.pop()
        quest.steps[0].objectives.append(QuestObjective(18, "Parler au garde", 1))
        self.assertIsNone(quest_solution_steps(quest)[0].objectives[0].objective_id)

    def test_source_progress_matching_rejects_conflicting_item_ids(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_steps,
        )

        quest = QuestRecord(
            id=913, name="Objets distincts", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            steps=[QuestStep(1, "Locale", "", [
                QuestObjective(
                    17, "Rapporter le trophée", 2, item_id=104,
                ),
            ])],
            source_solution_steps=[QuestStep(2, "Documentation", "", [
                QuestObjective(
                    -1, "Rapporter le trophée", 0, item_id=105,
                ),
            ])],
        )
        self.assertIsNone(
            quest_solution_steps(quest)[0].objectives[0].objective_id
        )
        quest.source_solution_steps[0].objectives[0].item_id = 104
        self.assertEqual(
            quest_solution_steps(quest)[0].objectives[0].objective_id,
            17,
        )

    def test_documentary_fallback_discards_placeholder_descriptions_only(self) -> None:
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_steps,
        )

        quest = QuestRecord(
            id=920, name="Nettoyage de source", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            source_solution_steps=[
                QuestStep(
                    id=-1, name="Titre", description="Qf>=20",
                    objectives=[QuestObjective(
                        id=-1001, text="Découvrir la carte : 9999",
                        type_id=0, map_label="[-2147483648,1]",
                    )],
                ),
                QuestStep(
                    id=-2, name="Autre", description=(
                        "Mini-carte L’aperçu de la carte sera affiché ici sur le site."
                    ),
                ),
                QuestStep(
                    id=-3, name="Conclusion", description="Parlez au gardien.",
                ),
            ],
        )
        steps = quest_solution_steps(quest)
        self.assertEqual([step.description for step in steps],
                         ["", "", "Parlez au gardien."])
        self.assertEqual(steps[0].objectives[0].text,
                         "Découvrir la carte : 9999")
        self.assertEqual(steps[0].objectives[0].position, "")
        self.assertEqual(steps[0].objectives[0].objective_id, None)

    def test_source_block_metadata_coordinates_render_only_verified_travel_links(self) -> None:
        from app.quest_catalog import QuestSolutionBlock
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_blocks,
        )
        from app.modules.encyclopedia.views.guides_view import (
            solution_text_document,
        )

        quest = QuestRecord(
            id=921, name="Positions des blocs", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            solution_blocks=[
                QuestSolutionBlock(
                    1, "text", "Parler au garde.", position="[ 003, -06 ]",
                ),
                QuestSolutionBlock(
                    2, "text", "Départ [3,-6]", position="[3,-6]",
                ),
                QuestSolutionBlock(
                    3, "text", "Continuer la quête.",
                    position="[2147483648,1]",
                ),
                QuestSolutionBlock(4, "text", "", position="[2,3]"),
                QuestSolutionBlock(5, "image", "", position="[2,3]"),
                QuestSolutionBlock(6, "heading", "", position="[2,3]"),
            ],
        )
        blocks = quest_solution_blocks(quest)
        self.assertEqual(len(blocks), 4)
        self.assertEqual(
            [block.position for block in blocks],
            ["[3,-6]", "[3,-6]", "", "[2,3]"],
        )
        labels = [solution_text_document((block,)) for block in blocks]
        try:
            self.assertIn("Position source", labels[0].text())
            self.assertIn("atlas-travel:3,-6", labels[0].text())
            self.assertEqual(labels[1].text().count("atlas-travel:3,-6"), 1)
            self.assertNotIn("Position source", labels[1].text())
            self.assertNotIn("atlas-travel:", labels[2].text())
            self.assertIn("Position source", labels[3].text())
            self.assertIn("atlas-travel:2,3", labels[3].text())
        finally:
            for label in labels:
                label.deleteLater()

    def test_documentary_fallback_notice_uses_visible_not_raw_blocks(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock
        from app.quest_catalog import QuestSolutionBlock

        for raw_block, expected_notice in (
            (QuestSolutionBlock(1, "text", "Qf>=20"), True),
            (QuestSolutionBlock(1, "text", "Parlez au chef."), False),
            (QuestSolutionBlock(1, "heading", "Étape 1"), True),
        ):
            with self.subTest(block=raw_block.content):
                provider = Mock()
                provider.get_catalog.return_value = SimpleNamespace(by_id={})
                sheet = QuestDetailView(provider, Mock(), Mock())
                sheet._prerequisite_rows = Mock(return_value=([], Mock()))
                sheet._ordered_neighbors = Mock(return_value=(None, None))
                quest = QuestRecord(
                    id=923, name="Source et avertissement", category="Quêtes",
                    level_min=1, level_max=200, start_criterion="",
                    solution_blocks=[raw_block],
                    source_solution_steps=[QuestStep(
                        id=-1, name="Étape source", description="",
                        objectives=[QuestObjective(
                            id=-1001, text="Parler au capitaine", type_id=1,
                        )],
                    )],
                )
                try:
                    sheet._render_solution(quest, None)
                    notices = [
                        label.text() for label in sheet.findChildren(QLabel)
                        if "Documentation locale complète indisponible" in label.text()
                    ]
                    self.assertEqual(bool(notices), expected_notice)
                finally:
                    sheet.deleteLater()
                    self.app.processEvents()

    def test_missing_documentary_image_has_explicit_fallback(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            DisplaySolutionBlock,
        )
        from app.modules.encyclopedia.views.guides_view import (
            solution_block_widget,
        )

        with TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing-illustration.png")
            label = solution_block_widget(DisplaySolutionBlock(
                "image", image_path=missing, caption="Carte de la quête",
            ))
            try:
                self.assertIsInstance(label, QLabel)
                self.assertEqual(label.objectName(), "MutedLabel")
                self.assertIn("Image locale indisponible", label.text())
                self.assertIn("Carte de la quête", label.text())
                self.assertFalse(label.styleSheet())
            finally:
                label.deleteLater()

    def test_precomputed_documentary_blocks_prevent_double_filtering(self) -> None:
        from unittest.mock import patch
        from app.quest_catalog import QuestSolutionBlock
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            quest_solution_blocks,
        )
        from app.modules.encyclopedia.views.guides_view import (
            quest_solution_document_widgets,
        )

        quest = QuestRecord(
            id=924, name="Contenu unique", category="Quêtes",
            level_min=1, level_max=200, start_criterion="",
            solution_blocks=[QuestSolutionBlock(1, "text", "Rejoindre [3,-6].")],
        )
        blocks = quest_solution_blocks(quest)
        with patch(
            "app.modules.encyclopedia.views.guides_view.quest_solution_blocks",
            side_effect=AssertionError("already filtered once"),
        ):
            widgets = quest_solution_document_widgets(
                quest, source_blocks=blocks,
            )
        try:
            self.assertEqual(len(widgets), 1)
            self.assertIn("atlas-travel:3,-6", widgets[0].text())
        finally:
            for widget in widgets:
                widget.deleteLater()

    def test_all_displayed_travel_coordinates_share_bold_link_markup(self) -> None:
        from PySide6.QtCore import Qt
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            DisplaySolutionBlock,
        )
        from app.modules.encyclopedia.views.guides_view import (
            copy_travel_link,
            copy_travel_position,
            linkify_travel_text,
            solution_text_document,
            text_label,
        )

        coordinates = "Rejoindre [-2,13], puis vérifier [5,-6]."
        html = linkify_travel_text(coordinates)
        self.assertEqual(html.count("<b>"), 2)
        self.assertIn("atlas-travel:-2,13", html)
        self.assertIn("atlas-travel:5,-6", html)
        self.assertNotIn("font-size:", html)
        self.assertIn(
            'href="atlas-travel:3,-6"',
            linkify_travel_text("Départ [ 003, -06 ]"),
        )
        for bad in (
            "[-2147483648,3]",
            "[2147483648,3]",
            "[" + "9" * 5000 + ",3]",
        ):
            with self.subTest(bad_length=len(bad)):
                self.assertNotIn("atlas-travel:", linkify_travel_text(bad))

        clipboard = QApplication.clipboard()
        clipboard.setText("commande précédente")
        copy_travel_link("atlas-travel:-2147483648,3")
        copy_travel_position("[2147483648,3]")
        self.assertEqual(clipboard.text(), "commande précédente")
        copy_travel_link("atlas-travel:5,-6")
        self.assertEqual(clipboard.text(), "/travel 5,-6")
        copy_travel_position("[ 003, -06 ]")
        self.assertEqual(clipboard.text(), "/travel 3,-6")

        for label in (
            text_label(coordinates, "QuestLaunchPosition"),
            solution_text_document(
                (DisplaySolutionBlock("text", coordinates),)
            ),
        ):
            try:
                self.assertEqual(label.textFormat(), Qt.RichText)
                self.assertIn("<b>", label.text())
                self.assertEqual(label.styleSheet(), "")
            finally:
                label.deleteLater()

    def test_right_column_round_trip_preserves_quest_and_scroll(self) -> None:
        # clear() is sufficient for layout tests; no game catalogue is fetched.
        sheet = QuestDetailView(object(), object(), object())
        sheet.resize(1050, 700)
        sheet.show()
        try:
            sheet.right_layout.insertWidget(0, QLabel("Détail local"))
            self.app.processEvents()
            # An explicit range tests the scrollbar contract independently of
            # offscreen Qt platform geometry and its varying size hints.
            bar = sheet.right_scroll.verticalScrollBar()
            bar.setRange(0, 240)
            bar.setValue(120)
            expected = bar.value()
            self.assertEqual(expected, 120)
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertIs(sheet.splitter.widget(1), sheet.right_panel)
            self.assertIsInstance(sheet.right_panel_toggle, AtlasPanelToggle)
            self.assertEqual(sheet.right_panel_toggle.objectName(), "GuideRightPanelToggle")
            self.assertEqual(sheet.right_panel_toggle.text(), "›")

            sheet.right_panel_toggle.click()
            self.assertTrue(sheet.right_panel.isHidden())
            self.assertTrue(sheet._right_panel_collapsed)
            self.assertEqual(sheet._right_panel_scroll_position, expected)
            self.assertEqual(sheet.right_panel_toggle.text(), "‹")
            self.assertIn("Réafficher", sheet.right_panel_toggle.accessibleName())

            sheet.right_panel_toggle.click()
            self.app.processEvents()
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertFalse(sheet._right_panel_collapsed)
            self.assertGreaterEqual(sheet.splitter.sizes()[1], 240)
            self.assertEqual(bar.value(), min(expected, bar.maximum()))
            self.assertEqual(sheet.right_panel_toggle.text(), "›")
            self.assertIn("Masquer", sheet.right_panel_toggle.toolTip())

            sheet.right_panel_toggle.click()
            sheet.clear("Pas de quête sélectionnée")
            self.assertTrue(sheet.right_panel.isHidden())
            sheet.right_panel_toggle.click()
            self.assertFalse(sheet.right_panel.isHidden())
        finally:
            sheet.close()
            sheet.deleteLater()
            self.app.processEvents()

    def test_embedded_guide_context_uses_same_reversible_control(self) -> None:
        from PySide6.QtCore import Qt
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestViewContext

        sheet = QuestDetailView(object(), object(), object())
        sheet.context = QuestViewContext(host="guides", guide_id="guide_local")
        context = sheet.context
        try:
            self.assertTrue(bool(sheet.right_panel_toggle.focusPolicy() & Qt.TabFocus))
            sheet.set_right_panel_collapsed(True)
            self.assertTrue(sheet.right_panel.isHidden())
            self.assertTrue(sheet.right_panel_toggle.property("collapsed"))
            sheet.set_right_panel_collapsed(True)  # Repeated signal is inert.
            sheet.set_right_panel_collapsed(False)
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertFalse(sheet.right_panel_toggle.property("collapsed"))
            self.assertIs(sheet.context, context)
            self.assertEqual(context.host, "guides")
        finally:
            sheet.deleteLater()
            self.app.processEvents()

    def test_right_toggle_uses_shared_unity_theme(self) -> None:
        css = atlas_stylesheet()
        self.assertIn("QToolButton#GuideRightPanelToggle", css)
        self.assertIn("border: 1px solid " + THEME_TOKENS["BORDER"], css)
        self.assertIn('QToolButton#GuideRightPanelToggle[collapsed="true"]', css)


if __name__ == "__main__":
    unittest.main()
