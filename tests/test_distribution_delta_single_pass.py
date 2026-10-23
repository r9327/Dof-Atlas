"""Integrity-preserving one-pass copies for unchanged differential files."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution.install import _copy_unchanged_verified
from app.distribution.manifest import ReleaseFile
from app.distribution.release_client import UpdateError


class DifferentialUnchangedFileTests(unittest.TestCase):
    def test_copy_has_expected_contents_without_separate_checksum_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "previous.bin"
            target = root / "next.bin"
            content = b"atlas-unchanged" * 100000
            original.write_bytes(content)
            entry = ReleaseFile("AtlasApp/unchanged.bin", len(content), hashlib.sha256(content).hexdigest())
            with patch("app.distribution.install.verify_file", side_effect=AssertionError("double hashing")):
                _copy_unchanged_verified(original, target, entry)
            self.assertEqual(target.read_bytes(), content)

    def test_mismatched_hash_refuses_copied_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "previous.bin"
            target = root / "next.bin"
            original.write_bytes(b"tampered")
            expected = ReleaseFile("AtlasApp/unchanged.bin", 8, hashlib.sha256(b"original").hexdigest())
            with self.assertRaisesRegex(UpdateError, "modified or missing"):
                _copy_unchanged_verified(original, target, expected)

    def test_missing_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = ReleaseFile("AtlasApp/missing.bin", 8, hashlib.sha256(b"original").hexdigest())
            with self.assertRaisesRegex(UpdateError, "modified or missing"):
                _copy_unchanged_verified(root / "missing.bin", root / "output.bin", entry)


if __name__ == "__main__":
    unittest.main()
