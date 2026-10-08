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

    def test_dynamic_import_without_literal_target_name_is_flagged(self):
        (self.root/'app/caller.py').write_text(
            "from importlib import import_module\n"
            "target = import_module(prefix + suffix)\n")
        with patch('tools.agent.reverse_impact_payload', return_value={
                'status': 'PASS', 'confirmed_relationships': []}):
            report = inspect_consumer_sites(self.root, 'app/target.py')
        self.assertIn('DYNAMIC_IMPORT_UNRESOLVED',
                      [item['kind'] for item in report['dynamic_leads']])
        self.assertTrue(report['candidate_scan_complete'])
    def test_importlib_alias_and_keyword_name_are_visible(self):
        (self.root / "app/caller.py").write_text(
            "from importlib import import_module as load\n"
            "a = load(prefix + suffix)\n"
            "b = load(name='app.' + 'target')\n"
        )
        with patch("tools.agent.reverse_impact_payload", return_value={
                "status": "PASS", "confirmed_relationships": []}):
            report = inspect_consumer_sites(self.root, "app/target.py")
        kinds = {item["kind"] for item in report["dynamic_leads"]}
        self.assertIn("DYNAMIC_IMPORT_UNRESOLVED", kinds)
        self.assertIn("LITERAL_IMPORT", kinds)
        self.assertFalse(report["safe_to_delete"])

    def test_exact_mentions_take_priority_over_generic_candidate_cap(self):
        for index in range(125):
            (self.root / "app" / f"aaa_{index:03d}.py").write_text(
                "from importlib import import_module\n"
                "load = import_module(variable)\n"
            )
        (self.root / "app" / "zzz_consumer.py").write_text(
            "from importlib import import_module\n"
            "load = import_module('app.target')\n"
        )
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        with patch("tools.agent.reverse_impact_payload", return_value={
                "status": "PASS", "confirmed_relationships": []}):
            report = inspect_consumer_sites(self.root, "app/target.py")
        self.assertTrue(report["truncated"])
        self.assertFalse(report["candidate_scan_complete"])
        self.assertIn("app/zzz_consumer.py", [
            row["source"] for row in report["dynamic_leads"]
            if row["kind"] == "LITERAL_IMPORT"
        ])
        self.assertFalse(report["dead_code_proven"])

    def test_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect_consumer_sites(self.root,"../outside.py")

if __name__=="__main__":
    unittest.main()
