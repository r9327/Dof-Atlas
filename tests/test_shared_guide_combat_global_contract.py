from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QFrame

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import AchievementProgressService, GuideProgressService
from app.modules.encyclopedia.views.deferred_achievement_guides_view import DeferredAchievementGuidesView
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualCard, SharedGuideManualView


class SharedGuideCombatGlobalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quest_provider = QuestProvider()
        cls.achievement_provider = AchievementProvider(quest_provider=cls.quest_provider)
        cls.achievement_provider.load_all()
        cls.guide_provider = GuideProvider(
            quest_provider=cls.quest_provider,
            achievement_provider=cls.achievement_provider,
        )
        cls.guide_provider.load_all()

    def _view(self, root: Path) -> DeferredAchievementGuidesView:
        quest_progress = root / "quest_progress.json"
        achievement_progress = root / "achievement_progress.json"
        guide_progress = root / "guide_progress.json"
        for path in (quest_progress, achievement_progress, guide_progress):
            path.write_text("{}", encoding="utf-8")
        view = DeferredAchievementGuidesView(
            lambda _text: None,
            provider=self.guide_provider,
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
            achievement_progress_service=AchievementProgressService(achievement_progress),
            guide_progress_service=GuideProgressService(guide_progress),
            quest_progress_path=quest_progress,
        )
        view.set_character_key("character:combat-global")
        return view

    def _service_for(self, view: DeferredAchievementGuidesView, guide_id: str):
        if guide_id == "guide_complet":
            return view.guide_ultime_service
        return view._catalog_manual_services[guide_id]

    def test_combats_are_inline_for_both_guide_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            for guide_id in ("guide_complet", "dofus_sylvestre"):
                self.assertTrue(view.select_guide(guide_id), guide_id)
                self.app.processEvents()
                self.assertIsInstance(view.stack.currentWidget(), SharedGuideManualView)
                service = self._service_for(view, guide_id)

                candidate = next(
                    (
                        (index, card)
                        for index, card in enumerate(service.cards)
                        if service.manual_sections_for_card("character:combat-global", card).get("boss")
                    ),
                    None,
                )
                self.assertIsNotNone(candidate, guide_id)
                index, source = candidate
                card = SharedGuideManualCard(
                    service,
                    "character:combat-global",
                    source,
                    index,
                )
                self.app.processEvents()

                checks = card.findChildren(QCheckBox, "GuideManualCombatCheck")
                self.assertTrue(checks, guide_id)
                self.assertTrue(
                    all(
                        check.parentWidget() is not None
                        and check.parentWidget().objectName() == "GuideManualCombatInlineRow"
                        for check in checks
                    ),
                    guide_id,
                )
                self.assertIsNone(card.findChild(QFrame, "GuideManualDungeonSection"), guide_id)
                card.deleteLater()

            view.deleteLater()
            self.app.processEvents()


    def test_non_combat_rows_do_not_hydrate_cold_quest_details(self) -> None:
        """Rich Quest lookups are reserved for genuinely ambiguous combat rows."""
        targets = [
            {"quest_id": 14, "objective_id": 37, "monster": "Bouftou Royal"},
            {"quest_id": 14, "objective_id": 38, "monster": "Tofu Royal"},
        ]
        fake = SimpleNamespace(
            _combat_targets=targets,
            _rendered_combat_keys=set(),
            _combat_key=SharedGuideManualCard._combat_key,
            _combat_text_matches=SharedGuideManualCard._combat_text_matches,
            _is_combat_row=SharedGuideManualCard._is_combat_row,
            _position_key=SharedGuideManualCard._position_key,
            _combat_evidence=Mock(side_effect=AssertionError("eager rich quest load")),
            _solution_combat_targets_for_row=Mock(return_value=[]),
        )
        ordinary = {"text": "Parler au garde du village", "position": "[1, 2]", "kind": "talk"}
        self.assertEqual(
            SharedGuideManualCard._combat_targets_for_row(fake, ordinary, "now"), []
        )
        fake._combat_evidence.assert_not_called()
        fake._solution_combat_targets_for_row.assert_not_called()

        # Even when the action kind is not marked combat, a monster name is
        # enough canonical evidence to preserve its inline objective.
        named = {"text": "Voir le Bouftou Royal", "position": "[1, 2]", "kind": "talk"}
        self.assertEqual(
            SharedGuideManualCard._combat_targets_for_row(fake, named, "now"),
            [targets[0]],
        )
        fake._combat_evidence.assert_not_called()

    def test_ambiguous_combat_still_resolves_source_evidence(self) -> None:
        target = {"quest_id": 14, "objective_id": 37, "monster": "Bouftou Royal"}
        fake = SimpleNamespace(
            _combat_targets=[target],
            _rendered_combat_keys=set(),
            _combat_key=SharedGuideManualCard._combat_key,
            _combat_text_matches=SharedGuideManualCard._combat_text_matches,
            _is_combat_row=SharedGuideManualCard._is_combat_row,
            _position_key=SharedGuideManualCard._position_key,
            _combat_evidence=Mock(return_value=("[1, 2]", "Vaincre la créature")),
            _solution_combat_targets_for_row=Mock(return_value=[]),
        )
        row = {"text": "Faire le combat indiqué", "position": "[1, 2]", "kind": "combat"}
        self.assertEqual(
            SharedGuideManualCard._combat_targets_for_row(fake, row, "boss"),
            [target],
        )
        fake._combat_evidence.assert_called_once_with(target)


if __name__ == "__main__":
    unittest.main()
