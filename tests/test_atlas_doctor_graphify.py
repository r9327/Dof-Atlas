from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import agent, atlas_doctor, graphify
from tools.atlas_doctor_lib.architecture import architecture, graph_status, summarize_graph
from tools.atlas_doctor_lib.core import git_state
from tools.atlas_doctor_lib.report import build_ai_report


ROOT = Path(__file__).resolve().parents[1]


class GraphifyDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doctor-graph-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git("init")
        self.git("config", "user.name", "Atlas Tests")
        self.git("config", "user.email", "atlas-tests@example.invalid")
        (self.root / "main.py").write_text("print('ok')\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("graphify-out/\n.ai/runtime/\n", encoding="utf-8")
        (self.root / ".graphifyignore").write_text("graphify-out/\n.git/\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-m", "baseline")
        self.tool = {"status": "PASS", "executable": "graphify", "version": graphify.PINNED_VERSION}

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True).stdout.strip()

    def fixture(self, extra=False):
        # Field names and semantics captured from graphifyy==0.9.72 AST output.
        nodes = [
            {"id": "a", "label": "audit", "_origin": "ast", "community": 0,
             "source_file": "tools/a.py", "source_location": "L1", "file_type": "code"},
            {"id": "b", "label": "run", "_origin": "ast", "community": 0,
             "source_file": "tools/b.py", "source_location": "L1", "file_type": "code"},
            {"id": "c", "label": "isolated", "_origin": "ast", "community": 1,
             "source_file": "tools/c.py", "source_location": "L1", "file_type": "code"},
        ]
        if extra:
            nodes.append({"id": "d", "source_file": "tools/d.py", "community": 1})
        return {
            "directed": False, "multigraph": False, "graph": {}, "nodes": nodes,
            "links": [{"source": "a", "target": "b", "relation": "calls", "_origin": "ast",
                       "confidence": "EXTRACTED", "confidence_score": 1.0, "weight": 1.0}],
            "hyperedges": [], "built_at_commit": git_state(self.root)["head"],
        }

    def write_graph(self, extra=False):
        output = self.root / "graphify-out"
        output.mkdir(exist_ok=True)
        (output / "graph.json").write_text(json.dumps(self.fixture(extra)), encoding="utf-8")
        (output / "graph.html").write_text("<html><body>Graphify</body></html>", encoding="utf-8")
        (output / "GRAPH_REPORT.md").write_text("# Graph report\n", encoding="utf-8")

    def build(self, extra=False):
        def generate(root):
            self.assertEqual(root, self.root)
            self.write_graph(extra)
            return {"status": "PASS", "tool": self.tool}
        with patch.object(graphify, "detect", return_value=self.tool), patch.object(graphify, "build_graph", side_effect=generate) as build:
            payload = architecture(self.root, rebuild=True)
        self.assertEqual(build.call_count, 1)
        self.assertEqual(payload["status"], "PASS")
        return payload

    def test_detection_missing_wrong_and_pinned_versions(self):
        for executable, version, expected in [(None, None, "MISSING"), ("graphify", "0.9.71", "WRONG_VERSION"), ("graphify", "0.9.72", "PASS")]:
            with self.subTest(expected=expected), patch.object(graphify, "_tool_environment", return_value=(executable, version)):
                self.assertEqual(graphify.detect(self.root)["status"], expected)
        (self.root / ".graphifyignore").unlink()
        with patch.object(graphify, "_tool_environment", return_value=("graphify", "0.9.72")):
            self.assertEqual(graphify.detect(self.root)["status"], "INVALID_CONFIG")

    def test_uv_managed_tool_detection_uses_its_own_python_metadata(self):
        home = self.root / "uv-tools"
        binary = home / "graphifyy" / ("Scripts" if os.name == "nt" else "bin")
        binary.mkdir(parents=True)
        python = binary / ("python.exe" if os.name == "nt" else "python")
        executable = binary / ("graphify.exe" if os.name == "nt" else "graphify")
        python.touch()
        executable.touch()
        with patch.object(graphify.metadata, "version", side_effect=graphify.metadata.PackageNotFoundError("graphifyy")), patch.object(graphify.sysconfig, "get_path", return_value=str(self.root / "absent")), patch.object(graphify.shutil, "which", return_value="uv"), patch.object(graphify.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, str(home), ""),
            subprocess.CompletedProcess([], 0, graphify.PINNED_VERSION, ""),
        ]) as run:
            self.assertEqual(graphify._tool_environment(), (str(executable), graphify.PINNED_VERSION))
        self.assertEqual(run.call_args_list[1].args[0][0], str(python))

    def test_pinned_uv_install_takes_precedence_over_old_python_install(self):
        home = self.root / "uv-tools"
        binary = home / "graphifyy" / ("Scripts" if os.name == "nt" else "bin")
        binary.mkdir(parents=True)
        python = binary / ("python.exe" if os.name == "nt" else "python")
        executable = binary / ("graphify.exe" if os.name == "nt" else "graphify")
        python.touch()
        executable.touch()
        current = self.root / "python-scripts"
        current.mkdir()
        (current / executable.name).touch()
        with patch.object(graphify.metadata, "version", return_value="0.9.71"), patch.object(graphify.sysconfig, "get_path", return_value=str(current)), patch.object(graphify.shutil, "which", return_value="uv"), patch.object(graphify.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, str(home), ""),
            subprocess.CompletedProcess([], 0, graphify.PINNED_VERSION, ""),
        ]):
            self.assertEqual(graphify._tool_environment(), (str(executable), graphify.PINNED_VERSION))

    def test_build_uses_canonical_safe_sequence_and_no_hook(self):
        self.write_graph()
        with patch.object(graphify, "detect", return_value=self.tool), patch.object(graphify.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            result = graphify.build_graph(self.root)
        self.assertEqual(result["status"], "PASS")
        invoked = [call.args[0] for call in run.call_args_list]
        self.assertIn(["graphify", "extract", ".", "--code-only"], invoked)
        self.assertIn(["graphify", "cluster-only", ".", "--no-label"], invoked)
        self.assertIn(["graphify", "export", "html", "--graph", "graphify-out/graph.json"], invoked)
        self.assertFalse(any("hook" in command for command in invoked))
        self.assertTrue(all(call.kwargs.get("cwd") == self.root for call in run.call_args_list))

    def test_missing_tool_blocks_generation_without_installation(self):
        with patch.object(graphify, "detect", return_value={"status": "MISSING"}), patch.object(graphify.subprocess, "run") as run:
            self.assertEqual(graphify.build_graph(self.root)["status"], "BLOCKED")
        run.assert_not_called()

    def test_real_links_schema_summary_and_invalid_endpoints(self):
        summary = summarize_graph(self.fixture())
        self.assertEqual((summary["node_count"], summary["link_count"]), (3, 1))
        self.assertEqual(summary["relation_counts"], {"calls": 1})
        self.assertEqual(summary["confidence_counts"], {"EXTRACTED": 1})
        self.assertEqual(summary["connected_component_count"], 2)
        self.assertEqual(summary["isolated_node_count"], 1)
        self.assertEqual(summary["most_connected_files"][0], {"path": "tools/a.py", "neighbor_file_count": 1})
        self.assertEqual(summary["cycle_analysis"]["status"], "NOT_COMPUTED")
        graph = self.fixture()
        graph["links"][0]["target"] = "absent"
        with self.assertRaises(ValueError):
            summarize_graph(graph)
        with self.assertRaises(ValueError):
            summarize_graph({"nodes": [], "edges": []})

    def test_missing_unstamped_invalid_and_current_graphs(self):
        with patch.object(graphify, "detect", return_value=self.tool):
            self.assertEqual(graph_status(self.root)["status"], "MISSING")
            self.write_graph()
            self.assertEqual(graph_status(self.root)["status"], "STALE")
        self.build()
        (self.root / "graphify-out/graph.json").write_text("{broken", encoding="utf-8")
        with patch.object(graphify, "detect", return_value=self.tool):
            self.assertEqual(graph_status(self.root)["status"], "INVALID")

    def test_abbreviated_graphify_commit_resolves_to_exact_head(self):
        self.build()
        path = self.root / "graphify-out/graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["built_at_commit"] = graph["built_at_commit"][:8]
        path.write_text(json.dumps(graph), encoding="utf-8")
        # Restamp via the canonical generation flow, not by changing fingerprints.
        with patch.object(graphify, "detect", return_value=self.tool), patch.object(graphify, "build_graph", return_value={"status": "PASS"}):
            self.assertEqual(architecture(self.root, rebuild=True)["status"], "PASS")
        graph["built_at_commit"] = "f" * 40
        path.write_text(json.dumps(graph), encoding="utf-8")
        with patch.object(graphify, "detect", return_value=self.tool):
            self.assertEqual(graph_status(self.root)["status"], "STALE")

    def test_cache_invalidates_for_content_changes_and_new_head(self):
        self.build()
        target = self.root / "main.py"
        for text in ["print('first')\n", "print('second')\n"]:
            target.write_text(text, encoding="utf-8")
            with patch.object(graphify, "detect", return_value=self.tool):
                self.assertEqual(graph_status(self.root)["status"], "STALE")
            self.build()
        self.git("add", "main.py")
        self.git("commit", "-m", "new HEAD")
        with patch.object(graphify, "detect", return_value=self.tool):
            self.assertEqual(graph_status(self.root)["status"], "STALE")

    def test_graph_signature_html_and_ignored_output(self):
        self.build()
        self.assertEqual(self.git("ls-files", "--", "graphify-out", ".ai/runtime"), "")
        self.assertEqual(self.git("status", "--short"), "")
        self.write_graph(extra=True)
        with patch.object(graphify, "detect", return_value=self.tool):
            self.assertEqual(graph_status(self.root)["status"], "STALE")
        self.build()
        (self.root / "graphify-out/graph.html").write_text("broken", encoding="utf-8")
        with patch.object(graphify, "detect", return_value=self.tool):
            self.assertEqual(graph_status(self.root)["status"], "INVALID")

    def test_quick_never_builds_or_detects_graphify(self):
        with patch.object(graphify, "build_graph", side_effect=AssertionError("unexpected scan")), patch.object(graphify, "detect", side_effect=AssertionError("unexpected probe")):
            result = atlas_doctor.command_quick(self.root, argparse.Namespace(json=True))
        self.assertIn("summary", result)

    def test_agent_report_contains_current_architecture_and_snapshot_delta(self):
        self.build()
        second = self.build(extra=True)
        self.assertEqual(second["count_delta"], {"node_count": 1, "link_count": 0})
        with patch.object(graphify, "detect", return_value=self.tool):
            report = build_ai_report(self.root)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["architecture"]["status"], "PASS")
        self.assertEqual(report["architecture"]["summary"]["node_count"], 4)

    def test_structural_agent_plan_requires_graph_without_building(self):
        for structural in (False, True):
            with self.subTest(structural=structural), patch.object(agent, "impact_payload", return_value={}), patch.object(agent.agent_planner, "build_plan", return_value={"status": "READY", "automation_safe": True}), patch("tools.atlas_doctor_lib.architecture.graph_status", return_value={"status": "MISSING"}) as status, contextlib.redirect_stdout(io.StringIO()) as output:
                args = ["plan", "tools/a.py", "--json"] + (["--structural"] if structural else [])
                self.assertEqual(agent.main(args), 0)
                payload = json.loads(output.getvalue())
            self.assertEqual(status.call_count, int(structural))
            self.assertEqual(payload["architecture_preflight"]["required"], structural)
            self.assertEqual(payload["automation_safe"], not structural)
            if structural:
                self.assertEqual(payload["policy"]["automatic_editing"], "requires_human_or_agent_review")

    def test_module_direct_script_cli_and_windows_wrappers(self):
        for command in [
            [sys.executable, "-m", "tools.atlas_doctor", "graph", "--help"],
            [sys.executable, str(ROOT / "tools/atlas_doctor.py"), "graph", "--help"],
        ]:
            result = subprocess.run(command, cwd=ROOT if "-m" in command else self.root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--rebuild", result.stdout)
            self.assertIn("--install", result.stdout)
        result = subprocess.run([sys.executable, "-m", "tools.atlas_doctor", "graph", "--json"], cwd=ROOT, capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1))
        self.assertEqual(json.loads(result.stdout)["schema_version"], 1)
        bat = (ROOT / "scripts" / "windows" / "Atlas_Doctor.bat").read_text(encoding="utf-8")
        self.assertIn("cd /d", bat)
        self.assertIn("-m tools.atlas_doctor %*", bat)
        wrapper = (ROOT / "tools/graphify.ps1").read_text(encoding="utf-8")
        self.assertIn("-m tools.graphify install", wrapper)
        self.assertIn('"tools.atlas_doctor", "graph", "--rebuild"', wrapper)
        self.assertNotIn("hook install", wrapper)


if __name__ == "__main__":
    unittest.main()
