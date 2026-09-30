from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.tool_catalog import catalog


class ToolSpecContractTests(unittest.TestCase):
    @staticmethod
    def _write(root: Path, relative: str, content: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_static_spec_overrides_heuristics_without_importing_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/spec_tool.py",
                "TOOL_SPEC = {\n"
                "    'schema_version': 1,\n"
                "    'id': 'spec-tool',\n"
                "    'role': 'canonical_validation',\n"
                "    'capabilities': ['validation', 'inspection'],\n"
                "    'modes': ['inspect'],\n"
                "    'cost_hint': 'cheap',\n"
                "    'side_effects': 'read_only',\n"
                "    'structured_output': True,\n"
                "    'canonical': True,\n"
                "    'recommended_tests': ['tests.test_spec_tool'],\n"
                "}\n"
                "raise RuntimeError('catalog must never import this module')\n"
                "import argparse, json\n"
                "def main():\n"
                "    p = argparse.ArgumentParser()\n"
                "    p.add_argument('--json', action='store_true')\n"
                "    print(json.dumps({'ok': True}))\n"
                "if __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tests/test_spec_tool.py",
                "# reference only; importing the tool is intentionally forbidden here\n"
                "TOOL_PATH = 'tools/spec_tool.py'\n",
            )
            report = catalog(root)

        row = report["tools"][0]
        self.assertEqual(row["tool_spec_source"], "explicit")
        self.assertEqual(row["preferred_role"], "canonical_validation")
        self.assertTrue(row["preferred_for_agent"])
        self.assertEqual(row["canonicality"], "preferred")
        self.assertEqual(row["capabilities"], ["validation", "inspection"])
        self.assertEqual(row["cost_hint"], "cheap")
        self.assertEqual(row["side_effects"], "read_only")
        self.assertEqual(row["modes"], ["inspect"])
        self.assertEqual(row["declared_tests"], ["tests.test_spec_tool"])
        self.assertTrue(row["safe_for_agent"])
        self.assertTrue(row["automation_ready"])
        self.assertEqual(report["explicit_tool_spec_count"], 1)
        self.assertEqual(report["invalid_tool_spec_count"], 0)

    def test_invalid_spec_is_visible_and_blocks_agent_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/bad_spec.py",
                "def make_spec(): return {}\n"
                "TOOL_SPEC = make_spec()\n"
                "import argparse, json\n"
                "def main():\n"
                "    argparse.ArgumentParser().parse_args()\n"
                "    print(json.dumps({'ok': True}))\n"
                "if __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tests/test_bad_spec.py",
                "from tools.bad_spec import main\n",
            )
            report = catalog(root)

        row = report["tools"][0]
        self.assertTrue(row["tool_spec_errors"])
        self.assertIn("fix_tool_spec_contract", row["upgrade_actions"])
        self.assertEqual(row["readiness"], "review_before_agent_use")
        self.assertFalse(row["safe_for_agent"])
        self.assertFalse(row["automation_ready"])
        self.assertEqual(report["invalid_tool_spec_count"], 1)

    def test_explicit_repo_mutator_can_be_safe_but_never_auto_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/guarded_mutator.py",
                "TOOL_SPEC = {\n"
                "    'schema_version': 1,\n"
                "    'id': 'guarded-mutator',\n"
                "    'role': 'maintenance_mutator',\n"
                "    'capabilities': ['generation'],\n"
                "    'modes': ['preview', 'apply'],\n"
                "    'cost_hint': 'cheap',\n"
                "    'side_effects': 'repo_mutation_explicit',\n"
                "    'structured_output': True,\n"
                "    'canonical': False,\n"
                "    'recommended_tests': ['tests.test_guarded_mutator'],\n"
                "}\n"
                "import argparse, json\n"
                "from pathlib import Path\n"
                "def main():\n"
                "    p = argparse.ArgumentParser()\n"
                "    p.add_argument('--apply', action='store_true')\n"
                "    p.add_argument('--json', action='store_true')\n"
                "    args = p.parse_args()\n"
                "    if args.apply: Path('x').write_text('x')\n"
                "    print(json.dumps({'ok': True}))\n"
                "if __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tests/test_guarded_mutator.py",
                "from tools.guarded_mutator import main\n",
            )
            report = catalog(root)

        row = report["tools"][0]
        self.assertEqual(row["mutation_state"], "guarded")
        self.assertEqual(row["side_effects"], "repo_mutation_explicit")
        self.assertEqual(row["readiness"], "agent_ready")
        self.assertTrue(row["safe_for_agent"])
        self.assertFalse(row["automation_ready"])


if __name__ == "__main__":
    unittest.main()
