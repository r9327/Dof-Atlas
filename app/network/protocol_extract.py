from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from app.constants import ROOT_DIR
from app.core.admin import process_id_for_window
from app.core.settings import load_settings
from app.network.build_fingerprint import (
    ActiveProtocolBuildFingerprintProvider,
    ProtocolBuildFiles,
    process_executable_path,
    protocol_build_files_for_executable,
)


DEFAULT_PROTOCOL_EXTRACT_ROOT = ROOT_DIR / ".cache" / "dofus_atlas" / "protocol_extract"
_REQUIRED_ASSEMBLY_MARKERS = (
    "Ankama.Dofus.Protocol.Connection",
    "Ankama.Dofus.Protocol.Game",
)


class ProtocolExtractionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProtocolExtractionResult:
    build_sha256: str
    output_dir: Path
    dummy_dll_count: int
    proto_file_count: int
    ankama_proto_file_count: int
    proto_tree_sha256: str
    il2cpp_dumper_sha256: str
    protodec_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "purpose": "exact_build_protocol_extraction_evidence_only",
            "authoritative_mapping": False,
            "build_sha256": self.build_sha256,
            "output_dir": str(self.output_dir),
            "dummy_dll_count": self.dummy_dll_count,
            "proto_file_count": self.proto_file_count,
            "ankama_proto_file_count": self.ankama_proto_file_count,
            "proto_tree_sha256": self.proto_tree_sha256,
            "il2cpp_dumper_sha256": self.il2cpp_dumper_sha256,
            "protodec_sha256": self.protodec_sha256,
        }


