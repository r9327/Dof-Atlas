from __future__ import annotations
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.atlas_doctor_lib.file_coverage import file_coverage

class FileCoverageTests(unittest.TestCase):
    def test_gaps_are_reported_without_claiming_dead_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git","init","-q"],cwd=root,check=True)
            for name in ("app/a.py","app/b.py"):
                p=root/name;p.parent.mkdir(exist_ok=True);p.write_text("pass\n")
            subprocess.run(["git","add","-A"],cwd=root,check=True)
            graph=root/"graph.json"
            graph.write_text(json.dumps({"nodes":[{"id":1,"source_file":"app/a.py"}]}))
            with patch("tools.atlas_doctor_lib.architecture.graph_status",return_value={
                    "status":"PASS","graph":str(graph)}):
                report=file_coverage(root)
            self.assertEqual(report["tracked_python_files"],2)
            self.assertEqual(report["unrepresented_files"],1)
            self.assertEqual(report["status"],"REVIEW")
            self.assertFalse(report["dead_code_proven"])
            self.assertFalse(report["runtime_coverage_proven"])

    def test_stale_never_counts_as_current(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            subprocess.run(["git","init","-q"],cwd=root,check=True)
            (root/"a.py").write_text("pass\n")
            subprocess.run(["git","add","-A"],cwd=root,check=True)
            graph=root/"graph.json"
            graph.write_text(json.dumps({"nodes":[{"id":1,"source_file":"a.py"}]}))
            with patch("tools.atlas_doctor_lib.architecture.graph_status",
                       return_value={"status":"STALE","graph":str(graph)}):
                report=file_coverage(root)
            self.assertEqual(report["coverage_percent"],100.0)
            self.assertEqual(report["status"],"REVIEW")

if __name__=="__main__":
    unittest.main()
