from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase7DCumulativeCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = (ROOT / "PHASE_CERTIFICATION.md").read_text(encoding="utf-8")

    def test_post_7e_cumulative_replay_is_required_before_phase8(self) -> None:
        for token in (
            "Verrou cumulatif Phase 7D après Phase 7E",
            "Phase 1 → 7E",
            "Avant tout démarrage de la Phase 8",
            "SHA exact de `main`",
            "`tools.atlas_integrity full`",
            "Phase Certification / Full Validation = PASS",
            "`FAIL`, `NOT RUN` ou `BLOCKED`",
            "100 % terminées",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.contract)


if __name__ == "__main__":
    unittest.main()
