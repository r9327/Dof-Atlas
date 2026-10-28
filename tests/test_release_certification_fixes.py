"""Regression: Guide Succès service identity and the explicit RAM margin."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from tools.atlas_doctor_lib.doctor_ui_qt import guide_runtime_identity


class ReleaseCertificationFixTests(unittest.TestCase):
    def test_guide_succes_runtime_without_guide_id_is_identified_by_service(self):
        service = object.__new__(GuideUltimeManualRuntimeService)
        self.assertFalse(hasattr(service, "guide_id"))
        self.assertEqual(guide_runtime_identity(service), "guide_complet")

    def test_sylvestre_id_comes_from_its_real_service(self):
        service = SimpleNamespace(guide_id="dofus_sylvestre")
        self.assertEqual(guide_runtime_identity(service), "dofus_sylvestre")
        self.assertIsNone(guide_runtime_identity(SimpleNamespace()))

    def test_ram_peak_and_preload_tolerance_preserve_budget_targets(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / ".github/workflows/phase8-memory-benchmark.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("peak_target_mb = 220.0", source)
        self.assertIn("peak_hard_limit_mb = hard_limit(peak_target_mb)", source)
        self.assertIn('if classify(peak_tree, peak_target_mb) == "FAIL":', source)
        self.assertIn("preload_target_mb = 95.0", source)
        self.assertIn("preload_limit_mb = hard_limit(preload_target_mb)", source)
        self.assertIn('if preload_status == "FAIL":', source)
        self.assertIn("retained_budgets_mb = {", source)
        self.assertIn('"guide_retained_tree_delta_mb": 20.0', source)
        self.assertIn("state = classify(measured, budget, allow_negative=True)", source)


if __name__ == "__main__":
    unittest.main()
