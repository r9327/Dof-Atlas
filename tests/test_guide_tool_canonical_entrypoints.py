from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_ultime_route_adapter import GuideUltimeRouteAdapter
from tools import guide_forensic, guide_gps


class GuideToolCanonicalEntrypointTests(unittest.TestCase):
    def test_gps_entrypoint_uses_player_safe_adapter(self) -> None:
        original = guide_gps._builder.AdventureRouteAdapter
        try:
            guide_gps._builder.AdventureRouteAdapter = object
            with self.assertRaises(SystemExit):
                # Stop before artifact work while proving adapter wiring happens.
                original_main = guide_gps._builder.main
                guide_gps._builder.main = lambda: (_ for _ in ()).throw(SystemExit(0))
                try:
                    guide_gps.main()
                finally:
                    guide_gps._builder.main = original_main
            self.assertIs(guide_gps._builder.AdventureRouteAdapter, GuideUltimeRouteAdapter)
        finally:
            guide_gps._builder.AdventureRouteAdapter = original

    def test_forensic_entrypoint_uses_player_safe_adapter(self) -> None:
        original = guide_forensic.base.AdventureRouteAdapter
        try:
            guide_forensic.base.AdventureRouteAdapter = object
            guide_forensic.GuideForensicAudit({}, {})
            self.assertIs(guide_forensic.base.AdventureRouteAdapter, GuideUltimeRouteAdapter)
        finally:
            guide_forensic.base.AdventureRouteAdapter = original

    def test_forensic_keeps_correct_order_rank_contract(self) -> None:
        route = {
            "conditional_branches": {
                "class_card": {"options": []},
                "order_cards": [
                    {
                        "rank": slot,
                        "alignment_level": level,
                        "options": [
                            {"order": order, "quest_id": slot * 100 + index}
                            for index, order in enumerate(("Cœur Vaillant", "Œil Attentif", "Esprit Salvateur"), 1)
                        ],
                    }
                    for slot, level in enumerate((20, 40, 60, 80, 100), 1)
                ],
            },
            "route": [],
        }
        audit = guide_forensic.GuideForensicAudit(route, {})
        audit.route_qids = set()
        audit._check_branch_contract()
        self.assertEqual(audit.hard, [])


if __name__ == "__main__":
    unittest.main()
