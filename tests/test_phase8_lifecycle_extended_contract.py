"""Pure regression checks for opt-in multi-cycle memory evidence (stdlib only)."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "tools" / "benchmark_phase8_memory.py"


def _drift_function():
    tree = ast.parse(BENCHMARK.read_text(encoding="utf-8"))
    method = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_home_rss_drift"
    )
    code = compile(
        ast.Module(body=[method], type_ignores=[]),
        filename=str(BENCHMARK),
        mode="exec",
    )
    namespace: dict[str, Any] = {"Any": Any}
    exec(code, namespace)
    return namespace["_home_rss_drift"]


class ExtendedNavigationEvidenceTests(unittest.TestCase):
    def test_positive_negative_and_missing_rss_are_not_falsified(self):
        drift = _drift_function()
        self.assertEqual(drift([
            {"tree_rss_mb": 105.1}, {"tree_rss_mb": 104.7},
            {"tree_rss_mb": 106.3}
        ]), 1.2)
        self.assertEqual(drift([
            {"tree_rss_mb": 105.1}, {"tree_rss_mb": 103.1}
        ]), -2.0)
        self.assertIsNone(drift([{"tree_rss_mb": 100.0}]))
        self.assertIsNone(drift([
            {"tree_rss_mb": None}, {"tree_rss_mb": 100.0}
        ]))

    def test_extended_windows_job_requires_manual_dispatch(self):
        workflow = (ROOT / ".github/workflows/phase8-memory-benchmark.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('lifecycle_cycles:', workflow)
        self.assertIn('default: "2"', workflow)
        self.assertIn('if ("${{ github.event_name }}" -eq "workflow_dispatch"', workflow)
        self.assertIn('--include-heavy-views', workflow)
        self.assertIn('python -X faulthandler tools/benchmark_phase8_memory.py', workflow)
        self.assertIn('peak_tree > 220.0', workflow)

    def test_longer_cycles_are_optional_without_changing_legacy_gates(self):
        source = BENCHMARK.read_text(encoding="utf-8")
        for evidence in (
            "def measure(*, navigation_cycles: int = 2, include_heavy_views: bool = False)",
            "for cycle in range(1, 3)",
            "for cycle in range(3, navigation_cycles + 1)",
            '"navigation_cycles": navigation_cycles',
            '"round_trip_home_drift_mb"',
            "if include_heavy_views:",
            '("craft", "Craft")',
            '("equipment", "Equipement")',
            'parser.add_argument("--include-heavy-views"',
        ):
            self.assertIn(evidence, source)
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
