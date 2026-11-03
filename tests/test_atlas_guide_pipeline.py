"""Synthetic-only end-to-end orchestration tests; no real guide data."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_guide_candidate_store import selected_candidate
from tools.atlas_guide_pipeline import GuidePipelineBlocked, stage_checked_candidate
from tools.atlas_guide_sequence_gate import _PHASE0

HEAD = "a" * 40
SOURCE = "b" * 64
ARTIFACT = "c" * 64
PILOT = "dofus_cawotte"


def receipt() -> dict:
    return {
        "status": "PASS", "head_sha": HEAD,
        "source_sha": "0" * 64, "artifact_sha256": ARTIFACT,
    }


def synthetic_plan() -> dict:
    return {
        "schema_version": 1,
        "next_guide_id": PILOT, "completed": [],
        "phase0": {name: receipt() for name in _PHASE0},
    }


def fake_trusted_host(name, digest, head, source) -> bool:
    if name in {"current.source_rights", "current.independent_reference"}:
        # Explicit TEST-ONLY witness; cannot prove third-party authorization.
        return (
            head == HEAD and isinstance(digest, str)
            and len(digest) == 64 and source == digest
        )
    return digest == ARTIFACT and head == HEAD and source == "0" * 64


def synthetic_source() -> dict:
    return {
        "schema_version": 1,
        "complete": True, "reference_verified": True,
        "rights_verified": True,
        "guides": [{
            "guide_id": PILOT, "title": "FICTIONAL TEST ONLY",
            "steps": [{
                "source_step_id": "fabricated-test-id",
                "title": "Fictitious step",
                "actions": [{
                    "action_id": "fictional-action",
                    "kind": "talk", "text": "Fictional NPC test action",
                }],
            }],
        }],
    }


class PipelineSyntheticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "candidates"
        self.source = synthetic_source()
        self.ref = copy.deepcopy(self.source)
        self.before = copy.deepcopy(self.source)
        self.before["guides"][0]["steps"][0]["actions"][0]["text"] = "Broken fixture"
        self.after = copy.deepcopy(self.source)

    def _run(self, **kw):
        args = {
            "plan": synthetic_plan(), "head_sha": HEAD,
            "verifier": fake_trusted_host, "authorized_source": self.source,
            "independent_reference": self.ref, "atlas_before": self.before,
            "atlas_after": self.after, "candidate_root": self.folder,
        }
        args.update(kw)
        return stage_checked_candidate(**args)

    def test_stages_only_one_verified_synthetic_candidate_and_never_activates(self):
        result = self._run()
        self.assertEqual(result["status"], "STAGED_NOT_ACTIVE_NOT_CERTIFIED")
        self.assertFalse(result["certified"])
        self.assertFalse(result["runtime_activation"])
        self.assertEqual(result["resolved_issue_count"], 1)
        self.assertEqual(selected_candidate(self.folder), result["candidate_sha256"])

    def test_phase0_tools_are_discoverable_and_never_claim_implicit_publication(self):
        # Use exactly the catalog's static AST parser. This is intentionally
        # cheaper than a full-repository tool audit on every scoped Guide test.
        from tools.tool_catalog import _validated_tool_spec

        root = Path(__file__).resolve().parents[1]
        expected = {
            "tools/atlas_guide_pipeline.py": ("atlas-guide-pipeline", True),
            "tools/atlas_guide_importer.py": ("atlas-guide-importer", False),
            "tools/atlas_guide_conformity.py": ("atlas-guide-conformity", False),
            "tools/atlas_guide_sequence_gate.py": ("atlas-guide-sequence", False),
            "tools/atlas_guide_candidate_store.py": ("atlas-guide-candidate-store", False),
        }
        for path, (tool_id, canonical) in expected.items():
            with self.subTest(tool=path):
                source = (root / path).read_text(encoding="utf-8")
                spec, errors = _validated_tool_spec(source, path)
                self.assertEqual(errors, [])
                self.assertIsNotNone(spec)
                self.assertEqual(spec["id"], tool_id)
                self.assertEqual(spec["canonical"], canonical)
                self.assertIn("guide", spec["capabilities"])
                self.assertEqual(spec["target_scopes"], ["encyclopedia_guide"])
                self.assertTrue(spec["recommended_tests"])
                for module in spec["recommended_tests"]:
                    path_on_disk = root / (module.replace(".", "/") + ".py")
                    self.assertTrue(path_on_disk.is_file(), module)
                if path.endswith("sequence_gate.py"):
                    self.assertEqual(spec["side_effects"], "read_only")
                else:
                    # All other modules expose an output/write entry point
                    # somewhere in the CLI or trusted API; don't auto-publish.
                    self.assertEqual(spec["side_effects"],
                                     "repo_mutation_explicit")

    def test_missing_trusted_host_blocks_before_filesystem_writes(self):
        with self.assertRaisesRegex(GuidePipelineBlocked, "missing trusted evidence"):
            self._run(verifier=None)
        self.assertFalse(self.folder.exists())

    def test_false_status_or_missing_required_tool_blocks(self):
        doc = synthetic_plan()
        doc["phase0"].pop("ui_interactions")
        with self.assertRaises(GuidePipelineBlocked):
            self._run(plan=doc)
        self.assertFalse(self.folder.exists())

    def test_wrong_next_guide_name_blocks(self):
        doc = synthetic_plan()
        doc["next_guide_id"] = "synthetic-other"
        with self.assertRaises(GuidePipelineBlocked):
            self._run(plan=doc)
        self.assertFalse(self.folder.exists())

    def test_malformed_one_guide_shape_is_rejected_before_disk(self):
        wrong = copy.deepcopy(self.source)
        wrong["guides"] = ["not-an-object"]
        with self.assertRaisesRegex(GuidePipelineBlocked, "source guide must be"):
            self._run(authorized_source=wrong)
        wrong_ref = copy.deepcopy(self.ref)
        wrong_ref["guides"] = [42]
        with self.assertRaisesRegex(GuidePipelineBlocked, "reference: guide must be"):
            self._run(independent_reference=wrong_ref)
        self.assertFalse(self.folder.exists())

    def test_missing_source_action_blocks(self):
        incomplete = copy.deepcopy(self.source)
        incomplete["guides"][0]["steps"][0]["actions"].clear()
        with self.assertRaises(GuidePipelineBlocked):
            self._run(authorized_source=incomplete)
        self.assertFalse(self.folder.exists())

    def test_atlas_after_difference_blocks(self):
        after = copy.deepcopy(self.after)
        after["guides"][0]["steps"][0]["actions"][0]["text"] = "Different"
        with self.assertRaisesRegex(GuidePipelineBlocked, "Atlas route differs"):
            self._run(atlas_after=after)
        self.assertFalse(self.folder.exists())

    def test_independent_reference_difference_blocks(self):
        ref = copy.deepcopy(self.ref)
        ref["guides"][0]["steps"][0]["title"] = "Different source"
        def digest(doc):
            raw = json.dumps(doc, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
            return hashlib.sha256(raw).hexdigest()

        source_sha = digest(self.source)
        ref_sha = digest(ref)
        self.assertNotEqual(ref_sha, source_sha)

        def independently_attested(name, artifact_sha, head, source):
            if name == "current.independent_reference":
                return head == HEAD and source == source_sha and artifact_sha == ref_sha
            return fake_trusted_host(name, artifact_sha, head, source)

        # Both independent witnesses must be accepted before comparing the
        # content; the comparator must still reject genuine source divergence.
        with self.assertRaisesRegex(GuidePipelineBlocked, "source differs"):
            self._run(independent_reference=ref, verifier=independently_attested)
        self.assertFalse(self.folder.exists())

    def test_current_source_and_reference_need_separate_trusted_receipts(self):
        def source_not_attested(name, digest, head, source):
            if name == "current.source_rights":
                return False
            return fake_trusted_host(name, digest, head, source)

        with self.assertRaisesRegex(GuidePipelineBlocked, "current.source_rights"):
            self._run(verifier=source_not_attested)
        self.assertFalse(self.folder.exists())

        def reference_not_attested(name, digest, head, source):
            if name == "current.independent_reference":
                return False
            return fake_trusted_host(name, digest, head, source)

        with self.assertRaisesRegex(
            GuidePipelineBlocked, "current.independent_reference"
        ):
            self._run(verifier=reference_not_attested)
        self.assertFalse(self.folder.exists())

    def test_current_reference_verifier_exception_blocks(self):
        def failing_witness(name, digest, head, source):
            if name.startswith("current."):
                raise RuntimeError("independent assessor unavailable")
            return fake_trusted_host(name, digest, head, source)

        with self.assertRaisesRegex(GuidePipelineBlocked, "trusted attestation"):
            self._run(verifier=failing_witness)
        self.assertFalse(self.folder.exists())

    def test_source_completeness_flag_is_required(self):
        source = copy.deepcopy(self.source)
        source["complete"] = False
        with self.assertRaises(GuidePipelineBlocked):
            self._run(authorized_source=source)
        self.assertFalse(self.folder.exists())

    def test_more_than_one_guide_never_processed(self):
        source = copy.deepcopy(self.source)
        source["guides"].append(copy.deepcopy(source["guides"][0]))
        with self.assertRaisesRegex(GuidePipelineBlocked, "one and only one"):
            self._run(authorized_source=source)
        self.assertFalse(self.folder.exists())

    def test_bad_predecessor_evidence_cannot_unlock_another_guide(self):
        doc = synthetic_plan()
        doc["next_guide_id"] = "synthetic-second"
        with self.assertRaises(GuidePipelineBlocked):
            self._run(plan=doc)
        self.assertFalse(self.folder.exists())


if __name__ == "__main__":
    unittest.main()
