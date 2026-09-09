from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.encyclopedia.services.adventure_route_adapter import AdventureRouteAdapter
from app.modules.encyclopedia.services.adventure_route_engine import (
    AdventureRouteEngine,
    RouteAction,
    RouteProgress,
)


class GuideUltimeV5OrRuntimeTests(unittest.TestCase):
    def test_engine_accepts_one_completed_qf_alternative(self):
        action = RouteAction(
            action_id="q100:start",
            quest_id=100,
            title="Q100",
            kind="start",
            prerequisite_quest_alternatives=(frozenset({10}), frozenset({20})),
            activates_quest=True,
        )
        engine = AdventureRouteEngine([action])
        no_branch = engine.plan(SimpleNamespace(level=200, character_class="", alignment="", alignment_level=0, order="", flags=frozenset()), RouteProgress())
        self.assertFalse(no_branch.steps)
        with_branch = engine.plan(
            SimpleNamespace(level=200, character_class="", alignment="", alignment_level=0, order="", flags=frozenset()),
            RouteProgress(completed_quest_ids={20}),
        )
        self.assertTrue(with_branch.steps)

    def test_adapter_preserves_qf_or_as_any_of(self):
        quest = SimpleNamespace(
            id=100,
            name="Convergence",
            start_criterion="(Qf=10&PG=1)|(Qf=20&PG=2)",
            level_min=1,
            steps=(),
        )
        catalog = SimpleNamespace(by_id={100: quest})
        guide = SimpleNamespace(quest_ids=(100,))
        result = AdventureRouteAdapter(catalog, guide).build()
        start = next(action for action in result.actions if action.action_id == "quest:100:start")
        self.assertEqual(start.prerequisites_quests, frozenset())
        self.assertEqual(
            set(start.prerequisite_quest_alternatives),
            {frozenset({10}), frozenset({20})},
        )

    def test_class_convergence_pg_pm_is_not_flagged_unknown(self):
        quest = SimpleNamespace(
            id=1960,
            name="Ça sent le gaz",
            start_criterion="(Qf=1971&PG=9&Pm=188744198)|(Qf=1968&PG=6&Pm=192413696)",
            level_min=1,
            steps=(),
        )
        catalog = SimpleNamespace(by_id={1960: quest})
        guide = SimpleNamespace(quest_ids=(1960,))
        result = AdventureRouteAdapter(catalog, guide).build()
        self.assertFalse(any(w.code == "unresolved_hard_criterion" for w in result.warnings))

    def test_known_runtime_gate_is_surfaced_not_fake_verified(self):
        quest = SimpleNamespace(
            id=944,
            name="Bûcher, c'est votre métier",
            start_criterion="PL>19&PJ>2,39",
            level_min=1,
            steps=(),
        )
        catalog = SimpleNamespace(by_id={944: quest})
        guide = SimpleNamespace(quest_ids=(944,))
        result = AdventureRouteAdapter(catalog, guide).build()
        gates = [w for w in result.warnings if w.code == "runtime_gate_criterion"]
        self.assertEqual(len(gates), 1)
        self.assertEqual(gates[0].criterion_codes, ("pj",))
        self.assertIn("PJ>2,39", gates[0].criterion)
        self.assertFalse(any(w.code == "unresolved_hard_criterion" for w in result.warnings))

    def test_truly_unknown_gate_stays_blocking(self):
        quest = SimpleNamespace(
            id=9999,
            name="Gate inconnu",
            start_criterion="ZZ=42",
            level_min=1,
            steps=(),
        )
        catalog = SimpleNamespace(by_id={9999: quest})
        guide = SimpleNamespace(quest_ids=(9999,))
        result = AdventureRouteAdapter(catalog, guide).build()
        self.assertTrue(any(w.code == "unresolved_hard_criterion" for w in result.warnings))
        start = next(action for action in result.actions if action.action_id == "quest:9999:start")
        self.assertIn("criterion-verified:9999", start.condition.required_flags)


if __name__ == "__main__":
    unittest.main()
