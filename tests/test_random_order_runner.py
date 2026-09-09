from __future__ import annotations

import unittest

from tools.random_order_tests import flatten, reproducible_suite


class AlphaTests(unittest.TestCase):
    def test_a(self) -> None:
        pass

    def test_b(self) -> None:
        pass


class BetaTests(unittest.TestCase):
    def test_c(self) -> None:
        pass

    def test_d(self) -> None:
        pass


class RandomOrderRunnerTests(unittest.TestCase):
    def _ids(self, seed: int) -> list[str]:
        source = unittest.TestLoader().loadTestsFromTestCase(AlphaTests)
        source.addTests(unittest.TestLoader().loadTestsFromTestCase(BetaTests))
        return [test.id() for test in flatten(reproducible_suite(flatten(source), seed))]

    def test_same_seed_reproduces_exact_order(self) -> None:
        self.assertEqual(self._ids(9327), self._ids(9327))

    def test_runner_keeps_every_test_exactly_once(self) -> None:
        self.assertEqual(len(self._ids(9327)), 4)
        self.assertEqual(len(set(self._ids(9327))), 4)


if __name__ == "__main__":
    unittest.main()
