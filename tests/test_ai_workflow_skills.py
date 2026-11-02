from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEW_SKILLS = {
    "codebase-navigation",
    "root-cause-debugging",
    "safe-architecture-cleanup",
    "pyside6-qtwebengine",
    "persistence-safety",
    "dofus-data-provenance",
    "evidence-driven-validation",
    "performance-triage",
}


class AiWorkflowSkillsTests(unittest.TestCase):
    def test_discoverable_skills_have_unique_valid_frontmatter(self) -> None:
        skills = sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))
        self.assertTrue(NEW_SKILLS.issubset({p.parent.name for p in skills}))
        seen = set()
        for path in skills:
            with self.subTest(path=str(path.relative_to(ROOT))):
                data = path.read_text(encoding="utf-8")
                self.assertTrue(data.startswith("---\n"))
                header = data.split("---\n", 2)[1]
                name = re.search(r"(?m)^name: ([a-z0-9-]+)$", header)
                self.assertIsNotNone(name)
                self.assertEqual(name.group(1), path.parent.name)
                self.assertRegex(header, r"(?m)^description: .{25,}$")
                self.assertIn("\n# ", data)
                self.assertNotIn(name.group(1), seen)
                seen.add(name.group(1))

    def test_specialist_skills_preserve_existing_guards(self) -> None:
        def skill(name: str) -> str:
            return (ROOT / f".agents/skills/{name}/SKILL.md").read_text(encoding="utf-8")
        cleanup = skill("safe-architecture-cleanup")
        for anchor in ("Graphify", "exact candidate SHA", "tools.tool_audit",
                       "tools.tool_catalog", "not proof of dead code"):
            self.assertIn(anchor, cleanup)
        self.assertIn("character:<id_dofus>", skill("persistence-safety"))
        self.assertIn("atomic write", skill("persistence-safety"))
        self.assertIn("PHASE_CERTIFICATION.md", skill("evidence-driven-validation"))
        self.assertIn("Draft", skill("evidence-driven-validation"))

    def test_canonical_routing_and_ci_are_wired(self) -> None:
        self.assertTrue((ROOT / "tools/skills/dofus-atlas-tools/SKILL.md").is_file())
        self.assertTrue((ROOT / ".agents/skills/find-docs/SKILL.md").is_file())
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/", agents)
        self.assertIn("tools/skills/dofus-atlas-tools/SKILL.md", agents)
        manifest = (ROOT / ".ai/scopes/quality_ci.yaml").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/", manifest)
        self.assertIn("tests/test_ai_workflow_skills.py", manifest)
        scopes = (ROOT / ".ai/context-map.yaml").read_text(encoding="utf-8")
        self.assertIn("tests.test_ai_workflow_skills", scopes)
        workflow = (ROOT / ".github/workflows/ai-context-ci.yml").read_text(encoding="utf-8")
        self.assertIn("test_ai_workflow_skills.py", workflow)

    def test_provider_instructions_route_to_doctor_and_catalog(self) -> None:
        """A provider must request the actual tool workflow, not merely name Doctor."""
        providers = [
            "CLAUDE.md", ".github/copilot-instructions.md",
            ".cursor/rules/atlas-doctor.mdc", "AI_CONTEXT.md",
        ]
        for name in providers:
            with self.subTest(name=name):
                content = (ROOT / name).read_text(encoding="utf-8")
                for anchor in (
                    "AI_ENTRYPOINT.md", "ai_tool_workflow",
                    "agent plan", "agent check --run-tests", "agent validate",
                    "tools.tool_catalog", "tools/skills/dofus-atlas-tools/SKILL.md",
                ):
                    self.assertIn(anchor, content)
        canonical = (ROOT / "AI_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("--preferred-only --safe-only --ready-only", canonical)
        self.assertIn("native_routes_executed_by_selection=false", canonical)

    def test_oss_docs_do_not_require_manual_enable_on_normal_check(self) -> None:
        docs = (ROOT / "docs/doctor-oss-routing.md").read_text(encoding="utf-8")
        self.assertIn("agent check --run-tests", docs)
        self.assertIn("automatiquement", docs)
        self.assertIn("--verify-live", docs)
        self.assertIn("NOT_AVAILABLE", docs)
        self.assertNotIn(
            "agent check tools/tool_catalog.py --run-tests --run-oss", docs
        )


if __name__ == "__main__":
    unittest.main()
