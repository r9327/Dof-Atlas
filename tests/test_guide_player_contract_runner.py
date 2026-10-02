from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GuidePlayerContractRunnerTests(unittest.TestCase):
    def test_canonical_guide_runner_emits_phase7e_player_contract_artifact(self) -> None:
        source = (ROOT / "tools" / "run_guide_ultime_ci.ps1").read_text(encoding="utf-8")
        self.assertIn(
            'Invoke-PythonCheck "10c_player_contract_7e" @("-m", "tools.guide_player_contract", "--strict-hard", "--output", ".\\artifacts\\ci_guide_ultime_logs\\player_contract_7e.json")',
            source,
        )


if __name__ == "__main__":
    unittest.main()
