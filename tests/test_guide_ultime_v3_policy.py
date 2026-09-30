from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
ROUTE_DIR = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeCanonicalPolicyTests(unittest.TestCase):
    def test_astrub_acquisition_is_integrated_at_the_natural_tavern_passage(self) -> None:
        chapter = load_manual_chapter(ROUTE_DIR / "astrub_v5.json")
        ast01 = next(row for row in chapter["stages"] if row.get("id") == "AST-01")
        tavern = next(
            row
            for row in ast01.get("route", [])
            if row.get("pos") == "[6,-18]" and "Lailait" in str(row.get("do") or "")
        )
        action = str(tavern.get("do") or "")

        self.assertIn("Mutualiser la taverne", action)
        self.assertIn("acheter le Lailait", action)
        self.assertIn("garder une Bière d'Astrub", action)
        self.assertNotIn("HDV", action)

        ast02 = next(row for row in chapter["stages"] if row.get("id") == "AST-02")
        gralahad = next(
            row
            for row in ast02.get("route", [])
            if row.get("pos") == "[6,-18]" and "Gralahad" in str(row.get("do") or "")
        )
        self.assertIn("Bière qui roule n'amasse pas mousse", str(gralahad.get("do") or ""))

    def test_fight_club_success_contract_requires_one_canonical_quest_completion(self) -> None:
        payload = json.loads((ROUTE_DIR / "success_contracts_v2.json").read_text(encoding="utf-8"))
        contract = next(
            row
            for row in payload.get("contracts", [])
            if row.get("success") == "Chahuteur clandestin"
        )

        self.assertEqual(contract.get("mode"), "all")
        self.assertEqual(contract.get("required_quests"), ["Fight club"])
        self.assertNotIn("counter", contract)
        self.assertNotIn("repeat_count", contract)


if __name__ == "__main__":
    unittest.main()
