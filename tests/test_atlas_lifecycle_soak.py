from __future__ import annotations

import unittest

from tools.atlas_lifecycle_soak import execute


class _PassingProbe(unittest.TestCase):
    def test_passes(self) -> None:
        self.assertTrue(True)


class AtlasLifecycleSoakTests(unittest.TestCase):
    @staticmethod
    def _factory(case: type[unittest.TestCase]):
        return lambda: unittest.TestLoader().loadTestsFromTestCase(case)

    def test_repeats_the_same_inventory_in_one_process(self) -> None:
        report = execute(
            ["probe"], cycles=3, suite_factory=self._factory(_PassingProbe)
        )
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["cycles_completed"], 3)
        self.assertEqual(report["counts"]["tests_per_cycle"], 1)
        self.assertEqual(report["counts"]["total_tests"], 3)

    def test_failure_stops_the_long_lived_run(self) -> None:
        class FailingProbe(unittest.TestCase):
            def runTest(self) -> None:
                self.fail("probe")

        report = execute(
            ["probe"], cycles=3, suite_factory=self._factory(FailingProbe)
        )
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["cycles_completed"], 1)
        self.assertEqual(report["counts"]["failures"], 1)

    def test_rejects_a_single_cycle(self) -> None:
        with self.assertRaises(ValueError):
            execute(
                ["probe"], cycles=1, suite_factory=self._factory(_PassingProbe)
            )


if __name__ == "__main__":
    unittest.main()
