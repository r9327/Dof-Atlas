from __future__ import annotations

import unittest

from tools import guide_integrity_contracts as contracts


class GuideIntegrityContractsTests(unittest.TestCase):
    def test_contract_surface_is_structured(self) -> None:
        action = contracts.normalize_action({"action_type": "talk", "actor_id": 9})
        result = contracts.validate_structured_actions([action])
        self.assertEqual(result["hard_error_count"], 0)


if __name__ == "__main__":
    unittest.main()
