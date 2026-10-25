"""Fast, fully offline checks of the Unity reference-asset inventory parser."""
from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools.assets.inspect_unity_assets import PNG_MAGIC, inventory, png_info, png_chunk_integrity


def fake_header(width: int = 48, height: int = 24) -> bytes:
    data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    block = b"IHDR" + data
    return PNG_MAGIC + struct.pack(">I", 13) + block + struct.pack(">I", zlib.crc32(block))


class UnityAssetInventoryTests(unittest.TestCase):
    def test_png_metadata_and_invalid_crc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sprite.png"
            path.write_bytes(fake_header(48, 24))
            self.assertEqual(png_info(path), (48, 24, 6))
            path.write_bytes(fake_header(48, 24)[:-1] + b"0")
            with self.assertRaisesRegex(ValueError, "CRC"):
                png_info(path)


    def test_complete_png_chunks_and_alpha(self) -> None:
        def chunk(kind: bytes, data: bytes) -> bytes:
            payload = kind + data
            return (struct.pack(">I", len(data)) + payload
                    + struct.pack(">I", zlib.crc32(payload)))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "complete.png"
            image = (PNG_MAGIC + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(bytes((0, 255, 0, 0, 255))))
                     + chunk(b"IEND", b""))
            path.write_bytes(image)
            self.assertTrue(png_chunk_integrity(path))
            # A damaged compressed-data chunk must not be marked valid.
            damaged = bytearray(image)
            damaged[47] ^= 1
            path.write_bytes(damaged)
            with self.assertRaisesRegex(ValueError, "CRC"):
                png_chunk_integrity(path)
            # The header alone is insufficient: IDAT and IEND must exist.
            path.write_bytes(fake_header())
            with self.assertRaisesRegex(ValueError, "truncated"):
                png_chunk_integrity(path)

    def test_inventory_fails_closed_without_required_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sprites").mkdir()
            (root / "fonts").mkdir()
            (root / "sprites" / "a.png").write_bytes(fake_header())
            (root / "fonts" / "Lexend-Regular.ttf").write_bytes(b"INVALID FONT")
            report = inventory(root)
            self.assertFalse(report["integrity_pass"])
            self.assertFalse(report["redistribution_authorized"])
            self.assertEqual(report["sprites"], 1)
            self.assertTrue(any("invalid TTF" in issue for issue in report["issues"]))
            self.assertTrue(any("background" in issue for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
