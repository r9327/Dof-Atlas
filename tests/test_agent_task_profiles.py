from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.agent_task_profiles import infer_task_type, load_config, select_work_card


class AgentTaskProfileTests(unittest.TestCase):
    def test_task_recommendation_is_used_when_user_does_not_choose_quality(self) -> None:
        card = select_work_card(task_type="tiny_edit", environ={})
        self.assertEqual(card["recommended_quality"], "economy")
        self.assertEqual(card["selected_quality"], "economy")
        self.assertEqual(card["selected_tier"], "economy")
        self.assertEqual(card["consumption_rank"], 1)
        self.assertEqual(card["consumption_label"], "low")
        self.assertFalse(card["user_override"])
        self.assertEqual(card["doctor_validation"], "independent")

    def test_requested_best_quality_selects_premium_tier(self) -> None:
        card = select_work_card(
            task_type="localized_fix",
            requested_quality="best",
            environ={},
        )
        self.assertEqual(card["recommended_quality"], "balanced")
        self.assertEqual(card["selected_quality"], "best")
        self.assertEqual(card["selected_tier"], "premium")
        self.assertEqual(card["reasoning_effort"], "high")
        self.assertEqual(card["consumption_label"], "high")
        self.assertTrue(card["user_override"])

    def test_user_can_choose_economy_even_when_task_recommends_premium(self) -> None:
        card = select_work_card(
            task_type="structural",
            requested_quality="economy",
            environ={},
        )
        self.assertEqual(card["recommended_quality"], "best")
        self.assertEqual(card["selected_quality"], "economy")
        self.assertEqual(card["selected_tier"], "economy")
        self.assertEqual(card["consumption_rank"], 1)
        self.assertTrue(card["user_override"])

    def test_model_id_is_resolved_from_environment_without_changing_policy(self) -> None:
        card = select_work_card(
            task_type="feature",
            requested_quality="balanced",
            environ={"DOF_AI_MODEL_BALANCED": "provider-model-v2"},
        )
        self.assertEqual(card["resolved_model"], "provider-model-v2")
        self.assertEqual(card["model_resolution"], "environment")

    def test_inference_uses_task_topology_only(self) -> None:
        self.assertEqual(infer_task_type([]), "read_only")
        self.assertEqual(infer_task_type(["docs/note.md"]), "tiny_edit")
        self.assertEqual(infer_task_type(["app/a.py"]), "localized_fix")
        self.assertEqual(infer_task_type(["app/a.py", "app/b.py"]), "feature")
        self.assertEqual(
            infer_task_type(["app/a.py"], structural=True),
            "structural",
        )
        self.assertEqual(
            infer_task_type(["app/a.py"], certification=True),
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
