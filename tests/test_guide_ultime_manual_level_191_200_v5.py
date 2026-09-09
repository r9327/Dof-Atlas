from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualLevel191200V5Tests(unittest.TestCase):
    def test_every_level200_macro_has_safe_pause(self) -> None:
        resolved = load_manual_chapter(BASE / "level_191_200_v5.json")
        self.assertEqual(resolved["stage_count"], 33)
        missing = []
        for stage in resolved["stages"]:
            has_checkpoint = isinstance(stage.get("pause_checkpoint"), dict)
            has_pause = isinstance(stage.get("pause"), list) and bool(stage.get("pause"))
            if not (has_checkpoint or has_pause):
                missing.append(str(stage.get("id") or ""))
        self.assertEqual(missing, [])

    def test_v5_keeps_same_causal_stage_count_as_v4(self) -> None:
        v4 = load_manual_chapter(BASE / "level_191_200_v4.json")
        v5 = load_manual_chapter(BASE / "level_191_200_v5.json")
        self.assertEqual([x["id"] for x in v4["stages"]], [x["id"] for x in v5["stages"]])


if __name__ == "__main__":
    unittest.main()
