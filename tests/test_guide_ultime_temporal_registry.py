from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_temporal_registry import load_temporal_registry

ROOT = Path(__file__).resolve().parents[1]
ROUTE_BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeTemporalRegistryTests(unittest.TestCase):
    def _write(self, root: Path, name: str, payload: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_entry_patch_deep_merges_without_losing_base_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {
                "schema_version": 1,
                "entries": [
                    {"id": "pandawushu", "type": "fixed_delay_chain", "delay_policy": {"after": "Rokwa", "hours": 24}},
                    {"id": "weekly", "type": "weekly"},
                ],
            })
            path = self._write(root, "v2.json", {
                "schema_version": 2,
                "base_file": "base.json",
                "entry_patches": {
                    "pandawushu": {
                        "delay_policy": {"separate_intro_wait": True},
                        "intro_wait_policy": {"default_kamas": 50000},
                    }
                },
            })
            resolved = load_temporal_registry(path)
            entries = {row["id"]: row for row in resolved["entries"]}
            self.assertEqual(set(entries), {"pandawushu", "weekly"})
            self.assertEqual(entries["pandawushu"]["delay_policy"]["after"], "Rokwa")
            self.assertEqual(entries["pandawushu"]["delay_policy"]["hours"], 24)
            self.assertTrue(entries["pandawushu"]["delay_policy"]["separate_intro_wait"])
            self.assertEqual(entries["pandawushu"]["intro_wait_policy"]["default_kamas"], 50000)
            self.assertEqual(resolved["_resolved_from"], ["base.json", "v2.json"])

    def test_entry_insertion_appends_new_timer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"entries": [{"id": "known", "type": "daily"}]})
            path = self._write(root, "v2.json", {
                "base_file": "base.json",
                "entry_insertions": [{"id": "frigost_vaccine_expiry", "type": "fixed_delay", "days": 7}],
            })
            resolved = load_temporal_registry(path)
            entries = {row["id"]: row for row in resolved["entries"]}
            self.assertEqual(set(entries), {"known", "frigost_vaccine_expiry"})
            self.assertEqual(entries["frigost_vaccine_expiry"]["days"], 7)
            self.assertEqual(resolved["_resolved_from"], ["base.json", "v2.json"])

    def test_duplicate_entry_insertion_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"entries": [{"id": "known", "type": "daily"}]})
            path = self._write(root, "v2.json", {"base_file": "base.json", "entry_insertions": [{"id": "known", "type": "weekly"}]})
            with self.assertRaises(ValueError):
                load_temporal_registry(path)

    def test_insertion_without_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"entries": [{"id": "known"}]})
            path = self._write(root, "v2.json", {"base_file": "base.json", "entry_insertions": [{"type": "weekly"}]})
            with self.assertRaises(ValueError):
                load_temporal_registry(path)

    def test_unknown_entry_patch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"entries": [{"id": "known"}]})
            path = self._write(root, "v2.json", {"base_file": "base.json", "entry_patches": {"typo": {"delay": 24}}})
            with self.assertRaises(KeyError):
                load_temporal_registry(path)

    def test_composition_cycle_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "a.json", {"base_file": "b.json", "entry_patches": {}})
            path = self._write(root, "b.json", {"base_file": "a.json", "entry_patches": {}})
            with self.assertRaises(ValueError):
                load_temporal_registry(path)

    def test_repository_v11_resolves_all_async_contracts(self) -> None:
        resolved = load_temporal_registry(ROUTE_BASE / "temporal_registry_v11.json")
        rows = [row for row in resolved["entries"] if isinstance(row, dict)]
        entries = {str(row["id"]): row for row in rows}
        self.assertEqual(len(rows), len(entries))

        blessure = entries["frigost_hunter_blessure_to_chasse"]
        self.assertEqual(blessure["delay_hours"], 13)
        self.assertEqual(blessure["position_policy"], "weekday_variable")
        self.assertEqual(len(blessure["weekday_start_positions"]), 7)

        chasse = entries["frigost_hunter_chasse_to_brocouille"]
        self.assertEqual(chasse["delay_hours"], 13)
        self.assertEqual(chasse["position_policy"], "weekday_variable")
        self.assertEqual(len(chasse["weekday_start_positions"]), 7)

        bonmonstres = entries["frigost_bonmonstres_attempt_window"]
        self.assertEqual(bonmonstres["attempt_window_minutes"], 5)
        self.assertEqual(bonmonstres["failure_cooldown_hours"], 1)

        self.assertEqual(entries["pandala_selenite_fight_respawn"]["approx_respawn_minutes"], 60)
        self.assertEqual(entries["pandala_yokaiku_itinerant_respawn"]["approx_respawn_minutes"], 120)
        self.assertEqual(entries["fungus_agrypnite_grilled_respawn"]["approx_respawn_minutes"], 10)
        self.assertEqual(entries["fungus_sword_fishing_spot_respawn"]["approx_respawn_minutes"], 1)

        season = entries["osavora_season_cycle"]
        self.assertEqual(season["rotation_order"], ["Naissance", "Chasse", "Repos"])
        self.assertEqual((season["change_weekday"], season["change_local_time"]), ("MO", "08:00"))
        self.assertTrue(season["hard_wait_forbidden"])

        titan = entries["osavora_gargandyas_weekend"]
        self.assertEqual((titan["open_weekday"], titan["open_local_time"]), ("FR", "19:00"))
        self.assertEqual((titan["close_weekday"], titan["close_local_time"]), ("MO", "08:00"))
        self.assertFalse(titan["capture_allowed"])
        self.assertTrue(titan["hard_wait_forbidden"])

        kral = entries["kralamoure_server_opening"]
        self.assertEqual(kral["minimum_people_to_open"], 49)
        self.assertEqual(kral["open_duration_minutes"], 40)
        self.assertTrue(kral["hard_wait_forbidden"])
        self.assertIn("étape19", kral["preferred_merge_condition"])

        lulu = entries["frigost_depot_lulu_day_window"]
        self.assertEqual((lulu["open_local_time"], lulu["close_local_time"]), ("08:00", "20:00"))
        self.assertTrue(lulu["hard_wait_forbidden"])

        slip = entries["frigost_chaud_slip_night_window"]
        self.assertEqual((slip["open_local_time"], slip["close_local_time"]), ("20:00", "08:00"))
        self.assertTrue(slip["wraps_midnight"])
        self.assertTrue(slip["hard_wait_forbidden"])

        self.assertEqual(resolved["_resolved_from"][-3:], [
            "temporal_registry_v9.json",
            "temporal_registry_v10.json",
            "temporal_registry_v11.json",
        ])


if __name__ == "__main__":
    unittest.main()
