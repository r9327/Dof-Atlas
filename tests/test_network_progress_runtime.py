from __future__ import annotations

import json
import logging
import queue
import tempfile
import threading
import time
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
from app.network.events import (
    AchievementCompletedEvent,
    CharacterIdentifiedEvent,
    NetworkEvent,
    QuestCompletedEvent,
    QuestObjectiveCompletedEvent,
)
from app.network.normalizer import DecodedClientMessage, ProtocolEventNormalizer
from app.network.progress_bridge import NetworkProgressBridge
from app.network.runtime import NetworkEventRuntime
from app.quest_catalog import QuestCatalog, QuestObjective, QuestRecord, QuestStep


class FakeAchievementProvider:
    def __init__(self, achievements=()):
        self._achievements = tuple(achievements)
        self._by_id = {int(row.id): row for row in self._achievements}

    def load_retained(self):
        return list(self._achievements)

    def get_by_id(self, achievement_id: int):
        return self._by_id.get(int(achievement_id))


class FakeNetworkSource:
    def __init__(self):
        self.events: queue.Queue[object] = queue.Queue()
        self.started = False
        self.stopped = threading.Event()
        self.fail_reads = 0

    def start(self) -> None:
        self.started = True
        self.stopped.clear()

    def stop(self) -> None:
        self.stopped.set()

    def read_event(self, timeout: float):
        if self.fail_reads:
            self.fail_reads -= 1
            raise ValueError("synthetic parser failure")
        if self.stopped.is_set():
            return None
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None


class UnknownReliableEvent(NetworkEvent):
    pass


class NetworkProgressRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.profile_path = self.root / "profiles.json"
        self.client_index_path = self.root / "client_index.json"
        self.profile_path.write_text(
            json.dumps({KEY_SESSION_ORDER: ["Alpha", "Beta", ""]}),
            encoding="utf-8",
        )
        self.client_index_path.write_text(
            json.dumps(
                {
                    "clients": [
                        {"index": 1, "name": "Alpha"},
                        {"index": 2, "name": "Beta"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.quest_path = self.root / "quest_progress.json"
        self.achievement_path = self.root / "achievement_progress.json"
        self.guide_path = self.root / "guide_progress.json"
        self.quest_progress = QuestProgressService(self.quest_path)
        self.achievement_progress = AchievementProgressService(self.achievement_path)
        self.quests = [
            QuestRecord(
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
            ),
            QuestRecord(
                id=20,
                name="Quest B",
                category="Test",
                level_min=1,
                level_max=200,
                start_criterion="",
                steps=[
                    QuestStep(
                        id=2000,
                        name="Step B",
                        description="",
                        objectives=[QuestObjective(id=200, text="B", type_id=1)],
                    )
                ],
            ),
        ]
        self.catalog = QuestCatalog(self.quests)
        quest_ref = SimpleNamespace(entity_type="quest", entity_id=10)
        achievement_objective = SimpleNamespace(
            id=501,
            objective_type="",
            entity_refs=(quest_ref,),
            criterion="",
            text="",
        )
        self.achievement = SimpleNamespace(
            id=500,
            category_name="Quêtes",
            objectives=(achievement_objective,),
        )
        self.provider = FakeAchievementProvider((self.achievement,))
        self.resolver = CharacterSlotResolver(
            self.profile_path,
            self.client_index_path,
            slot_count=3,
        )
        self.logger = logging.getLogger(f"network-test-{id(self)}")
        self.logger.addHandler(logging.NullHandler())
        self.bridge = NetworkProgressBridge(
            quest_catalog=self.catalog,
            quest_progress_service=self.quest_progress,
            achievement_progress_service=self.achievement_progress,
            achievement_provider=self.provider,
            character_resolver=self.resolver,
            logger=self.logger,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def identify(self, session_id: str, name: str, event_id: str = "identify"):
        character_id = {"Alpha": 1001, "Beta": 2002}[name]
        return self.bridge.handle(
            CharacterIdentifiedEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                character_name=name,
                character_id=character_id,
            )
        )

    def test_character_resolution_uses_verified_id_keys(self) -> None:
        alpha = self.resolver.resolve_for_session("Alpha", "session-a", 1001)
        beta = self.resolver.resolve_for_session("Beta", "session-b", 2002)
        self.assertIsNotNone(alpha)
        self.assertIsNotNone(beta)
        self.assertEqual(alpha.character_key, "character:1001")
        self.assertEqual(beta.character_key, "character:2002")

    def test_quest_completed_updates_shared_quest_and_achievement_progress(self) -> None:
        self.assertTrue(self.identify("session-a", "Alpha").accepted)
        result = self.bridge.handle(
            QuestCompletedEvent(
                session_id="session-a",
                event_id="quest-10",
                reliable=True,
                quest_id=10,
            )
        )
        self.assertTrue(result.accepted)
        self.assertTrue(result.changed)
        self.assertTrue(self.quest_progress.is_quest_completed("character:1001", 10))
        self.assertTrue(self.achievement_progress.is_achievement_completed("character:1001", 500))

    def test_duplicate_event_is_idempotent(self) -> None:
        self.identify("session-a", "Alpha")
        event = QuestCompletedEvent(
            session_id="session-a",
            event_id="same-event",
            reliable=True,
            quest_id=10,
        )
        first = self.bridge.handle(event)
        second = self.bridge.handle(event)
        self.assertTrue(first.changed)
        self.assertTrue(second.accepted)
        self.assertFalse(second.changed)
        self.assertEqual(second.reason, "duplicate_event")
        self.assertEqual(self.quest_progress.completed_quest_ids("character:1001"), {10})

    def test_out_of_order_quest_event_does_not_write_without_character(self) -> None:
        result = self.bridge.handle(
            QuestCompletedEvent(
                session_id="session-a",
                reliable=True,
                quest_id=10,
            )
        )
        self.assertFalse(result.accepted)
        self.assertFalse(self.quest_progress.is_quest_completed("slot:1", 10))
        self.assertFalse(self.quest_progress.is_quest_completed("slot:2", 10))

    def test_character_switch_routes_following_events_to_new_slot(self) -> None:
        self.identify("session-a", "Alpha", "identify-alpha")
        self.bridge.handle(
            QuestCompletedEvent(session_id="session-a", reliable=True, quest_id=10)
        )
        self.identify("session-a", "Beta", "identify-beta")
        self.bridge.handle(
            QuestCompletedEvent(session_id="session-a", reliable=True, quest_id=20)
        )
        self.assertTrue(self.quest_progress.is_quest_completed("character:1001", 10))
        self.assertFalse(self.quest_progress.is_quest_completed("character:1001", 20))
        self.assertTrue(self.quest_progress.is_quest_completed("character:2002", 20))
        self.assertFalse(self.quest_progress.is_quest_completed("character:2002", 10))

    def test_two_sessions_keep_progress_separate(self) -> None:
        self.identify("session-a", "Alpha", "identify-alpha")
        self.identify("session-b", "Beta", "identify-beta")
        self.bridge.handle(QuestCompletedEvent(session_id="session-a", reliable=True, quest_id=10))
        self.bridge.handle(QuestCompletedEvent(session_id="session-b", reliable=True, quest_id=20))
        self.assertEqual(self.quest_progress.completed_quest_ids("character:1001"), {10})
        self.assertEqual(self.quest_progress.completed_quest_ids("character:2002"), {20})

    def test_reconnection_replays_state_without_duplicate_progress(self) -> None:
        self.identify("old-session", "Alpha", "identify-old")
        self.bridge.handle(QuestCompletedEvent(session_id="old-session", reliable=True, quest_id=10))
        self.bridge.forget_session("old-session")
        self.identify("new-session", "Alpha", "identify-new")
        result = self.bridge.handle(
            QuestCompletedEvent(session_id="new-session", reliable=True, quest_id=10)
        )
        self.assertTrue(result.accepted)
        self.assertFalse(result.changed)
        self.assertEqual(self.quest_progress.completed_quest_ids("character:1001"), {10})

    def test_unreliable_event_never_writes(self) -> None:
        self.identify("session-a", "Alpha")
        result = self.bridge.handle(
            QuestCompletedEvent(session_id="session-a", reliable=False, quest_id=10)
        )
        self.assertFalse(result.accepted)
        self.assertFalse(self.quest_progress.is_quest_completed("slot:1", 10))

    def test_unknown_or_incomplete_events_never_write(self) -> None:
        self.identify("session-a", "Alpha")
        unknown = self.bridge.handle(
            UnknownReliableEvent(session_id="session-a", reliable=True)
        )
        unknown_quest = self.bridge.handle(
            QuestCompletedEvent(session_id="session-a", reliable=True, quest_id=999999)
        )
        self.assertFalse(unknown.accepted)
        self.assertFalse(unknown_quest.accepted)
        self.assertEqual(self.quest_progress.completed_quest_ids("slot:1"), set())

    def test_quest_objective_event_updates_objective_without_inferring_quest_end(self) -> None:
        self.identify("session-a", "Alpha")
        result = self.bridge.handle(
            QuestObjectiveCompletedEvent(
                session_id="session-a",
                reliable=True,
                quest_id=10,
                objective_id=100,
            )
        )
        self.assertTrue(result.changed)
        self.assertTrue(self.quest_progress.is_objective_completed("character:1001", 10, 100))
        self.assertFalse(self.quest_progress.is_quest_completed("character:1001", 10))

    def test_reliable_achievement_event_uses_existing_achievement_service(self) -> None:
        self.identify("session-a", "Alpha")
        result = self.bridge.handle(
            AchievementCompletedEvent(
                session_id="session-a",
                reliable=True,
                achievement_id=500,
            )
        )
        self.assertTrue(result.changed)
        self.assertTrue(self.achievement_progress.is_achievement_completed("character:1001", 500))

    def test_quest_completion_is_visible_to_existing_guide_calculator(self) -> None:
        calculator = GuideProgressCalculator(
            self.quest_progress,
            GuideProgressService(self.guide_path),
            self.achievement_progress,
            self.catalog.by_id,
        )
        guide = Guide(
            id="network-test-guide",
            title="Network test",
            category="Test",
            sections=(
                GuideSection(
                    id="section",
                    title="Section",
                    steps=(
                        GuideStep(id="quest:10", step_type="quest", order=1, entity_id=10),
                    ),
                ),
            ),
        )
        self.assertEqual(calculator.guide_progress(guide, "slot:1").completed, 0)
        self.identify("session-a", "Alpha")
        self.bridge.handle(QuestCompletedEvent(session_id="session-a", reliable=True, quest_id=10))
        progress = calculator.guide_progress(guide, "character:1001")
        self.assertEqual((progress.completed, progress.total), (1, 1))

    def test_normalizer_rejects_unverified_unknown_and_incomplete_messages(self) -> None:
        normalizer = ProtocolEventNormalizer()
        self.assertIsNone(
            normalizer.normalize(
                DecodedClientMessage(
                    session_id="session-a",
                    event_type="quest_completed",
                    fields={"quest_id": 10},
                    verified=False,
                )
            )
        )
        self.assertIsNone(
            normalizer.normalize(
                DecodedClientMessage(
                    session_id="session-a",
                    event_type="quest_completed",
                    fields={},
                    verified=True,
                )
            )
        )
        self.assertIsNone(
            normalizer.normalize(
                DecodedClientMessage(
                    session_id="session-a",
                    event_type="not_supported",
                    fields={"quest_id": 10},
                    verified=True,
                )
            )
        )

    def test_runtime_survives_parser_failure_then_processes_next_event(self) -> None:
        source = FakeNetworkSource()
        source.fail_reads = 1
        source.events.put(
            CharacterIdentifiedEvent(
                session_id="session-a",
                reliable=True,
                character_name="Alpha",
                character_id=1001,
            )
        )
        source.events.put(
            QuestCompletedEvent(
                session_id="session-a",
                reliable=True,
                quest_id=10,
            )
        )
        runtime = NetworkEventRuntime(source, self.bridge, logger=self.logger, read_timeout=0.05)
        self.assertTrue(runtime.start())
        self.assertTrue(self.wait_until(lambda: self.quest_progress.is_quest_completed("character:1001", 10)))
        self.assertTrue(runtime.stop())

    def test_runtime_stop_is_deterministic_and_restartable(self) -> None:
        source = FakeNetworkSource()
        runtime = NetworkEventRuntime(source, self.bridge, logger=self.logger, read_timeout=0.05)
        self.assertTrue(runtime.start())
        self.assertTrue(runtime.is_running)
        self.assertTrue(runtime.stop())
        self.assertFalse(runtime.is_running)
        self.assertTrue(runtime.start())
        self.assertTrue(runtime.stop())
        self.assertFalse(runtime.is_running)

    @staticmethod
    def wait_until(predicate, timeout: float = 1.5) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return bool(predicate())


if __name__ == "__main__":
    unittest.main()
