from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_auto_validation_contract import (
    build_card_auto_validation_contract,
)
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeIncarnamV2Tests(unittest.TestCase):
    @staticmethod
    def _stage(payload: dict, stage_id: str) -> dict:
        return next(row for row in payload.get("stages", []) or [] if row.get("id") == stage_id)

    @staticmethod
    def _service() -> GuideUltimeManualRuntimeService:
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.quest_provider = None
        service._quest_name_to_id = {}
        return service

    def test_manifest_promotes_incarnam_v2_without_changing_route_size(self) -> None:
        manifest = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = {row["id"]: row for row in manifest["canonical"]["chapters"]}
        self.assertEqual(chapters["incarnam"]["file"], "incarnam_v2.json")
        self.assertEqual(chapters["incarnam"]["stage_count"], 9)
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters.values()), 267)
        self.assertTrue(
            any(
                row.get("file") == "incarnam_v1.json" and row.get("by") == "incarnam_v2.json"
                for row in manifest.get("superseded", [])
            )
        )

    def test_v2_composes_the_same_nine_stable_stage_ids(self) -> None:
        old = load_manual_chapter(MANUAL / "incarnam_v1.json")
        new = load_manual_chapter(MANUAL / "incarnam_v2.json")
        old_ids = [str(row.get("id") or "") for row in old.get("stages", [])]
        new_ids = [str(row.get("id") or "") for row in new.get("stages", [])]
        self.assertEqual(len(new_ids), 9)
        self.assertEqual(new_ids, old_ids)

    def test_existing_inventory_targets_are_structured_at_their_gps_passages(self) -> None:
        payload = load_manual_chapter(MANUAL / "incarnam_v2.json")
        expected = {
            "INC-01": {"Lailait": 1},
            "INC-02": {
                "Blé": 18,
                "Poudre de Perlinpainpain": 4,
                "Œuf Chimérique": 2,
                "Pétale Diaphane": 2,
                "Plume Chimérique": 2,
            },
            "INC-03": {"Goujon": 8, "Peau de Gloot": 2},
            "INC-04": {
                "Laine Céleste": 2,
                "Bave de Bouftou": 4,
                "Bois de Frêne": 10,
                "Ortie": 13,
                "Cendres Éternelles": 11,
                "Feu Intérieur": 2,
                "Viande Intangible": 5,
            },
            "INC-05": {"Fer": 10, "Poudre d'Aminite": 3},
            "INC-06": {"Relique d'Incarnam": 3},
        }
        for stage_id, wanted in expected.items():
            stage = self._stage(payload, stage_id)
            actual = {
                str(row.get("name") or ""): int(row.get("quantity"))
                for row in stage.get("preparation", []) or []
                if isinstance(row, dict) and row.get("name") and row.get("quantity") is not None
            }
            for name, quantity in wanted.items():
                self.assertEqual(actual.get(name), quantity, f"{stage_id}: {name}")

    def test_kardorim_pass_is_structured_for_dungeon_and_waypoint_successes(self) -> None:
        payload = load_manual_chapter(MANUAL / "incarnam_v2.json")
        stage = self._stage(payload, "INC-07")
        self.assertEqual(stage["dungeon"]["name"], "Crypte de Kardorim")
        self.assertEqual(stage["dungeon"]["boss"], "Kardorim")
        waypoint_successes = {
            str(name)
            for waypoint in stage.get("waypoints", []) or []
            if isinstance(waypoint, dict)
            for name in waypoint.get("successes", []) or []
        }
        self.assertEqual(
            waypoint_successes,
            {
                "Kardorim — Premier",
                "Kardorim — Spécial",
                "Kardorim — Zombie",
                "Kardorim — Duo",
            },
        )

        service = self._service()
        card = service._stage_to_card(
            "incarnam",
            {"label": "Incarnam"},
            payload,
            stage,
            8,
        )
        contract = build_card_auto_validation_contract(card)
        self.assertEqual(contract["dungeons"][0]["name"], "Crypte de Kardorim")
        self.assertEqual(
            {row["name"] for row in contract["successes"]},
            waypoint_successes,
        )


if __name__ == "__main__":
    unittest.main()
