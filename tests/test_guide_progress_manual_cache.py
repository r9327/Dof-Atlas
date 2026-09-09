from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService


class GuideProgressManualCacheTests(unittest.TestCase):
    def test_repeated_membership_reuses_one_manual_step_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide_progress.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "characters": {
                            "slot:1": {
                                "manual_steps": {
                                    "guide_ultime_v5": ["page:a", "page:b"]
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            service = GuideProgressService(path)
            original = service._read_manual_steps_map

            with patch.object(service, "_read_manual_steps_map", wraps=original) as mapping:
                self.assertTrue(
                    service.is_manual_step_completed(
                        "slot:1", "guide_ultime_v5", "page:a"
                    )
                )
                self.assertTrue(
                    service.is_manual_step_completed(
                        "slot:1", "guide_ultime_v5", "page:b"
                    )
                )
                self.assertFalse(
                    service.is_manual_step_completed(
                        "slot:1", "guide_ultime_v5", "page:c"
                    )
                )

            self.assertEqual(mapping.call_count, 1)

    def test_mutation_invalidates_snapshot_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide_progress.json"
            service = GuideProgressService(path)

            self.assertFalse(
                service.is_manual_step_completed(
                    "character:1", "guide_ultime_v5", "page:a"
                )
            )
            service.set_manual_step_completed(
                "character:1", "guide_ultime_v5", "page:a", True
            )
            self.assertTrue(
                service.is_manual_step_completed(
                    "character:1", "guide_ultime_v5", "page:a"
                )
            )

    def test_peer_service_generation_invalidates_cached_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide_progress.json"
            first = GuideProgressService(path)
            second = GuideProgressService(path)

            self.assertFalse(
                second.is_manual_step_completed(
                    "character:1", "guide_ultime_v5", "page:a"
                )
            )
            first.set_manual_step_completed(
                "character:1", "guide_ultime_v5", "page:a", True
            )
            self.assertTrue(
                second.is_manual_step_completed(
                    "character:1", "guide_ultime_v5", "page:a"
                )
            )


if __name__ == "__main__":
    unittest.main()
