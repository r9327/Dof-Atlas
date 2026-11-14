"""Phase 0 synthetic proof for the packaged Guide trust boundary.

No real Ganymede data, source certificate or installed Atlas app is used.
"""
from __future__ import annotations

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
from tests.test_guide_imported_manual_runtime_service import _source_route


class TrustedSourcePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.route = _source_route("fictional-trusted")
        self.key = self.route["id"]
        self.file = self.root / "fictional-trusted.json"
        self.approved = True
        self.witness_calls: list[tuple[str, str, str]] = []
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
            "fictional-independent-receipt",
        )

    def witness(self, guide_id: str, file_sha: str, receipt: str) -> bool:
        self.witness_calls.append((guide_id, file_sha, receipt))
        return self.approved and guide_id == self.key and receipt == "fictional-independent-receipt"

    def loader(self, entry: GuidePackageEntry) -> GuideTrustedSourcePackage:
        return GuideTrustedSourcePackage(
            self.root, {self.key: entry}, witness=self.witness,
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
            GuideTrustedSourcePackage(self.root, {self.key: entry}, witness=None)
        self.approved = False
        with self.assertRaisesRegex(GuidePackageBlocked, "certificate"):
            self.loader(entry).load_route(self.key)
        self.approved = True
        poisoned = dict(self.route, source_compliance="CERTIFIED")
        entry = self.write(route=poisoned)
        with self.assertRaisesRegex(GuidePackageBlocked, "Invalid"):
            self.loader(entry).load_route(self.key)

    def test_duplicate_json_keys_and_nonfinite_values_are_rejected(self):
        raw = json.dumps(self.route).encode("utf-8")
        raw = raw.replace(b'{"id": ', b'{"id": "source_guide:fictional-trusted", "id": ', 1)
        entry = self.write(raw=raw)
        with self.assertRaisesRegex(GuidePackageBlocked, "Duplicate"):
            self.loader(entry).load_route(self.key)
        raw = json.dumps(self.route, allow_nan=True).encode("utf-8")
        raw = raw.replace(b'"index": 1', b'"index": NaN', 1)
        entry = self.write(raw=raw)
        with self.assertRaises(GuidePackageBlocked):
            self.loader(entry).load_route(self.key)

    def test_traversal_wrong_root_and_duplicate_package_ownership_are_rejected(self):
        entry = self.write()
        with self.assertRaises(GuidePackageBlocked):
            GuidePackageEntry(self.key, "../other.json", entry.sha256, "receipt")
        with self.assertRaises(GuidePackageBlocked):
            GuidePackageEntry(self.key, "folder/other.json", entry.sha256, "receipt")
        with self.assertRaises(GuidePackageBlocked):
            GuidePackageEntry(self.key, self.file.name, "not-a-hash", "receipt")
        with self.assertRaises(GuidePackageBlocked):
            GuideTrustedSourcePackage(
                self.root / "missing", {self.key: entry}, witness=self.witness,
            )
        other = GuidePackageEntry(
            "source_guide:another-fictional", entry.filename, entry.sha256, "receipt",
        )
        with self.assertRaisesRegex(GuidePackageBlocked, "two Guide identities"):
            GuideTrustedSourcePackage(
                self.root, {self.key: entry, other.guide_id: other},
                witness=self.witness,
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
