"""Contract: source-trusted Ganymède routes open as ordered manual steps.

No canonical quest/achievement completion is inferred from source hints.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    select_verified_replacement_path, certified_payload_sha256,
    reconstruct_trusted_manual_route,
    active_manual_catalog_sources, manual_source_completed_count,
)


GUIDES = Path(__file__).resolve().parents[1] / "data" / "encyclopedia" / "guides"


class GanymedeCatalogActivationTests(unittest.TestCase):
    def test_home_counts_only_the_twenty_actually_selected_source_routes(self) -> None:
        manifest = json.loads((
            GUIDES / "replacement_drafts" / "cutovers" / "cutover_manifest.json"
        ).read_text(encoding="utf-8"))["guides"]
        trusted = GUIDES / "replacement_drafts" / "cutovers"
        guides = [
            SimpleNamespace(id=guide_id, category="dofus", raw={})
            for guide_id in manifest
        ]
        provider = SimpleNamespace(
            guides_dir=GUIDES,
            _detail_entries={
                guide_id: (trusted / f"{guide_id}.json", index, {})
                for index, guide_id in enumerate(manifest)
            },
        )
        counts = active_manual_catalog_sources(provider, guides)
        self.assertEqual(set(counts), set(manifest))
        self.assertEqual(sum(total for _source, total in counts.values()), 1694)
        self.assertEqual(counts["dofus_cawotte"], (2205, 64))
        # An integrity fallback can still have an old quest guide in the
        # catalogue, but must never acquire a fake Ganymède progress counter.
        provider._detail_entries["dofus_cawotte"] = (
            GUIDES / "dofus_cawotte.json", 0, {},
        )
        self.assertNotIn(
            "dofus_cawotte", active_manual_catalog_sources(provider, guides),
        )

    def test_home_progress_counts_exact_step_keys_not_quests_or_foreign_route(self) -> None:
        checked = {
            "ganymede_2205_step_0001", "ganymede_2205_step_0002",
            "ganymede_2205_step_0999", "ganymede_9999_step_0003",
            "quest:123",
        }
        progress = SimpleNamespace(manual_steps=lambda key, guide: checked)
        self.assertEqual(
            manual_source_completed_count(
                progress, "character:123", "dofus_cawotte", 2205, 64,
            ), 2,
        )
        self.assertEqual(
            manual_source_completed_count(
                progress, "slot:1", "dofus_cawotte", 2205, 64,
            ), 0,
        )

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

    def test_compacted_memory_provider_keeps_exact_source_steps_on_open(self) -> None:
        """Route reconstructed from typed Guide models must preserve full SHA."""
        path = GUIDES / "replacement_drafts" / "cutovers" / "dofus_cawotte.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        section = payload["sections"][0]
        guide = SimpleNamespace(
            raw={key: value for key, value in payload.items()
                 if key not in {"sections", "parts"}},
            sections=(SimpleNamespace(
                raw={key: value for key, value in section.items() if key != "steps"},
                steps=tuple(SimpleNamespace(raw=dict(step)) for step in section["steps"]),
            ),),
        )
        rebuilt = reconstruct_trusted_manual_route(guide)
        self.assertEqual(certified_payload_sha256(rebuilt),
                         certified_payload_sha256(payload))
        self.assertEqual(
            rebuilt["sections"][0]["steps"][3]["id"], "ganymede_2205_step_0004"
        )
        guide.sections[0].steps[0].raw["source_step_number"] = 99
        with self.assertRaisesRegex(ValueError, "source route lost"):
            reconstruct_trusted_manual_route(guide)

    def test_every_activated_route_survives_compact_provider_roundtrip(self) -> None:
        """No route loses actions, sections or SHA through the memory-bound model."""
        catalogue = json.loads((GUIDES / "catalog.json").read_text(encoding="utf-8"))
        activated = [
            row for row in catalogue["guides"]
            if row.get("ganymede_manual_ui_ready") is True
        ]
        self.assertEqual(len(activated), 20)
        for row in activated:
            with self.subTest(guide=row["id"]):
                payload = json.loads((
                    GUIDES / "replacement_drafts" / "cutovers"
                    / f"{row['id']}.json"
                ).read_text(encoding="utf-8"))
                sections = tuple(
                    SimpleNamespace(
                        raw={key: val for key, val in section.items()
                             if key != "steps"},
                        steps=tuple(
                            SimpleNamespace(raw=dict(step))
                            for step in section["steps"]
                        ),
                    )
                    for section in payload["sections"]
                )
                guide = SimpleNamespace(
                    raw={key: val for key, val in payload.items()
                         if key not in {"sections", "parts"}},
                    sections=sections,
                )
                rebuilt = reconstruct_trusted_manual_route(guide)
                self.assertEqual(
                    certified_payload_sha256(rebuilt),
                    certified_payload_sha256(payload),
                )
                self.assertEqual(
                    len(rebuilt["sections"][0]["steps"]),
                    payload["expected_source_step_count"],
                )

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
