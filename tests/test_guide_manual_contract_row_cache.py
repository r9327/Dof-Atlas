from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard


class _Service:
    def __init__(self, contract):
        self.auto_validation_contract = contract
        self.card_key_calls = 0

    def card_key(self, card, fallback_index):
        self.card_key_calls += 1
        return str(card.get("key") or f"index:{fallback_index}")


class GuideManualContractRowCacheTests(unittest.TestCase):
    def test_contract_rows_are_indexed_once_and_reused(self) -> None:
        row_a = {"card_key": "a", "quests": [1]}
        row_b = {"card_key": "b", "quests": [2]}
        service = _Service({"cards": [row_a, row_b]})
        widget = SimpleNamespace(service=service, card={"key": "b"}, index=1)

        self.assertIs(GuideUltimeManualCard._contract_row(widget), row_b)
        first_cache = service._manual_contract_row_index_cache
        self.assertIs(GuideUltimeManualCard._contract_row(widget), row_b)
        self.assertIs(service._manual_contract_row_index_cache, first_cache)

    def test_replacing_contract_rebuilds_index(self) -> None:
        first = {"card_key": "a", "quests": [1]}
        service = _Service({"cards": [first]})
        widget = SimpleNamespace(service=service, card={"key": "a"}, index=0)
        self.assertIs(GuideUltimeManualCard._contract_row(widget), first)

        replacement = {"card_key": "a", "quests": [99]}
        service.auto_validation_contract = {"cards": [replacement]}
        self.assertIs(GuideUltimeManualCard._contract_row(widget), replacement)


if __name__ == "__main__":
    unittest.main()
