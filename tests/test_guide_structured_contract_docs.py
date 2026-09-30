from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GuideStructuredContractDocsTests(unittest.TestCase):
    def test_contract_migration_does_not_promote_regex_reviews(self) -> None:
        text = (ROOT / "tools/guide_structured_contracts.md").read_text(encoding="utf-8")
        self.assertIn("must not be promoted blindly from REVIEW to HARD", text)
        self.assertIn("GuideAction", text)


if __name__ == "__main__":
    unittest.main()
