from __future__ import annotations

import unittest
from pathlib import Path

from tools.atlas_mutation import execute


ROOT = Path(__file__).resolve().parents[1]


class TargetedMutationTests(unittest.TestCase):
    def test_every_registered_critical_mutant_is_killed(self) -> None:
        report = execute(ROOT)
        self.assertEqual(report["counts"]["generated"], 5)
        self.assertEqual(report["counts"]["killed"], 5)
        self.assertEqual(report["counts"]["survived"], 0)
        self.assertEqual(report["counts"]["error"], 0)
        self.assertEqual(report["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
