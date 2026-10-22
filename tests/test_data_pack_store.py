from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from app.distribution.data_pack_plan import DataPack, InvalidDataPack
from app.distribution.data_pack_store import (
    acknowledge_pack, active_pack, install_pack, rollback_pack,
)


class DataPackStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "install"
        self.staging = Path(self.temp.name) / "staging"
        self.user = self.root / "user" / "characters.json"
        self.user.parent.mkdir(parents=True)
        self.user.write_text('{"favorite":"Panda"}', encoding="utf-8")

    def artifact(self, revision: int, content: bytes, kind: str = "quests") -> DataPack:
        digest = sha256(content).hexdigest()
        filename = f"data/{kind}/v{revision}.json"
        path = self.staging / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return DataPack(kind, revision, 1, digest, filename)

    def test_install_and_acknowledge_are_atomic_for_user_data(self):
        pack = self.artifact(1, b'{"id":1}')
        self.assertEqual(install_pack(self.root, self.staging, pack), "INSTALLED")
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b'{"id":1}')
        self.assertEqual(self.user.read_text(encoding="utf-8"), '{"favorite":"Panda"}')
        self.assertTrue(acknowledge_pack(self.root, "quests"))
        self.assertFalse(acknowledge_pack(self.root, "quests"))
        self.assertEqual(install_pack(self.root, self.staging, pack), "ALREADY_ACTIVE")

    def test_upgrade_then_rollback_restores_verified_previous(self):
        old = self.artifact(1, b"old")
        install_pack(self.root, self.staging, old)
        acknowledge_pack(self.root, "quests")
        new = self.artifact(2, b"new")
        self.assertEqual(install_pack(self.root, self.staging, new), "INSTALLED")
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"new")
        self.assertTrue(rollback_pack(self.root, "quests"))
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"old")
        self.assertFalse(rollback_pack(self.root, "quests"))
        self.assertEqual(self.user.read_text(encoding="utf-8"), '{"favorite":"Panda"}')

    def test_new_install_rollback_clears_active_without_fake_previous(self):
        first = self.artifact(1, b"initial")
        self.assertEqual(install_pack(self.root, self.staging, first), "INSTALLED")
        self.assertTrue(rollback_pack(self.root, "quests"))
        self.assertIsNone(active_pack(self.root, "quests"))

    def test_pending_pack_blocks_second_update(self):
        first = self.artifact(1, b"v1")
        install_pack(self.root, self.staging, first)
        second = self.artifact(2, b"v2")
        with self.assertRaisesRegex(InvalidDataPack, "health validation"):
            install_pack(self.root, self.staging, second)
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"v1")

    def test_integrity_error_never_replaces_healthy_pack(self):
        first = self.artifact(1, b"original")
        install_pack(self.root, self.staging, first)
        acknowledge_pack(self.root, "quests")
        second = self.artifact(2, b"candidate")
        (self.staging / second.artifact_path).write_bytes(b"tampered")
        with self.assertRaises(InvalidDataPack):
            install_pack(self.root, self.staging, second)
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"original")

    def test_rollback_and_acknowledge_refuse_corrupted_blobs(self):
        old = self.artifact(1, b"old")
        install_pack(self.root, self.staging, old)
        acknowledge_pack(self.root, "quests")
        new = self.artifact(2, b"new")
        install_pack(self.root, self.staging, new)
        self.assertIsNotNone(active_pack(self.root, "quests"))
        assert old.sha256 != new.sha256
        old_path = self.root / "data-pack-store" / "versions" / "quests" / f"1-{old.sha256}.blob"
        old_path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(InvalidDataPack, "rollback pack"):
            rollback_pack(self.root, "quests")
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"new")
        active_pack(self.root, "quests").write_bytes(b"corrupt")
        with self.assertRaises(InvalidDataPack):
            acknowledge_pack(self.root, "quests")

    def test_pack_index_write_failure_keeps_old_active(self):
        first = self.artifact(1, b"v1")
        install_pack(self.root, self.staging, first)
        acknowledge_pack(self.root, "quests")
        second = self.artifact(2, b"v2")
        from app.distribution import data_pack_store
        real_replace = data_pack_store.os.replace
        def faulty_replace(src, dst):
            if str(dst).endswith("state.json"):
                raise OSError("simulated interruption")
            return real_replace(src, dst)
        with patch.object(data_pack_store.os, "replace", side_effect=faulty_replace):
            with self.assertRaises(OSError):
                install_pack(self.root, self.staging, second)
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"v1")

    def test_two_kinds_are_isolated(self):
        quest = self.artifact(1, b"quest", "quests")
        guide = self.artifact(1, b"guide", "guides")
        install_pack(self.root, self.staging, quest)
        acknowledge_pack(self.root, "quests")
        install_pack(self.root, self.staging, guide)
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"quest")
        self.assertEqual(active_pack(self.root, "guides").read_bytes(), b"guide")
        rollback_pack(self.root, "guides")
        self.assertIsNone(active_pack(self.root, "guides"))
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"quest")

    def test_corrupted_index_refused_without_reset(self):
        pack = self.artifact(1, b"good")
        install_pack(self.root, self.staging, pack)
        index = self.root / "data-pack-store" / "state.json"
        index.write_text("{corrupt", encoding="utf-8")
        with self.assertRaisesRegex(InvalidDataPack, "corrupt pack index"):
            active_pack(self.root, "quests")
        self.assertEqual(index.read_text(encoding="utf-8"), "{corrupt")

    def test_version_downgrade_refused(self):
        newer = self.artifact(2, b"latest")
        install_pack(self.root, self.staging, newer)
        acknowledge_pack(self.root, "quests")
        older = self.artifact(1, b"old")
        with self.assertRaisesRegex(InvalidDataPack, "downgrade"):
            install_pack(self.root, self.staging, older)
        self.assertEqual(active_pack(self.root, "quests").read_bytes(), b"latest")


if __name__ == "__main__":
    unittest.main()
