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

    def test_ai_provider_entrypoints_require_full_doctor_loop(self) -> None:
        """Catch instruction drift without adding another CI gate or tool registry."""
        paths = (
            "AI_ENTRYPOINT.md",
            "CLAUDE.md",
            ".github/copilot-instructions.md",
            "AI_CONTEXT.md",
            "tools/skills/dofus-atlas-tools/SKILL.md",
        )
        for relative in paths:
            with self.subTest(entrypoint=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("tools.atlas_doctor agent plan", text)
                self.assertIn("tools.atlas_doctor agent check", text)
                self.assertIn("--run-tests", text)
                self.assertIn("tools.atlas_doctor agent validate", text)
                self.assertIn("oss_selection", text)
                if relative != "AI_ENTRYPOINT.md":
                    self.assertIn("AI_ENTRYPOINT.md", text)

    def test_ai_evidence_states_are_not_confused_with_certification(self) -> None:
        entry = (ROOT / "AI_ENTRYPOINT.md").read_text(encoding="utf-8")
        skill = (ROOT / "tools/skills/dofus-atlas-tools/SKILL.md").read_text(encoding="utf-8")
        copilot = (ROOT / ".github/copilot-instructions.md").read_text(encoding="utf-8")
        validation = (ROOT / ".agents/skills/evidence-driven-validation/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("oss_advisory.execution_summary", entry)
        self.assertIn("oss_advisory.execution_summary", skill)
        self.assertIn("oss_advisory.execution_summary", copilot)
        self.assertIn("oss_advisory.execution_summary.gaps", validation)
        self.assertIn("doctor oss", entry)
        self.assertIn("--verify-live", entry)
        self.assertIn("PHASE_CERTIFICATION.md", skill)
        self.assertIn("Phase Certification", copilot)

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


if __name__ == "__main__":
    unittest.main()
