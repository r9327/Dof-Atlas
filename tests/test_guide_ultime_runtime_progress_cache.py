from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_auto_validation_contract import route_progress_counts
from app.modules.encyclopedia.services.guide_ultime_manual_conditions import GuideUltimeManualConditionsMixin
from app.modules.encyclopedia.services.guide_ultime_runtime_service import GuideUltimeRuntimeService


class _RevisionProgress:
    def __init__(self) -> None:
        self._coordinator = SimpleNamespace(generation=0)
        self._seen_generation = 0
        self._disk_signature = (1, 1, 1)
        self.completed_calls = 0

    def completed_quest_ids(self, _character_key: str) -> set[int]:
        self.completed_calls += 1
        return set()


class _RevisionAchievements(_RevisionProgress):
    def state_for(self, _character_key: str):
        return SimpleNamespace(is_achievement_completed=lambda _achievement_id: False)

    def is_achievement_completed(self, _character_key: str, _achievement_id: int) -> bool:
        return False

    def alignment_order_choice(self, _character_key: str):
        return None


class _RouteProgressProbe(GuideUltimeRuntimeService):
    def __init__(self) -> None:
        self.cards = [{"index": 1}, {"index": 2}]
        self.quest_progress = _RevisionProgress()
        self.achievement_progress = _RevisionAchievements()
        self.guide_progress = _RevisionProgress()
        self.reload_calls = 0
        self.card_state_calls = 0
        self.card_state_snapshot_calls = 0

    def reload_progress(self) -> None:
        self.reload_calls += 1

    def card_state(
        self,
        _character_key: str,
        _card: dict,
        fallback_index: int = 0,
        completed_quests: set[int] | frozenset[int] | None = None,
    ):
        self.card_state_calls += 1
        if completed_quests is not None:
            self.card_state_snapshot_calls += 1
        return SimpleNamespace(complete=fallback_index == 0)


class _FirstIncompleteProbe(_RouteProgressProbe):
    def card_quest_ids(self, _card: dict) -> tuple[int, ...]:
        return ()

    def card_success_ids(self, _card: dict) -> tuple[int, ...]:
        return ()

    def class_gate_satisfied(
        self,
        _character_key: str,
        _card: dict,
        completed_quests: set[int] | frozenset[int] | None = None,
    ) -> bool:
        _ = completed_quests
        return True


class _ManualRouteProbe(GuideUltimeManualConditionsMixin, GuideUltimeRuntimeService):
    """Minimal production-MRO probe without loading any Dofus route file."""

    def __init__(self) -> None:
        self.cards = [{"index": 1}, {"index": 2}]
        self.quest_progress = _RevisionProgress()
        self.achievement_progress = _RevisionAchievements()
        self.guide_progress = _RevisionProgress()
        self.reload_calls = 0
        self.card_state_calls = 0
        self.card_state_snapshot_calls = 0

    def reload_progress(self) -> None:
        self.reload_calls += 1

    def manual_class_gate_for_card(self, _card: dict):
        return None

    def manual_order_gate_for_card(self, _card: dict):
        return None

    def card_quest_ids(self, _card: dict) -> tuple[int, ...]:
        return ()

    def card_success_ids(self, _card: dict) -> tuple[int, ...]:
        return ()

    def manual_checked(self, _character_key: str, _key: str) -> bool:
        return False

    def card_state(
        self,
        character_key: str,
        card: dict,
        fallback_index: int = 0,
        completed_quests: set[int] | frozenset[int] | None = None,
    ):
        self.card_state_calls += 1
        if completed_quests is not None:
            self.card_state_snapshot_calls += 1
        return super().card_state(
            character_key,
            card,
            fallback_index,
            completed_quests=completed_quests,
        )


