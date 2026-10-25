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
_MAX_GITHUB_RELEASE_ASSET_BYTES = 2 * 1024**3 - 1
# Keep headroom below GitHub's strict 2 GiB-per-asset limit.
_CHUNK_BYTES = 1792 * 1024**2
_RUNTIME_SEEDS = {"_internal/data/local/zaaps.json"}
# Public builds cannot ship game-extracted theme sources without licence.
_UNLICENSED_THEME_COMPONENTS = ("app", "assets", "themes", "dofus_unity")


def _publishable(relative: Path) -> bool:
    if relative.as_posix() in _RUNTIME_SEEDS:
        return True
    parts = relative.parts
    folded = tuple(part.casefold() for part in parts)
    if any(folded[i:i + 4] == _UNLICENSED_THEME_COMPONENTS
           for i in range(len(folded) - 3)):
        return False
    if any(piece in _BLOCKED for piece in parts):
        return False
    if any(piece.lower() in ("data", "_internal") and parts[i + 1:i + 2] == ("local",)
           for i, piece in enumerate(parts)):
        return False
    if relative.name.lower() in _PRIVATE or relative.suffix.lower() in (".pem", ".key", ".pfx", ".env"):
        return False
    return True


def package_release(payload_dir: Path, output_dir: Path, source_sha: str, app_version: str,
                    data_version: str, schema_version: int,
                    launcher: Path | None = None,
                    base_manifest: Path | None = None) -> tuple[Path, Path]:
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
    oversized = archive_path.stat().st_size > _MAX_GITHUB_RELEASE_ASSET_BYTES
    manifest = {
        "protocol_version": 1, "app_version": app_version,
        "data_version": data_version, "schema_version": schema_version,
        "source_sha": source_sha, "entrypoint": "AtlasApp/AtlasApp.exe",
        "files": entries,
    }
    if oversized:
        full_digest = hashlib.sha256()
        pieces = []
        index = 0
        chunk_size = min(_CHUNK_BYTES, _MAX_GITHUB_RELEASE_ASSET_BYTES)
        with archive_path.open("rb") as source:
            while True:
                index += 1
                name = f"atlas-windows.part{index:04d}"
                target = output_dir / name
                part_digest = hashlib.sha256()
                size = 0
                with target.open("wb") as dest:
                    while size < chunk_size:
                        block = source.read(min(1024 * 1024, chunk_size - size))
                        if not block:
                            break
                        dest.write(block)
                        size += len(block)
                        part_digest.update(block)
                        full_digest.update(block)
                if not size:
                    target.unlink(missing_ok=True)
                    break
                pieces.append({"name": name, "size": size, "sha256": part_digest.hexdigest()})
                if len(pieces) > 64:
                    raise ValueError("Release requires too many GitHub assets")
        manifest["archive_parts"] = pieces
        manifest["archive_size"] = archive_path.stat().st_size
        manifest["archive_sha256"] = full_digest.hexdigest()
    if launcher is not None:
        if not launcher.is_file() or launcher.is_symlink() or not 0 < launcher.stat().st_size <= 128 * 1024**2:
            raise ValueError("Invalid Windows launcher asset")
        with launcher.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("Launcher does not contain a Windows executable")
            stream.seek(0)
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        manifest["launcher_sha256"] = digest.hexdigest()
        manifest["launcher_size"] = launcher.stat().st_size
    # Optional delta: changed files only, based on the previous public release.
    # Reusing unchanged files requires checking their SHA-256 on the client.
    if base_manifest is not None and base_manifest.is_file():
        previous = parse_manifest(base_manifest.read_bytes())
        if previous.schema_version == schema_version and previous.source_sha != source_sha:
            old = {entry.path: entry for entry in previous.files}
            changed = [entry for entry in entries if
                       entry["path"] not in old or
                       (entry["size"], entry["sha256"]) !=
                       (old[entry["path"]].size, old[entry["path"]].sha256)]
            if changed:
                delta_archive = output_dir / "atlas-delta.zip"
                with zipfile.ZipFile(delta_archive, "w", zipfile.ZIP_DEFLATED,
                                     compresslevel=6, allowZip64=True) as archive:
                    for entry in changed:
                        source = payload_dir / entry["path"].removeprefix("AtlasApp/")
                        archive.write(source, arcname=entry["path"])
                if (delta_archive.stat().st_size <= _MAX_GITHUB_RELEASE_ASSET_BYTES
                        and delta_archive.stat().st_size < archive_path.stat().st_size):
                    digest = hashlib.sha256()
                    with delta_archive.open("rb") as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(block)
                    manifest["delta"] = {
                        "base_source_sha": previous.source_sha,
                        "archive_sha256": digest.hexdigest(),
                        "archive_size": delta_archive.stat().st_size,
                        "paths": [entry["path"] for entry in changed],
                    }
                else:
                    delta_archive.unlink(missing_ok=True)
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
    parser.add_argument("--launcher", type=Path)
    parser.add_argument("--base-manifest", type=Path)
    options = parser.parse_args()
    for file in package_release(options.payload, options.output, options.source_sha,
                                options.app_version, options.data_version, options.schema_version,
                                options.launcher, options.base_manifest):
        print(file)


if __name__ == "__main__":
    main()
