from __future__ import annotations

import unittest
from pathlib import Path

from tools import validate_guide_ultime_manual_transversals as canonical

ROOT = Path(__file__).resolve().parents[1]


class GuideTransversalCanonicalTests(unittest.TestCase):
    def test_versioned_wrapper_is_retired(self) -> None:
        self.assertFalse((ROOT / "tools/validate_guide_ultime_manual_transversals_v16.py").exists())

    def test_current_chapter_contract_is_owned_by_canonical_module(self) -> None:
        chapters = {chapter_id: filename for chapter_id, filename, _ in canonical._impl.EXPECTED_CHAPTERS}
        self.assertEqual(chapters["level_191_200"], "level_191_200_v22.json")
        self.assertEqual(chapters["level_200_plus"], "level_200_plus_v11.json")


if __name__ == "__main__":
    unittest.main()
