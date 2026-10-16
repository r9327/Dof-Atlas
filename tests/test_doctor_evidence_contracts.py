from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.core import Issue
from tools.atlas_doctor_lib.audit import _validated_large_file_contracts
from tools.atlas_doctor_lib.consumer_sites import inspect_consumer_sites
from tools.atlas_doctor_lib.graph_audit import inspect_graph
from tools.tool_audit import _ui_scenario_routes, audit as audit_tools


class DoctorEvidenceContractsTests(unittest.TestCase):
    def test_same_rule_and_path_distinct_subjects_have_stable_ids(self):
        def issue(subject: str, evidence: str) -> Issue:
            return Issue(
                "invalid_large_file_contract", "git", "HIGH", "confirmed",
                "data/large_file_contracts.json", None, "Contract invalid",
                evidence, "fix", subject=subject,
            )
        a = issue("data/a.json", "sha256 invalid files[0]")
        b = issue("data/b.json", "sha256 invalid files[1]")
        self.assertNotEqual(a.id, b.id)
        self.assertEqual(a.id, issue("data/a.json", "new digest files[8]").id)
        self.assertEqual(a.to_dict()["subject"], "data/a.json")

    def test_large_contract_errors_name_stable_target_not_only_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rels = ("data/a.json", "data/b.json")
            for name in rels:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"{}\n")
            (root / "tools").mkdir()
            (root / "tools/gen.py").write_text("a.json b.json", encoding="utf-8")
            (root / "app").mkdir()
            (root / "app/client.py").write_text("a.json b.json", encoding="utf-8")
            rows = [
                {
                    "path": path, "role": "canonical_runtime_source",
                    "sha256": "0" * 64, "generator": "tools/gen.py",
                    "consumers": ["app/client.py"],
                } for path in rels
            ]
            (root / "data/large_file_contracts.json").write_text(
                json.dumps({"schema_version": 1, "files": rows}), encoding="utf-8"
            )
            _, errors = _validated_large_file_contracts(root)
            self.assertEqual(len(errors), 2)
            self.assertIn("target=data/a.json", errors[0])
            self.assertIn("target=data/b.json", errors[1])
            # Reordered entries retain stable subject names, not array positions.
            (root / "data/large_file_contracts.json").write_text(
                json.dumps({"schema_version": 1, "files": rows[::-1]}), encoding="utf-8"
            )
            _, reordered = _validated_large_file_contracts(root)
            self.assertEqual(
                {entry.split("target=", 1)[1].split(":", 1)[0] for entry in errors},
                {entry.split("target=", 1)[1].split(":", 1)[0] for entry in reordered},
            )

    def test_byte_contract_checks_lf_exactly_and_rejects_crlf_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "data/a.json"
            source.parent.mkdir(parents=True, exist_ok=True)
            literal = b'{\n  "a": 1\n}\n'
            source.write_bytes(literal)
            generator = root / "tools/gen.py"
            generator.parent.mkdir(parents=True)
            generator.write_text("a.json", encoding="utf-8")
            consumer = root / "app/client.py"
            consumer.parent.mkdir(parents=True)
            consumer.write_text("a.json", encoding="utf-8")
            (root / "data/large_file_contracts.json").write_text(
                json.dumps({"schema_version": 1, "files": [{
                    "path": "data/a.json", "role": "canonical_runtime_source",
                    "sha256": hashlib.sha256(literal).hexdigest(),
                    "generator": "tools/gen.py", "consumers": ["app/client.py"],
                }]}), encoding="utf-8",
            )
            _, errors = _validated_large_file_contracts(root)
            self.assertEqual(errors, [])
            # Same parsed JSON but different bytes is not a valid checksum.
            source.write_bytes(literal.replace(b"\n", b"\r\n"))
            _, errors = _validated_large_file_contracts(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("sha256 divergent", errors[0])

    def test_public_lazy_exports_are_static_only_not_runtime_use(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pack = root / "app/widgets"
            pack.mkdir(parents=True)
            (pack / "widget.py").write_text("class Widget: pass\n", encoding="utf-8")
            (pack / "__init__.py").write_text(
                "_LAZY_EXPORT_MODULES = {'Widget': 'widget', 'Alias': 'unrelated'}\n"
                "__all__ = ['Widget', 'Alias']\n"
                "def __getattr__(name): return None\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            with patch("tools.agent.reverse_impact_payload", return_value={
                "status": "PASS", "confirmed_relationships": []
            }):
                result = inspect_consumer_sites(root, "app/widgets/widget.py")
            self.assertEqual(result["public_lazy_export_count"], 1)
            self.assertEqual(result["public_lazy_exports"][0]["symbol"], "Widget")
            self.assertEqual(result["static_reference_kind"], "PUBLIC_LAZY_EXPORT")
            self.assertFalse(result["runtime_consumer_proven"])
            self.assertFalse(result["safe_to_delete"])
            (pack / "__init__.py").write_text(
                "_LAZY_EXPORT_MODULES = {'Widget': 'widget'}\n"
                "__all__ = ['Widget']\n", encoding="utf-8"
            )
            with patch("tools.agent.reverse_impact_payload", return_value={
                "status": "PASS", "confirmed_relationships": []
            }):
                missing = inspect_consumer_sites(root, "app/widgets/widget.py")
            self.assertEqual(missing["public_lazy_export_count"], 0)

    def test_pagination_exactly_covers_more_than_thirty_candidates(self):
        graph = {
            "nodes": [
                {"id": str(n), "source_file": f"app/views/f{n}.py",
                 "file_type": "code", "community": n}
                for n in range(85)
            ],
            "links": [],
        }
        first = inspect_graph(graph)
        self.assertEqual(first["limits"]["pagination"]["orphan_nodes"]["total"], 85)
        self.assertTrue(first["limits"]["pagination"]["orphan_nodes"]["truncated"])
        pages = [
            inspect_graph(graph, orphan_offset=offset)["orphan_nodes"]
            for offset in (0, 30, 60)
        ]
        combined = [node["id"] for page in pages for node in page]
        self.assertEqual(len(combined), 85)
        self.assertEqual(len(set(combined)), 85)
        full = inspect_graph(graph, page_limit=85)
        self.assertEqual(
            {node["id"] for node in full["orphan_nodes"]}, set(combined)
        )
        self.assertEqual(len(full["isolated_communities"]), 85)
        self.assertFalse(full["limits"]["pagination"]["isolated_communities"]["truncated"])

    def test_ui_scenario_router_is_registered_but_not_implicitly_run(self):
        root = Path(__file__).resolve().parents[1]
        contracts = _ui_scenario_routes(root)
        self.assertEqual(len(contracts), 4)
        self.assertTrue(all(x["observer_required"] for x in contracts.values()))
        report = audit_tools(root)
        for path, route in contracts.items():
            row = next(item for item in report["tools"] if item["path"] == path)
            self.assertEqual(row["ui_scenario_route"], route["scenario"])
            self.assertIn("tools/atlas_doctor.py", row["consumer_references"])
            self.assertIn("tests/test_atlas_doctor_capture_ui.py", row["contract_references"])
            self.assertNotIn(path, report["unreferenced_entrypoints"])
            self.assertFalse(row.get("safe_to_delete", False))


if __name__ == "__main__":
    unittest.main()
