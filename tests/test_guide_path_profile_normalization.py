"""Focused text-only regression for conservative Guide path names."""
from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_path_profiles import _loose_name


class GuidePathNameNormalizationTests(unittest.TestCase):
    def test_loose_names_keep_source_compatibility_and_ligatures(self) -> None:
        for raw, expected in (
            ("  CŒUR d’Éliotrope  ", "coeur d eliotrope"),
            ("Épée — fée", "epee fee"),
            ("Œuf & cœur", "oeuf coeur"),
            ("Cité d'Astrub", "cite d astrub"),
            (None, ""),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(_loose_name(raw), expected)


if __name__ == "__main__":
    unittest.main()
