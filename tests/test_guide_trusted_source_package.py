"""Phase 0 synthetic proof for the packaged Guide trust boundary.

No real Ganymede data, source certificate or installed Atlas app is used.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.guide_trusted_source_package import (
    GuidePackageBlocked,
    GuidePackageEntry,
    GuideTrustedSourcePackage,
)
from app.modules.encyclopedia.services.guide_shared_route_contract import (
    project_authorized_guide,
)


def _source_route(guide_id: str = "fictional-trusted") -> dict:
    """Standalone stdlib fixture: never import the Qt-initializing tests package."""
    return project_authorized_guide({
        "guide_id": guide_id,
        "title": f"Fictitious {guide_id}",
        "steps": [
            {
                "source_step_id": "first",
                "title": "Talk to fictional NPC",
                "quest_ids": [123],
                "actions": [
                    {"action_id": "talk", "kind": "talk",
                     "text": "Parler au PNJ fictif", "npc": "PNJ fictif"},
                ],
            },
            {
                "source_step_id": "second",
                "title": "Travel",
                "coordinates": [5, -2],
                "actions": [
                    {"action_id": "travel", "kind": "travel",
                     "text": "Aller en [5,-2]", "coordinates": [5, -2]},
                ],
            },
        ],
    })

TEST_HEAD = "a" * 40
TEST_SOURCE = hashlib.sha256(b"fictional authorized source export").hexdigest()


class TrustedSourcePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.route = _source_route("fictional-trusted")
        self.key = self.route["id"]
        self.file = self.root / "fictional-trusted.json"
        self.approved = True
        self.witness_calls: list[tuple[str, str, str, str, str]] = []
        self.progress = GuideProgressService(self.root / "progress.json")

    def write(self, *, route=None, raw: bytes | None = None) -> GuidePackageEntry:
        if raw is None:
            raw = json.dumps(
                self.route if route is None else route,
                ensure_ascii=False, sort_keys=True,
            ).encode("utf-8")
        self.file.write_bytes(raw)
        return GuidePackageEntry(
            self.key, self.file.name, hashlib.sha256(raw).hexdigest(),
            TEST_SOURCE, TEST_HEAD, "fictional-independent-receipt",
        )

    def witness(
        self, guide_id: str, file_sha: str, source_sha: str,
        head_sha: str, receipt: str,
    ) -> bool:
        self.witness_calls.append((guide_id, file_sha, source_sha, head_sha, receipt))
        return (
            self.approved and guide_id == self.key
            and source_sha == TEST_SOURCE and head_sha == TEST_HEAD
            and receipt == "fictional-independent-receipt"
        )

    def loader(self, entry: GuidePackageEntry) -> GuideTrustedSourcePackage:
        return GuideTrustedSourcePackage(
            self.root, {self.key: entry},
            build_head_sha=TEST_HEAD, witness=self.witness,
        )

    def test_lazy_factory_binds_exact_route_to_recheckable_authorizer(self):
        entry = self.write()
        loader = self.loader(entry)
        services = loader.factories(
            SimpleNamespace(), SimpleNamespace(), self.progress,
        )
        self.assertEqual(self.witness_calls, [])
        self.assertEqual(loader._loaded, {})
        self.assertEqual(tuple(services), (self.key,))
        service = services[self.key]()
        service.set_authorization_guard(loader.authorize)
        self.assertEqual(len(self.witness_calls), 1)
        self.assertEqual(service.guide_id, self.key)
        self.assertTrue(service.can_write_progress())
        self.assertFalse((self.root / "progress.json").exists())
        stage = service.cards[0]
        service.set_page_checked("character:1", stage, 0, True)
        self.assertTrue(service.page_checked("character:1", stage))
        self.approved = False
        self.assertFalse(loader.authorize(self.key, service.route))
        service.set_page_checked("character:1", stage, 0, False)
        self.assertTrue(service.page_checked("character:1", stage))
        self.approved = True
        service.route["steps"][0]["manual_title"] = "Injected UI content"
        self.assertFalse(loader.authorize(self.key, service.route))

    def test_retired_imported_service_cannot_reactivate_or_persist_progress(self):
        entry = self.write()
        loader = self.loader(entry)
        service = loader.factories(
            SimpleNamespace(), SimpleNamespace(), self.progress,
        )[self.key]()
        service.set_authorization_guard(loader.authorize)
        self.assertTrue(service.can_write_progress())
        service.retire()
        self.assertFalse(service.can_write_progress())
        with self.assertRaisesRegex(RuntimeError, "retired"):
            service.set_authorization_guard(loader.authorize)
        service.set_page_checked("character:1", service.cards[0], 0, True)
        self.assertFalse((self.root / "progress.json").exists())

    def test_installed_file_changes_revoke_existing_progress_permission(self):
        entry = self.write()
        loader = self.loader(entry)
        service = loader.factories(
            SimpleNamespace(), SimpleNamespace(), self.progress,
        )[self.key]()
        service.set_authorization_guard(loader.authorize)
        self.assertTrue(service.can_write_progress())
        self.file.write_bytes(self.file.read_bytes() + b" ")
        self.assertFalse(service.can_write_progress())
        service.set_page_checked("character:1", service.cards[0], 0, True)
        self.assertFalse((self.root / "progress.json").exists())

    def test_stale_code_head_and_unpinned_source_are_blocked(self):
        entry = self.write()
        with self.assertRaisesRegex(GuidePackageBlocked, "different app HEAD"):
            GuideTrustedSourcePackage(
                self.root, {self.key: entry},
                build_head_sha="b" * 40, witness=self.witness,
            )
        with self.assertRaisesRegex(GuidePackageBlocked, "source SHA-256"):
            GuidePackageEntry(
                self.key, self.file.name, entry.sha256,
                "0" * 64, TEST_HEAD, "receipt",
            )
        with self.assertRaisesRegex(GuidePackageBlocked, "exact app Git HEAD"):
            GuidePackageEntry(
                self.key, self.file.name, entry.sha256,
                TEST_SOURCE, "0" * 40, "receipt",
            )

    def test_wrong_bytes_and_wrong_id_are_blocked_before_authorization(self):
        entry = self.write()
        loader = self.loader(entry)
        self.file.write_bytes(self.file.read_bytes() + b" ")
        with self.assertRaisesRegex(GuidePackageBlocked, "SHA-256 mismatch"):
            loader.load_route(self.key)
        self.assertEqual(self.witness_calls, [])
        other = _source_route("fictional-other")
        entry = self.write(route=other)
        with self.assertRaisesRegex(GuidePackageBlocked, "mismatched"):
            self.loader(entry).load_route(self.key)

    def test_absent_or_revoked_witness_cannot_be_replaced_by_source_claim(self):
        entry = self.write()
        with self.assertRaisesRegex(GuidePackageBlocked, "witness"):
            GuideTrustedSourcePackage(
                self.root, {self.key: entry},
                build_head_sha=TEST_HEAD, witness=None,
            )
        self.approved = False
        with self.assertRaisesRegex(GuidePackageBlocked, "certificate"):
            self.loader(entry).load_route(self.key)
        self.approved = True
        poisoned = dict(self.route, source_compliance="CERTIFIED")
        entry = self.write(route=poisoned)
        with self.assertRaisesRegex(GuidePackageBlocked, "Invalid"):
            self.loader(entry).load_route(self.key)

    def test_attested_file_with_forged_ui_projection_is_rejected(self):
        # A forged or lossy projected route must fail even when the supplied
        # synthetic witness approves its exact SHA. Metadata is not a proof.
        forged = copy.deepcopy(self.route)
        forged["steps"][0]["manual_title"] = "Injected UI text"
        entry = self.write(route=forged)
        with self.assertRaisesRegex(GuidePackageBlocked, "differs from authored source"):
            self.loader(entry).load_route(self.key)
        forged = copy.deepcopy(self.route)
        forged["steps"][0]["manual_sections"]["now"].clear()
        entry = self.write(route=forged)
        with self.assertRaisesRegex(GuidePackageBlocked, "differs from authored source"):
            self.loader(entry).load_route(self.key)

    def test_duplicate_json_keys_and_nonfinite_values_are_rejected(self):
        raw = (b'{"id":"source_guide:fictional-trusted",'
               b'"id":"source_guide:fictional-trusted",'
               b'"source_compliance":"NOT_CERTIFIED","steps":[]}')
        entry = self.write(raw=raw)
        with self.assertRaisesRegex(GuidePackageBlocked, "Duplicate"):
            self.loader(entry).load_route(self.key)
        raw = (b'{"id":"source_guide:fictional-trusted",'
               b'"source_compliance":"NOT_CERTIFIED",'
               b'"index":NaN,"steps":[]}')
        entry = self.write(raw=raw)
        with self.assertRaises(GuidePackageBlocked):
            self.loader(entry).load_route(self.key)

    def test_traversal_wrong_root_and_duplicate_package_ownership_are_rejected(self):
        entry = self.write()
        with self.assertRaises(GuidePackageBlocked):
            GuidePackageEntry(self.key, "../other.json", entry.sha256, TEST_SOURCE, TEST_HEAD, "receipt")
        with self.assertRaises(GuidePackageBlocked):
            GuidePackageEntry(self.key, "folder/other.json", entry.sha256, TEST_SOURCE, TEST_HEAD, "receipt")
        with self.assertRaises(GuidePackageBlocked):
            GuidePackageEntry(self.key, self.file.name, "not-a-hash", TEST_SOURCE, TEST_HEAD, "receipt")
        with self.assertRaises(GuidePackageBlocked):
            GuideTrustedSourcePackage(
                self.root / "missing", {self.key: entry},
                build_head_sha=TEST_HEAD, witness=self.witness,
            )
        other = GuidePackageEntry(
            "source_guide:another-fictional", entry.filename, entry.sha256,
            TEST_SOURCE, TEST_HEAD, "receipt",
        )
        with self.assertRaisesRegex(GuidePackageBlocked, "two Guide identities"):
            GuideTrustedSourcePackage(
                self.root, {self.key: entry, other.guide_id: other},
                build_head_sha=TEST_HEAD, witness=self.witness,
            )

    def test_symlink_to_route_is_rejected(self):
        entry = self.write()
        original = self.root / "real.json"
        self.file.replace(original)
        try:
            self.file.symlink_to(original)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this test platform")
        with self.assertRaisesRegex(GuidePackageBlocked, "redirected"):
            self.loader(entry).load_route(self.key)


if __name__ == "__main__":
    unittest.main()
