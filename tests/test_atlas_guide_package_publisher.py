"""Synthetic, Qt-free certification-gated package preparation regressions.

Only fictional source routes and local temp directories are exercised.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.services.guide_trusted_source_package import (
    GuidePackageEntry,
    GuideTrustedSourcePackage,
)
from tools.atlas_guide_candidate_store import (
    publish_candidate, rollback_candidate, selected_candidate,
)
from tools.atlas_guide_importer import prepare_preview
from tools import atlas_guide_package_publisher as publisher
from tools.atlas_guide_package_publisher import (
    GuidePackagePublishBlocked, install_attested_guide_package,
    prepare_attested_guide_package, rollback_installed_guide_package,
    selected_installed_guide_package,
)

HEAD = "a" * 40
GUIDE = "source_guide:fictional-pilot"
CERT = "synthetic-witness-only:fictional-pilot"


def source() -> dict:
    return {
        "schema_version": 1, "rights_verified": True,
        "reference_verified": True, "complete": True,
        "guides": [{
            "guide_id": "fictional-pilot", "title": "Synthetic test route",
            "steps": [{
                "source_step_id": "step-one", "title": "Fictional starting point",
                "coordinates": [4, -7],
                "actions": [{
                    "action_id": "travel", "kind": "travel",
                    "text": "Aller en [4,-7]", "coordinates": [4, -7],
                }],
            }],
        }],
    }


class GuidePackagePublisherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = self.root / "candidates"
        self.out = self.root / "package-one"
        self.install = self.root / "installed"
        self.preview = prepare_preview(
            source(), expected_guides=1, expected_steps=1,
        )
        self.staged = publish_candidate(self.preview, root=self.store)
        self.calls = []
        self.grant = True

    def witness(self, guide_id, digest, source_sha, head, certificate):
        self.calls.append((guide_id, digest, source_sha, head, certificate))
        return (self.grant and guide_id == GUIDE and head == HEAD
                and certificate == CERT and source_sha == self.preview["source_sha256"]
                and isinstance(digest, str) and len(digest) == 64)

    def args(self, **overrides):
        params = {
            "candidate_root": self.store,
            "expected_selected": self.staged["candidate_sha256"],
            "route_id": GUIDE, "destination": self.out,
            "build_head_sha": HEAD, "certificate_ref": CERT,
            "witness": self.witness,
        }
        params.update(overrides)
        return params

    def test_prepares_one_bounded_canonical_route_without_activation(self):
        before = copy.deepcopy(self.preview)
        result = prepare_attested_guide_package(**self.args())
        self.assertEqual(self.preview, before)
        self.assertEqual(result["status"], "PACKAGE_PREPARED_NOT_INSTALLED")
        self.assertFalse(result["runtime_activation"])
        self.assertFalse(result["certified"])
        self.assertEqual(result["candidate_sha256"], self.staged["candidate_sha256"])
        self.assertEqual(result["route_id"], GUIDE)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ["fictional-pilot.json"])
        self.assertEqual(selected_candidate(self.store), self.staged["candidate_sha256"])
        self.assertFalse((self.root / "progress.json").exists())
        self.assertGreaterEqual(len(self.calls), 3)

        entry = GuidePackageEntry(**result["entry"])
        self.assertEqual(
            hashlib.sha256((self.out / entry.filename).read_bytes()).hexdigest(),
            result["package_sha256"],
        )
        loader = GuideTrustedSourcePackage(
            self.out, {GUIDE: entry}, build_head_sha=HEAD,
            witness=self.witness,
        )
        route = loader.load_route(GUIDE)
        self.assertEqual(route, self.preview["routes"][0])
        self.assertTrue(loader.authorize(GUIDE, route))
        self.grant = False
        self.assertFalse(loader.authorize(GUIDE, route))

    def test_untrusted_or_stale_certificates_refuse_before_write(self):
        for overrides in (
            {"witness": None}, {"witness": lambda *args: 1},
            {"witness": lambda *args: False},
            {"build_head_sha": "0" * 40},
            {"certificate_ref": ""},
            {"route_id": "source_guide:unknown"},
            {"expected_selected": "b" * 64},
        ):
            with self.subTest(overrides=list(overrides)):
                with self.assertRaises(GuidePackagePublishBlocked):
                    prepare_attested_guide_package(**self.args(**overrides))
                self.assertFalse(self.out.exists())

    def test_revoked_after_preflight_never_publishes(self):
        calls = 0

        def witness(*args):
            nonlocal calls
            calls += 1
            return calls == 1

        with self.assertRaises(GuidePackagePublishBlocked):
            prepare_attested_guide_package(**self.args(witness=witness))
        self.assertFalse(self.out.exists())
        self.assertEqual(selected_candidate(self.store), self.staged["candidate_sha256"])

    def test_revoked_post_copy_cleans_exclusively_created_package(self):
        calls = 0

        def witness(*args):
            nonlocal calls
            calls += 1
            # Preflight, scratch load, pre-publication accept; reject final load.
            return calls <= 3

        with self.assertRaises(GuidePackagePublishBlocked):
            prepare_attested_guide_package(**self.args(witness=witness))
        self.assertFalse(self.out.exists())
        self.assertFalse(list(self.root.glob(".atlas-guide-package-*")))

    def test_stale_selection_after_attestation_refuses_without_destination(self):
        def change_selection(*args):
            rollback_candidate(
                root=self.store,
                expected_selected=self.staged["candidate_sha256"],
                restore_sha256="NONE",
            )
            return True

        with self.assertRaises(GuidePackagePublishBlocked):
            prepare_attested_guide_package(**self.args(witness=change_selection))
        self.assertFalse(self.out.exists())
        self.assertEqual(selected_candidate(self.store), "NONE")

    def test_never_adopts_overwrites_or_deletes_existing_package(self):
        self.out.mkdir()
        previous = self.out / "keep.json"
        previous.write_text('{"original": true}', encoding="utf-8")
        with self.assertRaisesRegex(GuidePackagePublishBlocked, "new dedicated directory"):
            prepare_attested_guide_package(**self.args())
        self.assertEqual(previous.read_text(encoding="utf-8"), '{"original": true}')

    def test_atomic_file_failure_cleans_new_destination(self):
        with patch("tools.atlas_guide_package_publisher.os.replace",
                   side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(GuidePackagePublishBlocked):
                prepare_attested_guide_package(**self.args())
        self.assertFalse(self.out.exists())
        self.assertEqual(selected_candidate(self.store), self.staged["candidate_sha256"])
        self.assertFalse(list(self.root.glob(".atlas-guide-package-*")))

    def test_wrong_or_multi_guide_candidate_is_not_a_package(self):
        with self.assertRaises(GuidePackagePublishBlocked):
            prepare_attested_guide_package(
                **self.args(route_id="source_guide:fictional-other"),
            )
        second = source()["guides"][0]
        another = copy.deepcopy(second)
        another["guide_id"] = "fictional-second"
        alternative = source()
        alternative["guides"].append(another)
        multi = prepare_preview(
            alternative, expected_guides=2, expected_steps=2,
        )
        candidate_sha = publish_candidate(
            multi, root=self.store, expected_selected=self.staged["candidate_sha256"],
        )["candidate_sha256"]
        with self.assertRaisesRegex(GuidePackagePublishBlocked, "one complete"):
            prepare_attested_guide_package(
                **self.args(expected_selected=candidate_sha),
            )
        self.assertFalse(self.out.exists())

    def test_partial_preview_cannot_cross_trusted_package_gate(self):
        incomplete = source()
        incomplete["complete"] = False
        partial = prepare_preview(
            incomplete, expected_guides=95, expected_steps=7705, partial=True,
        )
        candidate_sha = publish_candidate(
            partial, root=self.store, expected_selected=self.staged["candidate_sha256"],
        )["candidate_sha256"]
        with self.assertRaisesRegex(GuidePackagePublishBlocked, "one complete"):
            prepare_attested_guide_package(
                **self.args(expected_selected=candidate_sha),
            )
        self.assertFalse(self.out.exists())

    def test_unsafe_paths_and_candidate_store_overlap_refuse_without_writes(self):
        for path in (
            self.store,
            self.store / "packages",
            self.root,
            self.root / "data" / "guide.json",
            self.root / "saves" / "package",
            self.root / "artifacts" / ".." / "source",
        ):
            with self.subTest(path=str(path)):
                with self.assertRaises(GuidePackagePublishBlocked):
                    prepare_attested_guide_package(
                        **self.args(destination=path),
                    )
        self.assertFalse((self.root / "data").exists())
        self.assertFalse((self.root / "saves").exists())

    def test_junction_parent_refuses_on_non_windows_ci_too(self):
        alias = self.root / "linked"
        output = alias / "bundle"
        original = Path.is_junction
        with patch.object(Path, "is_junction",
                          lambda path: path == alias or original(path)):
            with self.assertRaises(GuidePackagePublishBlocked):
                prepare_attested_guide_package(
                    **self.args(destination=output),
                )
        self.assertFalse(alias.exists())

    def test_source_file_sha_and_separate_witness_remain_required(self):
        result = prepare_attested_guide_package(**self.args())
        entry = GuidePackageEntry(**result["entry"])
        file = self.out / entry.filename
        file.write_bytes(file.read_bytes() + b" ")
        package = GuideTrustedSourcePackage(
            self.out, {GUIDE: entry}, build_head_sha=HEAD, witness=self.witness,
        )
        with self.assertRaises(ValueError):
            package.load_route(GUIDE)
        self.assertFalse(package.authorize(GUIDE, self.preview["routes"][0]))

    def test_transactional_install_rechecks_and_never_activates_runtime(self):
        prepared = prepare_attested_guide_package(**self.args())
        result = install_attested_guide_package(
            prepared=prepared, install_root=self.install,
            build_head_sha=HEAD, witness=self.witness,
        )
        self.assertEqual(result["status"], "PACKAGE_INSTALLED_NOT_ACTIVATED")
        self.assertEqual(result["previous_sha256"], "NONE")
        self.assertEqual(result["selected_sha256"], prepared["package_sha256"])
        self.assertFalse(result["certified"])
        self.assertFalse(result["runtime_activation"])
        selected = selected_installed_guide_package(
            install_root=self.install, build_head_sha=HEAD, witness=self.witness,
        )
        self.assertEqual(selected["selected_sha256"], prepared["package_sha256"])
        self.assertFalse((self.root / "progress.json").exists())
        self.assertTrue(self.out.is_dir())

    def test_install_stale_selection_and_revocation_fail_without_store_creation(self):
        prepared = prepare_attested_guide_package(**self.args())
        for expected, witness in (("b" * 64, self.witness), ("NONE", lambda *args: False)):
            with self.subTest(expected=expected):
                with self.assertRaises(GuidePackagePublishBlocked):
                    install_attested_guide_package(
                        prepared=prepared, install_root=self.install,
                        expected_selected=expected,
                        build_head_sha=HEAD, witness=witness,
                    )
        self.assertFalse(self.install.exists())

    def test_installed_selection_rejects_unexpected_metadata(self):
        prepared = prepare_attested_guide_package(**self.args())
        install_attested_guide_package(
            prepared=prepared, install_root=self.install,
            build_head_sha=HEAD, witness=self.witness,
        )
        selected_file = self.install / "selected.json"
        payload = json.loads(selected_file.read_text(encoding="utf-8"))
        payload["ignored_override"] = True
        selected_file.write_text(
            json.dumps(payload, sort_keys=True), encoding="utf-8",
        )
        with self.assertRaisesRegex(
                GuidePackagePublishBlocked, "selection contract"):
            selected_installed_guide_package(
                install_root=self.install,
                build_head_sha=HEAD,
                witness=self.witness,
            )

    def test_post_install_failure_restores_pointer_and_removes_new_generation(self):
        prepared = prepare_attested_guide_package(**self.args())
        original = publisher._verify_installed_generation
        calls = 0

        def fail_after_pointer(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise GuidePackagePublishBlocked("synthetic post-pointer failure")
            return original(*args, **kwargs)

        with patch.object(publisher, "_verify_installed_generation", fail_after_pointer):
            with self.assertRaisesRegex(GuidePackagePublishBlocked, "post-pointer"):
                install_attested_guide_package(
                    prepared=prepared, install_root=self.install,
                    build_head_sha=HEAD, witness=self.witness,
                )
        selected = selected_installed_guide_package(
            install_root=self.install, build_head_sha=HEAD, witness=self.witness,
        )
        self.assertEqual(selected["selected_sha256"], "NONE")
        self.assertEqual(list((self.install / "generations").iterdir()), [])

    def test_ambiguous_pointer_replace_is_detected_and_rolled_back(self):
        prepared = prepare_attested_guide_package(**self.args())
        original = publisher._atomic_document
        injected = False

        def replace_then_fail(path, payload):
            nonlocal injected
            original(path, payload)
            if (path.name == "selected.json"
                    and payload.get("selected_sha256") != "NONE"
                    and not injected):
                injected = True
                raise OSError("synthetic success then failure")

        with patch.object(publisher, "_atomic_document", replace_then_fail):
            with self.assertRaises(GuidePackagePublishBlocked):
                install_attested_guide_package(
                    prepared=prepared, install_root=self.install,
                    build_head_sha=HEAD, witness=self.witness,
                )
        selected = selected_installed_guide_package(
            install_root=self.install, build_head_sha=HEAD, witness=self.witness,
        )
        self.assertEqual(selected["selected_sha256"], "NONE")
        self.assertEqual(list((self.install / "generations").iterdir()), [])

    def test_concurrent_install_lock_is_never_removed_by_loser(self):
        prepared = prepare_attested_guide_package(**self.args())
        publisher._managed_install_root(self.install, initialize=True)
        lock = self.install / ".install.lock"
        lock.write_text("other transaction", encoding="utf-8")
        with self.assertRaisesRegex(GuidePackagePublishBlocked, "already running"):
            install_attested_guide_package(
                prepared=prepared, install_root=self.install,
                build_head_sha=HEAD, witness=self.witness,
            )
        self.assertEqual(lock.read_text(encoding="utf-8"), "other transaction")

    def test_explicit_installed_rollback_is_cas_and_post_verified(self):
        prepared = prepare_attested_guide_package(**self.args())
        installed = install_attested_guide_package(
            prepared=prepared, install_root=self.install,
            build_head_sha=HEAD, witness=self.witness,
        )
        with self.assertRaisesRegex(GuidePackagePublishBlocked, "Stale"):
            rollback_installed_guide_package(
                install_root=self.install, expected_selected="b" * 64,
                build_head_sha=HEAD, witness=self.witness,
            )
        rollback = rollback_installed_guide_package(
            install_root=self.install,
            expected_selected=installed["selected_sha256"],
            build_head_sha=HEAD, witness=self.witness,
        )
        self.assertEqual(rollback["status"], "INSTALLED_PACKAGE_ROLLED_BACK")
        self.assertEqual(rollback["selected_sha256"], "NONE")
        selected = selected_installed_guide_package(
            install_root=self.install, build_head_sha=HEAD, witness=self.witness,
        )
        self.assertEqual(selected["status"], "NO_PACKAGE_INSTALLED")

    def test_install_two_generations_then_restore_previous_verified_package(self):
        prepared_one = prepare_attested_guide_package(**self.args())
        installed_one = install_attested_guide_package(
            prepared=prepared_one, install_root=self.install,
            build_head_sha=HEAD, witness=self.witness,
        )
        changed_source = source()
        changed_source["guides"][0]["steps"][0]["actions"][0]["text"] = (
            "Aller prudemment en [4,-7]"
        )
        preview_two = prepare_preview(
            changed_source, expected_guides=1, expected_steps=1,
        )
        staged_two = publish_candidate(
            preview_two, root=self.store,
            expected_selected=self.staged["candidate_sha256"],
        )
        out_two = self.root / "package-two"

        def both_sources(guide_id, digest, source_sha, head, certificate):
            return (guide_id == GUIDE and head == HEAD and certificate == CERT
                    and source_sha in {
                        self.preview["source_sha256"], preview_two["source_sha256"],
                    }
                    and isinstance(digest, str) and len(digest) == 64)

        prepared_two = prepare_attested_guide_package(
            candidate_root=self.store,
            expected_selected=staged_two["candidate_sha256"],
            route_id=GUIDE, destination=out_two,
            build_head_sha=HEAD, certificate_ref=CERT, witness=both_sources,
        )
        installed_two = install_attested_guide_package(
            prepared=prepared_two, install_root=self.install,
            expected_selected=installed_one["selected_sha256"],
            build_head_sha=HEAD, witness=both_sources,
        )
        self.assertNotEqual(
            installed_two["selected_sha256"], installed_one["selected_sha256"],
        )
        restored = rollback_installed_guide_package(
            install_root=self.install,
            expected_selected=installed_two["selected_sha256"],
            restore_sha256=installed_one["selected_sha256"],
            build_head_sha=HEAD, witness=both_sources,
        )
        self.assertEqual(restored["selected_sha256"], installed_one["selected_sha256"])
        selected = selected_installed_guide_package(
            install_root=self.install, build_head_sha=HEAD, witness=both_sources,
        )
        self.assertEqual(selected["selected_sha256"], installed_one["selected_sha256"])


if __name__ == "__main__":
    unittest.main()
