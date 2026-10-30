"""Contract: source-trusted Ganymède routes open as ordered manual steps.

No canonical quest/achievement completion is inferred from source hints.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    select_verified_replacement_path,
)


GUIDES = Path(__file__).resolve().parents[1] / "data" / "encyclopedia" / "guides"


class GanymedeCatalogActivationTests(unittest.TestCase):
    def test_twenty_source_trusted_dofus_routes_are_integrity_gated(self) -> None:
        catalogue = json.loads((GUIDES / "catalog.json").read_text(encoding="utf-8"))
        manifest = json.loads(
            (GUIDES / "replacement_drafts" / "cutovers" / "cutover_manifest.json")
            .read_text(encoding="utf-8")
        )
        declared = manifest["guides"]
        enabled = [
            row for row in catalogue["guides"]
            if row.get("ganymede_manual_ui_ready") is True
        ]
        self.assertEqual(len(enabled), 20)
        self.assertEqual({row["id"] for row in enabled}, set(declared))
        step_count = 0
        for row in enabled:
            with self.subTest(guide=row["id"]):
                self.assertEqual(row["category"], "dofus")
                path = select_verified_replacement_path(
                    GUIDES, row, allow_source_manual=True,
                )
                self.assertIsNotNone(path)
                self.assertEqual(path.parent.name, "cutovers")
                payload = json.loads(path.read_text(encoding="utf-8"))
                source = declared[row["id"]]
                self.assertEqual(payload["id"], row["id"])
                self.assertEqual(payload["source_guide_id"], source["source_guide_id"])
                self.assertEqual(payload["replacement_status"], "TRUSTED_SOURCE_STEPS")
                self.assertFalse(payload["auto_completion_allowed"])
                self.assertFalse(payload["canonical_objectives_certified"])
                steps = payload["sections"][0]["steps"]
                self.assertEqual(len(steps), source["source_step_count"])
                self.assertTrue(all(
                    item["id"] == f"ganymede_{source['source_guide_id']}_step_{i:04d}"
                    and item["manual_completion_allowed"] is True
                    and item["auto_completion_allowed"] is False
                    for i, item in enumerate(steps, 1)
                ))
                self.assertTrue(any(item.get("content") for item in steps))
                step_count += len(steps)
        self.assertEqual(step_count, 1694)

    def test_unmapped_or_disabled_sources_keep_original_atlas_guide(self) -> None:
        catalogue = json.loads((GUIDES / "catalog.json").read_text(encoding="utf-8"))
        for row in catalogue["guides"]:
            if row["id"] in {"dokille", "dofoozbz"}:
                with self.subTest(guide=row["id"]):
                    self.assertIsNone(select_verified_replacement_path(
                        GUIDES, row, allow_source_manual=True,
                    ))
                    self.assertNotIn("ganymede_manual_ui_ready", row)


if __name__ == "__main__":
    unittest.main()
