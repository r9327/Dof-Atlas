from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.guide_ultime_generated_service import GuideUltimeGeneratedService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import AchievementProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.views.guide_ultime_universal_view import GuideUltimeUniversalView
from app.modules.encyclopedia.views.guide_ultime_walkthrough_card import GuideUltimeWalkthroughCard, QuestWalkthroughIndex
from app.quest_catalog import QuestObjective, QuestRecord, QuestStep


class FakeQuestProvider:
    def __init__(self, quest: QuestRecord) -> None:
        self.quest = quest

    def get_quest(self, quest_id: int):
        return self.quest if int(quest_id) == int(self.quest.id) else None


class GuideUltimeWalkthroughTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.quest_path = root / "quest_progress.json"
        self.achievement_path = root / "achievement_progress.json"
        self.guide_path = root / "guide_progress.json"
        route_path = root / "guide_ultime_gps_route.json"
        final_path = root / "guide_ultime_final.json"
        route = {
            "schema_version": 5,
            "universal_route": {"common_route_quest_count": 1, "qq_required_count": 1600},
            "conditional_branches": {
                "class_card": {
                    "options": [
                        {"class": "Huppermage", "quest_id": 42},
                        {"class": "Eliotrope", "quest_id": 99},
                    ]
                }
            },
            "steps": [{
                "index": 1,
                "planned_at_level": 10,
                "destination": "[5,6] Test",
                "x": 5,
                "y": 6,
                "zone": "Zone test",
                "a_prendre": [{"quest_id": 42, "quest_name": "Quête test", "title": "Prendre — Quête test"}],
                "a_faire_ici": [{"quest_id": 42, "quest_name": "Quête test", "objective_id": 4201, "title": "Parler au PNJ"}],
                "progresse_aussi": {"quest_ids": [42], "success_ids": []},
                "a_preparer": [],
                "hard_runtime_gates": [],
                "avant_de_partir": [],
                "succes_monstres_a_faire": [],
                "succes_donjon_a_faire": [],
                "ensuite": None,
            }],
        }
        route_path.write_text(json.dumps(route), encoding="utf-8")
        final_path.write_text(json.dumps({"schema_version": 5}), encoding="utf-8")
        self.q = QuestProgressService(self.quest_path)
        self.a = AchievementProgressService(self.achievement_path)
        self.g = GuideProgressService(self.guide_path)
        self.service = GuideUltimeGeneratedService(self.q, self.a, self.g, route_path=route_path, final_path=final_path)

        source_objective = QuestObjective(
            id=-1001,
            text="Parlez à Capitaine Testeur puis choisissez la première réponse.",
            type_id=0,
            map_label="[7,8]",
        )
        quest = QuestRecord(
            id=42,
            name="Quête test",
            category="Test",
            level_min=10,
            level_max=10,
            start_criterion="",
            zones=["Zone test"],
            source_solution_steps=[QuestStep(id=-1, name="La rencontre", description="Présentez-vous au capitaine.", objectives=[source_objective])],
            steps=[QuestStep(id=1, name="", description="", objectives=[QuestObjective(id=4201, text="Parler au PNJ", type_id=1)])],
            source_info={
                "launch_position": {"position": "[5,6]"},
                "source_meta": {"startNpc": "Garde Départ", "startCoords": "[5,6]", "zone": "Zone test"},
            },
        )
        self.provider = FakeQuestProvider(quest)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_start_instruction_names_npc_and_is_not_a_quest_completion_checkbox(self):
        card = self.service.cards[0]
        widget = GuideUltimeWalkthroughCard(
            self.service,
            "hero",
            card,
            0,
            active=True,
            compact=False,
            quest_toggle=lambda *_args: None,
            objective_toggle=lambda *_args: None,
            walkthrough=QuestWalkthroughIndex(self.provider),
        )
        labels = [label.text() for label in widget.findChildren(QLabel)]
        self.assertTrue(any("Parler à Garde Départ" in text for text in labels))
        self.assertTrue(any("Départ : [5,6]" in text for text in labels))
        checkboxes = widget.findChildren(QCheckBox)
        self.assertFalse(any("Prendre — Quête test" == box.text() for box in checkboxes))
        self.assertFalse(self.q.is_quest_completed("hero", 42))
        widget.close()

    def test_objective_uses_documentary_walkthrough_text_and_position(self):
        index = QuestWalkthroughIndex(self.provider)
        detail = index.objective(42, 4201)
        self.assertIn("Capitaine Testeur", detail.text)
        self.assertEqual(detail.position, "[7,8]")
        self.assertEqual(detail.step_title, "La rencontre")
        self.assertIn("Présentez-vous", detail.step_description)

    def test_every_visible_position_is_clickable_and_copies_travel_command(self):
        view = GuideUltimeUniversalView(self.service, character_key="hero", quest_provider=self.provider)
        QApplication.processEvents()
        targets = [
            label for label in view.findChildren(QLabel)
            if label.property("travelCopyEnabled") and "[" in label.text()
        ]
        self.assertTrue(targets)
        target = next(label for label in targets if "[5,6]" in label.text())
        self.assertEqual(target.property("travelCommand"), "/travel 5,6")
        event = QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(1, 1),
            QPointF(1, 1),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        QApplication.sendEvent(target, event)
        self.assertEqual(QApplication.clipboard().text(), "/travel 5,6")
        view.close()

    def test_breadcrumb_is_directly_inside_guide_and_returns_to_guides(self):
        view = GuideUltimeUniversalView(self.service, character_key="hero", quest_provider=self.provider)
        QApplication.processEvents()
        first_item = view.breadcrumb_layout.itemAt(0)
        self.assertIsNotNone(first_item)
        button = first_item.widget()
        self.assertIsInstance(button, QPushButton)
        self.assertEqual(button.objectName(), "GuideBreadcrumbButton")
        self.assertEqual(button.text(), "Guides")
        calls: list[bool] = []
        view.backToGuidesRequested.connect(lambda: calls.append(True))
        button.click()
        QApplication.processEvents()
        self.assertEqual(calls, [True])
        view.close()

    def test_class_is_never_manually_selectable(self):
        view = GuideUltimeUniversalView(self.service, character_key="hero", quest_provider=self.provider)
        QApplication.processEvents()
        texts = [box.text() for box in view.findChildren(QCheckBox)]
        self.assertFalse(any("Huppermage" in text or "Eliotrope" in text for text in texts))
        view.close()

    def test_stale_zone_without_valid_coords_does_not_override_v5_route_and_sentinel_is_hidden(self):
        stale_quest = QuestRecord(
            id=42,
            name="Quête test",
            category="Test",
            level_min=1,
            level_max=1,
            start_criterion="",
            zones=["Village d'Amakna"],
            source_solution_steps=[],
            steps=[QuestStep(id=1, name="", description="", objectives=[QuestObjective(id=4201, text="Parler", type_id=1)])],
            source_info={
                "source_meta": {
                    "startNpc": "Ganymède",
                    "startCoords": "[-2147483648,-2147483648]",
                    "zone": "Village d'Amakna",
                }
            },
        )
        provider = FakeQuestProvider(stale_quest)
        index = QuestWalkthroughIndex(provider)
        npc, position, zone = index.start_details(42)
        self.assertEqual(npc, "Ganymède")
        self.assertEqual(position, "")
        self.assertEqual(zone, "")

        card = dict(self.service.cards[0])
        card["zone"] = "Astrub"
        card["x"] = 4
        card["y"] = -19
        card["ensuite"] = {
            "x": -2147483648,
            "y": -2147483648,
            "zone": "Village d'Amakna",
        }
        widget = GuideUltimeWalkthroughCard(
            self.service,
            "hero",
            card,
            0,
            active=True,
            compact=False,
            quest_toggle=lambda *_args: None,
            objective_toggle=lambda *_args: None,
            walkthrough=index,
        )
        labels = [label.text() for label in widget.findChildren(QLabel)]
        self.assertTrue(any("Astrub" in text and "[4,-19]" in text for text in labels))
        self.assertFalse(any("-2147483648" in text for text in labels))
        self.assertFalse(any("Village d'Amakna" in text for text in labels))
        widget.close()


if __name__ == "__main__":
    unittest.main()
