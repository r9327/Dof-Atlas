from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import doctor_shadow_campaign
from tools.atlas_doctor_lib.certification_shadow import _actual_required_groups

HEAD = "b" * 40


def archived(*, verdict="PASS", sha=HEAD):
    groups = {}
    for name in _actual_required_groups():
        groups[name] = {"status": "PASS", "required": True, "commands": [],
                        "blockers": []}
    groups["FULL_SUITE"]["commands"] = [{"exit_code": 0, "tests": 2267}]
    groups["FULL_SUITE"]["tests"] = 2267
    return {
        "schema_version": 1, "mode": "FULL",
        "head": sha, "verdict": verdict,
        "duration_seconds": 4864.007,
        "validations_required": sorted(groups),
        "groups": groups, "blockers": [] if verdict == "PASS" else ["RUNTIME_FAILED"],
    }


def plan(*, sha=HEAD, scoped="SCOPED_TESTS_PASS"):
    return {
        "kind": "doctor_adaptive_certification_plan", "candidate_sha": sha,
        "plan_fingerprint": "test-plan",
        "status": "READY_TO_RUN_SCOPED",
        "execution": {"status": scoped},
    }


class ShadowCampaignTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_real_shape_archive_inspection_is_not_a_shadow_pass(self):
        f = self.save("archived.json", archived())
        result = doctor_shadow_campaign.campaign(inspect_full=[f])
        self.assertEqual(result["status"], "FULL_ARCHIVES_VALIDATED_ONLY")
        self.assertEqual(result["inspected_archives"], 1)
        self.assertEqual(result["shadow_pairs"], 0)
        self.assertFalse(result["records"][0]["shadow_comparison_performed"])
        self.assertEqual(result["records"][0]["observed_full_tests"], 2267)
        self.assertFalse(result["trusted_workflow_provenance"])
        self.assertFalse(result["safe_to_replace_full"])

    def test_same_sha_comparison_can_find_hidden_failures(self):
        p = self.save("plan.json", plan())
        f = archived(verdict="BLOCKED")
        f["groups"]["DATA_INTEGRITY"]["status"] = "BLOCKED"
        z = self.save("full.json", f)
        result = doctor_shadow_campaign.campaign(pairs=[[p, z]])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["false_negative_candidates"], 1)
        self.assertFalse(result["safe_to_replace_full"])

    def test_wrong_sha_is_invalid_even_when_both_are_green(self):
        p = self.save("plan.json", plan(sha="a" * 40))
        f = self.save("full.json", archived())
        outcome = doctor_shadow_campaign.campaign(pairs=[[p, f]])
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(outcome["invalid_evidence"], 1)

    def test_fake_two_group_full_does_not_pass_inspection(self):
        fake = archived()
        fake["validations_required"] = ["FULL_SUITE", "DATA_INTEGRITY"]
        f = self.save("fake.json", fake)
        self.assertEqual(doctor_shadow_campaign.campaign(
            inspect_full=[f]
        )["status"], "BLOCKED")

    def test_empty_and_excessive_cohort_rejected(self):
        with self.assertRaises(ValueError):
            doctor_shadow_campaign.campaign()
        with self.assertRaises(ValueError):
            doctor_shadow_campaign.campaign(inspect_full=[
                Path("f.json")] * 13)

    def test_invalid_plan_shape_is_rejected(self):
        p = self.save("plan.json", {"candidate_sha": HEAD})
        f = self.save("full.json", archived())
        with self.assertRaises(ValueError):
            doctor_shadow_campaign.campaign(pairs=[[p, f]])

    def test_cli_can_inspect_archives_without_running_full(self):
        f = self.save("archive.json", archived())
        out = self.root / "report.json"
        self.assertEqual(doctor_shadow_campaign.main(
            ["--inspect-full", str(f), "--output", str(out)]), 0)
        self.assertEqual(json.loads(out.read_text())["status"],
                         "FULL_ARCHIVES_VALIDATED_ONLY")


if __name__ == "__main__":
    unittest.main()
