from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase8StartStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = (ROOT / "PHASE_CERTIFICATION.md").read_text(encoding="utf-8")

    def test_phase8_baseline_and_first_existing_chantier_are_recorded(self) -> None:
        for token in (
            "Phase 8 — état initial",
            "`STARTED`",
            "`8f6357ce0e731d98ad700138d795533ae21ea4fa`",
            "Atlas Integrity FULL : `PASS`",
            "1 906 tests",
            "Doctor HARD : `REVIEW`",
            "Graphify 0.9.72 : `PASS`",
            "DA-LOG-015",
            "initialisation du logging par effet de bord",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.contract)


if __name__ == "__main__":
    unittest.main()
