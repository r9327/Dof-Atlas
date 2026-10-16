from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools.atlas_json_raw import audit_raw_inputs, verify_raw_inputs
from scripts.windows.quest_assets import RELATIVE_ROOT
from tools.atlas_json_inventory import main


SHA = "a" * 40


class PublicRawInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.quest = {"source_repo": "dofusdude/dofus3-main", "tag": "3.7.10.10", "assets": {}}
        self.craft = {"schema_version": 1, **deepcopy(self.quest)}
        self.rows = {
            "quests": [{"id": 1, "categoryId": 2, "stepIds": {"Array": [3]}}],
            "quest_categories": [{"id": 2}],
            "quest_steps": [{"id": 3, "questId": 1, "objectiveIds": {"Array": [4]}}],
            "quest_objectives": [{"id": 4, "stepId": 3}],
            "achievements": [{"id": 5, "categoryId": 7, "objectiveIds": {"Array": [6]}}],
            "achievement_objectives": [{"id": 6, "achievementId": 5}],
            "achievement_categories": [{"id": 7}],
            "jobs": [{"id": 8}],
            "items": [{"id": 10}, {"id": 20}],
            "recipes": [{"resultId": 10, "jobId": 8, "ingredientIds": {"Array": [20]},
                         "quantities": {"Array": [2]}}],
        }
        for name, rows in self.rows.items():
            self.write(name + ".json", {"references": {"RefIds": [
                {"type": {"class": "TestData"}, "data": row} for row in rows]}})
        self.write("languages/fr.json", {"entries": {"1": "Public"}})
        patcher = patch("tools.atlas_json_raw.read_lock", return_value=self.quest)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, data):
        path = self.root / RELATIVE_ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data).encode()
        path.write_bytes(content)
        pin = {"asset": path.name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        lock = self.craft if name == "recipes.json" else self.quest
        lock["assets"][name] = pin
        craft_path = self.root / "scripts/windows/craft_assets_lock.json"
        craft_path.parent.mkdir(parents=True, exist_ok=True)
        craft_path.write_text(json.dumps(self.craft))

    def test_complete_public_sources_have_separate_code_and_dataset_identities(self):
        report = audit_raw_inputs(self.root, SHA)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["relation_status"], "PASS")
        self.assertEqual(len(report["files"]), 11)
        self.assertEqual(report["candidate_sha"], SHA)
        self.assertEqual(len(report["dataset_fingerprint"]), 64)
        verify_raw_inputs(report, audit_raw_inputs(self.root, SHA))
        other = audit_raw_inputs(self.root, "b" * 40)
        self.assertEqual(other["dataset_fingerprint"], report["dataset_fingerprint"])
        with self.assertRaisesRegex(ValueError, "changed during"):
            verify_raw_inputs(report, other)

    def test_same_size_tamper_cannot_pass_the_release_pin(self):
        before = audit_raw_inputs(self.root, SHA)
        path = self.root / RELATIVE_ROOT / "recipes.json"
        original = path.read_bytes()
        path.write_bytes(original.replace(b"[2]", b"[3]"))
        self.assertEqual(path.stat().st_size, len(original))
        after = audit_raw_inputs(self.root, SHA)
        self.assertEqual(after["status"], "BLOCKED")
        with self.assertRaises(ValueError):
            verify_raw_inputs(before, after)

    def test_a_different_reviewed_dataset_still_invalidates_the_running_snapshot(self):
        before = audit_raw_inputs(self.root, SHA)
        self.write("languages/fr.json", {"entries": {"1": "Changed"}})
        after = audit_raw_inputs(self.root, SHA)
        self.assertEqual(after["status"], "PASS")
        with self.assertRaisesRegex(ValueError, "changed during"):
            verify_raw_inputs(before, after)

    def test_missing_source_and_malformed_json_stay_blocked(self):
        (self.root / RELATIVE_ROOT / "quests.json").unlink()
        self.assertEqual(audit_raw_inputs(self.root, SHA)["status"], "BLOCKED")
        self.write("quests.json", [])
        self.assertEqual(audit_raw_inputs(self.root, SHA)["status"], "BLOCKED")

    def test_unresolved_foreign_key_is_review_and_preserves_the_exact_ids(self):
        self.rows["quest_objectives"][0]["stepId"] = 999
        self.write("quest_objectives.json", {"references": {"RefIds": [
            {"data": self.rows["quest_objectives"][0]}]}})
        report = audit_raw_inputs(self.root, SHA)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["relation_status"], "REVIEW")
        row = next(r for r in report["relations"] if r["relation"] == "quest_objectives.stepId")
        self.assertEqual(row["missing"], [{"source_id": 4, "target_id": 999}])

    def test_private_files_are_not_read_or_named_and_symlinks_are_refused(self):
        private = self.root / "config/private_character.json"
        private.parent.mkdir()
        private.write_text("SECRET_PLAYER_STATE")
        report = audit_raw_inputs(self.root, SHA)
        self.assertNotIn("SECRET_PLAYER_STATE", json.dumps(report))
        self.assertNotIn("private_character", json.dumps(report))
        path = self.root / RELATIVE_ROOT / "recipes.json"
        original = path.read_bytes()
        path.unlink()
        private.write_bytes(original)
        path.symlink_to(private)
        self.assertEqual(audit_raw_inputs(self.root, SHA)["status"], "BLOCKED")

    def test_forged_fingerprint_and_inconsistent_locks_are_rejected(self):
        before = audit_raw_inputs(self.root, SHA)
        forged = deepcopy(before)
        forged["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            verify_raw_inputs(forged, before)
        self.craft["tag"] = "another-release"
        (self.root / "scripts/windows/craft_assets_lock.json").write_text(json.dumps(self.craft))
        self.assertEqual(audit_raw_inputs(self.root, SHA)["status"], "BLOCKED")

    def test_cli_records_drift_as_a_failing_report(self):
        before = self.root / "before.json"
        before.write_text(json.dumps(audit_raw_inputs(self.root, SHA)))
        self.write("languages/fr.json", {"entries": {"1": "Changed"}})
        output = self.root / "after.json"
        arguments = ["inventory", "--root", str(self.root), "--raw-inputs", "--candidate-sha", SHA,
                     "--verify-against", str(before), "--output", str(output)]
        with patch("sys.argv", arguments), patch("tools.atlas_json_inventory.subprocess.run",
                                                 return_value=SimpleNamespace(stdout=SHA)):
            self.assertEqual(main(), 1)
        report = json.loads(output.read_text())
        self.assertEqual(report["status"], "BLOCKED")
        self.assertNotIn("unchanged_during_validation", report)

    def test_cli_rejects_wrong_code_sha_before_recording_evidence(self):
        output = self.root / "wrong.json"
        arguments = ["inventory", "--root", str(self.root), "--raw-inputs", "--candidate-sha", "b" * 40,
                     "--output", str(output)]
        with patch("sys.argv", arguments), patch("tools.atlas_json_inventory.subprocess.run",
                                                 return_value=SimpleNamespace(stdout=SHA)):
            with self.assertRaises(SystemExit) as exc:
                main()
        self.assertEqual(exc.exception.code, 2)
        self.assertFalse(output.exists())
