from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.atlas_doctor_lib.isolate_triage import triage_isolates

class IsolateTriageTests(unittest.TestCase):
    def test_stale_graph_does_not_authorize_source_review(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("tools.atlas_doctor_lib.architecture.graph_status",
                       return_value={"status":"STALE"}):
                result=triage_isolates(Path(d))
            self.assertEqual(result["status"],"BLOCKED")
            self.assertFalse(result["dead_code_proven"])

    def test_source_probe_bounded_and_never_authorizes_deletion(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/"graph.json"
            p.write_text(json.dumps({"nodes":[],"links":[]}))
            evidence={"status":"PASS","graph":str(p),
                      "graph_signature":hashlib.sha256(p.read_bytes()).hexdigest()}
            finding={"orphan_nodes":[
                        {"file":"app/a.py"},{"file":"app/b.py"},{"file":"tests/c.py"}],
                     "weak_production_candidates":[]}
            scan={"static_confirmed_count":1,"dynamic_lead_count":2,
                  "candidate_files":3,"truncated":False,"source_errors":[]}
            with patch("tools.atlas_doctor_lib.architecture.graph_status",return_value=evidence), \
                 patch("tools.atlas_doctor_lib.graph_audit.inspect_graph",return_value=finding), \
                 patch("tools.atlas_doctor_lib.consumer_sites.inspect_consumer_sites",return_value=scan) as checker:
                result=triage_isolates(root,limit=1)
            self.assertEqual(result["status"],"REVIEW")
            self.assertEqual(checker.call_count,1)
            self.assertTrue(result["truncated"])
            self.assertFalse(result["findings"][0]["safe_to_remove"])
            self.assertEqual(result["findings"][0]["review"],"HAS_SOURCE_IMPORT_CONSUMERS")

    def test_weak_candidates_can_be_paged_without_skipping(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            graph=root/"graph.json"
            graph.write_text(json.dumps({"nodes":[],"links":[]}))
            evidence={"status":"PASS","graph":str(graph),
                      "graph_signature":hashlib.sha256(graph.read_bytes()).hexdigest()}
            def fake_audit(graph, *, root=None, weak_offset=0):
                all_rows=[{"file":f"app/module_{i}.py"} for i in range(5)]
                return {"orphan_nodes":[],"isolated_communities":[],
                        "weak_production_candidates":all_rows[weak_offset:],
                        "limits":{"weak_total":5,"unreported_weak_nodes":0}}
            checked={"static_confirmed_count":0,"dynamic_lead_count":0,
                     "candidate_files":0,"truncated":False,"source_errors":[]}
            with patch("tools.atlas_doctor_lib.architecture.graph_status",return_value=evidence), \
                 patch("tools.atlas_doctor_lib.graph_audit.inspect_graph",side_effect=fake_audit), \
                 patch("tools.atlas_doctor_lib.consumer_sites.inspect_consumer_sites",return_value=checked):
                a=triage_isolates(root,kind="weak",offset=0,limit=2)
                b=triage_isolates(root,kind="weak",offset=a["next_offset"],limit=2)
                c=triage_isolates(root,kind="weak",offset=b["next_offset"],limit=2)
            self.assertEqual([e["file"] for page in (a,b,c) for e in page["findings"]],
                             [f"app/module_{i}.py" for i in range(5)])
            self.assertIsNone(c["next_offset"])
            self.assertFalse(any(e["safe_to_remove"] for e in a["findings"]))

    def test_scan_budget_rejects_excessive_work(self):
        with self.assertRaises(ValueError):
            triage_isolates(Path("."),limit=100)

if __name__=="__main__":
    unittest.main()
