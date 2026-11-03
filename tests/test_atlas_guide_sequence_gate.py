"""Purely synthetic sequencing tests. NO real guide data is read or prepared."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_guide_sequence_gate import (
    _PER_GUIDE, _PHASE0, assess_next, main,
)

HEAD = "a" * 40
OTHER_HEAD = "f" * 40
SOURCE = "b" * 64
ZERO = "0" * 64
ARTIFACT = "c" * 64


def receipt(source_sha: str = ZERO, head_sha: str = HEAD) -> dict:
    return {
        "status": "PASS",
        "head_sha": head_sha,
        "source_sha": source_sha,
        "artifact_sha256": ARTIFACT,
    }


def phase0() -> dict:
    return {key: receipt() for key in _PHASE0}


def record(guide_id: str, predecessor: str = "", source_sha: str = SOURCE) -> dict:
    return {
        "guide_id": guide_id, "predecessor_id": predecessor,
        "head_sha": HEAD, "source_sha": source_sha,
        "total_steps": 5, "certified_steps": 5,
        "total_actions": 14, "certified_actions": 14,
        "certification_status": "CERTIFIED",
        "blocking_issues": 0, "unverified_issues": 0,
        "receipts": {key: receipt(source_sha) for key in _PER_GUIDE},
    }


def plan(next_id: str = "dofus_cawotte", completed: list | None = None) -> dict:
    return {
        "schema_version": 1, "next_guide_id": next_id,
        "phase0": phase0(), "completed": [] if completed is None else completed,
    }


def trusted_fake_verifier(_name: str, digest: str, head: str, source_sha: str) -> bool:
    # This fake is used ONLY in synthetic tests. The standalone CLI never has it.
    return digest == ARTIFACT and head == HEAD and source_sha in (SOURCE, ZERO)


class TestSequenceGateSynthetic(unittest.TestCase):
    def test_unqualified_tools_block_pilot(self):
        doc = plan()
        doc["phase0"].pop("windows_dofus")
        result = assess_next(doc, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("phase0.windows_dofus", result["missing_proofs"])

    def test_default_cli_never_trusts_user_supplied_pass_flags(self):
        result = assess_next(plan(), head_sha=HEAD)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["may_prepare_next"])
        self.assertFalse(result["certified"])

    def test_trusted_host_may_review_only_the_pilot_first(self):
        result = assess_next(plan(), head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertTrue(result["may_prepare_next"])
        self.assertEqual(result["status"], "ELIGIBLE_FOR_INDEPENDENT_REVIEW")
        self.assertFalse(result["certified"])
        self.assertFalse(result["real_guide_processed"])

    def test_no_second_guide_before_pilot_certification(self):
        result = assess_next(
            plan("guide-synthetic-2"), head_sha=HEAD, verifier=trusted_fake_verifier
        )
        self.assertFalse(result["may_prepare_next"])
        self.assertIn("pilot.cawotte_must_be_first", result["missing_proofs"])

    def test_dokoko_fallback_requires_independent_unavailability_evidence(self):
        request = plan("dokoko")
        blocked = assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertIn(
            "pilot.cawotte_source_unavailability_not_proven", blocked["missing_proofs"]
        )
        request["fallback_evidence"] = receipt()
        eligible = assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertTrue(eligible["may_prepare_next"])

    def test_unverified_previous_guide_blocks_the_next(self):
        request = plan("synthetic-next", [record("dofus_cawotte")])
        request["completed"][0]["receipts"].pop("independent_human_comparison")
        blocked = assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertFalse(blocked["may_prepare_next"])
        self.assertIn(
            "completed[0].independent_human_comparison", blocked["missing_proofs"]
        )

    def test_complete_synthetic_chain_is_only_eligible_for_review(self):
        first = record("dofus_cawotte")
        second = record("synthetic-2", predecessor="dofus_cawotte")
        outcome = assess_next(plan("synthetic-3", [first, second]),
                              head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertTrue(outcome["may_prepare_next"])
        self.assertEqual(outcome["verified_completed_count"], 2)
        self.assertFalse(outcome["certified"])

    def test_certificate_and_exact_full_coverage_required_before_next(self):
        for mutation in (
            {"certification_status": "PENDING"},
            {"certified_steps": 4},
            {"certified_actions": 13},
            {"total_steps": 0},
            {"total_actions": True},
        ):
            with self.subTest(mutation=mutation):
                prev = record("dofus_cawotte")
                prev.update(mutation)
                decision = assess_next(
                    plan("synthetic-next", [prev]),
                    head_sha=HEAD, verifier=trusted_fake_verifier
                )
                self.assertFalse(decision["may_prepare_next"])
        prev = record("dofus_cawotte")
        prev["receipts"].pop("independent_final_certificate")
        decision = assess_next(
            plan("synthetic-next", [prev]),
            head_sha=HEAD, verifier=trusted_fake_verifier
        )
        self.assertIn(
            "completed[0].independent_final_certificate",
            decision["missing_proofs"]
        )

    def test_missing_or_corrupt_comparator_evidence_blocks(self):
        request = plan("synthetic-next", [record("dofus_cawotte")])
        request["completed"][0]["receipts"]["source_to_atlas_comparison"][
            "artifact_sha256"
        ] = "x" * 64
        outcome = assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertIn("completed[0].source_to_atlas_comparison", outcome["missing_proofs"])

    def test_source_sha_and_exact_head_must_match_all_receipts(self):
        request = plan("synthetic-next", [record("dofus_cawotte")])
        request["completed"][0]["receipts"]["windows_dofus_manual_review"][
            "head_sha"
        ] = OTHER_HEAD
        result = assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertIn("completed[0].windows_dofus_manual_review", result["missing_proofs"])

    def test_bad_counts_and_unverified_steps_fail_closed(self):
        for value in (True, "5", -1, 0, None):
            with self.subTest(value=value):
                candidate = record("dofus_cawotte")
                candidate["certified_steps"] = value
                outcome = assess_next(plan("synthetic-next", [candidate]),
                                      head_sha=HEAD, verifier=trusted_fake_verifier)
                self.assertIn("completed[0].incomplete_coverage", outcome["missing_proofs"])

    def test_broken_chain_and_duplicate_guide_fails(self):
        records = [
            record("dofus_cawotte"),
            record("synthetic-2", predecessor="wrong"),
            record("synthetic-2", predecessor="synthetic-2"),
        ]
        outcome = assess_next(plan("synthetic-3", records), head_sha=HEAD,
                              verifier=trusted_fake_verifier)
        self.assertIn("completed[1].broken_chain", outcome["missing_proofs"])
        self.assertIn("completed[2].duplicate_or_invalid_id", outcome["missing_proofs"])

    def test_fallback_pilot_also_needs_receipt_when_marked_completed(self):
        request = plan("synthetic-next", [record("dokoko")])
        outcome = assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertIn(
            "pilot.cawotte_source_unavailability_not_proven", outcome["missing_proofs"]
        )
        request["fallback_evidence"] = receipt()
        outcome = assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertTrue(outcome["may_prepare_next"])

    def test_missing_verifier_or_verifier_exception_never_passes(self):
        def broken(*_args):
            raise RuntimeError("certification unavailable")
        outcome = assess_next(plan(), head_sha=HEAD, verifier=broken)
        self.assertFalse(outcome["may_prepare_next"])

    def test_bad_git_sha_rejected(self):
        for bad in ("a" * 64, "not-a-sha", "A" * 40):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                assess_next(plan(), head_sha=bad)

    def test_boolean_schema_version_never_unlocks_phase_zero(self):
        request = plan()
        request["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "unsupported sequencing plan"):
            assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)

    def test_invalid_next_guide_id_is_not_eligible_for_review(self):
        for bad in ("", " ", "..", "../other", "malformed/id", "x" * 121):
            with self.subTest(next_id=bad), self.assertRaisesRegex(ValueError, "invalid guide"):
                assess_next(plan(next_id=bad), head_sha=HEAD,
                            verifier=trusted_fake_verifier)

    def test_invalid_completed_guide_identity_blocks_the_chain(self):
        for bad in (" ", "..", "../fictitious", "x" * 121):
            with self.subTest(guide_id=bad):
                decision = assess_next(plan("synthetic-next", [record(bad)]),
                                       head_sha=HEAD, verifier=trusted_fake_verifier)
                self.assertIn("completed[0].duplicate_or_invalid_id",
                              decision["missing_proofs"])

    def test_first_completed_guide_cannot_claim_a_foreign_predecessor(self):
        old = record("dofus_cawotte", predecessor="not-a-real-predecessor")
        decision = assess_next(plan("synthetic-next", [old]), head_sha=HEAD,
                               verifier=trusted_fake_verifier)
        self.assertIn("completed[0].unexpected_predecessor",
                      decision["missing_proofs"])
        self.assertFalse(decision["may_prepare_next"])

    def test_inputs_not_mutated(self):
        request = plan("synthetic-next", [record("dofus_cawotte")])
        before = copy.deepcopy(request)
        assess_next(request, head_sha=HEAD, verifier=trusted_fake_verifier)
        self.assertEqual(request, before)

    def test_cli_reports_blocked_and_cannot_process_any_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps(plan()), encoding="utf-8")
            self.assertEqual(main(["--plan", str(path), "--head-sha", HEAD]), 1)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["plan.json"])


if __name__ == "__main__":
    unittest.main()
