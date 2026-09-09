from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

from app.modules.encyclopedia.services.guide_ultime_route_adapter import (
    GuideUltimeRouteAdapter,
)
from tools import audit_guide_ultime_route_forensic as base


class ForensicAuditV2(base.ForensicAudit):
    """Forensic V2: sanitized GPS semantics + correct Order rank contract."""

    def __init__(self, route: dict[str, Any], final: dict[str, Any]) -> None:
        # The base constructor resolves this global at runtime.
        base.AdventureRouteAdapter = GuideUltimeRouteAdapter
        super().__init__(route, final)

    def _check_branch_contract(self) -> None:
        branches = self.route.get("conditional_branches") if isinstance(self.route.get("conditional_branches"), dict) else {}
        class_card = branches.get("class_card") if isinstance(branches.get("class_card"), dict) else {}
        class_options = [row for row in class_card.get("options", []) or [] if isinstance(row, dict)]
        class_qids = [base._safe_int(row.get("quest_id")) for row in class_options]
        class_qids = [qid for qid in class_qids if qid is not None]
        if len(class_qids) != len(set(class_qids)):
            self.error("duplicate_class_branch_quest_ids")
        leaked_classes = set(class_qids) & set(self.route_qids)
        if leaked_classes:
            self.error("class_branch_quest_leaked_into_common_route", quest_ids=sorted(leaked_classes))

        order_cards = [row for row in branches.get("order_cards", []) or [] if isinstance(row, dict)]
        bonta_by_order: dict[str, dict[int, int]] = defaultdict(dict)
        expected_levels = {20, 40, 60, 80, 100}
        expected_slots = {1, 2, 3, 4, 5}
        seen_slots: set[int] = set()
        seen_levels: set[int] = set()

        for card in order_cards:
            slot = base._safe_int(card.get("rank"))
            level = base._safe_int(card.get("alignment_level"))
            if slot is not None:
                seen_slots.add(slot)
            if level is not None:
                seen_levels.add(level)
            if slot is None or level is None:
                self.error("bonta_order_card_missing_rank_or_level", card=card)
                continue
            expected_level = (20, 40, 60, 80, 100)[slot - 1] if 1 <= slot <= 5 else None
            if expected_level is None or level != expected_level:
                self.error(
                    "bonta_order_rank_level_mismatch",
                    slot=slot,
                    alignment_level=level,
                    expected_alignment_level=expected_level,
                )
            for option in card.get("options", []) or []:
                if not isinstance(option, dict):
                    continue
                name = str(option.get("order") or "").strip()
                key = base._norm(name)
                if key not in {"coeur vaillant", "oeil attentif", "esprit salvateur"}:
                    continue
                qid = base._safe_int(option.get("quest_id"))
                if qid is not None:
                    bonta_by_order[key][level] = qid

        if seen_slots != expected_slots:
            self.error("bonta_order_slots_incomplete", slots=sorted(seen_slots), expected=sorted(expected_slots))
        if seen_levels != expected_levels:
            self.error("bonta_order_levels_incomplete", levels=sorted(seen_levels), expected=sorted(expected_levels))

        for order in ("coeur vaillant", "oeil attentif", "esprit salvateur"):
            got = set(bonta_by_order.get(order, {}))
            if got != expected_levels:
                self.error("bonta_order_levels_incomplete_for_order", order=order, levels=sorted(got), expected=sorted(expected_levels))
            leaked = set(bonta_by_order.get(order, {}).values()) & set(self.route_qids)
            if leaked:
                self.error("bonta_order_quest_leaked_into_common_route", order=order, quest_ids=sorted(leaked))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--repair-safe", action="store_true")
    args = parser.parse_args()

    if not base.ROUTE_PATH.exists() or not base.FINAL_PATH.exists():
        print("Artefacts V5 absents. Lance d'abord tools/run_guide_ultime_v5.ps1")
        return 2

    route = base._read_json(base.ROUTE_PATH)
    final = base._read_json(base.FINAL_PATH)
    repairs: list[dict[str, Any]] = []

    if args.repair_safe:
        repairing = ForensicAuditV2(route, final)
        repairing.safe_repair()
        repairs = list(repairing.repairs)
        base._write_json(base.ROUTE_PATH, route)

    audit = ForensicAuditV2(route, final)
    audit.repairs = repairs
    audit.run_checks()
    result = audit.result()
    result["forensic_version"] = 2
    base._write_json(base.OUT_PATH, result)

    summary = result["summary"]
    print(
        "FORENSIC V2 "
        f"cards={summary['route_card_count']} quests={summary['route_quest_count']} "
        f"actions={summary['route_action_count']} hard={summary['hard_error_count']} "
        f"warnings={summary['warning_count']} no_coord={summary['cards_without_travel_coordinate']} "
        f"sentinel={summary['sentinel_value_count']} repairs={len(repairs)}"
    )
    print(f"Audit: {base.OUT_PATH}")
    if args.strict and result["hard_errors"]:
        print("FORENSIC V2 STRICT FAIL")
        by_code: dict[str, int] = defaultdict(int)
        for row in result["hard_errors"]:
            by_code[str(row.get("code") or "unknown")] += 1
        print(json.dumps(dict(sorted(by_code.items())), ensure_ascii=False, indent=2))
        return 1
    print("FORENSIC V2 STRICT PASS" if args.strict else "FORENSIC V2 AUDIT DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
