import hashlib
from pathlib import Path
import tempfile
import unittest

from app.distribution.data_pack_plan import DataPack, InvalidDataPack
from app.distribution.data_pack_verify import verify_staged_pack

CONTENT = b'{"records":[{"id":1,"name":"quest"}]}'
SHA = hashlib.sha256(CONTENT).hexdigest()


class PackVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "data" / "quests" / "v2.json"
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(CONTENT)
        self.pack = DataPack("quests", 2, 1, SHA, "data/quests/v2.json")

    def test_verifies_downloaded_bytes_without_mutation(self):
        before = self.file.read_bytes()
        result = verify_staged_pack(self.pack, self.root)
        self.assertEqual(result.status, "VERIFIED_BLOB_ONLY")
        self.assertEqual(result.bytes_checked, len(CONTENT))
        self.assertEqual(self.file.read_bytes(), before)

    def test_rejects_wrong_digest(self):
        wrong = DataPack("quests", 2, 1, "b" * 64, "data/quests/v2.json")
        with self.assertRaisesRegex(InvalidDataPack, "SHA-256"):
            verify_staged_pack(wrong, self.root)

    def test_rejects_oversized_blob(self):
        with self.assertRaisesRegex(InvalidDataPack, "maximum"):
            verify_staged_pack(self.pack, self.root, max_bytes=len(CONTENT)-1)

    def test_rejects_missing_staged_blob(self):
        self.file.unlink()
        with self.assertRaises(InvalidDataPack):
            verify_staged_pack(self.pack, self.root)

    def test_rejects_path_traversal(self):
        bad = DataPack("quests", 2, 1, SHA, "data/../outside.json")
        with self.assertRaises(InvalidDataPack):
            verify_staged_pack(bad, self.root)


if __name__ == "__main__":
    unittest.main()
