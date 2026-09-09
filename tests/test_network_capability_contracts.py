from __future__ import annotations

import unittest

from app.network.contracts import (
    full_calibration_capabilities_ready,
    missing_full_calibration_capabilities,
    missing_runtime_capabilities,
    runtime_capabilities_ready,
)


class NetworkCapabilityContractTests(unittest.TestCase):
    def test_catch_up_only_never_counts_as_live_quest_completion(self) -> None:
        journal_only = {
            "character_identified",
            "quest_journal_snapshot",
            "quest_completion",
        }
        self.assertFalse(runtime_capabilities_ready(journal_only))
        self.assertEqual(
            missing_runtime_capabilities(journal_only),
            ("quest_completion",),
        )

    def test_legacy_snapshot_never_satisfies_current_catch_up_contract(self) -> None:
        legacy_snapshot = {
            "character_identified",
            "quest_completed",
            "quest_completion",
            "finished_quests_snapshot",
        }
        self.assertTrue(runtime_capabilities_ready(legacy_snapshot))
        self.assertFalse(full_calibration_capabilities_ready(legacy_snapshot))
        self.assertEqual(
            missing_full_calibration_capabilities(legacy_snapshot),
            ("quest_journal_snapshot",),
        )

    def test_live_only_mapping_is_runtime_ready_but_not_full_calibration_ready(self) -> None:
        live_only = {"character_identified", "quest_completed", "quest_completion"}
        self.assertTrue(runtime_capabilities_ready(live_only))
        self.assertFalse(full_calibration_capabilities_ready(live_only))
        self.assertEqual(
            missing_full_calibration_capabilities(live_only),
            ("quest_journal_snapshot",),
        )

    def test_full_mapping_requires_live_and_reviewed_journal_capabilities(self) -> None:
        full = {
            "character_identified",
            "quest_completed",
            "quest_completion",
            "quest_journal_snapshot",
        }
        self.assertTrue(runtime_capabilities_ready(full))
        self.assertTrue(full_calibration_capabilities_ready(full))
        self.assertEqual(missing_full_calibration_capabilities(full), ())


if __name__ == "__main__":
    unittest.main()
