from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tools import agent


ROOT = Path(__file__).resolve().parents[1]


class AgentToolTests(unittest.TestCase):
    def test_doctor_accepts_current_router(self) -> None:
        payload = agent.doctor_payload(ROOT)
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["context_index_current"])
        self.assertEqual(payload["scope_count"], 23)
        self.assertEqual(payload["errors"], [])

    def test_inspect_combines_scope_manifest_and_existing_rules(self) -> None:
        payload = agent.inspect_scope(ROOT, "encyclopedia_guide")
        self.assertEqual(payload["kind"], "feature")
        self.assertIn("AGENTS.md", payload["rules"])
        self.assertIn("data/AGENTS.md", payload["rules"])
        self.assertIn("PHASE_CERTIFICATION.md", payload["rules"])
        self.assertIn(
            "data/routes/guide_ultime_manual/manifest_v1.json",
            payload["canonical_entries"],
        )
        self.assertIn(
            "app/modules/encyclopedia/views/guides_view.py",
            payload["working_set"],
        )
        self.assertIn("persistence_identity", payload["shared_dependencies"])

    def test_inspect_preserves_placeholder_state(self) -> None:
        payload = agent.inspect_scope(ROOT, "encyclopedia_bestiary")
        self.assertEqual(payload["implementation"], "placeholder")
        self.assertEqual(payload["canonical_entries"], [])

    def test_impact_routes_only_declared_working_set_anchors(self) -> None:
        path = "app/modules/encyclopedia/views/guides_view.py"
        payload = agent.impact_payload(ROOT, [path])
        self.assertEqual(payload["scope_matches"][path], ["encyclopedia_guide"])
        self.assertEqual(payload["scopes"], ["encyclopedia_guide"])
        self.assertIn("persistence_identity", payload["shared_dependencies"])
        self.assertIn(
            "data/routes/guide_ultime_manual/manifest_v1.json",
            payload["canonical_entries"],
        )
        self.assertIn("tests.test_guide_ultime_manual_prerequisites", payload["recommended_tests"])

    def test_validate_delegates_directly_to_atlas_integrity(self) -> None:
        arguments = ["critical", "--base-ref", "origin/main", "--json"]
        with mock.patch.object(agent.atlas_integrity, "main", return_value=7) as delegated:
            exit_code = agent.main(["validate", *arguments])
        self.assertEqual(exit_code, 7)
        delegated.assert_called_once_with(arguments)


if __name__ == "__main__":
    unittest.main()
