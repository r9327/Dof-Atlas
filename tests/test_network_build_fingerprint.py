from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from app.network.build_fingerprint import (
    ProtocolBuildFiles,
    protocol_build_files_for_executable,
    protocol_build_sha256,
)


class NetworkBuildFingerprintTests(unittest.TestCase):
    def test_supported_unity_layout_is_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "Dofus.exe"
            executable.write_bytes(b"exe")
            assembly = root / "GameAssembly.dll"
            assembly.write_bytes(b"assembly")
            metadata = root / "Dofus_Data" / "il2cpp_data" / "Metadata" / "global-metadata.dat"
            metadata.parent.mkdir(parents=True)
            metadata.write_bytes(b"metadata")

            files = protocol_build_files_for_executable(executable)
            self.assertIsNotNone(files)
            self.assertEqual(files.game_assembly, assembly)
            self.assertEqual(files.global_metadata, metadata)

    def test_missing_protocol_input_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "Dofus.exe"
            executable.write_bytes(b"exe")
            (root / "GameAssembly.dll").write_bytes(b"assembly")
            self.assertIsNone(protocol_build_files_for_executable(executable))

    def test_fingerprint_covers_both_protocol_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assembly = root / "GameAssembly.dll"
            metadata = root / "global-metadata.dat"
            assembly.write_bytes(b"assembly-v1")
            metadata.write_bytes(b"metadata-v1")
            files = ProtocolBuildFiles(assembly, metadata)

            first = protocol_build_sha256(files)
            self.assertIsNotNone(first)
            self.assertEqual(len(first), 64)

            metadata.write_bytes(b"metadata-v2")
            second = protocol_build_sha256(files)
            self.assertIsNotNone(second)
            self.assertNotEqual(first, second)

            expected = hashlib.sha256()
            expected.update(b"GameAssembly.dll\0assembly-v1\0")
            expected.update(b"global-metadata.dat\0metadata-v2\0")
            self.assertEqual(second, expected.hexdigest())


if __name__ == "__main__":
    unittest.main()
