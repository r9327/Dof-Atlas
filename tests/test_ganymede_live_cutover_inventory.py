"""Validate actual Git-tracked Ganymede cutover routes, not synthetic fixtures.

This verifies on-disk payload integrity, not Qt manual-step UI readiness or
safety of migrating existing user progress.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    select_verified_replacement_path,
)

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "data/encyclopedia/guides"


class RealGanymedeCutoverInventoryTests(unittest.TestCase):
    def test_all_real_cutovers_match_signed_payloads_when_manual_ui_explicit(self):
        manifest_file = GUIDES / "replacement_drafts/cutovers/cutover_manifest.json"
        catalog_file = GUIDES / "catalog.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        declarations = manifest["guides"]
        self.assertEqual(len(declarations), 20)
        rows = {row["id"]: row for row in catalog["guides"]}
        actual_ready = 0
        for guide_id, declaration in sorted(declarations.items()):
            with self.subTest(guide_id=guide_id):
                self.assertTrue(declaration["enabled"])
                self.assertEqual(declaration["status"], "TRUSTED_SOURCE_STEPS")
                row = rows[guide_id]
                self.assertEqual(row["category"], "dofus")
                # The files really exist, and hash/step-count/source contracts
                # must all pass, without enabling unfinished UI contracts.
                expected = GUIDES / "replacement_drafts/cutovers" / (guide_id + ".json")
                self.assertEqual(select_verified_replacement_path(
                    GUIDES, row, allow_source_manual=True), expected)
                catalog_ready = row.get("ganymede_manual_ui_ready") is True
                actual_ready += catalog_ready
                selected = select_verified_replacement_path(
                    GUIDES, row, allow_source_manual=catalog_ready)
                self.assertEqual(selected, expected if catalog_ready else None)
        # Count is an observable readiness metric, NOT a certification or
        # a hard-coded assertion that UI must remain disabled.
        print(f"real Ganymede source routes: {len(declarations)}; "
              f"catalog manual UI opt-ins: {actual_ready}")


if __name__ == "__main__":
    unittest.main()
