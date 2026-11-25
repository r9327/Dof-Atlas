from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from app.quest_catalog import normalize_text
from tools.guide_integrity_structured import validate_runtime_lines


class GuideManualStructuredRuntimeTests(unittest.TestCase):
    @staticmethod
    def _service() -> GuideUltimeManualRuntimeService:
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.quest_provider = None
        service._quest_name_to_id = {
            normalize_text("Quête A"): 101,
            normalize_text("Quête B"): 202,
        }
        return service

    def test_guide_launch_actions_never_promote_objective_or_conflicting_start(self):
        from types import SimpleNamespace
        from app.quest_catalog import QuestRecord, QuestStep, QuestObjective
        from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import GuideCatalogManualRuntimeService
        from app.modules.encyclopedia.services.guide_ultime_route_adapter import GuideUltimeRouteAdapter
        from app.modules.encyclopedia.services.guide_quest_view_model import quest_start_info

        quest = QuestRecord(101, "Quête A", "Test", 1, 1, "", steps=[
            QuestStep(id=1, name="Objectif", description="", objectives=[
                QuestObjective(id=1, text="Aller au lieu", type_id=0, map_label="[5,6]"),
            ]),
        ])
        service = object.__new__(GuideCatalogManualRuntimeService)
        step = SimpleNamespace(id="q101")
        info = quest_start_info(quest, include_map_images=False)
        self.assertEqual(info.position, "[5,6]")
        self.assertEqual(info.declared_launch_position, "")
        cards = service._quest_segments(step, quest, finalize=False)
        self.assertEqual(cards[0]["position"], "")
        self.assertIn("Position de lancement à confirmer", cards[0]["sections"]["now"][0]["text"])
        self.assertTrue(any(row.get("position") == "[5,6]" for card in cards
                            for row in card["sections"]["now"]))
        adapter = object.__new__(GuideUltimeRouteAdapter)
        adapter.catalog = SimpleNamespace(by_id={101: quest})
        adapter.raw_quests = {101: {"startPosition": [{"mapId": 10}]}}
        adapter.raw_maps = {10: {"posX": 1, "posY": 2}}
        quest.source_info = {"native_start": {"map_id": 10, "position": "[1,2]"},
                             "source_meta": {"startCoords": "[3,4]"}}
        self.assertEqual(service._quest_segments(step, quest, finalize=False)[0]["position"], "")
        self.assertIsNone(adapter._start_location(101).x)
        quest.source_info["source_meta"]["startCoords"] = "[1,2]"
        self.assertEqual(service._quest_segments(step, quest, finalize=False)[0]["position"], "[1,2]")
        self.assertEqual((adapter._start_location(101).x, adapter._start_location(101).y), (1, 2))

    def test_first_incomplete_uses_one_rule_for_generated_and_manual_routes(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from app.modules.encyclopedia.services.guide_ultime_runtime_service import GuideUltimeRuntimeService

        self.assertIs(GuideUltimeManualRuntimeService.first_incomplete_index,
                      GuideUltimeRuntimeService.first_incomplete_index)
        for runtime in (GuideUltimeRuntimeService, GuideUltimeManualRuntimeService):
            with self.subTest(runtime=runtime.__name__):
                service = object.__new__(runtime)
                service.cards = [{"quest_ids": [101]}, {}, {}]
                service.reload_progress = Mock()
                service.quest_progress = SimpleNamespace(completed_quest_ids=lambda key: {101})
                service._route_cache_key = lambda key: (key, 0)
                service.card_state = Mock(side_effect=lambda key, card, index, **kw:
                                          SimpleNamespace(complete=index != 0))
                # Historical quest completion must not bypass the actual
                # automatic conditions and class/order gates of the sheet.
                self.assertEqual(service.first_incomplete_index("a"), 0)
                self.assertEqual(service.card_state.call_count, 1)
                self.assertEqual(service.route_sheet_progress("a"), (2, 3))
                self.assertEqual(service.card_state.call_count, 4)
                self.assertEqual(service.first_incomplete_index("a"), 0)
                self.assertEqual(service.card_state.call_count, 4)

    def test_route_completion_cache_reuses_eight_characters_and_current_revision(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        service = self._service()
        service.cards = [{}, {}, {}]
        service.reload_progress = Mock()
        service.quest_progress = SimpleNamespace(completed_quest_ids=lambda key: set())
        revision = [0]
        service._route_cache_key = lambda key: (key, id(service.cards), len(service.cards), revision[0])
        service.card_state = Mock(side_effect=lambda key, card, index, **kw:
                                  SimpleNamespace(complete=index != int(key) % 3))
        keys = tuple(str(i) for i in range(8))
        for key in keys:
            self.assertEqual(service.route_sheet_progress(key), (2, 3))
        self.assertEqual(service.card_state.call_count, 24)
        for key in reversed(keys):
            self.assertEqual(service.first_incomplete_index(key), int(key) % 3)
            self.assertEqual(service.route_sheet_progress(key), (2, 3))
        self.assertEqual(service.card_state.call_count, 24)
        self.assertEqual(len(service._route_completion_cache), 8)
        service.route_sheet_progress("8")
        self.assertEqual(len(service._route_completion_cache), 8)
        revision[0] += 1
        service.route_sheet_progress("1")
        self.assertEqual(service.card_state.call_count, 30)
        self.assertEqual(len(service._route_completion_cache), 1)

    def test_route_completion_scan_is_not_cached_if_revision_changes_mid_scan(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        service = self._service()
        service.cards = [{}]
        service.reload_progress = Mock()
        service.quest_progress = SimpleNamespace(completed_quest_ids=lambda key: set())
        revision = [0]
        service._route_cache_key = lambda key: (key, id(service.cards), len(service.cards), revision[0])
        def changing_state(*args, **kwargs):
            revision[0] += 1
            return SimpleNamespace(complete=False)
        service.card_state = Mock(side_effect=changing_state)
        self.assertEqual(service.route_completion_flags("1"), b"\x00")
        self.assertFalse(getattr(service, "_route_completion_cache", {}))
        self.assertEqual(service.route_completion_flags("1"), b"\x00")
        self.assertEqual(service.card_state.call_count, 2)

    def test_manual_runtime_integer_adapter_keeps_existing_conversion(self) -> None:
        for source, expected in (("12", 12), (True, 1), (-8, -8), (None, None), ("bad", None)):
            with self.subTest(source=source):
                self.assertEqual(GuideUltimeManualRuntimeService._as_int(source), expected)

    def test_waypoints_emit_only_canonical_travel_semantics(self) -> None:
        service = self._service()
        stage = {
            "waypoints": [
                {
                    "x": 5,
                    "y": -3,
                    "label": "Zaap test",
                    "quests": ["Quête A"],
                    "actions": ["Parler au PNJ puis acheter un objet."],
                },
                {
                    "x": "6",
                    "y": "-2",
                    "quests": ["Quête B", "Quête B"],
                    "actions": ["Combattre le monstre."],
                },
            ]
        }

        lines = service._stage_structured_runtime_lines(stage)

        self.assertEqual(len(lines), 2)
        first = lines[0]
        self.assertEqual(first["kind"], "semantic")
        self.assertEqual(first["position"], "[5,-3] — Zaap test")
        action = first["guide_actions"][0]
        self.assertEqual(action["action_type"], "travel")
        self.assertEqual(action["quest_ids"], [101])
        self.assertEqual(action["position"], "[5,-3] — Zaap test")
        self.assertEqual(action["metadata"], {"source": "manual_waypoint"})
        self.assertFalse(action["purchase_alternative"])
        self.assertFalse(action["requires_preparation"])
        for forbidden in ("actor_id", "item_id", "monster_id", "map_id"):
            self.assertNotIn(forbidden, action)

        second = lines[1]["guide_actions"][0]
        self.assertEqual(second["quest_ids"], [202])
        self.assertEqual(second["position"], "[6,-2]")

        report = validate_runtime_lines(lines)
        self.assertEqual(report["structured_line_count"], 2)
        self.assertEqual(report["action_count"], 2)
        self.assertEqual(report["hard_error_count"], 0)

    def test_invalid_waypoints_are_ignored_and_identical_actions_are_deduplicated(self) -> None:
        service = self._service()
        stage = {
            "quests": ["Quête B"],
            "waypoints": [
                {"x": 1, "y": 2, "quests": ["Quête A"]},
                {"x": 1, "y": 2, "quests": ["Quête A"]},
                {"x": None, "y": 2, "quests": ["Quête A"]},
                {"x": "not-an-int", "y": 2, "quests": ["Quête A"]},
                {"x": 7, "y": 8, "quests": ["conditional:classe"]},
            ],
        }

        lines = service._stage_structured_runtime_lines(stage)

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["guide_actions"][0]["quest_ids"], [101])
        # A waypoint never inherits stage-wide quest ids: only explicit waypoint
        # associations are safe to promote to structured runtime semantics.
        self.assertEqual(lines[1]["guide_actions"][0]["quest_ids"], [])

    def test_stage_card_keeps_visible_lines_and_adds_parallel_structured_payload(self) -> None:
        service = self._service()
        stage = {
            "id": "stage-test",
            "title": "Étape test",
            "waypoints": [
                {
                    "x": 5,
                    "y": -3,
                    "label": "Zaap test",
                    "quests": ["Quête A"],
                    "actions": ["Parler au PNJ."],
                }
            ],
        }

        card = service._stage_to_card(
            "chapter-test",
            {"label": "Chapitre test"},
            {},
            stage,
            1,
        )

        self.assertEqual(
            card["manual_lines"],
            [
                {
                    "kind": "action",
                    "position": "[5,-3] — Zaap test",
                    "text": "Parler au PNJ.",
                }
            ],
        )
        self.assertEqual(
            card["structured_runtime_lines"],
            service._stage_structured_runtime_lines(stage),
        )
        self.assertEqual(card["manual_stage_id"], "stage-test")


if __name__ == "__main__":
    unittest.main()
