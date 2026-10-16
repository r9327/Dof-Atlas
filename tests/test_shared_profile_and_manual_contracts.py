from __future__ import annotations

import unittest

from app import storage
from app.core import profile_settings, zaap_shortcuts
from app.modules.encyclopedia.services import guide_ultime_manual_runtime_core as core
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService as ManualRuntime,
)


class SharedProfileAndManualContractsTests(unittest.TestCase):
    def test_storage_exposes_exact_core_profile_functions(self):
        for name in ("default_profiles", "profile_bool", "parse_zaap_click_position"):
            with self.subTest(name=name):
                self.assertIs(getattr(storage, name), getattr(profile_settings, name))
        defaults = storage.default_profiles()
        self.assertTrue(defaults)
        self.assertIsNot(defaults, storage.default_profiles())
        self.assertTrue(storage.profile_bool({"feature": "oui"}, "feature"))
        self.assertFalse(storage.profile_bool({"feature": "false"}, "feature"))
        self.assertEqual(
            storage.parse_zaap_click_position("20,-4"), (20, 0)
        )

    def test_one_canonical_zaap_ratio_parser_preserves_semantics(self):
        self.assertIs(profile_settings.parse_unit_ratio, zaap_shortcuts.parse_unit_ratio)
        for value, expected in (
            ("0", 0.0), (".75", 0.75), ("1", 1.0),
            ("-0.1", None), ("1.1", None), ("nan", None), ("invalid", None),
        ):
            with self.subTest(value=value):
                self.assertEqual(profile_settings.parse_unit_ratio(value), expected)

    def test_manual_runtime_inherits_neutral_overrides_without_new_copies(self):
        base = core.GuideUltimeManualRuntimeService
        for name in ("_structured_rows_from_fields", "_link_next_cards", "_stage_to_card"):
            with self.subTest(name=name):
                self.assertNotIn(name, ManualRuntime.__dict__)
                inherited = getattr(ManualRuntime, name)
                original = getattr(base, name)
                # A classmethod rebinds __self__ on subclasses even when
                # the underlying implementation is the same.
                self.assertIs(
                    getattr(inherited, "__func__", inherited),
                    getattr(original, "__func__", original),
                )
        self.assertIn("_stage_lines", ManualRuntime.__dict__)
        self.assertIn("manual_sections_for_card", ManualRuntime.__dict__)
        cards = [
            {"destination": "A", "x": 1, "y": 2, "zone": "Zone",
             "subzone": "Sub", "manual_stage_id": "stage-1"},
            {"destination": "B", "x": 3, "y": 4, "zone": "Zone",
             "subzone": "Sub", "manual_stage_id": "stage-2"},
        ]
        ManualRuntime._link_next_cards(cards)
        self.assertEqual(cards[0]["ensuite"]["manual_stage_id"], "stage-2")
        self.assertIsNone(cards[-1]["ensuite"])


if __name__ == "__main__":
    unittest.main()
