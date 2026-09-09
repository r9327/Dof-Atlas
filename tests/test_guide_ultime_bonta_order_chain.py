from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.quest_catalog import normalize_text


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"
RANKS = (20, 40, 60, 80, 100)
ORDER_KEYS = ("coeur vaillant", "oeil attentif", "esprit salvateur")


class GuideUltimeBontaOrderChainTests(unittest.TestCase):
    @staticmethod
    def _payload(rank: int) -> dict:
        path = MANUAL / f"bonta_order_rank{rank}_v1.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _trigger_rank(payload: dict) -> int:
        trigger = payload.get("trigger") if isinstance(payload.get("trigger"), dict) else {}
        raw = trigger.get("minimum_alignment_rank") or trigger.get("minimum_rank")
        return int(raw)

    def test_all_five_ranks_keep_same_exactly_one_order(self) -> None:
        for rank in RANKS:
            with self.subTest(rank=rank):
                payload = self._payload(rank)
                self.assertEqual(self._trigger_rank(payload), rank)
                options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
                self.assertEqual(tuple(options), ORDER_KEYS)

                policy = payload.get("selection_policy") if isinstance(payload.get("selection_policy"), dict) else {}
                self.assertIs(policy.get("exactly_one"), True)
                self.assertIs(policy.get("unselected_routes_hidden"), True)
                if rank == 20:
                    self.assertIs(policy.get("manual_reselection_after_choice"), False)
                else:
                    self.assertIs(policy.get("order_change_forbidden"), True)

    def test_each_order_gate_points_to_same_order_at_next_rank(self) -> None:
        payloads = {rank: self._payload(rank) for rank in RANKS}
        for rank, next_rank in zip(RANKS, RANKS[1:]):
            current = payloads[rank]["options"]
            following = payloads[next_rank]["options"]
            for order_key in ORDER_KEYS:
                with self.subTest(rank=rank, next_rank=next_rank, order=order_key):
                    gate = current[order_key].get("next_order_gate")
                    self.assertIsInstance(gate, dict)
                    self.assertEqual(int(gate.get("alignment_rank")), next_rank)
                    self.assertEqual(
                        normalize_text(gate.get("quest")),
                        normalize_text(following[order_key].get("quest")),
                    )

    def test_late_rank_schema_stays_compatible_with_runtime_parser(self) -> None:
        for rank in RANKS:
            with self.subTest(rank=rank):
                payload = self._payload(rank)
                trigger = payload.get("trigger") if isinstance(payload.get("trigger"), dict) else {}
                parsed_rank = trigger.get("minimum_alignment_rank") or trigger.get("minimum_rank")
                required = trigger.get("required_quest") or trigger.get("after_quest")
                self.assertEqual(int(parsed_rank), rank)
                self.assertTrue(str(required or "").strip())


if __name__ == "__main__":
    unittest.main()
