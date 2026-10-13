"""Package a frozen AtlasApp onedir tree as a release archive + file manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from app.distribution.manifest import parse_manifest, valid_path

_BLOCKED = {".git", ".github", "tests", "tools", "logs", ".cache", "__pycache__"}
_PRIVATE = {"client_profiles.json", "client_index.json", "client_index.ini",
            "network_character_bindings.json", "craft_selection.json",
            "quest_progress.json", "bootstrap_status.txt"}
_LFS = b"version https://git-lfs.github.com/spec/v1"
_RUNTIME_SEEDS = {"_internal/data/local/zaaps.json"}


def _publishable(relative: Path) -> bool:
    if relative.as_posix() in _RUNTIME_SEEDS:
        return True
    parts = relative.parts
    if any(piece in _BLOCKED for piece in parts):
        return False
    if any(piece.lower() in ("data", "_internal") and parts[i + 1:i + 2] == ("local",)
           for i, piece in enumerate(parts)):
        return False
    if relative.name.lower() in _PRIVATE or relative.suffix.lower() in (".pem", ".key", ".pfx", ".env"):
        return False
    return True


def package_release(payload_dir: Path, output_dir: Path, source_sha: str, app_version: str,
                    data_version: str, schema_version: int) -> tuple[Path, Path]:
    if not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("source_sha must be a verified 40-character GitHub SHA")
    if not payload_dir.is_dir() or not (payload_dir / "AtlasApp.exe").is_file():
        raise ValueError("PyInstaller AtlasApp.exe output is missing")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / "atlas-windows.zip"
    manifest_path = output_dir / "atlas-manifest.json"
    entries = []
    paths = sorted((p for p in payload_dir.rglob("*") if p.is_file()), key=lambda p: str(p).casefold())
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in paths:
            if path.is_symlink() or any(part.is_symlink() for part in path.parents if part != payload_dir):
                raise ValueError("Symlinks are forbidden in release packages")
            relative = path.relative_to(payload_dir)
            if not _publishable(relative):
                continue
            name = valid_path("AtlasApp/" + relative.as_posix())
            digest = hashlib.sha256()
            with path.open("rb") as source:
                prefix = source.read(len(_LFS))
                if prefix == _LFS:
                    raise ValueError(f"Git LFS pointer was not materialized: {relative}")
                digest.update(prefix)
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            archive.write(path, arcname=name, compress_type=zipfile.ZIP_DEFLATED,
                          compresslevel=6)
            entries.append({"path": name, "size": path.stat().st_size, "sha256": digest.hexdigest()})
    manifest = {
        "protocol_version": 1, "app_version": app_version,
        "data_version": data_version, "schema_version": schema_version,
        "source_sha": source_sha, "entrypoint": "AtlasApp/AtlasApp.exe",
        "files": entries,
    }
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    parse_manifest(payload)  # Fail the build if the updater cannot accept the package.
    manifest_path.write_bytes(payload)
    return archive_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--schema-version", type=int, default=1)
    options = parser.parse_args()
    for file in package_release(options.payload, options.output, options.source_sha,
                                options.app_version, options.data_version, options.schema_version):
        print(file)


if __name__ == "__main__":
    main()
