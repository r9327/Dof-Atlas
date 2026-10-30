from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard


class _Service:
    def __init__(self, contract):
        self.auto_validation_contract = contract
        self.card_key_calls = 0

    def card_key(self, card, fallback_index):
        self.card_key_calls += 1
        return str(card.get("key") or f"index:{fallback_index}")


class GuideManualContractRowCacheTests(unittest.TestCase):
    def test_contract_rows_are_indexed_once_and_reused(self) -> None:
        row_a = {"card_key": "a", "quests": [1]}
        row_b = {"card_key": "b", "quests": [2]}
        service = _Service({"cards": [row_a, row_b]})
        widget = SimpleNamespace(service=service, card={"key": "b"}, index=1)

        self.assertIs(GuideUltimeManualCard._contract_row(widget), row_b)
        first_cache = service._manual_contract_row_index_cache
        self.assertIs(GuideUltimeManualCard._contract_row(widget), row_b)
        self.assertIs(service._manual_contract_row_index_cache, first_cache)

    def test_long_guide_tooltip_index_is_not_rebuilt_for_each_line(self) -> None:
        # Static hot-path budget check. The UI-level tooltip behavior remains
        # covered by the shared manual Qt contract tests separately.
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "app" / "modules" / "encyclopedia" / "views"
            / "shared_manual_guide_view.py"
        ).read_text(encoding="utf-8")
        module = ast.parse(source)
        renderer = next(
            node for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef) and node.name == "_add_line_section"
        )
        line_loop = next(
            node for node in renderer.body
            if isinstance(node, ast.For)
            and isinstance(node.target, ast.Tuple)
            and any(
                isinstance(value, ast.Name) and value.id == "row_index"
                for value in node.target.elts
            )
        )
        before_line = [
            node for node in renderer.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "quest_names"
                for target in node.targets
            )
        ]
        self.assertEqual(len(before_line), 1)
        self.assertLess(before_line[0].lineno, line_loop.lineno)
        self.assertFalse(any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "quest_names"
                for target in node.targets
            )
            for node in ast.walk(line_loop)
        ))

    def test_bulk_guide_combat_evidence_preserves_order_ids_quantities_and_dedup(self) -> None:
        combat_10 = {"objective_id": 80, "monster": "Bouftou Royal", "quantity": 2}
        combat_20 = {"objective_id": 90, "monster": "Tofu Royal", "quantity": 3}
        per_quest = Mock(side_effect=AssertionError("must use one batch"))
        batch = Mock(return_value={
            10: {"combats": [combat_10, combat_10]},
            20: {"combats": [combat_20]},
        })
        provider = SimpleNamespace(
            guide_evidence=per_quest,
            guide_evidence_many=batch,
            get_quest=Mock(side_effect=AssertionError("rich Quest read on Qt")),
        )
        fake = SimpleNamespace(
            service=SimpleNamespace(quest_provider=provider),
            card={"manual_quest_ids": [10, 20, 10]},
            _quest_rows=[(10, "Première quête"), (20, "Seconde quête")],
            _safe_positive_int=GuideUltimeManualCard._safe_positive_int,
        )
        result = GuideUltimeManualCard._quest_combat_targets(
            fake, {"now": [{"text": "Combattre Bouftou Royal puis Tofu Royal"}]}
        )
        self.assertEqual(result, [
            {"quest_id": 10, "objective_id": 80, "quest_name": "Première quête",
             "monster": "Bouftou Royal", "quantity": 2},
            {"quest_id": 20, "objective_id": 90, "quest_name": "Seconde quête",
             "monster": "Tofu Royal", "quantity": 3},
        ])
        batch.assert_called_once_with([10, 20, 10])
        per_quest.assert_not_called()
        provider.get_quest.assert_not_called()

    def test_legacy_provider_combat_evidence_remains_identical(self) -> None:
        provider = SimpleNamespace(
            guide_evidence=Mock(return_value={
                "combats": [{"objective_id": 80, "monster": "Bouftou Royal",
                             "quantity": 2}]
            }),
            get_quest=Mock(side_effect=AssertionError("compact source exists")),
        )
        fake = SimpleNamespace(
            service=SimpleNamespace(quest_provider=provider),
            card={"manual_quest_ids": [10]},
            _quest_rows=[(10, "Quête stable")],
            _safe_positive_int=GuideUltimeManualCard._safe_positive_int,
        )
        result = GuideUltimeManualCard._quest_combat_targets(
            fake, {"now": [{"text": "Combattre Bouftou Royal"}]}
        )
        self.assertEqual(
            [(row["quest_id"], row["objective_id"], row["quantity"]) for row in result],
            [(10, 80, 2)],
        )
        provider.guide_evidence.assert_called_once_with(10)

    def test_waypoint_index_is_built_once_and_preserves_authored_order(self) -> None:
        # A long Guide must not rescan all waypoints on every visible row.
        waypoints = [
            {"x": 1, "y": 2, "quests": ["Une quête", "Autre quête", "Une quête"]},
            {"x": 3, "y": 4, "quests": ["Autre quête"]},
            {"x": 1, "y": 2, "quests": ["Autre quête"]},
            {"label": "[5,-6]", "quests": ["Une quête"]},
        ]
        fake = SimpleNamespace(
            card={"manual_stage_data": {"waypoints": waypoints}},
            _quest_rows=[(10, "Une quête"), (20, "Autre quête")],
            _waypoint_quest_ids_by_position=None,
            _position_key=GuideUltimeManualCard._position_key,
            _quest_name_key=GuideUltimeManualCard._quest_name_key,
        )
        lookup = GuideUltimeManualCard._waypoint_quest_ids_for_row
        self.assertEqual(lookup(fake, {"position": "[1, 2]"}), [10, 20])
        self.assertEqual(lookup(fake, {"position": "[3, 4]"}), [20])
        self.assertEqual(lookup(fake, {"position": "[5,-6]"}), [10])
        self.assertEqual(lookup(fake, {"position": "inconnu"}), [])
        first_cache = fake._waypoint_quest_ids_by_position
        self.assertIsNotNone(first_cache)
        waypoints.clear()
        self.assertEqual(lookup(fake, {"position": "[1, 2]"}), [10, 20])
        self.assertIs(first_cache, fake._waypoint_quest_ids_by_position)

    def test_fallback_quest_name_matches_use_one_normalized_index(self) -> None:
        fake = SimpleNamespace(
            _quest_rows=[(10, "Une quête"), (20, "Autre quête")],
            _quest_normalized_rows=None,
            _quest_name_key=GuideUltimeManualCard._quest_name_key,
            _waypoint_quest_ids_for_row=lambda row: [],
        )
        lookup = GuideUltimeManualCard._quest_ids_for_row
        self.assertEqual(lookup(fake, {"text": "Finir Une quête"}), [10])
        cached = fake._quest_normalized_rows
        self.assertEqual(lookup(fake, {"text": "Finir Autre quête"}), [20])
        self.assertIs(fake._quest_normalized_rows, cached)
        # A multi-Quest sheet cannot invent a link for unrelated actions.
        self.assertEqual(lookup(fake, {"text": "Parler au PNJ"}), [])

    def test_replacing_contract_rebuilds_index(self) -> None:
        first = {"card_key": "a", "quests": [1]}
        service = _Service({"cards": [first]})
        widget = SimpleNamespace(service=service, card={"key": "a"}, index=0)
        self.assertIs(GuideUltimeManualCard._contract_row(widget), first)

        replacement = {"card_key": "a", "quests": [99]}
        service.auto_validation_contract = {"cards": [replacement]}
        self.assertIs(GuideUltimeManualCard._contract_row(widget), replacement)


if __name__ == "__main__":
    unittest.main()
