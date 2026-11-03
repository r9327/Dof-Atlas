"""Synthetic-only end-to-end orchestration tests; no real guide data."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_guide_candidate_store import selected_candidate
from tools.atlas_guide_pipeline import (
    GuidePipelineBlocked, main, stage_checked_candidate, preview_staged_guide,
)
from tools.atlas_guide_sequence_gate import _PER_GUIDE, _PHASE0, assess_next

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

    def test_pipeline_pinned_preview_exposes_shared_card_contract_only(self):
        staged = self._run()
        receipt = preview_staged_guide(
            candidate_root=self.folder,
            expected_selected=staged["candidate_sha256"],
            route_id=f"source_guide:{PILOT}",
        )
        self.assertEqual(receipt["status"], "STAGED_PREVIEW_ONLY")
        self.assertFalse(receipt["certified"])
        self.assertFalse(receipt["runtime_activation"])
        route = receipt["route"]
        self.assertEqual(route["source_compliance"], "NOT_CERTIFIED")
        self.assertEqual(route["route_model"], "authored_step_actions")
        self.assertEqual(route["id"], f"source_guide:{PILOT}")
        self.assertEqual(route["steps"][0]["manual_stage_id"],
                         f"source:{PILOT}:fabricated-test-id")
        self.assertEqual(route["steps"][0]["manual_sections"]["now"][0]["text"],
                         "Fictional NPC test action")
        self.assertEqual(selected_candidate(self.folder), staged["candidate_sha256"])
        self.assertFalse((self.folder / "data").exists())

    def test_pipeline_preview_requires_existing_exact_selection(self):
        from app.modules.encyclopedia.services.guide_shared_route_contract import (
            GuideRouteContractError,
        )

        with self.assertRaises(GuideRouteContractError):
            preview_staged_guide(
                candidate_root=self.folder, expected_selected="a" * 64,
                route_id=f"source_guide:{PILOT}",
            )
        self.assertFalse(self.folder.exists())
        staged = self._run()
        for selection, route_id in (
            ("NONE", f"source_guide:{PILOT}"),
            ("b" * 64, f"source_guide:{PILOT}"),
            (staged["candidate_sha256"], "source_guide:unverified"),
        ):
            with self.subTest(selection=selection, route_id=route_id):
                with self.assertRaises(GuideRouteContractError):
                    preview_staged_guide(
                        candidate_root=self.folder,
                        expected_selected=selection,
                        route_id=route_id,
                    )
        self.assertEqual(selected_candidate(self.folder), staged["candidate_sha256"])

    def test_95_sequential_synthetic_stagings_are_isolated_and_never_active(self):
        # Complete-capacity exercise: 95 entirely fabricated single-step
        # routes, not a copy of or a certificate for the 95 real guide routes.
        history = []
        attested_sources: set[str] = set()
        selection = "NONE"
        for index in range(95):
            guide_id = PILOT if index == 0 else f"synthetic-{index:03d}"
            source = synthetic_source()
            source["guides"][0]["guide_id"] = guide_id
            source["guides"][0]["steps"][0]["actions"][0]["text"] = (
                f"Independent fictional action {index}"
            )
            reference = copy.deepcopy(source)
            after = copy.deepcopy(source)
            before = copy.deepcopy(source)
            before["guides"][0]["steps"][0]["actions"][0]["text"] = (
                f"Broken fictional snapshot {index}"
            )
            request = synthetic_plan()
            request["next_guide_id"] = guide_id
            request["completed"] = copy.deepcopy(history)

            def host(name, digest, head, source_sha):
                if name.startswith("current."):
                    return (head == HEAD and digest == source_sha
                            and isinstance(digest, str) and len(digest) == 64)
                return (
                    head == HEAD and digest == ARTIFACT
                    and (source_sha == "0" * 64 or source_sha in attested_sources)
                )

            # One wrong action in the 48th staged candidate must not write
            # any new generation, replace the selection, or unlock the next.
            if index == 47:
                invalid_after = copy.deepcopy(after)
                invalid_after["guides"][0]["steps"][0]["actions"][0]["text"] = (
                    "An unaudited fictional action"
                )
                with self.assertRaisesRegex(GuidePipelineBlocked, "Atlas route differs"):
                    stage_checked_candidate(
                        plan=request, head_sha=HEAD, verifier=host,
                        authorized_source=source,
                        independent_reference=reference,
                        atlas_before=before, atlas_after=invalid_after,
                        candidate_root=self.folder, expected_selected=selection,
                    )
                self.assertEqual(selected_candidate(self.folder), selection)
                self.assertEqual(
                    len(list((self.folder / "generations").glob("*.json"))), index
                )

            result = stage_checked_candidate(
                plan=request, head_sha=HEAD, verifier=host,
                authorized_source=source,
                independent_reference=reference,
                atlas_before=before, atlas_after=after,
                candidate_root=self.folder, expected_selected=selection,
            )
            self.assertEqual(result["guide_id"], guide_id)
            self.assertEqual(result["status"], "STAGED_NOT_ACTIVE_NOT_CERTIFIED")
            self.assertFalse(result["certified"])
            self.assertFalse(result["runtime_activation"])
            self.assertEqual(result["resolved_issue_count"], 1)
            self.assertNotEqual(result["candidate_sha256"], selection)
            selection = result["candidate_sha256"]
            self.assertEqual(selected_candidate(self.folder), selection)
            sha = result["source_sha256"]
            attested_sources.add(sha)
            history.append({
                "guide_id": guide_id,
                "predecessor_id": (
                    history[-1]["guide_id"] if history else ""
                ),
                "head_sha": HEAD, "source_sha": sha,
                "total_steps": 1, "certified_steps": 1,
                "total_actions": 1, "certified_actions": 1,
                "blocking_issues": 0, "unverified_issues": 0,
                "certification_status": "CERTIFIED",
                # Test-only synthetic witnesses: not real proof.
                "receipts": {
                    name: {
                        "status": "PASS", "head_sha": HEAD,
                        "source_sha": sha, "artifact_sha256": ARTIFACT,
                    }
                    for name in _PER_GUIDE
                },
            })
        self.assertEqual(len(history), 95)
        self.assertEqual(
            len(list((self.folder / "generations").glob("*.json"))), 95
        )
        self.assertEqual(selected_candidate(self.folder), selection)
        request = synthetic_plan()
        request["completed"] = copy.deepcopy(history)
        request["next_guide_id"] = "synthetic-096"
        blocked = assess_next(request, head_sha=HEAD, verifier=host)
        self.assertFalse(blocked["may_prepare_next"])
        self.assertIn("sequence.inventory_already_complete", blocked["missing_proofs"])
        self.assertFalse(blocked["certified"])
        self.assertFalse((self.folder / "installed").exists())
        self.assertFalse((self.folder / "character_progress.json").exists())

    def test_witness_cannot_change_attested_content_before_staging(self):
        def mutating_host(name, digest, head, source):
            allowed = fake_trusted_host(name, digest, head, source)
            if name == "current.independent_reference":
                # Every in-memory export mutates to the SAME new payload.
                # An equality-only comparator would approve this forged
                # replacement even though the witness saw the OLD digests.
                for export in (self.source, self.ref, self.after):
                    export["guides"][0]["steps"][0]["actions"][0]["text"] = (
                        "Unattested fabricated replacement"
                    )
            return allowed

        with self.assertRaisesRegex(
            GuidePipelineBlocked, "snapshots changed during verification"
        ):
            self._run(verifier=mutating_host)
        self.assertFalse(self.folder.exists())

    def test_witness_cannot_change_atlas_before_or_after_observations(self):
        for name in ("before", "after"):
            with self.subTest(name=name):
                source = synthetic_source()
                reference = copy.deepcopy(source)
                before = copy.deepcopy(source)
                before["guides"][0]["steps"][0]["actions"][0]["text"] = "Before mismatch"
                after = copy.deepcopy(source)
                target = before if name == "before" else after
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp) / "staged"

                    def mutating_host(witness, digest, head, source_sha):
                        result = fake_trusted_host(witness, digest, head, source_sha)
                        if witness == "current.independent_reference":
                            target["guides"][0]["steps"][0]["actions"][0]["text"] = (
                                "Unreviewed changed observation"
                            )
                        return result

                    with self.assertRaisesRegex(
                        GuidePipelineBlocked, "snapshots changed during verification"
                    ):
                        self._run(
                            authorized_source=source, independent_reference=reference,
                            atlas_before=before, atlas_after=after,
                            verifier=mutating_host, candidate_root=root,
                        )
                    self.assertFalse(root.exists())

    def test_witness_cannot_revoke_prior_phase0_receipt(self):
        request = synthetic_plan()
        def mutating_host(name, digest, head, source):
            if name == "phase0.windows_dofus":
                request["phase0"]["doctor"]["status"] = "BLOCKED"
            return fake_trusted_host(name, digest, head, source)
        with self.assertRaisesRegex(GuidePipelineBlocked, "sequencing plan changed"):
            self._run(plan=request, verifier=mutating_host)
        self.assertFalse(self.folder.exists())

    def test_witness_cannot_change_sequencing_plan_after_initial_gate(self):
        request = synthetic_plan()
        def mutating_host(name, digest, head, source):
            if name == "current.independent_reference":
                request["phase0"]["doctor"]["status"] = "BLOCKED"
            return fake_trusted_host(name, digest, head, source)
        with self.assertRaisesRegex(GuidePipelineBlocked, "snapshots changed"):
            self._run(plan=request, verifier=mutating_host)
        self.assertFalse(self.folder.exists())

    def test_read_only_cli_rejects_ambiguous_plans_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            base = json.dumps(synthetic_plan())
            for contents in (
                base.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1),
                base[:-1] + ', "meta": NaN}',
                base[:-1] + ', "meta": 1e9999}',
                '[]',
            ):
                with self.subTest(contents=contents[-40:]):
                    path.write_text(contents, encoding="utf-8")
                    with self.assertRaises(SystemExit) as exc:
                        main(["--plan", str(path), "--head-sha", HEAD])
                    self.assertEqual(exc.exception.code, 2)
                    self.assertEqual([p.name for p in Path(tmp).iterdir()], ["plan.json"])

    def test_witness_cannot_retarget_guide_after_sequence_gate(self):
        request = synthetic_plan()
        def mutating_host(name, digest, head, source):
            if name == "phase0.optimized_guides_regression":
                request["next_guide_id"] = "unauthorized-second-guide"
            return fake_trusted_host(name, digest, head, source)

        with self.assertRaisesRegex(
            GuidePipelineBlocked, "sequencing plan changed"
        ):
            self._run(plan=request, verifier=mutating_host)
        self.assertFalse(self.folder.exists())

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

    def test_catalog_routes_guide_tools_without_implicit_mutations(self):
        # Exercise the actual catalog selector in a tiny isolated repository
        # snapshot. No Qt import, network, full source scan or guide data.
        from tools.tool_catalog import catalog, select_tools

        root = Path(__file__).resolve().parents[1]
        paths = (
            "tools/atlas_guide_pipeline.py",
            "tools/atlas_guide_importer.py",
            "tools/atlas_guide_conformity.py",
            "tools/atlas_guide_sequence_gate.py",
            "tools/atlas_guide_candidate_store.py",
        )
        with tempfile.TemporaryDirectory() as temp:
            scratch = Path(temp)
            for relative in paths:
                destination = scratch / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(
                    (root / relative).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            for relative in (
                "test_atlas_guide_pipeline.py",
                "test_atlas_guide_importer_preview.py",
                "test_atlas_guide_conformity.py",
                "test_atlas_guide_sequence_gate.py",
                "test_atlas_guide_candidate_store.py",
            ):
                destination = scratch / "tests" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                module = relative.removeprefix("test_").removesuffix(".py")
                symbol = ("publish_candidate" if module == "atlas_guide_candidate_store"
                          else "main")
                destination.write_text(
                    f"from tools.{module} import {symbol}\n",
                    encoding="utf-8",
                )
            report = catalog(scratch)
            by_path = {row["path"]: row for row in report["tools"]}
            self.assertEqual(set(by_path), set(paths))
            self.assertFalse(report["invalid_tool_specs"])
            self.assertTrue(all(
                row["tool_spec_source"] == "explicit"
                for row in by_path.values()
            ))
            self.assertEqual(
                by_path["tools/atlas_guide_pipeline.py"]["preferred_role"],
                "guide_candidate_control_plane",
            )
            routed = select_tools(report, capability="guide", safe_only=True)
            safe_paths = {row["path"] for row in routed["tools"]}
            self.assertIn("tools/atlas_guide_pipeline.py", safe_paths)
            self.assertIn("tools/atlas_guide_sequence_gate.py", safe_paths)
            self.assertNotIn("tools/atlas_guide_candidate_store.py", safe_paths)
            self.assertTrue(
                by_path["tools/atlas_guide_sequence_gate.py"]["automation_ready"]
            )
            self.assertFalse(
                by_path["tools/atlas_guide_pipeline.py"]["automation_ready"]
            )
            self.assertFalse(
                by_path["tools/atlas_guide_candidate_store.py"]["automation_ready"]
            )

    def test_nonfinite_source_is_rejected_before_any_candidate_write(self):
        source = copy.deepcopy(self.source)
        source["guides"][0]["extra_metadata"] = float("inf")
        with self.assertRaisesRegex(GuidePipelineBlocked, "non-JSON-compatible"):
            self._run(authorized_source=source)
        self.assertFalse(self.folder.exists())

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
