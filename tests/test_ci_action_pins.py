"""Regression for pinned checkout v7 in the three legacy CI workflows."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PIN = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
EXPECTED = {
    ".github/workflows/documentalist_cross_repo_e2e.yml": 3,
    ".github/workflows/feature_scoped_proof.yml": 1,
    ".github/workflows/holding_atlas_updater_e2e.yml": 2,
}


class CheckoutActionPinTests(unittest.TestCase):
    def test_checkout_v7_pins_on_legacy_workflows(self):
        for path, count in EXPECTED.items():
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertEqual(text.count("uses: " + PIN), count)
                self.assertNotIn("actions/checkout@v4", text)


if __name__ == "__main__":
    unittest.main()
