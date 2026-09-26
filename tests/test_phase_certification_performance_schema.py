from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "phase-certification.yml"


class PhaseCertificationPerformanceSchemaTests(unittest.TestCase):
    def test_certification_consumes_canonical_encyclopedia_benchmark_schema(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Measure canonical Encyclopedia user paths", source)
        self.assertIn("payload.get(\"schema_version\") != 4", source)
        self.assertIn("github.event_name == 'workflow_dispatch'", source)
        for metric in (
            "quests_open_ms",
            "quests_open_max_ui_block_ms",
            "achievements_open_ms",
            "achievements_open_max_ui_block_ms",
            "guide_open_ms",
            "guide_open_max_ui_block_ms",
            "first_achievement_detail_max_ui_block_ms",
            "first_guide_detail_max_ui_block_ms",
            "rss_after_all_views_mb",
            "idle_cpu_percent_one_core",
        ):
            with self.subTest(metric=metric):
                self.assertIn(f'\"{metric}\"', source)

        for obsolete in (
            "quests_index_open_ms",
            "achievements_index_open_ms",
            "guide_index_open_ms",
            "rss_after_first_views_mb",
            "Phase 7B timing performance",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, source)


if __name__ == "__main__":
    unittest.main()
