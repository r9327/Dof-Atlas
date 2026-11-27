"""Shared streaming digest used by Guide and Quest release manifests."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from app.core.file_hash import sha256_file


class FileHashTests(unittest.TestCase):
    def test_empty_and_multichunk_files_have_exact_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.bin"
            for payload in (b"", b"Atlas", (b"atlas-release" * 100_000)):
                with self.subTest(size=len(payload)):
                    path.write_bytes(payload)
                    self.assertEqual(sha256_file(path), hashlib.sha256(payload).hexdigest())

    def test_missing_file_keeps_io_failure_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                sha256_file(Path(directory) / "missing.bin")


if __name__ == "__main__":
    unittest.main()
