"""An authorized full-pack import cannot silently install partial guides."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.import_ganymede_instruction_pack import examine_pack, install_pack


class GanymedePackImporterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.destination = self.root / "target"
        self.index = self.root / "index.json"
        self.index.write_text(json.dumps({
            "guides": [{
                "ganymede_guide_id": guide_id,
                "title": str(guide_id),
                "source_url": f"https://ganymede-app.com/guides/{guide_id}",
                "listed_step_count": 1,
            } for guide_id in (2203, 2205)]
        }), encoding="utf-8")

    def add_route(self, guide_id):
        self.source.joinpath(
            f"ganymede_{guide_id}_instructions.json",
        ).write_text(json.dumps({
            "schema_version": 1,
            "source_guide_id": guide_id,
            "source_url": f"https://ganymede-app.com/guides/{guide_id}",
            "expected_source_step_count": 1,
            "rights_basis": "atlas_original",
            "steps": [{
                "source_step_number": 1,
                "title": "Étape vérifiée",
                "instructions": "Consigne écrite et vérifiée par Atlas",
                "actions": [{
                    "kind": "talk", "text": "Interagir avec le PNJ vérifié",
                }],
            }],
        }, ensure_ascii=False), encoding="utf-8")

    def test_missing_route_blocks_install_without_touching_destination(self):
        self.add_route(2203)
        report = examine_pack(self.source, index_path=self.index, expected_routes=2)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["validated_steps"], 1)
        self.assertEqual(report["missing_files"], ["ganymede_2205_instructions.json"])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            install_pack(self.source, self.destination, index_path=self.index, expected_routes=2)
        self.assertFalse(self.destination.exists())

    def test_authorized_full_pack_installs_and_never_overwrites(self):
        self.add_route(2203)
        self.add_route(2205)
        report = examine_pack(self.source, index_path=self.index, expected_routes=2)
        self.assertEqual(report["status"], "PASS")
        result = install_pack(self.source, self.destination, index_path=self.index, expected_routes=2)
        self.assertEqual(result["installed_files"], 2)
        self.assertEqual(len(list(self.destination.glob("*_instructions.json"))), 2)
        with self.assertRaises(FileExistsError):
            install_pack(self.source, self.destination, index_path=self.index, expected_routes=2)

    def test_bad_route_or_extraneous_route_blocks_install(self):
        self.add_route(2203)
        self.add_route(2205)
        self.source.joinpath(
            "ganymede_2205_instructions.json",
        ).write_text("{}", encoding="utf-8")
        report = examine_pack(self.source, index_path=self.index, expected_routes=2)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual([r["source_id"] for r in report["invalid_routes"]], [2205])
        self.add_route(2205)
        self.add_route(9999)
        report = examine_pack(self.source, index_path=self.index, expected_routes=2)
        self.assertEqual(report["unexpected_files"], ["ganymede_9999_instructions.json"])
        self.assertEqual(report["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
