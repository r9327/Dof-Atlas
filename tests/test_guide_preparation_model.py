from __future__ import annotations

import gc
import json
import tracemalloc
import unittest
import zlib
from pathlib import Path

from app.modules.encyclopedia.services.guide_preparation_model import (
    aggregate_remaining, card_claims, category_for,
)


class GuidePreparationModelTests(unittest.TestCase):
    def test_structured_and_textual_complement_without_mirror_double_count(self):
        card = {
            "manual_stage_id": "stage:1",
            "a_preparer": [
                {"item_id": 101, "name": "Potion de rappel", "quantity": 3,
                 "_source_field": "quest_required_items"},
            ],
            "manual_sections": {"prepare": [
                {"text": "Prépare 3 × Potion de rappel."},
                {"text": "Prépare 2 × Clef du donjon."},
            ]},
        }
        claims = card_claims(card)
        self.assertEqual(len(claims), 2)
        self.assertEqual([(c.name, c.quantity) for c in claims], [
            ("Potion de rappel", 3), ("Clef du donjon", 2),
        ])
        self.assertEqual(claims[0].item_id, 101)

    def test_soul_stones_keys_and_professions_are_exposed(self):
        card = {
            "manual_stage_id": "stage:2",
            "a_preparer": [
                {"name": "Pierre d'âme parfaite", "quantity": 4},
                {"name": "Clef du donjon Royalmouth", "quantity": 1},
            ],
            "profession_gates": [{"name": "Alchimiste niveau 50"}],
        }
        found = card_claims(card)
        self.assertEqual([row.category for row in found], [
            "Pierres d'âme", "Clefs", "Métiers",
        ])
        self.assertIsNone(found[-1].quantity)

    def test_duplicates_are_not_false_purchases(self):
        card = {
            "manual_stage_id": "stage:3",
            "a_preparer": [
                {"name": "Potion", "quantity": 2},
                {"name": "Potion", "quantity": 2},
                {"name": "Potion", "quantity": 2, "source_step_id": "different-use"},
            ],
        }
        claims = card_claims(card)
        self.assertEqual(len(claims), 2)

    def test_sum_only_explicit_consumptions_and_max_reusables(self):
        cards = [
            {"manual_stage_id": "one", "a_preparer": [
                {"item_id": 9, "name": "Potion A", "quantity": 2, "consumable": True},
                {"item_id": 11, "name": "Objet B", "quantity": 1, "reusable": True},
            ]},
            {"manual_stage_id": "two", "a_preparer": [
                {"item_id": 9, "name": "Potion A", "quantity": 3, "consumable": True},
                {"item_id": 11, "name": "Objet B", "quantity": 4, "reusable": True},
            ]},
        ]
        rows = aggregate_remaining((card, False) for card in cards)
        by_id = {need.item_id: need for need in rows}
        self.assertEqual((by_id[9].quantity, by_id[9].confidence),
                         (5, "additive_consumption"))
        self.assertEqual((by_id[11].quantity, by_id[11].confidence),
                         (4, "reusable_maximum"))
        self.assertEqual(by_id[11].claim_count, 2)
        self.assertEqual(len(by_id[11].sources), 2)

    def test_ambiguous_consumption_and_missing_quantity_are_unknown(self):
        cards = [
            {"manual_stage_id": "one", "a_preparer": [
                {"name": "Objet rare", "quantity": 2},
                {"name": "Potion inconnue"},
            ]},
            {"manual_stage_id": "two", "a_preparer": [
                {"name": "Objet rare", "quantity": 3},
            ]},
        ]
        data = {row.name: row for row in aggregate_remaining((c, False) for c in cards)}
        self.assertIsNone(data["Objet rare"].quantity)
        self.assertEqual(data["Objet rare"].confidence, "multiple_uses_ambiguous")
        self.assertIsNone(data["Potion inconnue"].quantity)
        self.assertEqual(data["Potion inconnue"].confidence, "quantity_unverified")

    def test_completed_stages_excluded_from_remaining(self):
        first = {"manual_stage_id": "one", "a_preparer": [
            {"name": "Potion", "quantity": 2, "consumable": True},
        ]}
        second = {"manual_stage_id": "two", "a_preparer": [
            {"name": "Potion", "quantity": 4, "consumable": True},
        ]}
        rows = aggregate_remaining(((first, True), (second, False)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].quantity, 4)

    def test_unverified_candidates_do_not_claim_possession(self):
        card = {"manual_stage_id": "stage:4", "source_action_candidates": [
            {"kind": "prepare_object", "object_id": 361, "label": "Cawotte"}
        ]}
        self.assertEqual(card_claims(card), ())
        self.assertEqual(aggregate_remaining(((card, False),)), ())

    def test_unknown_quantity_is_not_faked_as_one(self):
        rows = card_claims({"a_preparer": [
            {"name": "Pierre d'âme", "quantity": 0},
            {"name": "Potion", "quantity": True},
            {"name": "Clef", "quantity": "unknown"},
        ]})
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.quantity is None for row in rows))

    def test_compact_267_cards_six_characters_memory_with_five_percent_margin(self):
        """Preparation-only allocation proof; NOT the full Phase 8 app RSS gate."""
        cards = []
        for index in range(267):
            stage = {
                "id": f"route-stage-{index}",
                "resource_plan": {"resources": [
                    {"item": f"Potion témoin {index}", "quantity": 2},
                    {"resource": f"Clef témoin {index}", "quantity": 1},
                    {"name": f"Objet témoin {index}", "quantity": 3},
                ]},
            }
            cards.append({
                "manual_stage_id": stage["id"],
                "_manual_stage_payload": zlib.compress(
                    json.dumps(stage, ensure_ascii=False).encode("utf-8")
                ),
                "a_preparer": [],
            })
        gc.collect()
        # This is a local memory-budget guard for preparation allocations
        # alone, not the 95MB preload / 250MB process-tree Phase 8 metrics.
        budget_bytes = 2 * 1024 * 1024
        allowed_bytes = int(budget_bytes * 1.05)
        tracemalloc.start()
        try:
            for character_index in range(6):
                results = aggregate_remaining(
                    (card, False) for card in cards
                )
                self.assertEqual(
                    len(results), 801,
                    f"6-character scenario {character_index} lost authored items",
                )
                del results
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        print(
            f"ATLAS_PREPARATION_MEMORY cards=267 characters=6 "
            f"peak_bytes={peak} budget_bytes={budget_bytes} "
            f"allowed_bytes={allowed_bytes} margin=5pct",
            flush=True,
        )
        self.assertLessEqual(
            peak, allowed_bytes,
            "Preparation-only allocations exceeded 2 MiB + 5% margin",
        )

    def test_real_guide_ultime_canonical_267_stage_sources(self):
        """Read the canonical authored chapters, without remote catalogue/GUI."""
        from app.modules.encyclopedia.services.guide_ultime_manual_route import (
            load_manual_chapter,
        )
        from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
            GuideUltimeManualRuntimeService,
        )
        manual_dir = (Path(__file__).resolve().parents[1] /
                      "data/routes/guide_ultime_manual")
        manifest = json.loads(
            (manual_dir / "manifest_v1.json").read_text(encoding="utf-8")
        )
        chapters = manifest["canonical"]["chapters"]
        total = 0
        global_claims = []
        for meta in chapters:
            chapter = load_manual_chapter(
                manual_dir / meta["file"], _memo={}
            )
            stages = [row for row in chapter["stages"] if isinstance(row, dict)]
            self.assertEqual(len(stages), int(meta["stage_count"]), meta["id"])
            schedule = GuideUltimeManualRuntimeService._chapter_preparation_schedule(
                chapter, stages,
            )
            for index, stage in enumerate(stages):
                card = {
                    "manual_stage_id": str(stage.get("id") or f"{meta['id']}-{index}"),
                    "manual_chapter_id": meta["id"],
                    "a_preparer": [],
                    "_manual_stage_payload": zlib.compress(
                        json.dumps(stage, ensure_ascii=False).encode("utf-8")
                    ),
                }
                if schedule.get(index):
                    card["_manual_chapter_preparation_payload"] = zlib.compress(
                        json.dumps(schedule[index], ensure_ascii=False).encode("utf-8")
                    )
                keys_before = set(card)
                claims = card_claims(card)
                self.assertEqual(set(card), keys_before)
                self.assertNotIn("manual_stage_data", card)
                for claim in claims:
                    self.assertTrue(claim.identity)
                    self.assertTrue(claim.name)
                    self.assertTrue(claim.source)
                    if claim.quantity is not None:
                        self.assertGreater(claim.quantity, 0)
                if meta["id"] == "incarnam":
                    global_claims.extend(claims)
                total += 1
        self.assertEqual(total, 267)
        first_chapter = {row.name: row.quantity for row in global_claims}
        self.assertEqual(first_chapter["Blé"], 18)
        self.assertEqual(first_chapter["Goujon"], 8)
        print(
            f"ATLAS_GUIDES_CANONICAL chapters={len(chapters)} cards={total} "
            f"incarnam_claims={len(global_claims)} no_catalog_download=true",
            flush=True,
        )

    def test_real_sylvestre_quest_dependencies_not_false_inventory(self):
        root = Path(__file__).resolve().parents[1]
        guide = json.loads((
            root / "data/encyclopedia/guides/dofus_sylvestre.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(guide["id"], "dofus_sylvestre")
        route = next(
            part for part in guide["sections"]
            if part["id"] == "dofus_sylvestre_v4_route"
        )
        steps = route["steps"]
        self.assertGreaterEqual(len(steps), 200)
        source = {
            "manual_stage_id": "sylvestre:source",
            "source_action_candidates": steps,
        }
        self.assertEqual(card_claims(source), ())
        self.assertEqual(aggregate_remaining(((source, False),)), ())

    def test_real_ganymede_candidates_never_certified_as_inventory(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((
            root / "data/encyclopedia/guides/ganymede_2205_action_candidates.json"
        ).read_text(encoding="utf-8"))
        self.assertFalse(data["ready_to_replace"])
        self.assertEqual(data["certified_actions"], 0)
        self.assertGreaterEqual(len(data["steps"]), 60)
        count = 0
        for step in data["steps"]:
            candidates = step.get("actions") or []
            count += sum(x.get("kind") == "prepare_object" for x in candidates)
            card = {
                "manual_stage_id": step["stable_step_id"],
                "source_action_candidates": candidates,
            }
            self.assertEqual(card_claims(card), ())
        self.assertGreater(count, 0)

    def test_global_chapter_inventory_survives_anchor_card_completion(self):
        first = {
            "manual_stage_id": "INC-00",
            "manual_chapter_id": "incarnam",
            "a_preparer": [
                {"name": "Blé", "quantity": 18,
                 "_source_field": "chapter_preparation"},
                {"name": "Potion locale", "quantity": 2,
                 "_source_field": "a_preparer"},
            ],
        }
        last = {"manual_stage_id": "INC-08",
                "manual_chapter_id": "incarnam", "a_preparer": []}
        pending = aggregate_remaining(((first, True), (last, False)))
        self.assertEqual([(row.name, row.quantity) for row in pending],
                         [("Blé", 18)])
        self.assertEqual(aggregate_remaining(((first, True), (last, True))), ())
        self.assertEqual(
            {row.name for row in aggregate_remaining(((first, False), (last, False)))},
            {"Blé", "Potion locale"},
        )

    def test_compact_incarnam_preparation_keeps_route_unhydrated(self):
        from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
            GuideUltimeManualRuntimeService,
        )
        root = Path(__file__).resolve().parents[1]
        chapter = json.loads((
            root / "data/routes/guide_ultime_manual/incarnam_v1.json"
        ).read_text(encoding="utf-8"))
        stages = chapter["stages"]
        schedule = GuideUltimeManualRuntimeService._chapter_preparation_schedule(
            chapter, stages,
        )
        first = stages[0]
        card = {
            "manual_stage_id": first["id"],
            "a_preparer": [],
            "_manual_stage_payload": zlib.compress(json.dumps(
                first, ensure_ascii=False,
            ).encode("utf-8")),
            "_manual_chapter_preparation_payload": zlib.compress(json.dumps(
                schedule[0], ensure_ascii=False,
            ).encode("utf-8")),
        }
        before_keys = set(card)
        claims = card_claims(card)
        results = {claim.name: claim.quantity for claim in claims}
        self.assertEqual(results["Blé"], 18)
        self.assertEqual(results["Goujon"], 8)
        self.assertEqual(results["Relique d'Incarnam"], 3)
        self.assertEqual(set(card), before_keys)
        self.assertNotIn("manual_stage_data", card)
        self.assertEqual(
            {row.name: row.quantity for row in aggregate_remaining(((card, False),))},
            results,
        )

    def test_compact_payload_is_bounded_and_never_uses_action_candidates(self):
        enormous = zlib.compress(b"x" * (4 * 1024 * 1024 + 1))
        self.assertEqual(card_claims({
            "manual_stage_id": "bomb",
            "_manual_stage_payload": enormous,
        }), ())
        stage = {
            "resource_plan": {
                "items": [{"item": "Potion de foyer", "quantity": 2}],
            },
            "source_action_candidates": [
                {"name": "Suggestion Ganymède", "quantity": 999},
            ],
        }
        card = {"manual_stage_id": "stage:one", "a_preparer": [],
                "_manual_stage_payload": zlib.compress(json.dumps(stage).encode())}
        self.assertEqual(
            [(c.name, c.quantity) for c in card_claims(card)],
            [("Potion de foyer", 2)],
        )

    def test_authored_incarnam_resource_plan_reaches_cards(self):
        """Use real retained chapter data, not an invented synthetic item."""
        from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
            GuideUltimeManualRuntimeService,
        )
        root = Path(__file__).resolve().parents[1]
        chapter = json.loads((
            root / "data/routes/guide_ultime_manual/incarnam_v1.json"
        ).read_text(encoding="utf-8"))
        authored = chapter["resource_plan"]["collect_before_leaving_incarnam"]
        self.assertGreater(len(authored), 10)
        schedule = GuideUltimeManualRuntimeService._chapter_preparation_schedule(
            chapter, chapter["stages"],
        )
        self.assertIn(0, schedule)
        card = {
            "manual_stage_id": chapter["stages"][0]["id"],
            "a_preparer": schedule[0],
        }
        claims = card_claims(card)
        quantities = {claim.name: claim.quantity for claim in claims}
        self.assertEqual(quantities["Blé"], 18)
        self.assertEqual(quantities["Goujon"], 8)
        self.assertEqual(quantities["Relique d'Incarnam"], 3)
        self.assertGreaterEqual(len(quantities), len(authored))

    def test_nested_authored_resources_not_confused_with_candidate_actions(self):
        card = {"manual_stage_id": "fixture", "a_preparer": [{
            "_source_field": "resource_plan",
            "collect_before_leaving": [
                {"resource": "Ortie", "quantity": 13},
                {"item": "Fer", "quantity": 10},
            ],
            "notes": [{"policy": "Aucun achat forcé"}],
        }], "source_action_candidates": [{
            "label": "Objet Ganymède", "quantity": 999, "kind": "prepare_object",
        }]}
        claims = card_claims(card)
        self.assertEqual([(c.name, c.quantity) for c in claims],
                         [("Ortie", 13), ("Fer", 10)])
        self.assertTrue(all(c.source == "resource_plan" for c in claims))

    def test_missing_identity_never_uses_slot(self):
        rows = card_claims({"a_preparer": [
            {"name": "Potion de Rappel", "quantity": 1, "slot": 7},
        ]})
        self.assertEqual(rows[0].identity, "name:potion de rappel")
        self.assertEqual(category_for("Pierre d’âme parfaite"), "Pierres d'âme")


if __name__ == "__main__":
    unittest.main()
