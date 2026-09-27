from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import agent, agent_hotspots


ROOT = Path(__file__).resolve().parents[1]


class AgentHotspotTests(unittest.TestCase):
    def _write_scope(
        self,
        root: Path,
        scope: str,
        *,
        kind: str,
        working_set: list[str],
        shared_dependencies: list[str] | None = None,
        implementation: str | None = None,
    ) -> None:
        lines = [
            "schema_version: 1",
            f"scope: {scope}",
            f"kind: {kind}",
        ]
        if implementation is not None:
            lines.append(f"implementation: {implementation}")
        lines.append("working_set:")
        lines.extend(f"  - {path}" for path in working_set)
        dependencies = shared_dependencies or []
        if dependencies:
            lines.append("shared_dependencies:")
            lines.extend(f"  - {dependency}" for dependency in dependencies)
        else:
            lines.append("shared_dependencies: []")
        lines.append("context_entries: []")
        (root / f".ai/scopes/{scope}.yaml").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    def _write_demo_router(self, root: Path) -> None:
        (root / ".ai/scopes").mkdir(parents=True)
        (root / ".ai/context-map.yaml").write_text(
            """schema_version: 2
rule_defaults:
  - AGENTS.md
scopes:
  shared:
    kind: shared_infrastructure
    manifest: .ai/scopes/shared.yaml
    rule_entries: []
    canonical_entries:
      - app/core/character_identity.py
    test_entries: []
  feature_a:
    kind: feature
    manifest: .ai/scopes/feature_a.yaml
    rule_entries: []
    canonical_entries: []
    test_entries: []
  feature_b:
    kind: feature
    manifest: .ai/scopes/feature_b.yaml
    rule_entries: []
    canonical_entries: []
    test_entries: []
  startup:
    kind: feature
    manifest: .ai/scopes/startup.yaml
    rule_entries: []
    canonical_entries:
      - main.py
    test_entries: []
  low:
    kind: feature
    manifest: .ai/scopes/low.yaml
    rule_entries: []
    canonical_entries: []
    test_entries: []
  placeholder:
    kind: feature
    implementation: placeholder
    manifest: .ai/scopes/placeholder.yaml
    rule_entries: []
    canonical_entries:
      - main.py
    test_entries: []
""",
            encoding="utf-8",
        )
        self._write_scope(
            root,
            "shared",
            kind="shared_infrastructure",
            working_set=["app/core/character_identity.py"],
        )
        self._write_scope(
            root,
            "feature_a",
            kind="feature",
            working_set=["app/feature_a.py"],
            shared_dependencies=["shared"],
        )
        self._write_scope(
            root,
            "feature_b",
            kind="feature",
            working_set=["app/feature_b.py"],
            shared_dependencies=["shared"],
        )
        self._write_scope(root, "startup", kind="feature", working_set=["main.py"])
        self._write_scope(root, "low", kind="feature", working_set=["docs/readme.md"])
        self._write_scope(
            root,
            "placeholder",
            kind="feature",
            working_set=["main.py"],
            implementation="placeholder",
        )

    def test_hotspots_are_informational_and_use_existing_risk_plus_centrality(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_demo_router(root)
            payload = agent_hotspots.hotspots_payload(root)

        self.assertEqual(payload["source"], "atlas-integrity-risk-and-scope-dependencies")
        self.assertEqual(payload["mode"], "INFORMATIONAL")
        self.assertFalse(payload["blocking"])
        hotspots = {item["scope"]: item for item in payload["hotspots"]}
        self.assertIn("shared", hotspots)
        self.assertIn("startup", hotspots)
        self.assertNotIn("low", hotspots)
        self.assertNotIn("placeholder", hotspots)
        self.assertEqual(hotspots["shared"]["consumer_count"], 2)
        self.assertEqual(set(hotspots["shared"]["consumer_scopes"]), {"feature_a", "feature_b"})
        self.assertIn("shared_dependency:multiple_consumers", hotspots["shared"]["indicators"])
        self.assertIn(hotspots["shared"]["risk"], {"HIGH", "CRITICAL"})
        self.assertIn(hotspots["startup"]["risk"], {"HIGH", "CRITICAL"})

    def test_scope_filter_keeps_report_small(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_demo_router(root)
            payload = agent_hotspots.hotspots_payload(root, ["shared", "low"])

        self.assertEqual(payload["scopes"], ["shared", "low"])
        self.assertEqual([item["scope"] for item in payload["hotspots"]], ["shared"])

    def test_hotspots_reject_unknown_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_demo_router(root)
            with self.assertRaisesRegex(agent.AgentConfigError, "unknown scope"):
                agent_hotspots.hotspots_payload(root, ["missing"])

    def test_real_router_reports_policy_backed_hotspots_without_placeholder(self) -> None:
        payload = agent_hotspots.hotspots_payload(ROOT)
        hotspots = {item["scope"]: item for item in payload["hotspots"]}
        self.assertIn("quality_ci", hotspots)
        self.assertIn("persistence_identity", hotspots)
        self.assertNotIn("encyclopedia_bestiary", hotspots)
        self.assertTrue(
            all(
                item["risk"] in agent_hotspots.HOTSPOT_RISK_LEVELS
                or item["consumer_count"] >= agent_hotspots.HOTSPOT_MIN_SHARED_CONSUMERS
                for item in payload["hotspots"]
            )
        )


if __name__ == "__main__":
    unittest.main()
