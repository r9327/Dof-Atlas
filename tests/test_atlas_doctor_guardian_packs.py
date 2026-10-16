from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.guardian_packs import PACKS, guardian_plan


class DoctorGuardianPackTests(unittest.TestCase):
    def test_all_domain_packs_are_unique_and_declared(self):
        identifiers = [row["id"] for row in PACKS]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(
            set(identifiers),
            {"core", "ui", "quests_guides", "network", "persistence",
             "performance", "release", "security", "simplicity"},
        )
        self.assertTrue(all(row["concerns"] for row in PACKS))

    def test_cross_domain_plan_selects_guardians_without_duplicate_execution(self):
        plan = {
            "paths": [
                "app/modules/encyclopedia/views/quest_view.py",
                "app/modules/encyclopedia/services/quest_progress_service.py",
                "app/network/session.py",
            ],
            "scopes": ["encyclopedia_quests", "network_capture"],
            "rules": ["PERFORMANCE_GUARDRAILS.md"],
            "required_groups": ["PERSISTENCE"],
            "execution_tests": ["tests.test_quests", "tests.test_network", "tests.test_quests"],
            "validation_command": ["py", "-m", "tools.agent", "validate", "critical"],
        }
        result = guardian_plan(plan)
        selected = set(result["selected_ids"])
        self.assertTrue({"core", "ui", "quests_guides", "network", "persistence",
                         "performance", "security", "simplicity"}.issubset(selected))
        self.assertNotIn("release", selected)
        self.assertEqual(result["execution"]["test_processes"], 1)
        self.assertEqual(result["execution"]["test_modules"],
                         ["tests.test_quests", "tests.test_network"])
        self.assertTrue(result["execution"]["deduplicated"])
        self.assertFalse(result["execution"]["extra_full_run"])

    def test_release_only_plan_does_not_enable_unrelated_runtime_packs(self):
        result = guardian_plan({
            "paths": [".github/workflows/distribution.yml"],
            "scopes": ["quality_ci"], "rules": [], "required_groups": [],
            "execution_tests": [], "validation_command": [],
        })
        self.assertEqual(set(result["selected_ids"]), {"core", "release"})
        self.assertEqual(result["execution"]["test_processes"], 0)

    def test_unknown_non_python_path_still_keeps_core_guardian(self):
        result = guardian_plan({"paths": ["README.md"]})
        self.assertEqual(result["selected_ids"], ["core"])


if __name__ == "__main__":
    unittest.main()
