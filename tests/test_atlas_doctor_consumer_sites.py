from __future__ import annotations
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.atlas_doctor_lib.consumer_sites import inspect_consumer_sites

class DoctorConsumerSiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="doctor-consumers-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"app").mkdir()
        (self.root/"app/target.py").write_text("def helper(): return 1\n")
        (self.root/"app/caller.py").write_text(
            "from importlib import import_module\n"
            "x = import_module('app.target')\n"
            "signal.connect(target)\n"
            "y = getattr(registry, 'target')\n")
        subprocess.run(["git","init","-q"],cwd=self.root,check=True)
        subprocess.run(["git","add","-A"],cwd=self.root,check=True)

    def test_dynamic_and_qt_are_leads_not_proof_of_dead_code(self):
        with patch("tools.agent.reverse_impact_payload",return_value={
                "status":"REVIEW","confirmed_relationships":[]}):
            report=inspect_consumer_sites(self.root,"app/target.py")
        kinds={row["kind"] for row in report["dynamic_leads"]}
        self.assertEqual(kinds,{"LITERAL_IMPORT","QT_CONNECT_CANDIDATE","REFLECTIVE_CANDIDATE"})
        self.assertFalse(report["safe_to_delete"])
        self.assertFalse(report["dead_code_proven"])
        self.assertFalse(report["tests_executed"])

    def test_nonliteral_import_is_explicitly_unknown(self):
        (self.root/"app/caller.py").write_text("from importlib import import_module\n"
                                              "target = import_module(prefix + 'target')\n")
        with patch("tools.agent.reverse_impact_payload",return_value={
                "status":"PASS","confirmed_relationships":[]}):
            report=inspect_consumer_sites(self.root,"app/target.py")
        self.assertIn("DYNAMIC_IMPORT_UNRESOLVED",[x["kind"] for x in report["dynamic_leads"]])

    def test_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect_consumer_sites(self.root,"../outside.py")

if __name__=="__main__":
    unittest.main()
