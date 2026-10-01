from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.agent_task_profiles import infer_task_type, load_config, select_work_card


class AgentTaskProfileTests(unittest.TestCase):
    def test_economy_task_selects_cheapest_eligible_tier(self) -> None:
        card = select_work_card(
            task_type="tiny_edit",
            requested_quality="economy",
            work_depth="SOFT",
            environ={},
        )
        self.assertEqual(card["selected_tier"], "economy")
        self.assertEqual(card["cost_rank"], 1)
        self.assertEqual(card["effective_quality"], "economy")

    def test_requested_best_quality_selects_premium_tier(self) -> None:
        card = select_work_card(
            task_type="localized_fix",
            requested_quality="best",
            work_depth="SOFT",
            environ={},
        )
        self.assertEqual(card["selected_tier"], "premium")
        self.assertEqual(card["reasoning_effort"], "high")

    def test_risk_floor_cannot_be_lowered_by_requested_quality(self) -> None:
        card = select_work_card(
            task_type="structural",
            requested_quality="economy",
            work_depth="HARD",
            environ={},
        )
        self.assertEqual(card["effective_quality"], "best")
        self.assertEqual(card["selected_tier"], "premium")
        self.assertTrue(card["escalations"])

    def test_model_id_is_resolved_from_environment_without_changing_policy(self) -> None:
        card = select_work_card(
            task_type="feature",
            requested_quality="balanced",
            work_depth="MEDIUM",
            environ={"DOF_AI_MODEL_BALANCED": "provider-model-v2"},
        )
        self.assertEqual(card["resolved_model"], "provider-model-v2")
        self.assertEqual(card["model_resolution"], "environment")

    def test_inference_is_topology_and_depth_driven(self) -> None:
        self.assertEqual(infer_task_type([], work_depth="SOFT"), "read_only")
        self.assertEqual(infer_task_type(["docs/note.md"], work_depth="SOFT"), "tiny_edit")
        self.assertEqual(infer_task_type(["app/a.py"], work_depth="SOFT"), "localized_fix")
        self.assertEqual(infer_task_type(["app/a.py", "app/b.py"], work_depth="SOFT"), "feature")
        self.assertEqual(infer_task_type(["app/a.py"], work_depth="HARD"), "refactor")
        self.assertEqual(
            infer_task_type(["app/a.py"], work_depth="SOFT", structural=True),
            "structural",
        )
        self.assertEqual(
            infer_task_type([".github/workflows/ci.yml"], work_depth="SOFT"),
            "certification",
        )

    def test_invalid_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "schema_version"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
