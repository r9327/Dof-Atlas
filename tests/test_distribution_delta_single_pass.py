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

    def test_immutable_image_uses_link_and_checks_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "old.png"
            target = root / "new.png"
            content = b"atlas-picture" * 100000
            original.write_bytes(content)
            entry = ReleaseFile(
                "AtlasApp/_internal/data/encyclopedia/images/quests/old.png",
                len(content), hashlib.sha256(content).hexdigest(),
            )
            marks = []
            _copy_unchanged_verified(original, target, entry, marks.append)
            self.assertTrue(target.samefile(original))
            self.assertEqual(target.read_bytes(), content)
            self.assertEqual(marks[-1], len(content))
            self.assertGreater(len(marks), 1)

    def test_unlinkable_image_falls_back_to_verified_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "old.png"
            target = root / "new.png"
            content = b"atlas-picture" * 100000
            original.write_bytes(content)
            entry = ReleaseFile(
                "AtlasApp/_internal/data/images/old.png",
                len(content), hashlib.sha256(content).hexdigest(),
            )
            with patch("app.distribution.install.os.link", side_effect=OSError("no hardlinks")):
                _copy_unchanged_verified(original, target, entry)
            self.assertFalse(target.samefile(original))
            self.assertEqual(target.read_bytes(), content)

    def test_mutable_and_executable_files_never_share_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b"must-be-independent" * 10000
            for path in (
                "AtlasApp/_internal/data/cache/map.png",
                "AtlasApp/_internal/data/bootstrap/craft_seed.sqlite",
                "AtlasApp/_internal/data/raw/quests.json",
                "AtlasApp/AtlasApp.exe",
            ):
                with self.subTest(path=path):
                    original = root / "original"
                    target = root / "new"
                    original.write_bytes(content)
                    entry = ReleaseFile(path, len(content), hashlib.sha256(content).hexdigest())
                    with patch("app.distribution.install.os.link",
                               side_effect=AssertionError("unexpected hardlink")):
                        _copy_unchanged_verified(original, target, entry)
                    self.assertFalse(target.samefile(original))
                    self.assertEqual(target.read_bytes(), content)
                    target.unlink()

    def test_tampered_linkable_image_aborts_before_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "old.png"
            target = root / "new.png"
            content = b"tampered-image" * 15000
            original.write_bytes(content)
            entry = ReleaseFile(
                "AtlasApp/_internal/data/images/old.png", len(content),
                hashlib.sha256(b"trusted" * 25000).hexdigest(),
            )
            with self.assertRaisesRegex(UpdateError, "modified or missing"):
                _copy_unchanged_verified(original, target, entry)

    def test_missing_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = ReleaseFile("AtlasApp/missing.bin", 8, hashlib.sha256(b"original").hexdigest())
            with self.assertRaisesRegex(UpdateError, "modified or missing"):
                _copy_unchanged_verified(root / "missing.bin", root / "output.bin", entry)


if __name__ == "__main__":
    unittest.main()
