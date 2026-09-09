from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.constants import KEY_SESSION_ORDER
from app.modules.encyclopedia.models import Guide, GuideSection, GuideStep
from app.modules.encyclopedia.services.guide_progress_calculator import GuideProgressCalculator
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)
from app.network.character_resolver import CharacterSlotResolver
from app.network.events import CharacterIdentifiedEvent, QuestCompletedEvent
from app.network.progress_bridge import NetworkProgressBridge
from app.quest_catalog import QuestCatalog, QuestObjective, QuestRecord, QuestStep


class _AchievementProvider:
    def __init__(self, achievement) -> None:
        self.achievement = achievement

    def load_retained(self):
        return [self.achievement]

    def get_by_id(self, achievement_id: int):
        if int(achievement_id) == int(self.achievement.id):
            return self.achievement
        return None


class ProgressCrossSurfaceReloadTests(unittest.TestCase):
    def test_network_completion_survives_reload_on_quest_guide_and_achievement_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_path = root / "profiles.json"
            client_index_path = root / "client_index.json"
            quest_path = root / "quest_progress.json"
            achievement_path = root / "achievement_progress.json"
            guide_path = root / "guide_progress.json"

            profile_path.write_text(
                json.dumps({KEY_SESSION_ORDER: ["Alpha"]}),
                encoding="utf-8",
            )
            client_index_path.write_text(
                json.dumps({"clients": [{"index": 1, "name": "Alpha"}]}),
                encoding="utf-8",
            )

            quest = QuestRecord(
                id=10,
                name="Quest A",
                category="Test",
                level_min=1,
                level_max=200,
                start_criterion="",
                steps=[
                    QuestStep(
                        id=1000,
                        name="Step A",
                        description="",
                        objectives=[QuestObjective(id=100, text="A", type_id=1)],
                    )
                ],
            )
            catalog = QuestCatalog([quest])
            quest_ref = SimpleNamespace(entity_type="quest", entity_id=10)
            achievement_objective = SimpleNamespace(
                id=501,
                objective_type="",
                entity_refs=(quest_ref,),
                criterion="",
                text="",
            )
            achievement = SimpleNamespace(
                id=500,
                category_name="Quêtes",
                objectives=(achievement_objective,),
            )
            provider = _AchievementProvider(achievement)
            quest_progress = QuestProgressService(quest_path)
            achievement_progress = AchievementProgressService(achievement_path)
            resolver = CharacterSlotResolver(
                profile_path,
                client_index_path,
                slot_count=1,
            )
            logger = logging.getLogger(f"progress-reload-{id(self)}")
            logger.addHandler(logging.NullHandler())
            bridge = NetworkProgressBridge(
                quest_catalog=catalog,
                quest_progress_service=quest_progress,
                achievement_progress_service=achievement_progress,
                achievement_provider=provider,
                character_resolver=resolver,
                logger=logger,
            )

            identified = bridge.handle(
                CharacterIdentifiedEvent(
                    session_id="session-a",
                    event_id="identify-alpha",
                    reliable=True,
                    character_name="Alpha",
                    character_id=1001,
                )
            )
            completed = bridge.handle(
                QuestCompletedEvent(
                    session_id="session-a",
                    event_id="quest-10",
                    reliable=True,
                    quest_id=10,
                )
            )
            self.assertTrue(identified.accepted)
            self.assertTrue(completed.accepted)
            self.assertTrue(completed.changed)

            character_key = "character:1001"
            fresh_quests = QuestProgressService(quest_path)
            fresh_achievements = AchievementProgressService(achievement_path)
            fresh_guides = GuideProgressService(guide_path)
            guide = Guide(
                id="reload-guide",
                title="Reload guide",
                category="Test",
                sections=(
                    GuideSection(
                        id="section",
                        title="Section",
                        steps=(
                            GuideStep(
                                id="quest:10",
                                step_type="quest",
                                order=1,
                                entity_id=10,
                            ),
                        ),
                    ),
                ),
            )
            calculator = GuideProgressCalculator(
                fresh_quests,
                fresh_guides,
                fresh_achievements,
                catalog.by_id,
            )

            self.assertTrue(fresh_quests.is_quest_completed(character_key, 10))
            self.assertTrue(
                fresh_achievements.is_achievement_completed(character_key, 500)
            )
            progress = calculator.guide_progress(guide, character_key)
            self.assertEqual((progress.completed, progress.total), (1, 1))

            for path in (quest_path, achievement_path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(set(payload["characters"]), {character_key})
                self.assertNotIn("slot:1", payload["characters"])


if __name__ == "__main__":
    unittest.main()
