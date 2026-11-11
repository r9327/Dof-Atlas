from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_progress_service import (
    GuideProgressService,
)
from app.modules.encyclopedia.services.guide_imported_manual_runtime_service import (
    ImportedSourceManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_shared_route_contract import (
    project_authorized_guide,
)


def _source_route(guide_id: str = "fictional-route") -> dict:
    return project_authorized_guide({
        "guide_id": guide_id,
        "title": f"Fictitious {guide_id}",
        "steps": [
            {
                "source_step_id": "first",
                "title": "Talk to fictional NPC",
                "quest_ids": [123],
                "actions": [
                    {"action_id": "talk", "kind": "talk",
                     "text": "Parler au PNJ fictif", "npc": "PNJ fictif"},
                ],
            },
            {
                "source_step_id": "second",
                "title": "Travel",
                "coordinates": [5, -2],
                "actions": [
                    {"action_id": "travel", "kind": "travel",
                     "text": "Aller en [5,-2]", "coordinates": [5, -2]},
                ],
            },
        ],
    })


class ImportedSourceRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.progress_path = Path(self.temp.name) / "guide_progress.json"
        self.guide_progress = GuideProgressService(self.progress_path)
        self.others = SimpleNamespace(reload=lambda: None)

    def _runtime(self, route: dict) -> ImportedSourceManualRuntimeService:
        service = ImportedSourceManualRuntimeService(
            self.others, self.others, self.guide_progress, route=route,
        )
        # Fixture-only explicit authorizer. Production injection requires an
        # independent certified-route witness before the same guard is set.
        service.set_authorization_guard(
            lambda guide_id, projected: projected["id"] == guide_id,
        )
        return service

    def test_selected_source_never_loads_the_generated_v5_or_optimized_route(self):
        route = _source_route()
        service = self._runtime(route)
        self.assertTrue(service.available)
        self.assertEqual(service.guide_id, "source_guide:fictional-route")
        self.assertEqual(service.progress_id, service.guide_id)
        self.assertEqual(service.guide_title, "Fictitious fictional-route")
        self.assertEqual(len(service.cards), 2)
        self.assertEqual(service.page_key(service.cards[0], 0),
                         "source:fictional-route:first")
        self.assertEqual(service.page_key(service.cards[1], 1),
                         "source:fictional-route:second")
        self.assertEqual(service.route_sheet_progress("character:1"), (0, 2))
        self.assertEqual(service.first_incomplete_index("character:1"), 0)
        self.assertFalse(self.progress_path.exists())
        with self.assertRaisesRegex(RuntimeError, "explicit injection"):
            service.load()

    def test_stable_source_progress_is_atomic_and_isolated_by_guide_and_character(self):
        left = self._runtime(_source_route("fictional-left"))
        right = self._runtime(_source_route("fictional-right"))
        self.assertNotEqual(left.progress_id, right.progress_id)
        self.assertNotEqual(left.page_key(left.cards[0]), right.page_key(right.cards[0]))
        left.set_page_checked("character:1", left.cards[0], 0, True)
        self.assertTrue(left.page_checked("character:1", left.cards[0], 0))
        self.assertFalse(left.page_checked("character:2", left.cards[0], 0))
        self.assertFalse(right.page_checked("character:1", right.cards[0], 0))
        self.assertEqual(left.route_sheet_progress("character:1"), (1, 2))
        self.assertEqual(left.first_incomplete_index("character:1"), 1)
        self.assertEqual(right.route_sheet_progress("character:1"), (0, 2))
        self.assertFalse(self.guide_progress.manual_steps(
            "character:1", "guide_ultime_v5"
        ))
        self.assertFalse(self.guide_progress.manual_steps(
            "character:1", "catalog_manual:dofus_sylvestre"
        ))
        left.set_page_checked("character:1", left.cards[0], 0, False)
        self.assertEqual(left.route_sheet_progress("character:1"), (0, 2))

    def test_missing_revoked_or_failing_authorization_never_writes_progress(self):
        service = ImportedSourceManualRuntimeService(
            self.others, self.others, self.guide_progress,
            route=_source_route(),
        )
        card = service.cards[0]
        self.assertFalse(service.can_write_progress())
        service.set_page_checked("character:1", card, 0, True)
        self.assertFalse(self.progress_path.exists())
        allow = {"ok": True}
        service.set_authorization_guard(
            lambda _route, _document: allow["ok"],
        )
        self.assertTrue(service.can_write_progress())
        service.set_page_checked("character:1", card, 0, True)
        self.assertTrue(service.page_checked("character:1", card))
        allow["ok"] = False
        service.set_page_checked("character:1", card, 0, False)
        self.assertTrue(service.page_checked("character:1", card))
        service.set_authorization_guard(
            lambda _route, _document: (_ for _ in ()).throw(RuntimeError("revoked")),
        )
        self.assertFalse(service.can_write_progress())
        service.set_page_checked("character:2", card, 0, True)
        self.assertFalse(service.page_checked("character:2", card))

    def test_prerequisite_without_guide_policy_blocks_validation_not_display(self):
        route = _source_route()
        route["steps"][0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"},
        ]
        pending = self._runtime(route)
        first = pending.cards[0]
        self.assertTrue(pending.available)
        self.assertEqual(len(pending.manual_sections_for_card("character:1", first)["now"]), 1)
        self.assertTrue(pending.manual_order_choice_blocking("character:1", first))
        pending.set_page_checked("character:1", first, 0, True)
        self.assertFalse(self.progress_path.exists())
        self.assertIn("prérequis", pending.manual_validation_block_reason())
        self.assertFalse(pending.manual_order_choice_blocking(
            "character:1", pending.cards[1],
        ))

    def test_qualified_per_guide_policy_is_per_character_and_fails_closed(self):
        route = _source_route()
        route["steps"][0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"},
        ]
        authorized = ImportedSourceManualRuntimeService(
            self.others, self.others, self.guide_progress,
            route=route,
            gate_evaluator=lambda key, _card: key == "character:1",
        )
        authorized.set_authorization_guard(lambda _id, _route: True)
        first = authorized.cards[0]
        self.assertFalse(authorized.manual_order_choice_blocking("character:1", first))
        self.assertTrue(authorized.manual_order_choice_blocking("character:2", first))
        authorized.set_page_checked("character:2", first, 0, True)
        self.assertFalse(self.progress_path.exists())
        authorized.set_page_checked("character:1", first, 0, True)
        self.assertTrue(authorized.page_checked("character:1", first))
        self.assertFalse(authorized.page_checked("character:2", first))
        denied = ImportedSourceManualRuntimeService(
            self.others, self.others, self.guide_progress,
            route=route,
            gate_evaluator=lambda *_: (_ for _ in ()).throw(ValueError("unavailable")),
        )
        denied.set_authorization_guard(lambda *_: True)
        self.assertTrue(denied.manual_order_choice_blocking("character:2", denied.cards[0]))

    def test_direct_progress_write_cannot_skip_hard_prerequisites(self):
        route = _source_route()
        route["steps"][0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"},
        ]
        service = self._runtime(route)
        key = service.cards[0]["manual_stage_id"]
        # Shared UI can write by key, not only through set_page_checked().
        service.set_manual_checked("character:1", key, True)
        self.assertFalse(service.manual_checked("character:1", key))
        self.assertFalse(self.progress_path.exists())
        # Removing a precondition on an external copy never changes authority.
        forged = copy.deepcopy(service.cards[0])
        forged["hard_runtime_gates"] = []
        service.set_page_checked("character:1", forged, 0, True)
        self.assertFalse(self.progress_path.exists())

    def test_only_literal_true_from_authorizer_and_gate_can_write(self):
        route = _source_route()
        route["steps"][0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"},
        ]
        service = ImportedSourceManualRuntimeService(
            self.others, self.others, self.guide_progress, route=route,
            gate_evaluator=lambda *_: "yes",
        )
        service.set_authorization_guard(lambda *_: 1)
        key = service.cards[0]["manual_stage_id"]
        self.assertFalse(service.can_write_progress())
        service.set_manual_checked("character:1", key, True)
        self.assertFalse(self.progress_path.exists())
        service.set_authorization_guard(lambda *_: True)
        self.assertTrue(service.can_write_progress())
        self.assertTrue(service.manual_order_choice_blocking(
            "character:1", service.cards[0],
        ))
        service.set_manual_checked("character:1", key, True)
        self.assertFalse(self.progress_path.exists())
        service._gate_evaluator = lambda *_: True
        service.set_manual_checked("character:1", key, True)
        self.assertTrue(service.manual_checked("character:1", key))

    def test_foreign_copied_card_cannot_inject_sections_or_evaluator_payload(self):
        route = _source_route()
        route["steps"][0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"},
        ]
        evaluated = []

        def evaluate(character_key, card):
            evaluated.append((character_key, card["manual_sections"]["now"][0]["text"]))
            return card["manual_sections"]["now"][0]["text"] == "Parler au PNJ fictif"

        service = ImportedSourceManualRuntimeService(
            self.others, self.others, self.guide_progress, route=route,
            gate_evaluator=evaluate,
        )
        service.set_authorization_guard(lambda *_: True)
        copied = copy.deepcopy(service.cards[0])
        copied["manual_sections"]["now"][0]["text"] = "FAUX OBJECTIF"
        copied["hard_runtime_gates"] = []
        self.assertEqual(
            service.manual_sections_for_card("character:1", copied),
            service.cards[0]["manual_sections"],
        )
        self.assertEqual(
            service.manual_lines_for_card("character:1", copied),
            service.cards[0]["manual_sections"]["now"],
        )
        self.assertFalse(service.manual_order_choice_blocking("character:1", copied))
        service.set_page_checked("character:1", copied, 0, True)
        self.assertTrue(service.page_checked("character:1", service.cards[0]))
        self.assertEqual(evaluated, [
            ("character:1", "Parler au PNJ fictif"),
            ("character:1", "Parler au PNJ fictif"),
        ])

    def test_shared_reader_getters_never_leak_mutable_canonical_source(self):
        service = self._runtime(_source_route())
        card = service.cards[0]
        original_text = card["manual_sections"]["now"][0]["text"]

        sections = service.manual_sections_for_card("character:1", card)
        lines = service.manual_lines_for_card("character:1", card)
        self.assertIsNot(sections, card["manual_sections"])
        self.assertIsNot(lines[0], card["manual_sections"]["now"][0])
        sections["now"][0]["text"] = "UI overwritten action"
        sections["now"].append({"kind": "action", "text": "UI injected action"})
        lines[0]["text"] = "UI overwritten line"

        self.assertEqual(card["manual_sections"]["now"][0]["text"], original_text)
        self.assertEqual(len(card["manual_sections"]["now"]), 1)
        self.assertEqual(
            service.manual_sections_for_card("character:1", card)["now"][0]["text"],
            original_text,
        )
        self.assertEqual(
            service.manual_lines_for_card("character:1", card)[0]["text"],
            original_text,
        )
        self.assertFalse(self.progress_path.exists())

    def test_buggy_runtime_evaluator_cannot_clear_future_source_gates(self):
        route = _source_route()
        route["steps"][0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"},
        ]
        evaluated = []

        def corrupting_evaluator(character_key, supplied_card):
            evaluated.append(character_key)
            supplied_card["hard_runtime_gates"].clear()
            supplied_card["manual_sections"]["now"][0]["text"] = "TAMPERED"
            return False

        service = ImportedSourceManualRuntimeService(
            self.others, self.others, self.guide_progress,
            route=route, gate_evaluator=corrupting_evaluator,
        )
        service.set_authorization_guard(lambda *_: True)
        key = service.page_key(service.cards[0])
        for _ in range(2):
            service.set_manual_checked("character:1", key, True)
            self.assertFalse(service.manual_checked("character:1", key))
        self.assertEqual(evaluated, ["character:1", "character:1"])
        self.assertEqual(
            service.cards[0]["hard_runtime_gates"],
            [{"kind": "alignment", "expected": "Bonta"}],
        )
        self.assertEqual(
            service.cards[0]["manual_sections"]["now"][0]["text"],
            "Parler au PNJ fictif",
        )
        self.assertFalse(self.progress_path.exists())

    def test_single_gate_evaluation_per_page_write_and_fail_closed(self):
        route = _source_route()
        route["steps"][0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"},
        ]
        calls = []
        service = ImportedSourceManualRuntimeService(
            self.others, self.others, self.guide_progress, route=route,
            gate_evaluator=lambda key, card: (calls.append((key, card)), False)[1],
        )
        service.set_authorization_guard(lambda *_: True)
        service.set_page_checked("character:1", service.cards[0], 0, True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], service.cards[0])
        self.assertIsNot(calls[0][1], service.cards[0])
        self.assertFalse(self.progress_path.exists())
        with self.assertRaisesRegex(ValueError, "Unknown source step"):
            service.manual_order_choice_blocking(
                "character:1", {"manual_stage_id": "source:foreign:first"},
            )

    def test_source_quest_name_never_auto_completes_uncertified_action(self):
        route = _source_route()
        service = self._runtime(route)
        card = service.cards[0]
        self.assertEqual(card["manual_quest_ids"], [123])
        self.assertFalse(service.card_auto_complete("character:1", card))
        self.assertEqual(service.card_automatic_values("character:1", card), ())
        self.assertFalse(service.page_checked("character:1", card))
        self.assertEqual(service.progress("character:1").full_success_total, 0)
        self.assertFalse(self.progress_path.exists())

    def test_source_cards_are_detached_and_allow_no_cross_route_progress_key(self):
        source = _source_route()
        service = self._runtime(source)
        source["steps"][0]["manual_title"] = "OUTSIDE MUTATION"
        source["steps"][0]["manual_sections"]["now"][0]["text"] = "FAKE"
        self.assertNotIn("OUTSIDE", service.cards[0]["manual_title"])
        self.assertNotEqual(
            service.cards[0]["manual_sections"]["now"][0]["text"], "FAKE",
        )
        with self.assertRaisesRegex(ValueError, "Unknown source step"):
            service.page_key({"manual_stage_id": "source:fictional-right:first"})
        self.assertFalse(self.progress_path.exists())

    def test_manual_source_progress_keys_cannot_target_another_route(self):
        service = self._runtime(_source_route())
        invalid_keys = (
            "source:another-route:first",
            "source:fictional-route:unknown",
            "__ui:preparation_ready:source_guide:another-route:item",
            "__ui:preparation_ready:source_guide:fictional-route:",
            "__ui:unrecognized",
            None,
        )
        for key in invalid_keys:
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "Unknown or foreign"):
                    service.set_manual_checked("character:1", key, True)
        self.assertFalse(self.progress_path.exists())
        # Keep the two existing shared-header and preparation UI controls.
        lock_key = "__ui:shared_route_locked__"
        ready_key = f"__ui:preparation_ready:{service.guide_id}:fictional-item"
        service.set_manual_checked("character:1", lock_key, True)
        service.set_manual_checked("character:1", ready_key, True)
        self.assertTrue(service.manual_checked("character:1", lock_key))
        self.assertTrue(service.manual_checked("character:1", ready_key))
        self.assertEqual(
            self.guide_progress.manual_steps("character:1", service.progress_id),
            {lock_key, ready_key},
        )
        self.assertFalse(self.guide_progress.manual_steps(
            "character:1", "guide_ultime_v5"
        ))

    def test_forged_copy_cannot_bypass_guide_specific_runtime_gates(self):
        route = _source_route()
        route["steps"][0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"},
        ]
        service = self._runtime(route)
        forged = copy.deepcopy(service.cards[0])
        forged["hard_runtime_gates"] = []
        # The stable key is still valid, but a copied card is not the
        # authority for its prerequisites.
        self.assertEqual(service.page_key(forged), service.page_key(service.cards[0]))
        service.set_page_checked("character:1", forged, 0, True)
        self.assertFalse(self.progress_path.exists())
        self.assertFalse(service.page_checked("character:1", service.cards[0]))

    def test_reordering_or_inserting_steps_preserves_stable_progress(self):
        old = _source_route()
        service = self._runtime(old)
        service.set_page_checked("character:1", service.cards[1], 1, True)
        original_key = service.page_key(service.cards[1])
        changed = copy.deepcopy(old)
        new_card = copy.deepcopy(changed["steps"][0])
        new_card["source_step_id"] = "inserted"
        new_card["manual_stage_id"] = "source:fictional-route:inserted"
        changed["steps"].insert(0, new_card)
        for index, card in enumerate(changed["steps"], 1):
            card["index"] = index
        rebuilt = self._runtime(changed)
        self.assertEqual(rebuilt.page_key(rebuilt.cards[2]), original_key)
        self.assertEqual(rebuilt.route_sheet_progress("character:1"), (1, 3))
        self.assertEqual(rebuilt.first_incomplete_index("character:1"), 0)
        self.assertFalse(rebuilt.page_checked("character:2", rebuilt.cards[2], 2))

    def test_direct_injection_rejects_unsafe_projected_ids_and_boolean_indexes(self):
        baseline = _source_route()
        bad_guides = (
            "..", "with spaces", "slash/path", ".",
            "control\n", "x" * 121, "colon:id",
        )
        for bad in bad_guides:
            with self.subTest(guide=bad):
                route = copy.deepcopy(baseline)
                route["id"] = "source_guide:" + bad
                with self.assertRaises(ValueError):
                    self._runtime(route)
                self.assertFalse(self.progress_path.exists())
        for bad in ("..", "space in step", "escape/step", "weird:step", "x" * 121):
            with self.subTest(step=bad):
                route = copy.deepcopy(baseline)
                route["steps"][0]["source_step_id"] = bad
                route["steps"][0]["manual_stage_id"] = f"source:fictional-route:{bad}"
                with self.assertRaises(ValueError):
                    self._runtime(route)
                self.assertFalse(self.progress_path.exists())
        route = copy.deepcopy(baseline)
        route["steps"][0]["index"] = True
        with self.assertRaisesRegex(ValueError, "ordering"):
            self._runtime(route)

    def test_rejects_mismatched_duplicate_or_unprojected_cards_before_navigation(self):
        baseline = _source_route()
        mutations = (
            lambda x: x.update({"id": "guide_complet"}),
            lambda x: x.update({"source_compliance": "CERTIFIED"}),
            lambda x: x["steps"][0].update({"manual_stage_id": "source:other:first"}),
            lambda x: x["steps"][0].update({"manual_source": False}),
            lambda x: x["steps"][0].update({"manual_sections": None}),
            lambda x: x["steps"][0].update({"index": 777}),
            lambda x: x["steps"].append(copy.deepcopy(x["steps"][0])),
        )
        for change in mutations:
            with self.subTest(change=change):
                route = copy.deepcopy(baseline)
                change(route)
                with self.assertRaises(ValueError):
                    self._runtime(route)
                self.assertFalse(self.progress_path.exists())


if __name__ == "__main__":
    unittest.main()
