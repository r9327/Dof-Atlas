from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_ultime_runtime_service import (
    GuideUltimeRuntimeService,
)


class _ChecklistKeyService(GuideUltimeRuntimeService):
    def __init__(self) -> None:
        pass


class GuideManualCombatChecklistTests(unittest.TestCase):
    def test_monster_target_keeps_quantity_in_player_instruction(self) -> None:
        self.assertEqual(
            GuideUltimeManualRuntimeService._structured_target_instruction(
                {"name": "Piou Rouge", "quantity": 4},
                "monstre",
            ),
            "Tue 4 × Piou Rouge.",
        )

    def test_combat_checklist_identity_changes_when_required_quantity_changes(self) -> None:
        service = _ChecklistKeyService()
        card = {
            "manual_source": True,
            "manual_chapter_id": "astrub",
            "manual_stage_id": "combat-test",
        }
        four = {"kind": "action", "position": "", "text": "Tue 4 × Piou Rouge."}
        five = {"kind": "action", "position": "", "text": "Tue 5 × Piou Rouge."}

        four_key = service.checklist_key(card, "boss", four)
        five_key = service.checklist_key(card, "boss", five)

        self.assertNotEqual(four_key, five_key)
        self.assertIn("manual:astrub:combat-test", four_key)
        self.assertIn(":boss:", four_key)


if __name__ == "__main__":
    unittest.main()
