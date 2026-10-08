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

    def test_communities_can_be_paged_beyond_first_30(self):
        from tools.atlas_doctor_lib.graph_audit import inspect_graph
        graph={"nodes":[{"id":str(i),"source_file":f"app/feature_{i}.py",
                         "file_type":"code","community":i}
                         for i in range(37)],"links":[]}
        first=inspect_graph(graph,community_offset=0)
        second=inspect_graph(graph,community_offset=30)
        self.assertEqual(len(first["isolated_communities"]),30)
        self.assertEqual(len(second["isolated_communities"]),7)
        self.assertEqual(second["limits"]["community_total"],37)
        self.assertEqual(second["limits"]["unreported_communities"],0)


    def test_orphan_nodes_and_triage_page_beyond_first_30(self):
        import hashlib
        from tools.atlas_doctor_lib.graph_audit import inspect_graph
        graph = {"nodes": [{"id": str(i), "source_file": f"app/orphan_{i:02d}.py",
                            "file_type": "code", "community": i} for i in range(37)],
                 "links": []}
        first = inspect_graph(graph, orphan_offset=0)
        second = inspect_graph(graph, orphan_offset=30)
        self.assertEqual(len(first["orphan_nodes"]), 30)
        self.assertEqual(len(second["orphan_nodes"]), 7)
        self.assertEqual(second["limits"]["orphan_total"], 37)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "graph.json"
            output.write_text(json.dumps(graph), encoding="utf-8")
            signature = hashlib.sha256(output.read_bytes()).hexdigest()
            evidence = {"status": "PASS", "graph": str(output),
                        "graph_signature": signature}
            review = {"static_confirmed_count": 0, "dynamic_lead_count": 0,
                      "candidate_files": 0, "truncated": False, "source_errors": []}
            rows = []
            cursor = 0
            with (patch("tools.atlas_doctor_lib.architecture.graph_status", return_value=evidence),
                 patch("tools.atlas_doctor_lib.consumer_sites.inspect_consumer_sites", return_value=review)):
                while True:
                    page = triage_isolates(root, kind="orphan", limit=10, offset=cursor)
                    rows.extend(row["file"] for row in page["findings"])
                    if page["next_offset"] is None:
                        break
                    self.assertGreater(page["next_offset"], cursor)
                    cursor = page["next_offset"]
            self.assertEqual(len(rows), 37)
            self.assertEqual(len(set(rows)), 37)
            self.assertFalse(page["dead_code_proven"])

    def test_community_island_does_not_imply_file_isolation(self):
        from tools.atlas_doctor_lib.graph_audit import inspect_graph
        graph = {"nodes": [
            {"id": "a", "source_file": "app/widget.py", "file_type": "code", "community": 0},
            {"id": "b", "source_file": "app/widget.py", "file_type": "code", "community": 1},
            {"id": "c", "source_file": "app/caller.py", "file_type": "code", "community": 1},
        ], "links": [{"source": "b", "target": "c", "relation": "imports", "confidence": "EXTRACTED"}]}
        report = inspect_graph(graph)
        island = next(row for row in report["isolated_communities"] if row["community"] == 0)
        self.assertEqual(island["production_files_linked_elsewhere"], 1)
        self.assertEqual(island["sample_linked_production_files"], ["app/widget.py"])
        self.assertEqual(island["classification"], "ISOLATED_SUBCOMMUNITY_IN_CONNECTED_FILES")
        self.assertFalse(island["whole_files_proven_unreachable"])

    def test_scan_budget_rejects_excessive_work(self):
        with self.assertRaises(ValueError):
            triage_isolates(Path("."),limit=100)

if __name__=="__main__":
    unittest.main()