def extract_protocol_from_build(
    files: ProtocolBuildFiles,
    build_sha256: str,
    *,
    il2cpp_dumper_path: str | Path,
    protodec_path: str | Path,
    output_dir: str | Path,
    post_build_sha256_provider: Callable[[], str | None] | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> ProtocolExtractionResult:
    """Extract current-build protobuf files into an isolated local workspace.

    Atlas itself never writes into the Dofus install. Caller-supplied third-party
    tools receive the two IL2CPP input paths and an isolated output directory;
    their exact executable bytes are fingerprinted before and after execution.
    Existing output is never deleted or reused, preventing stale DummyDll/proto
    files from being mistaken for this build.
    """

    build = str(build_sha256 or "").strip().casefold()
    if not _is_sha256(build):
        raise ProtocolExtractionError("invalid Dofus build fingerprint")
    try:
        game_files_available = files.game_assembly.is_file() and files.global_metadata.is_file()
    except OSError as exc:
        raise ProtocolExtractionError("cannot inspect Dofus IL2CPP build files") from exc
    if not game_files_available:
        raise ProtocolExtractionError("Dofus IL2CPP build files are unavailable")

    il2cpp_dumper = _required_tool(il2cpp_dumper_path, "Il2CppDumper")
    protodec = _required_tool(protodec_path, "protodec")
    il2cpp_sha256 = _sha256_file(il2cpp_dumper)
    protodec_sha256 = _sha256_file(protodec)

    root = Path(output_dir)
    if root.exists():
        try:
            if any(root.iterdir()):
                raise ProtocolExtractionError(
                    f"protocol extraction output must be empty: {root}"
                )
        except OSError as exc:
            raise ProtocolExtractionError(f"cannot inspect extraction output: {root}") from exc
    try:
        root.mkdir(parents=True, exist_ok=True)
        il2cpp_output = root / "il2cpp"
        proto_output = root / "protos" / "decompiled"
        il2cpp_output.mkdir(parents=True, exist_ok=False)
        proto_output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise ProtocolExtractionError(f"cannot prepare protocol extraction output: {root}") from exc

    _run_tool(
        runner,
        (
            str(il2cpp_dumper),
            str(files.game_assembly),
            str(files.global_metadata),
            str(il2cpp_output),
        ),
        label="Il2CppDumper",
    )

    dummy_dll = il2cpp_output / "DummyDll"
    dummy_files = tuple(sorted(dummy_dll.glob("*.dll"), key=lambda path: path.name.casefold()))
    if not dummy_dll.is_dir() or not dummy_files:
        raise ProtocolExtractionError("Il2CppDumper produced no DummyDll assemblies")

    _run_tool(
        runner,
        (
            str(protodec),
            str(dummy_dll),
            str(proto_output),
            "--include-properties-without-non-user-code-attribute",
        ),
        label="protodec",
    )

    proto_files = tuple(sorted(proto_output.rglob("*.proto"), key=lambda path: str(path).casefold()))
    if not proto_files:
        raise ProtocolExtractionError("protodec produced no .proto files")
    ankama_proto_count = sum(1 for path in proto_files if _contains_ankama_protocol_marker(path))
    if ankama_proto_count <= 0:
        raise ProtocolExtractionError(
            "protodec output contains no Ankama Dofus protocol assembly markers"
        )

    if _sha256_file(il2cpp_dumper) != il2cpp_sha256:
        raise ProtocolExtractionError("Il2CppDumper executable changed during extraction")
    if _sha256_file(protodec) != protodec_sha256:
        raise ProtocolExtractionError("protodec executable changed during extraction")

    if post_build_sha256_provider is not None:
        try:
            post_build = str(post_build_sha256_provider() or "").strip().casefold()
        except Exception as exc:
            raise ProtocolExtractionError("cannot re-check Dofus build after extraction") from exc
        if post_build != build:
            raise ProtocolExtractionError(
                "Dofus build changed while protocol extraction was running"
            )

    result = ProtocolExtractionResult(
        build_sha256=build,
        output_dir=root,
        dummy_dll_count=len(dummy_files),
        proto_file_count=len(proto_files),
        ankama_proto_file_count=ankama_proto_count,
        proto_tree_sha256=_hash_named_files(proto_files, root=proto_output),
        il2cpp_dumper_sha256=il2cpp_sha256,
        protodec_sha256=protodec_sha256,
    )
    _write_json_atomic(root / "extraction_manifest.json", _manifest_payload(result))
    return result


def resolve_active_protocol_build() -> tuple[ProtocolBuildFiles, str]:
    settings = load_settings()
    handles = tuple(
        dict.fromkeys(
            int(client.handle)
            for client in settings.clients
            if _positive_int(getattr(client, "handle", None)) is not None
        )
    )
    if not handles:
        raise ProtocolExtractionError("no connected Dofus window handle is configured in Dofus Atlas")

    fingerprint_provider = ActiveProtocolBuildFingerprintProvider(lambda: handles)
    build_sha256 = str(fingerprint_provider() or "").strip().casefold()
    if not _is_sha256(build_sha256):
        raise ProtocolExtractionError("could not fingerprint the active Dofus Unity build")

    first_pid = process_id_for_window(handles[0])
    executable = process_executable_path(first_pid)
    if executable is None:
        raise ProtocolExtractionError("could not resolve the active Dofus executable")
    files = protocol_build_files_for_executable(executable)
    if files is None:
        raise ProtocolExtractionError("could not locate Dofus IL2CPP build files")
    return files, build_sha256


def _required_tool(value: str | Path, label: str) -> Path:
    path = Path(value)
    try:
        if not path.is_file():
            raise ProtocolExtractionError(f"{label} executable not found: {path}")
    except OSError as exc:
        raise ProtocolExtractionError(f"cannot inspect {label} executable: {path}") from exc
    return path


def _run_tool(
    runner: Callable[..., Any],
    command: Sequence[str],
    *,
    label: str,
) -> None:
    try:
        completed = runner(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProtocolExtractionError(f"{label} execution failed") from exc
    returncode = int(getattr(completed, "returncode", 1))
    if returncode != 0:
        output = str(getattr(completed, "stdout", "") or "")
        tail = "\n".join(output.splitlines()[-8:]).strip()
        suffix = f": {tail}" if tail else ""
        raise ProtocolExtractionError(f"{label} exited with code {returncode}{suffix}")


def _contains_ankama_protocol_marker(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError):
        return False
    return any(marker in text for marker in _REQUIRED_ASSEMBLY_MARKERS)


def _manifest_payload(result: ProtocolExtractionResult) -> dict[str, Any]:
    payload = result.to_dict()
    payload["output_dir"] = "."
    payload["privacy"] = "tool_hashes_build_fingerprint_and_output_hashes_only"
    payload["game_files_copied"] = False
    return payload


def _hash_named_files(paths: Sequence[Path], *, root: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ProtocolExtractionError("proto output escaped extraction root") from exc
        digest.update(relative.encode("utf-8", errors="strict"))
        digest.update(b"\0")
        try:
            with path.open("rb") as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError as exc:
            raise ProtocolExtractionError(f"cannot hash extracted proto: {path}") from exc
        digest.update(b"\0")
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise ProtocolExtractionError(f"cannot hash tool executable: {path}") from exc
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProtocolExtractionError(f"cannot write extraction manifest: {path}") from exc


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract protobuf schemas from the exact active Dofus Unity build using "
            "caller-supplied Il2CppDumper and protodec executables. Atlas writes only "
            "to the extraction output directory."
        )
    )
    parser.add_argument("--il2cpp-dumper", required=True)
    parser.add_argument("--protodec", required=True)
    parser.add_argument(
        "--output-dir",
        default="",
        help="Empty output directory. Defaults to .cache/dofus_atlas/protocol_extract/<build_sha256>.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        files, build_sha256 = resolve_active_protocol_build()
        output_dir = (
            Path(args.output_dir)
            if str(args.output_dir or "").strip()
            else DEFAULT_PROTOCOL_EXTRACT_ROOT / build_sha256
        )
        fingerprint_provider = ActiveProtocolBuildFingerprintProvider(
            lambda: tuple(
                int(client.handle)
                for client in load_settings().clients
                if _positive_int(getattr(client, "handle", None)) is not None
            )
        )
        result = extract_protocol_from_build(
            files,
            build_sha256,
            il2cpp_dumper_path=args.il2cpp_dumper,
            protodec_path=args.protodec,
            output_dir=output_dir,
            post_build_sha256_provider=fingerprint_provider,
        )
    except (ProtocolExtractionError, OSError, ValueError) as exc:
        print(f"network protocol extraction failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_PROTOCOL_EXTRACT_ROOT",
    "ProtocolExtractionError",
    "ProtocolExtractionResult",
    "extract_protocol_from_build",
    "resolve_active_protocol_build",
]


if __name__ == "__main__":
    raise SystemExit(main())
