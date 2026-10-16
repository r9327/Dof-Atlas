from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = MANUAL / "manifest_v1.json"
GUARDRAILS = ROOT / "DEVELOPMENT_GUARDRAILS.md"


class GuideUltimeManualSourceContractTests(unittest.TestCase):
    def test_manual_manifest_is_the_declared_source_of_truth(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        guardrails = GUARDRAILS.read_text(encoding="utf-8")

        self.assertIn("data/routes/guide_ultime_manual/manifest_v1.json", guardrails)
        self.assertEqual(payload.get("guide_id"), "guide_ultime_manual")
        self.assertIsInstance(payload.get("canonical"), dict)

    def test_manifest_keeps_current_canonical_route(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        canonical = payload.get("canonical") if isinstance(payload.get("canonical"), dict) else {}
        chapter_rows = canonical.get("chapters") if isinstance(canonical.get("chapters"), list) else []
        chapters = {
            str(row.get("id") or ""): row
            for row in chapter_rows
            if isinstance(row, dict)
        }

        self.assertEqual(chapters["level_120_150"].get("file"), "level_120_150_v21.json")
        self.assertEqual(chapters["level_191_200"].get("file"), "level_191_200_v22.json")
        self.assertEqual(chapters["level_200_plus"].get("file"), "level_200_plus_v11.json")
        self.assertEqual(sum(int(row.get("stage_count") or 0) for row in chapters.values()), 267)


if __name__ == "__main__":
    unittest.main()
