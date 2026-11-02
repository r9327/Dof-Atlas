"""Focused tests for the PR337-coupled, offline Atlas Guide Importer."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.atlas_guide_importer import _step_hash, run_pipeline
from tools.import_ganymede_authored_routes import main as legacy_import_main


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class GuideImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "incoming"
        self.target = self.root / "atlas"
        self.source.mkdir()
        self.index = self.root / "index.json"
        self.index.write_text(json.dumps({"guides": [
            {"ganymede_guide_id": gid, "title": f"Guide {gid}",
             "source_url": f"https://ganymede-app.com/guides/{gid}",
             "listed_step_count": 2}
            for gid in (2203, 2205)
        ]}), encoding="utf-8")
        self.manifest = self.root / "reference.json"

    def write_guide(self, gid: int, *, copy_values: list[str] | None = None,
                    items: list[dict] | None = None) -> dict:
        steps = [
            {"source_step_number": 1, "title": "Départ",
             "instructions": "Rejoindre le point de départ.",
             "actions": [{"kind": "travel", "text": "Au village",
                          "coordinates": [-3, 4]}]},
            {"source_step_number": 2, "title": "PNJ",
             "instructions": "Rencontrer le PNJ et suivre les étapes.",
             "actions": [{"kind": "talk", "text": "Voir le personnage"},
                         {"kind": "fight", "text": "Combattre le monstre"}]},
        ]
        if copy_values:
            steps[1]["actions"][0]["copy_values"] = copy_values
        if items:
            steps[1]["actions"][0]["items"] = items
        payload = {
            "schema_version": 1, "source_guide_id": gid,
            "source_url": f"https://ganymede-app.com/guides/{gid}",
            "expected_source_step_count": 2,
            "rights_basis": "atlas_original",
            "steps": steps,
        }
        file = self.source / f"ganymede_{gid}_instructions.json"
        file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def write_reference(self, gids: tuple[int, ...]) -> None:
        references = []
        for gid in gids:
            file = self.source / f"ganymede_{gid}_instructions.json"
            contents = file.read_bytes()
            doc = json.loads(contents)
            references.append({
                "source_guide_id": gid, "source_url": doc["source_url"],
                "file_sha256": digest(contents),
                "step_sha256": [_step_hash(s) for s in doc["steps"]],
            })
        self.manifest.write_text(json.dumps(
            {"schema_version": 1, "guides": references},
        ), encoding="utf-8")

    def run_import(self, **options):
        return run_pipeline(self.source, index_path=self.index, target_dir=self.target,
                            expected_routes=2, **options)

    def test_no_reference_is_read_only_and_not_verified(self):
        self.write_guide(2203)
        self.write_guide(2205)
        result = self.run_import()
        self.assertEqual(result["status"], "REFERENCE_REQUIRED")
        self.assertFalse(result["source_parity_certified"])
        self.assertFalse(result["gameplay_certified"])
        self.assertEqual(result["validated_actions"], 6)
        self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(ValueError, "reference required"):
            self.run_import(apply=True)
        self.assertFalse(self.target.exists())

    def test_matching_hashes_cannot_authorize_publication(self):
        self.write_guide(2203)
        self.write_guide(2205)
        self.write_reference((2203, 2205))
        preview = self.run_import(manifest_path=self.manifest)
        self.assertEqual(preview["status"], "PREFLIGHT_PASS")
        self.assertEqual(preview["validated_steps"], 4)
        self.assertEqual(preview["validated_actions"], 6)
        self.assertFalse(preview["source_parity_certified"])
        self.assertFalse(preview["rights_verified"])
        self.assertFalse(preview["gameplay_certified"])
        self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(ValueError, "independent source parity"):
            self.run_import(manifest_path=self.manifest, apply=True)
        self.assertFalse(self.target.exists())

    def test_payload_change_after_manifest_is_rejected_before_write(self):
        self.write_guide(2203)
        self.write_guide(2205)
        self.write_reference((2203, 2205))
        p = self.source / "ganymede_2205_instructions.json"
        p.write_text(p.read_text(encoding="utf-8").replace(
            "Voir le personnage", "Voir une autre personne",
        ), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "reference mismatch"):
            self.run_import(manifest_path=self.manifest, apply=True)
        self.assertFalse(self.target.exists())

    def test_missing_and_extra_reference_ids_block_publication(self):
        self.write_guide(2203)
        self.write_guide(2205)
        self.write_reference((2203,))
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            self.run_import(manifest_path=self.manifest, apply=True)
        self.assertFalse(self.target.exists())

    def test_broken_step_order_blocks_before_projection(self):
        self.write_guide(2203)
        self.write_guide(2205)
        self.write_reference((2203, 2205))
        p = self.source / "ganymede_2203_instructions.json"
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["steps"][1]["source_step_number"] = 3
        p.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_import(manifest_path=self.manifest, apply=True)
        self.assertFalse(self.target.exists())

    def test_explicit_copy_target_and_item_survive_canonical_bridge(self):
        self.write_guide(2203, copy_values=["Nom précis à copier"],
                         items=[{"name": "Ressource précise", "quantity": 2}])
        self.write_guide(2205)
        self.write_reference((2203, 2205))
        report = self.run_import(manifest_path=self.manifest)
        self.assertEqual(report["status"], "PREFLIGHT_PASS")
        route = next(r for r in report["routes"] if r["source_id"] == 2203)
        self.assertEqual(route["explicit_copy_targets_preserved"], 1)
        self.assertFalse(report["gameplay_certified"])

    def test_overwrite_does_not_bypass_certification(self):
        self.write_guide(2203)
        self.write_guide(2205)
        self.write_reference((2203, 2205))
        self.target.mkdir()
        path = self.target / "ganymede_2203_instructions.json"
        path.write_text("existing content must be preserved", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "independent source parity"):
            self.run_import(manifest_path=self.manifest, apply=True,
                            allow_overwrite=True)
        self.assertEqual(path.read_text(encoding="utf-8"),
                         "existing content must be preserved")

    def test_strict_full_inventory_and_explicit_partial_mode(self):
        self.write_guide(2203)
        self.write_reference((2203,))
        with self.assertRaisesRegex(ValueError, "Missing 1"):
            self.run_import(manifest_path=self.manifest, apply=True)
        preview = self.run_import(
            manifest_path=self.manifest, strict=False)
        self.assertEqual(preview["missing_routes"], [2205])
        with self.assertRaisesRegex(ValueError, "independent source parity"):
            self.run_import(manifest_path=self.manifest,
                            strict=False, apply=True)
        self.assertFalse(self.target.exists())


    def test_secondary_cli_cannot_bypass_publication_gate(self):
        self.write_guide(2203)
        output = io.StringIO()
        with patch("sys.argv", ["import_ganymede_authored_routes",
                                "--source-dir", str(self.source), "--apply"]):
            with redirect_stdout(output):
                exit_code = legacy_import_main()
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "BLOCKED")
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
