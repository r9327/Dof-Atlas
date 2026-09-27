from __future__ import annotations

import unittest
from pathlib import Path

from tools import agent


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_GLOBAL_WORKING_SET_ANCHORS = {
    "",
    ".",
    "app",
    "data",
    "tests",
    "tools",
}


def _probe_for_anchor(anchor: str) -> str:
    normalized = agent.ai_context.normalize_path(anchor)
    if normalized.endswith("/"):
        return normalized.rstrip("/") + "/__road_ia_checkpoint__.py"
    return normalized


class AgentGlobalCheckpointTests(unittest.TestCase):
    def test_all_active_scopes_have_bounded_routable_working_sets(self) -> None:
        context_map, manifests = agent._model(ROOT)
        active_scopes: list[str] = []

        for scope, config in context_map["scopes"].items():
            manifest = manifests[scope]
            implementation = agent._scope_implementation(config, manifest)
            if implementation == "placeholder":
                continue

            active_scopes.append(scope)
            working_set = list(manifest.get("working_set", []))
            self.assertTrue(working_set, f"{scope}: active scope must declare a working_set")
            self.assertTrue(
                config.get("canonical_entries"),
                f"{scope}: active scope must expose canonical_entries",
            )
            self.assertTrue(
                config.get("test_entries"),
                f"{scope}: active scope must expose targeted test_entries",
            )

            for anchor in working_set:
                normalized = agent.ai_context.normalize_path(str(anchor)).rstrip("/")
                self.assertNotIn(
                    normalized,
                    FORBIDDEN_GLOBAL_WORKING_SET_ANCHORS,
                    f"{scope}: working_set anchor is too broad: {anchor}",
                )

            owned_probe = None
            for anchor in working_set:
                probe = _probe_for_anchor(str(anchor))
                detail = agent.ownership_payload(ROOT, [probe])["paths"][probe]
                if detail["status"] == "OWNED" and detail["primary_scope"] == scope:
                    owned_probe = probe
                    break

            self.assertIsNotNone(
                owned_probe,
                f"{scope}: no working_set anchor routes back to its primary scope",
            )

            impact = agent.impact_payload(ROOT, [str(owned_probe)])
            self.assertIn(scope, impact["scopes"])
            self.assertEqual(impact["unowned_paths"], [])
            self.assertEqual(impact["ambiguous_paths"], [])
            self.assertTrue(impact["working_set"])
            self.assertTrue(impact["recommended_tests"])

        self.assertTrue(active_scopes)
        self.assertIn("feature", {context_map["scopes"][scope]["kind"] for scope in active_scopes})
        self.assertIn(
            "shared_infrastructure",
            {context_map["scopes"][scope]["kind"] for scope in active_scopes},
        )

    def test_placeholders_remain_context_only(self) -> None:
        context_map, manifests = agent._model(ROOT)
        placeholders = [
            scope
            for scope, config in context_map["scopes"].items()
            if agent._scope_implementation(config, manifests[scope]) == "placeholder"
        ]
        self.assertTrue(placeholders)

        for scope in placeholders:
            inspected = agent.inspect_scope(ROOT, scope)
            self.assertEqual(inspected["implementation"], "placeholder")
            self.assertEqual(inspected["canonical_entries"], [])
            self.assertEqual(inspected["test_entries"], [])
            for anchor in inspected["working_set"]:
                probe = _probe_for_anchor(anchor)
                detail = agent.ownership_payload(ROOT, [probe])["paths"][probe]
                self.assertNotEqual(detail["primary_scope"], scope)
                self.assertIn(scope, detail["placeholder_scopes"])


if __name__ == "__main__":
    unittest.main()
