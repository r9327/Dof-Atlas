"""Regression: upgraded Atlas CI workflows use the reviewed setup-python v7.1.0 SHA."""
from pathlib import Path
import unittest

WORKFLOWS = (
    "ai-context-ci.yml",
    "app-ci.yml",
    "atlas-doctor-complete-benchmark.yml",
    "atlas-exhaustive-benchmark.yml",
    "atlas-public-release-smoke.yml",
    "atlas-short-full-app.yml",
    "atlas-windows-distribution.yml",
    "ci-bounded-autofix.yml",
    "delivery-guard.yml",
    "doctor-certification.yml",
    "doctor-runtime-perf.yml",
    "doctor-ui.yml",
    "documentalist_cross_repo_e2e.yml",
    "encyclopedia-provider-import.yml",
    "feature_scoped_proof.yml",
    "graphify-map.yml",
    "graphify-targeted-ci.yml",
    "guides-focused-proof.yml",
    "holding_atlas_updater_e2e.yml",
    "json-focused-data-contract.yml",
    "phase-certification.yml",
    "phase8-memory-benchmark.yml",
    "phase8-preload-benchmark.yml",
    "pr303-commit-patch-audit.yml",
    "pr303-repair-static-audit.yml",
    "scoped-pr-ci.yml",
)
ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PIN = "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0"


class SetupPythonActionPinTests(unittest.TestCase):
    def test_exact_pins_in_upgraded_workflows(self):
        for name in WORKFLOWS:
            with self.subTest(workflow=name):
                content = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn(PIN, content)
                self.assertNotIn("actions/setup-python@v5", content)
                self.assertNotIn("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", content)


if __name__ == "__main__":
    unittest.main()
