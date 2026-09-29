from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.tool_catalog import catalog, select_tools


ROOT = Path(__file__).resolve().parents[1]


class ToolCatalogTests(unittest.TestCase):
    @staticmethod
    def _write(root: Path, relative: str, content: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_agent_ready_tool_is_machine_readable_and_tested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/sample.py",
                "import argparse, json\n"
                "def main():\n"
                "    p = argparse.ArgumentParser()\n"
                "    p.add_argument('--json', action='store_true')\n"
                "    print(json.dumps({'ok': True}))\n"
                "if __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tests/test_sample.py",
                "from tools.sample import main\n",
            )
            report = catalog(root)

        row = report["tools"][0]
        self.assertTrue(row["structured_output"])
        self.assertTrue(row["discoverable_help"])
        self.assertEqual(row["mutation_state"], "none")
        self.assertEqual(row["readiness"], "agent_ready")
        self.assertTrue(row["safe_for_agent"])
        self.assertTrue(row["automation_ready"])
        self.assertGreaterEqual(row["readiness_score"], 85)
        self.assertEqual(row["invocation"], "py -3.13 -m tools.sample")

    def test_unguarded_mutator_requires_review_before_agent_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/mutator.py",
                "import argparse, json\n"
                "from pathlib import Path\n"
                "def main():\n"
                "    argparse.ArgumentParser().parse_args()\n"
                "    Path('x').write_text('x')\n"
                "    print(json.dumps({'ok': True}))\n"
                "if __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tests/test_mutator.py",
                "from tools.mutator import main\n",
            )
            report = catalog(root)

        row = report["tools"][0]
        self.assertEqual(row["mutation_state"], "unguarded")
        self.assertEqual(row["readiness"], "review_before_agent_use")
        self.assertFalse(row["safe_for_agent"])
        self.assertFalse(row["automation_ready"])
        self.assertIn(
            "make_default_read_only_and_require_explicit_apply_flag",
            row["upgrade_actions"],
        )
        self.assertEqual(report["unguarded_mutator_count"], 1)

    def test_safe_and_ready_selection_filters_out_unsafe_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            safe_source = (
                "import argparse, json\n"
                "def main():\n"
                "    p = argparse.ArgumentParser()\n"
                "    p.add_argument('--json', action='store_true')\n"
                "    print(json.dumps({'ok': True}))\n"
                "if __name__ == '__main__': main()\n"
            )
            unsafe_source = (
                "import argparse, json\n"
                "from pathlib import Path\n"
                "def main():\n"
                "    p = argparse.ArgumentParser()\n"
                "    p.add_argument('--json', action='store_true')\n"
                "    Path('x').write_text('x')\n"
                "    print(json.dumps({'ok': True}))\n"
                "if __name__ == '__main__': main()\n"
            )
            self._write(root, "tools/safe_validation.py", safe_source)
            self._write(root, "tools/unsafe_validation.py", unsafe_source)
            self._write(
                root,
                "tests/test_safe_validation.py",
                "from tools.safe_validation import main\n",
            )
            self._write(
                root,
                "tests/test_unsafe_validation.py",
                "from tools.unsafe_validation import main\n",
            )
            report = catalog(root)
            safe_selection = select_tools(
                report,
                capability="validation",
                safe_only=True,
            )
            ready_selection = select_tools(
                report,
                capability="validation",
                ready_only=True,
            )

        safe_selected = {row["path"] for row in safe_selection["tools"]}
        ready_selected = {row["path"] for row in ready_selection["tools"]}
        self.assertIn("tools/safe_validation.py", safe_selected)
        self.assertNotIn("tools/unsafe_validation.py", safe_selected)
        self.assertEqual(ready_selected, {"tools/safe_validation.py"})
        self.assertTrue(safe_selection["read_only"])
        self.assertTrue(safe_selection["filters"]["safe_only"])
        self.assertTrue(ready_selection["filters"]["ready_only"])

    def test_versioned_wrapper_is_legacy_and_not_automation_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "tools/base.py", "def main(): return 0\n")
            for version in (1, 2):
                self._write(
                    root,
                    f"tools/sample_v{version}.py",
                    "from tools import base\n"
                    "if __name__ == '__main__':\n"
                    "    raise SystemExit(base.main())\n",
                )
            report = catalog(root)
            selection = select_tools(report, ready_only=True)

        rows = {row["path"]: row for row in report["tools"]}
        row = rows["tools/sample_v2.py"]
        self.assertIn("collapse_version_family_after_consumer_review", row["upgrade_actions"])
        self.assertIn("absorb_or_remove_thin_wrapper_after_contract_review", row["upgrade_actions"])
        self.assertEqual(row["canonicality"], "legacy")
        self.assertEqual(row["readiness"], "legacy_review")
        self.assertFalse(row["preferred_for_agent"])
        self.assertFalse(row["automation_ready"])
        self.assertNotIn(
            "tools/sample_v2.py",
            {item["path"] for item in selection["tools"]},
        )

    def test_repository_catalog_exposes_canonical_ai_entrypoints(self) -> None:
        report = catalog(ROOT)
        preferred = {row["path"] for row in report["preferred_entrypoints"]}
        self.assertEqual(report["schema_version"], 1)
        self.assertTrue(report["read_only"])
        self.assertIn("automation_ready_count", report)
        self.assertIn("tools/agent.py", preferred)
        self.assertIn("tools/ai_context.py", preferred)
        self.assertIn("tools/atlas_integrity.py", preferred)
        self.assertIn("tools/guide_integrity.py", preferred)
        self.assertIn("tools/tool_audit.py", preferred)
        self.assertIn("tools/tool_catalog.py", preferred)
        self.assertGreater(report["tool_count"], 50)


if __name__ == "__main__":
    unittest.main()
