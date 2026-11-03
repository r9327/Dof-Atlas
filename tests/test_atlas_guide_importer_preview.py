"""Read-only source creator: complete, partial, invalid and anti-mutation checks."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_shared_route_contract import GuideRouteContractError
from tools.atlas_guide_importer import main, prepare_preview


def valid_export() -> dict:
    return {
        "schema_version": 1,
        "rights_verified": True,
        "reference_verified": True,
        "complete": True,
        "guides": [{
            "guide_id": 1,
            "title": "Route exemple",
            "steps": [{
                "source_step_id": "first",
                "title": "Départ",
                "coordinates": [1, -2],
                "actions": [
                    {"action_id": "travel", "kind": "travel",
                     "text": "Aller à [1,-2]", "coordinates": [1, -2]},
                    {"action_id": "talk", "kind": "talk",
                     "text": "Parler au PNJ X", "npc": "PNJ X"},
                ],
            }],
        }],
    }


class GuideImporterPreviewTests(unittest.TestCase):
    def test_full_manifest_validates_counts_and_remains_uncertified(self):
        data = valid_export()
        prior = copy.deepcopy(data)
        actual = prepare_preview(data, expected_guides=1, expected_steps=1)
        self.assertEqual(data, prior)
        self.assertFalse(actual["certified"])
        self.assertEqual(actual["status"], "PREVIEW_ONLY_NOT_CERTIFIED")
        self.assertEqual(actual["mode"], "DRY_RUN_ONLY")
        self.assertEqual(actual["action_count"], 2)
        self.assertEqual(actual["routes"][0]["steps"][0]["manual_stage_id"], "source:1:first")

    def test_default_95_guides_7705_steps_blocks_incomplete_export(self):
        with self.assertRaisesRegex(GuideRouteContractError, "expected 95"):
            prepare_preview(valid_export())

    def test_full_step_mismatch_is_blocking(self):
        with self.assertRaisesRegex(GuideRouteContractError, "expected 2"):
            prepare_preview(valid_export(), expected_guides=1, expected_steps=2)

    def test_partial_requires_explicit_marking_and_no_completion_claim(self):
        data = valid_export()
        data["complete"] = False
        result = prepare_preview(data, partial=True)
        self.assertTrue(result["is_partial"])
        self.assertFalse(result["certified"])
        data["complete"] = True
        with self.assertRaisesRegex(GuideRouteContractError, "must not declare"):
            prepare_preview(data, partial=True)

    def test_same_guide_id_is_rejected(self):
        data = valid_export()
        data["guides"].append(copy.deepcopy(data["guides"][0]))
        with self.assertRaisesRegex(GuideRouteContractError, "duplicate"):
            prepare_preview(data, expected_guides=2, expected_steps=2)

    def test_unverified_rights_or_reference_is_blocking(self):
        for key in ("rights_verified", "reference_verified"):
            data = valid_export()
            data[key] = False
            with self.subTest(key=key), self.assertRaisesRegex(
                GuideRouteContractError, "rights evidence"
            ):
                prepare_preview(data, expected_guides=1, expected_steps=1)

    def test_invalid_source_content_rejected_by_shared_adapter(self):
        data = valid_export()
        data["guides"][0]["steps"][0]["actions"][0].pop("coordinates")
        data["guides"][0]["steps"][0].pop("coordinates")
        with self.assertRaisesRegex(GuideRouteContractError, "coordinates"):
            prepare_preview(data, expected_guides=1, expected_steps=1)

    def test_cli_no_output_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "authorized.json"
            data = valid_export()
            data["complete"] = False
            source.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(main([
                "--source", str(source), "--partial",
            ]), 0)
            self.assertEqual([p.name for p in Path(temporary).iterdir()], ["authorized.json"])

    def test_cli_creates_only_explicit_preview_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "authorized.json"
            output = root / "preview.json"
            data = valid_export()
            data["complete"] = False
            source.write_text(json.dumps(data), encoding="utf-8")
            args = [
                "--source", str(source), "--partial",
                "--output", str(output),
            ]
            self.assertEqual(main(args), 0)
            output_data = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(output_data["certified"])
            self.assertEqual(output_data["guide_count"], 1)
            with self.assertRaises(SystemExit) as raised:
                main(args)
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse((root / "installed_route.json").exists())

    def test_cli_refuses_duplicate_and_nonfinite_json_without_preview_write(self):
        for malformed in ("duplicate_root", "duplicate_action", "nan", "infinity", "overflow"):
            with self.subTest(malformed=malformed), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = root / "authorized.json"
                output = root / "preview.json"
                document = valid_export()
                document["complete"] = False
                raw = json.dumps(document)
                if malformed == "duplicate_root":
                    raw = raw.replace('"guides": ', '"guides": [], "guides": ', 1)
                elif malformed == "duplicate_action":
                    raw = raw.replace('"action_id": "talk"',
                                      '"action_id": "talk", "action_id": "shadow"', 1)
                elif malformed == "nan":
                    raw = raw.replace('"text": "Parler au PNJ X"',
                                      '"text": "Parler au PNJ X", "capture": NaN', 1)
                elif malformed == "infinity":
                    raw = raw.replace('"text": "Parler au PNJ X"',
                                      '"text": "Parler au PNJ X", "capture": Infinity', 1)
                else:
                    raw = raw.replace('"text": "Parler au PNJ X"',
                                      '"text": "Parler au PNJ X", "capture": 1e9999', 1)
                source.write_text(raw, encoding="utf-8")
                with self.assertRaises(SystemExit) as raised:
                    main(["--source", str(source), "--partial", "--output", str(output)])
                self.assertEqual(raised.exception.code, 2)
                self.assertFalse(output.exists())

    def test_cli_rejects_custom_full_inventory_counts(self):
        # The standalone CLI must never redefine "full" as 1/1. Internal
        # test/pipeline APIs may project a single synthetic guide.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "authorized.json"
            output = root / "preview.json"
            source.write_text(json.dumps(valid_export()), encoding="utf-8")
            with self.assertRaises(SystemExit) as raised:
                main([
                    "--source", str(source),
                    "--expected-guides", "1", "--expected-steps", "1",
                    "--output", str(output),
                ])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.exists())

    def test_cli_rejects_incomplete_manifest_without_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "authorized.json"
            output = root / "preview.json"
            source.write_text(json.dumps(valid_export()), encoding="utf-8")
            with self.assertRaises(SystemExit) as raised:
                main(["--source", str(source), "--output", str(output)])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.exists())

    def test_invalid_numeric_limits_fail_closed(self):
        for count in (0, -1, True, "95"):
            with self.subTest(count=count), self.assertRaises(GuideRouteContractError):
                prepare_preview(valid_export(), expected_guides=count)

    def test_symlinked_preview_output_is_rejected_without_external_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic.json"
            document = valid_export()
            document["complete"] = False
            source.write_text(json.dumps(document), encoding="utf-8")
            actual = root / "redirected.json"
            alias = root / "preview.json"
            try:
                alias.symlink_to(actual)
            except OSError:
                self.skipTest("Windows symlinks unavailable to this test user")
            with self.assertRaises(SystemExit) as raised:
                main(["--source", str(source), "--partial", "--output", str(alias)])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(actual.exists())
            self.assertTrue(alias.is_symlink())

    def test_symlinked_preview_parent_does_not_escape_selected_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic.json"
            document = valid_export()
            document["complete"] = False
            source.write_text(json.dumps(document), encoding="utf-8")
            outside = root / "outside"
            outside.mkdir()
            alias = root / "preview-alias"
            try:
                alias.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Windows directory symlinks unavailable to this test user")
            with self.assertRaises(SystemExit) as raised:
                main(["--source", str(source), "--partial",
                      "--output", str(alias / "preview.json")])
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(list(outside.iterdir()), [])

    def test_boolean_schema_version_never_counts_as_v1(self):
        data = valid_export()
        data["schema_version"] = True
        with self.assertRaisesRegex(GuideRouteContractError, "schema_version"):
            prepare_preview(data, expected_guides=1, expected_steps=1)

    def test_cli_rejects_case_variant_protected_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic.json"
            document = valid_export()
            document["complete"] = False
            source.write_text(json.dumps(document), encoding="utf-8")
            output = root / "DATA" / "preview.json"
            with self.assertRaises(SystemExit) as raised:
                main(["--source", str(source), "--partial", "--output", str(output)])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.parent.exists())


if __name__ == "__main__":
    unittest.main()
