from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.json_store import read_json_resilient
from app.modules.encyclopedia.views.related_preload_state import RelatedPreloadGate, RelatedPreloadState


class FaultInjectionContractsTests(unittest.TestCase):
    def test_missing_json_returns_isolated_empty_state_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            default = {"completed": []}
            result = read_json_resilient(path, default)
            result["completed"].append(1)
            self.assertEqual(default, {"completed": []})
            self.assertFalse(path.exists())

    def test_unavailable_provider_reaches_explicit_terminal_failure(self) -> None:
        gate = RelatedPreloadGate()
        self.assertTrue(gate.begin())
        gate.mark_failed()
        self.assertEqual(gate.state, RelatedPreloadState.FAILED)
        self.assertFalse(gate.begin())
        self.assertEqual(gate.attempts, 1)


if __name__ == "__main__":
    unittest.main()
