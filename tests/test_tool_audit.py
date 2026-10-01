from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.tool_audit import audit


ROOT = Path(__file__).resolve().parents[1]


class ToolAuditTests(unittest.TestCase):
    @staticmethod
    def _write(root: Path, relative: str, content: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_utf8_bom_python_is_not_reported_as_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "tools/bom_tool.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "def main(): return 0\nif __name__ == '__main__': main()\n",
                encoding="utf-8-sig",
            )
            report = audit(root)

        self.assertEqual(report["parse_error_count"], 0)
        self.assertNotIn("tools/bom_tool.py", report["parse_errors"])

    def test_from_tools_import_is_classified_as_consumer_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/sample.py",
                "def main(): return 0\nif __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tests/test_sample.py",
                "from tools import sample\n",
            )
            report = audit(root)

        row = next(row for row in report["tools"] if row["path"] == "tools/sample.py")
        self.assertEqual(row["import_references"], ["tests/test_sample.py"])
        self.assertEqual(row["consumer_references"], ["tests/test_sample.py"])
        self.assertEqual(row["test_consumer_references"], ["tests/test_sample.py"])
        self.assertEqual(row["text_references"], [])
        self.assertNotIn("tools/sample.py", report["unreferenced_entrypoints"])

    def test_plain_text_mention_is_not_a_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/sample.py",
                "def main(): return 0\nif __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tests/test_source_contract.py",
                "EXPECTED = 'tools/sample.py'\n",
            )
            report = audit(root)

        row = next(row for row in report["tools"] if row["path"] == "tools/sample.py")
        self.assertEqual(row["references"], ["tests/test_source_contract.py"])
        self.assertEqual(row["text_references"], ["tests/test_source_contract.py"])
        self.assertEqual(row["consumer_references"], [])
        self.assertEqual(row["test_references"], ["tests/test_source_contract.py"])
        self.assertEqual(row["test_consumer_references"], [])
        self.assertIn("tools/sample.py", report["unreferenced_entrypoints"])

    def test_powershell_python_file_invocation_is_a_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/sample.py",
                "def main(): return 0\nif __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tools/run.ps1",
                "py -3.13 -u .\\tools\\sample.py --strict\n",
            )
            report = audit(root)

        row = next(row for row in report["tools"] if row["path"] == "tools/sample.py")
        self.assertEqual(row["invocation_references"], ["tools/run.ps1"])
        self.assertEqual(row["consumer_references"], ["tools/run.ps1"])
        self.assertEqual(row["text_references"], [])

    def test_powershell_module_helper_invocation_is_a_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/sample.py",
                "def main(): return 0\nif __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tools/run.ps1",
                'Invoke-PythonCheck "sample" @("-m", "tools.sample", "--strict")\n',
            )
            report = audit(root)

        row = next(row for row in report["tools"] if row["path"] == "tools/sample.py")
        self.assertEqual(row["invocation_references"], ["tools/run.ps1"])
        self.assertEqual(row["consumer_references"], ["tools/run.ps1"])

    def test_python_subprocess_literal_invocation_is_a_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/sample.py",
                "def main(): return 0\nif __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tools/caller.py",
                "import subprocess\n"
                "subprocess.run(['python', '-m', 'tools.sample', '--json'])\n",
            )
            report = audit(root)

        row = next(row for row in report["tools"] if row["path"] == "tools/sample.py")
        self.assertEqual(row["invocation_references"], ["tools/caller.py"])
        self.assertEqual(row["consumer_references"], ["tools/caller.py"])

    def test_versioned_family_and_test_reference_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/sample_v1.py",
                "def main(): return 0\nif __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tools/sample_v2.py",
                "def main(): return 0\nif __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tests/test_sample.py",
                "from tools.sample_v2 import main\n",
            )
            report = audit(root)

        self.assertEqual(report["versioned_family_count"], 1)
        family = report["versioned_families"][0]
        self.assertEqual(family["versions"], [1, 2])
        row = next(
            row
            for row in report["tools"]
            if row["path"] == "tools/sample_v2.py"
        )
        self.assertEqual(row["test_references"], ["tests/test_sample.py"])
        self.assertEqual(row["consumer_references"], ["tests/test_sample.py"])

    def test_wrapper_path_hack_and_cwd_dependency_are_inventory_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "tools/base.py", "def main(): return 0\n")
            self._write(
                root,
                "tools/wrapper.py",
                "from tools import base\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(base.main())\n",
            )
            self._write(
                root,
                "tools/legacy.py",
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path.cwd()))\n"
                "def main(): return 0\n"
                "if __name__ == '__main__': main()\n",
            )
            report = audit(root)

        self.assertIn("tools/wrapper.py", report["wrappers"])
        self.assertIn("tools/legacy.py", report["path_hacks"])
        self.assertIn("tools/legacy.py", report["cwd_dependencies"])
        self.assertFalse(report["blocking"])

    def test_path_hack_detector_ignores_its_own_rule_literals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/detector.py",
                "FORBIDDEN = {'sys.path.insert', 'sys.path.append'}\n",
            )
            report = audit(root)

        self.assertNotIn("tools/detector.py", report["path_hacks"])

    def test_mutation_capability_distinguishes_explicit_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/unsafe.py",
                "from pathlib import Path\n"
                "def main(): Path('x').write_text('x')\n"
                "if __name__ == '__main__': main()\n",
            )
            self._write(
                root,
                "tools/gated.py",
                "import argparse\n"
                "from pathlib import Path\n"
                "def main():\n"
                "    parser = argparse.ArgumentParser()\n"
                "    parser.add_argument('--apply', action='store_true')\n"
                "    Path('x').write_text('x')\n"
                "if __name__ == '__main__': main()\n",
            )
            report = audit(root)

        self.assertIn("tools/unsafe.py", report["mutation_without_gate"])
        self.assertNotIn("tools/gated.py", report["mutation_without_gate"])
        self.assertIn("tools/gated.py", report["mutation_capable"])

    def test_zero_consumer_reference_is_only_a_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(
                root,
                "tools/manual.py",
                "def main(): return 0\nif __name__ == '__main__': main()\n",
            )
            report = audit(root)

        row = report["tools"][0]
        self.assertEqual(row["recommendation"], "review_unconsumed_entrypoint")
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertFalse(report["blocking"])
        self.assertIn("not standalone proof", report["note"])

    def test_repository_inventory_covers_current_canonical_tooling(self) -> None:
        report = audit(ROOT)
        paths = {row["path"] for row in report["tools"]}
        self.assertGreater(report["tool_count"], 50)
        self.assertIn("tools/agent.py", paths)
        self.assertIn("tools/atlas_integrity.py", paths)
        self.assertIn("tools/guide_integrity.py", paths)
        self.assertIn("tools/tool_audit.py", paths)
        self.assertEqual(report["parse_error_count"], len(report["parse_errors"]))
        self.assertNotIn("tools/tool_audit.py", report["parse_errors"])
        self.assertFalse(report["blocking"])


if __name__ == "__main__":
    unittest.main()
