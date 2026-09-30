from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from tools import agent


class AgentPlanCliTests(unittest.TestCase):
    @staticmethod
    def _impact() -> dict:
        return {
            "paths": ["app/example.py"],
            "scopes": ["app"],
            "unowned_paths": [],
            "ambiguous_paths": [],
            "recommended_tests": ["tests.test_example"],
            "rules": ["AGENTS.md"],
            "canonical_entries": [],
            "context_entries": [],
            "working_set": ["app/"],
        }

    def test_plan_json_delegates_to_planner_without_becoming_a_gate(self) -> None:
        planned = {
            "schema_version": 1,
            "source": "tools.agent_planner",
            "read_only": True,
            "status": "REVIEW_REQUIRED",
            "automation_safe": False,
            "paths": ["app/example.py"],
        }
        output = io.StringIO()
        with (
            patch.object(agent, "impact_payload", return_value=self._impact()) as impact,
            patch.object(agent.agent_planner, "build_plan", return_value=planned) as planner,
            redirect_stdout(output),
        ):
            exit_code = agent.main(["plan", "app/example.py", "--json"])

        self.assertEqual(exit_code, 0)
        impact.assert_called_once_with(agent.ROOT, ["app/example.py"])
        planner.assert_called_once_with(agent.ROOT, ["app/example.py"], self._impact())
        self.assertEqual(json.loads(output.getvalue()), planned)

    def test_plan_human_output_uses_existing_payload_renderer(self) -> None:
        planned = {
            "schema_version": 1,
            "source": "tools.agent_planner",
            "read_only": True,
            "status": "READY",
            "automation_safe": True,
            "paths": ["tools/agent.py"],
        }
        output = io.StringIO()
        with (
            patch.object(agent, "impact_payload", return_value=self._impact()),
            patch.object(agent.agent_planner, "build_plan", return_value=planned),
            redirect_stdout(output),
        ):
            exit_code = agent.main(["plan", "tools/agent.py"])

        self.assertEqual(exit_code, 0)
        rendered = output.getvalue()
        self.assertIn("status: READY", rendered)
        self.assertIn("automation_safe: True", rendered)


if __name__ == "__main__":
    unittest.main()
