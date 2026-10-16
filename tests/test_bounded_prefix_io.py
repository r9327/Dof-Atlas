from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_dofus_data.utils import detect_encoding, load_json_safe
from app.modules.encyclopedia.tools.audit_quests_guides import (
    duplicate_files_by_hash, is_exploitable_image,
)
from tests.test_quests_guides_audit import _ci_image_source_is_valid


class BoundedPrefixIoTests(unittest.TestCase):
    def test_sparse_seventy_megabyte_file_only_reads_prefixes(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "huge.png"
            with image.open("wb") as h:
                h.write(b"\x89PNG\r\n\x1a\n" + b"X" * 8)
                h.truncate(72_317_050)
            original_open = Path.open
            reads = []

            class SpyFile:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    self.stream.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

                def read(self, size=-1):
                    reads.append(size)
                    if size < 0 or size > 513:
                        raise AssertionError(f"unbounded probe read: {size}")
                    return self.stream.read(size)

                def __getattr__(self, name):
                    return getattr(self.stream, name)

            def spy_open(path, *args, **kwargs):
                stream = original_open(path, *args, **kwargs)
                return SpyFile(stream) if args and args[0] == "rb" else stream

            with patch.object(Path, "open", spy_open), patch.object(
                Path, "read_bytes", side_effect=AssertionError("full read forbidden")
            ):
                self.assertEqual(detect_encoding(image), "utf-8")
                self.assertTrue(is_exploitable_image(image))
                self.assertTrue(_ci_image_source_is_valid(image))
            # After rejecting LFS, the image validator makes another bounded
            # 16-byte signature read; assert all four actual reads.
            self.assertEqual(reads, [4, 16, 513, 16])

    def test_bom_utf8_and_utf16_and_short_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "a.json"
            for raw, expected in (
                (b"\xef\xbb\xbf" + b'{"a":1}', "utf-8-sig"),
                ('{"a":1}'.encode("utf-16"), "utf-16"),
                (b'{"a":1}', "utf-8"),
                (b"", "utf-8"),
            ):
                path.write_bytes(raw)
                self.assertEqual(detect_encoding(path), expected)
                if raw:
                    self.assertEqual(load_json_safe(path), {"a": 1})

    def test_svg_bounded_probe_and_lfs_pointer_strictness(self):
        with tempfile.TemporaryDirectory() as temp:
            svg = Path(temp) / "huge.svg"
            with svg.open("wb") as stream:
                stream.write(b'<?xml version="1.0"?><svg xmlns="x"></svg>')
                stream.truncate(72_317_050)
            with patch.object(Path, "read_text", side_effect=AssertionError("full SVG read forbidden")):
                self.assertTrue(is_exploitable_image(svg))
            pointer = Path(temp) / "valid.png"
            prefix = (b"version https://git-lfs.github.com/spec/v1\n"
                      b"oid sha256:" + b"a" * 64 + b"\nsize 90000\n")
            pointer.write_bytes(prefix)
            self.assertTrue(_ci_image_source_is_valid(pointer))
            pointer.write_bytes(prefix + b"junk")
            self.assertFalse(_ci_image_source_is_valid(pointer))
            pointer.write_bytes(prefix + b" " * 520)
            self.assertFalse(_ci_image_source_is_valid(pointer))
            pointer.write_bytes(b"version https://git-lfs.github.com/spec/v1\n"
                                b"oid sha256:bad\nsize 5\n")
            self.assertFalse(_ci_image_source_is_valid(pointer))

    def test_duplicate_digest_reads_full_data_in_chunks(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a.png", Path(temp) / "b.png"
            sample = b"large enough contents" * 1000
            a.write_bytes(sample)
            b.write_bytes(sample)
            result = duplicate_files_by_hash((a, b))
            self.assertEqual(result[hashlib.sha256(sample).hexdigest()], [a, b])


if __name__ == "__main__":
    unittest.main()