class GuideUltimeRuntimeProgressCacheTests(unittest.TestCase):
    def test_route_sheet_progress_reuses_card_scan_until_progress_revision_changes(self):
        service = _RouteProgressProbe()

        self.assertEqual(service.route_sheet_progress("slot:1"), (1, 2))
        self.assertEqual(service.route_sheet_progress("slot:1"), (1, 2))

        self.assertEqual(service.reload_calls, 2)
        self.assertEqual(service.card_state_calls, 2)
        self.assertEqual(service.card_state_snapshot_calls, 2)
        self.assertEqual(service.quest_progress.completed_calls, 1)

        service.quest_progress._coordinator.generation += 1
        self.assertEqual(service.route_sheet_progress("slot:1"), (1, 2))
        self.assertEqual(service.card_state_calls, 4)
        self.assertEqual(service.card_state_snapshot_calls, 4)
        self.assertEqual(service.quest_progress.completed_calls, 2)

    def test_first_incomplete_index_reuses_scan_until_published_revision_changes(self):
        service = _FirstIncompleteProbe()

        self.assertEqual(service.first_incomplete_index("slot:1"), 1)
        self.assertEqual(service.first_incomplete_index("slot:1"), 1)
        self.assertEqual(service.reload_calls, 2)
        self.assertEqual(service.card_state_calls, 2)
        self.assertEqual(service.card_state_snapshot_calls, 2)
        self.assertEqual(service.quest_progress.completed_calls, 1)

        # Simulate another live Atlas service publishing guide progress before
        # this probe has observed it locally. The cache key must still change.
        service.guide_progress._coordinator.generation += 1
        self.assertEqual(service.first_incomplete_index("slot:1"), 1)
        self.assertEqual(service.reload_calls, 3)
        self.assertEqual(service.card_state_calls, 4)
        self.assertEqual(service.card_state_snapshot_calls, 4)
        self.assertEqual(service.quest_progress.completed_calls, 2)

    def test_route_progress_counts_reuses_dungeon_scan_until_published_revision_changes(self):
        service = _RouteProgressProbe()
        contract = {
            "cards": [
                {
                    "card_key": "manual:route:1",
                    "quests": [{"quest_id": 1}],
                    "dungeons": [{"name": "Donjon A"}],
                },
                {
                    "card_key": "manual:route:2",
                    "quests": [{"quest_id": 2}],
                    "dungeons": [{"name": "Donjon B"}],
                },
            ]
        }

        first = route_progress_counts(service, "slot:1", contract)
        second = route_progress_counts(service, "slot:1", contract)

        self.assertEqual(first, second)
        self.assertEqual(first["dungeons_completed"], 1)
        self.assertEqual(first["dungeons_total"], 2)
        self.assertEqual(service.reload_calls, 2)
        self.assertEqual(service.card_state_calls, 2)
        self.assertEqual(service.card_state_snapshot_calls, 2)
        self.assertEqual(service.quest_progress.completed_calls, 1)

        service.achievement_progress._coordinator.generation += 1
        third = route_progress_counts(service, "slot:1", contract)
        self.assertEqual(third, first)
        self.assertEqual(service.reload_calls, 3)
        self.assertEqual(service.card_state_calls, 4)
        self.assertEqual(service.card_state_snapshot_calls, 4)
        self.assertEqual(service.quest_progress.completed_calls, 2)

    def test_manual_production_mro_accepts_and_reuses_route_snapshot(self):
        service = _ManualRouteProbe()

        self.assertEqual(service.route_sheet_progress("slot:1"), (0, 2))
        self.assertEqual(service.card_state_calls, 2)
        self.assertEqual(service.card_state_snapshot_calls, 2)
        self.assertEqual(service.quest_progress.completed_calls, 1)

        first = _ManualRouteProbe()
        self.assertEqual(first.first_incomplete_index("slot:1"), 0)
        self.assertEqual(first.first_incomplete_index("slot:1"), 0)
        self.assertEqual(first.reload_calls, 2)
        self.assertEqual(first.card_state_calls, 1)
        self.assertEqual(first.card_state_snapshot_calls, 1)
        self.assertEqual(first.quest_progress.completed_calls, 1)


if __name__ == "__main__":
    unittest.main()
