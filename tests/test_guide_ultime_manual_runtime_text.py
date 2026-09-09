from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import GuideUltimeManualRuntimeService
from app.quest_catalog import normalize_text


class _QuestProvider:
    def get_quest(self, quest_id: int):
        if quest_id == 42:
            return SimpleNamespace(id=42, name="Au détour d'un rêve perdu")
        raise KeyError(quest_id)


class GuideUltimeManualRuntimeTextTests(unittest.TestCase):
    def _service(self):
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.quest_provider = _QuestProvider()
        service._quest_name_to_id = {normalize_text("Au détour d'un rêve perdu"): 42}
        return service

    def test_take_instruction_keeps_exact_quest_name(self):
        service = self._service()
        quest_key = normalize_text("Au détour d'un rêve perdu")
        rendered = service._clean_player_instruction(
            "Prendre Au détour d'un rêve perdu auprès du PNJ.",
            [quest_key],
        )
        self.assertIn("Au détour d'un rêve perdu", rendered)
        self.assertNotIn("la quête en cours", rendered)

    def test_progress_instruction_hides_repeated_quest_name(self):
        service = self._service()
        quest_key = normalize_text("Au détour d'un rêve perdu")
        rendered = service._clean_player_instruction(
            "Avancer Au détour d'un rêve perdu avec le PNJ.",
            [quest_key],
        )
        self.assertNotIn("Au détour d'un rêve perdu", rendered)
        self.assertIn("Parler avec", rendered)

    def test_turn_in_instruction_hides_repeated_quest_name(self):
        service = self._service()
        quest_key = normalize_text("Au détour d'un rêve perdu")
        rendered = service._clean_player_instruction(
            "Terminer Au détour d'un rêve perdu auprès du PNJ.",
            [quest_key],
        )
        self.assertNotIn("Au détour d'un rêve perdu", rendered)
        self.assertIn("la quête en cours", rendered)
        self.assertIn("PNJ", rendered)


if __name__ == "__main__":
    unittest.main()
