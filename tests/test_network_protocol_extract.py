from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.network.build_fingerprint import ProtocolBuildFiles
from app.network.protocol_extract import ProtocolExtractionError, extract_protocol_from_build


class FakeExtractionRunner:
    def __init__(
        self,
        il2cpp_tool: Path,
        protodec_tool: Path,
        *,
        ankama_marker: bool = True,
        fail_tool: str = "",
        mutate_protodec: bool = False,
    ) -> None:
        self.il2cpp_tool = il2cpp_tool
        self.protodec_tool = protodec_tool
        self.ankama_marker = ankama_marker
        self.fail_tool = fail_tool
        self.mutate_protodec = mutate_protodec
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        command = [str(value) for value in command]
        self.commands.append(command)
        executable = Path(command[0])
        if executable == self.il2cpp_tool:
            if self.fail_tool == "il2cpp":
                return SimpleNamespace(returncode=9, stdout="dumper failed")
            output_dir = Path(command[3])
            dummy = output_dir / "DummyDll"
            dummy.mkdir(parents=True, exist_ok=True)
            (dummy / "Ankama.Dofus.Protocol.Game.dll").write_bytes(b"dummy")
            return SimpleNamespace(returncode=0, stdout="ok")
        if executable == self.protodec_tool:
            if self.fail_tool == "protodec":
                return SimpleNamespace(returncode=7, stdout="protodec failed")
            output_dir = Path(command[2])
            output_dir.mkdir(parents=True, exist_ok=True)
            marker = "// Ankama.Dofus.Protocol.Game\n" if self.ankama_marker else "// unrelated\n"
            (output_dir / "game.proto").write_text(
                'syntax = "proto3";\n' + marker + "message irj { int32 a = 1; }\n",
                encoding="utf-8",
            )
            if self.mutate_protodec:
                self.protodec_tool.write_bytes(b"changed-tool")
            return SimpleNamespace(returncode=0, stdout="ok")
        raise AssertionError(f"unexpected command: {command}")


class NetworkProtocolExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game_assembly = self.root / "GameAssembly.dll"
        self.metadata = self.root / "global-metadata.dat"
        self.game_assembly.write_bytes(b"game-assembly")
        self.metadata.write_bytes(b"metadata")
        self.files = ProtocolBuildFiles(self.game_assembly, self.metadata)
        self.il2cpp_tool = self.root / "Il2CppDumper.exe"
        self.protodec_tool = self.root / "protodec.exe"
        self.il2cpp_tool.write_bytes(b"il2cpp-tool")
        self.protodec_tool.write_bytes(b"protodec-tool")
        self.output = self.root / "extract"
        self.build = "a" * 64

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def extract(self, runner: FakeExtractionRunner, *, post_build: str | None = None):
        return extract_protocol_from_build(
            self.files,
            self.build,
            il2cpp_dumper_path=self.il2cpp_tool,
            protodec_path=self.protodec_tool,
            output_dir=self.output,
            post_build_sha256_provider=(lambda: post_build or self.build),
            runner=runner,
        )

    def test_extracts_individual_ankama_protos_and_writes_privacy_safe_manifest(self) -> None:
        runner = FakeExtractionRunner(self.il2cpp_tool, self.protodec_tool)
        result = self.extract(runner)

        self.assertEqual(result.build_sha256, self.build)
        self.assertEqual(result.dummy_dll_count, 1)
        self.assertEqual(result.proto_file_count, 1)
        self.assertEqual(result.ankama_proto_file_count, 1)
        self.assertEqual(len(result.proto_tree_sha256), 64)
        self.assertEqual(len(runner.commands), 2)
        self.assertEqual(Path(runner.commands[0][3]), self.output / "il2cpp")
        self.assertEqual(Path(runner.commands[1][1]), self.output / "il2cpp" / "DummyDll")
        self.assertEqual(Path(runner.commands[1][2]), self.output / "protos" / "decompiled")

        manifest = json.loads((self.output / "extraction_manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["authoritative_mapping"])
        self.assertFalse(manifest["game_files_copied"])
        self.assertEqual(manifest["output_dir"], ".")
        serialized = json.dumps(manifest)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn(str(self.game_assembly), serialized)
        self.assertNotIn(str(self.metadata), serialized)

    def test_existing_nonempty_output_is_never_reused(self) -> None:
        self.output.mkdir()
        (self.output / "stale.txt").write_text("stale", encoding="utf-8")
        runner = FakeExtractionRunner(self.il2cpp_tool, self.protodec_tool)
        with self.assertRaises(ProtocolExtractionError):
            self.extract(runner)
        self.assertEqual(runner.commands, [])

    def test_tool_failure_fails_closed(self) -> None:
        runner = FakeExtractionRunner(
            self.il2cpp_tool,
            self.protodec_tool,
            fail_tool="il2cpp",
        )
        with self.assertRaisesRegex(ProtocolExtractionError, "Il2CppDumper exited with code 9"):
            self.extract(runner)

    def test_no_ankama_protocol_marker_fails_closed(self) -> None:
        runner = FakeExtractionRunner(
            self.il2cpp_tool,
            self.protodec_tool,
            ankama_marker=False,
        )
        with self.assertRaisesRegex(ProtocolExtractionError, "no Ankama Dofus protocol"):
            self.extract(runner)

    def test_build_change_during_extraction_fails_closed(self) -> None:
        runner = FakeExtractionRunner(self.il2cpp_tool, self.protodec_tool)
        with self.assertRaisesRegex(ProtocolExtractionError, "build changed"):
            self.extract(runner, post_build="b" * 64)

    def test_tool_change_during_extraction_fails_closed(self) -> None:
        runner = FakeExtractionRunner(
            self.il2cpp_tool,
            self.protodec_tool,
            mutate_protodec=True,
        )
        with self.assertRaisesRegex(ProtocolExtractionError, "protodec executable changed"):
            self.extract(runner)


if __name__ == "__main__":
    unittest.main()
