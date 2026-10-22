"""Validate comparability and fail-closed behavior of Windows RAM probes."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "tools" / "compare_phase8_lifecycle.py"
_spec = importlib.util.spec_from_file_location("atlas_lifecycle_compare", _MODULE)
module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(module)


class LifecycleComparisonTests(unittest.TestCase):
    def make_probe(self, root, name, *, sha="a" * 40, cycles=5, platform="win32"):
        domains = ("quests", "achievements", "guide", "craft", "equipment")
        result = {
            "schema_version": 1,
            "environment": {"platform": platform, "python": "3.13.0",
                            "qt_qpa_platform": "offscreen"},
            "metrics": {"git_head": sha, "navigation_cycles": cycles,
                        "include_heavy_views": True,
                        "round_trip_home": {
                            name: [{"tree_rss_mb": 125 + i * 2,
                                    "process_rss_mb": 96 + i} for i in range(cycles)]
                            for name in domains}},
        }
        path = root / name
        path.write_text(json.dumps(result), encoding="utf-8")
        return path

    def test_realistic_valid_measurements_never_claim_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = self.make_probe(root, "before.json")
            after = self.make_probe(root, "after.json", sha="b" * 40)
            measured = module.compare(before, after)
            self.assertEqual(measured["status"], "MEASUREMENT_ONLY_NOT_CERTIFIED")
            self.assertEqual(len(measured["domains"]), 5)
            self.assertEqual(measured["domains"]["guide"]["tree_rss_mb"]["before_drift_mb"], 8.0)

    def test_rejects_linux_and_different_cycle_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = self.make_probe(root, "before.json")
            linux = self.make_probe(root, "linux.json", platform="linux")
            with self.assertRaisesRegex(ValueError, "Native Windows"):
                module.compare(before, linux)
            other = self.make_probe(root, "other.json", cycles=6)
            with self.assertRaisesRegex(ValueError, "Incompatible navigation"):
                module.compare(before, other)

    def test_rejects_missing_or_forged_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = self.make_probe(root, "before.json")
            after = self.make_probe(root, "after.json")
            data = json.loads(after.read_text())
            data["metrics"]["round_trip_home"]["equipment"].pop()
            after.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete cycle"):
                module.compare(before, after)
            data["metrics"]["round_trip_home"]["equipment"].append(
                {"tree_rss_mb": 130, "process_rss_mb": True})
            after.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "numeric RSS"):
                module.compare(before, after)

    def test_requires_verified_sha_and_same_python_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = self.make_probe(root, "before.json")
            after = self.make_probe(root, "after.json")
            data = json.loads(after.read_text())
            data["environment"]["python"] = "3.12"
            after.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Incompatible environment"):
                module.compare(before, after)
            data["environment"]["python"] = "3.13.0"
            data["metrics"]["git_head"] = "unverified"
            after.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "40-character"):
                module.compare(before, after)


if __name__ == "__main__":
    unittest.main()
