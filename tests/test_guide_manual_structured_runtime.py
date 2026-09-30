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
