from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_RELATIVE = "tools/skills/dofus-atlas-tools/SKILL.md"
TEST_RELATIVE = "tests/test_dofus_atlas_tools_skill.py"
SKILL = ROOT / SKILL_RELATIVE


class DofusAtlasToolsSkillTests(unittest.TestCase):
    def test_skill_routes_to_canonical_machine_readable_contract(self) -> None:
        text = SKILL.read_text(encoding="utf-8")

        self.assertTrue(text.startswith("---\nname: dofus-atlas-tools\n"))
        self.assertIn("tools/tool_catalog.py", text)
        self.assertIn("TOOL_SPEC", text)
        self.assertIn("py -3.13 -m tools.tool_catalog --json", text)
        self.assertIn("--preferred-only --safe-only --ready-only --json", text)
        self.assertIn("automation_ready=true", text)
        self.assertIn("GRAPHIFY.md", text)
        self.assertIn("PHASE_CERTIFICATION.md", text)

    def test_repository_file_references_in_skill_exist(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        references = set(
            re.findall(
                r"(?<![A-Za-z0-9_.-])((?:tools|\.ai)/[A-Za-z0-9_./-]+\.(?:py|md|json|yaml|yml|ps1))",
                text,
            )
        )
        references.update({"AGENTS.md", "GRAPHIFY.md", "PHASE_CERTIFICATION.md"})

        self.assertTrue(references)
        missing = sorted(relative for relative in references if not (ROOT / relative).exists())
        self.assertEqual(missing, [])

    def test_quality_ci_scope_and_tool_guidance_route_to_skill(self) -> None:
        tooling_guidance = (ROOT / "tools/AGENTS.md").read_text(encoding="utf-8")
        scope_manifest = (ROOT / ".ai/scopes/quality_ci.yaml").read_text(encoding="utf-8")

        self.assertIn(SKILL_RELATIVE, tooling_guidance)
        self.assertIn(SKILL_RELATIVE, scope_manifest)
        self.assertIn(TEST_RELATIVE, scope_manifest)


if __name__ == "__main__":
    unittest.main()
